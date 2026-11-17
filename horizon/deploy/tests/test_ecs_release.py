import hashlib
import importlib.util
import io
import json
import sqlite3
import sys
import tarfile
from pathlib import Path

import pytest


@pytest.fixture
def release():
    path = Path(__file__).parents[1] / "ecs_release.py"
    spec = importlib.util.spec_from_file_location("ecs_release", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def archive(path, entries):
    with tarfile.open(path, "w:gz") as tar:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            payload = data.encode()
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_archive_cannot_escape_release_directory(release, tmp_path):
    path = tmp_path / "bad.tgz"
    archive(path, {"../escape": "bad"})
    with pytest.raises(ValueError):
        release.extract_archive(path, tmp_path / "release")
    assert not (tmp_path / "escape").exists()


def test_archive_rejects_symlinks(release, tmp_path):
    path = tmp_path / "links.tgz"
    with tarfile.open(path, "w:gz") as tar:
        info = tarfile.TarInfo("frontend/link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/horizon/horizon.env"
        tar.addfile(info)
    with pytest.raises(ValueError):
        release.extract_archive(path, tmp_path / "release")


def test_invalid_commit_rejected(release):
    with pytest.raises(ValueError):
        release.validate_sha("../current")


def test_mismatched_digest_does_not_touch_services(release, tmp_path):
    calls = []
    paths = release.Paths(tmp_path)
    path = tmp_path / "release.tgz"
    archive(path, {"backend/pyproject.toml": ""})
    with pytest.raises(ValueError, match="digest"):
        release.deploy("a" * 40, path, "0" * 64, paths, lambda *a, **kw: calls.append(a))
    assert calls == []


def test_successful_commit_is_skipped(release, tmp_path):
    paths = release.Paths(tmp_path)
    paths.state.parent.mkdir(parents=True)
    paths.state.write_text(json.dumps({"sha": "a" * 40}))
    assert release.deploy("a" * 40, tmp_path / "not-needed.tgz", "0" * 64, paths) == "unchanged"


def test_build_hook_cannot_redirect_root_cache_ownership(release, tmp_path, monkeypatch):
    candidate = tmp_path / "release"
    cache = candidate / "frontend/.next/cache"
    outside = tmp_path / "outside"
    outside.mkdir()
    owned = []
    monkeypatch.setattr(release, "set_owner", lambda path: owned.append(path.resolve()))

    def build_hook(command, **kwargs):
        if "install" in command:
            cache.rmdir()
            cache.symlink_to(outside, target_is_directory=True)

    release.prepare_release(candidate, build_hook)
    assert cache.is_symlink()
    assert owned == [candidate.resolve()]


def test_failed_health_restores_database_and_old_release(release, tmp_path, monkeypatch):
    paths = release.Paths(tmp_path)
    paths.config.mkdir(parents=True)
    paths.data.mkdir(parents=True)
    old = paths.releases / "old" / "horizon"
    old.mkdir(parents=True)
    paths.current.symlink_to(old, target_is_directory=True)
    paths.env.write_text(f"DATABASE_URL=sqlite:///{paths.database}\n")
    with sqlite3.connect(paths.database) as db:
        db.execute("CREATE TABLE marker(value TEXT)")
        db.execute("INSERT INTO marker VALUES ('original')")
    payload = tmp_path / "release.tgz"
    digest = archive(payload, {"backend/pyproject.toml": "", "frontend/server.js": "", "seed/sources.json": "[]"})
    monkeypatch.setattr(release, "prepare_release", lambda *a, **kw: None)
    monkeypatch.setattr(release, "wait_healthy", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("health failed")))
    monkeypatch.setattr(release, "set_owner", lambda *a, **kw: None)
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if "alembic" in " ".join(command):
            with sqlite3.connect(paths.database) as db:
                db.execute("UPDATE marker SET value='changed'")
    with pytest.raises(RuntimeError, match="health failed"):
        release.deploy("b" * 40, payload, digest, paths, run)
    assert paths.current.resolve() == old
    with sqlite3.connect(paths.database) as db:
        assert db.execute("SELECT value FROM marker").fetchone()[0] == "original"
    assert not paths.state.exists()
    assert ["systemctl", "start", "horizon-api", "horizon-web"] in calls
