#!/usr/bin/env python3
"""Root-owned receiver for the existing single-instance SQLite deployment."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from datetime import datetime, timezone


class Paths:
    def __init__(self, root=Path("/")):
        root = Path(root)
        self.base = root / "opt/policy-espresso"
        self.releases = self.base / "releases"
        self.current = self.base / "current"
        self.state = self.base / "deployed.json"
        self.config = root / "etc/horizon"
        self.env = self.config / "horizon.env"
        self.data = root / "var/lib/horizon"
        self.database = self.data / "horizon.db"
        self.backups = root / "var/backups/horizon"


def validate_sha(sha):
    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise ValueError("Expected full commit SHA")


def extract_archive(archive, target):
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        if len(members) > 30000 or sum(m.size for m in members) > 700 * 1024**2:
            raise ValueError("Artifact exceeds extraction limit")
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or "\\" in member.name:
                raise ValueError("Unsafe artifact path")
            if not (member.isfile() or member.isdir()):
                raise ValueError("Artifact links and special files are forbidden")
            if path.parts and path.parts[0] not in {"backend", "frontend", "seed"}:
                raise ValueError("Unexpected artifact directory")
        tar.extractall(target, members=members, filter="data")


def run(command, **kwargs):
    subprocess.run(command, check=True, **kwargs)


def environment(paths):
    values = {}
    for line in paths.env.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        parsed = shlex.split(value, comments=False)
        values[key.strip()] = parsed[0] if parsed else ""
    if values.get("DATABASE_URL") != f"sqlite:///{paths.database}":
        raise ValueError("This receiver only supports the configured local SQLite database")
    return {**os.environ, **values, "PYTHONDONTWRITEBYTECODE": "1"}


def set_owner(path):
    user = pwd.getpwnam("horizon")
    # Keep parent directories root-owned until their children are finished.
    for directory, dirs, files in os.walk(path, topdown=False, followlinks=False):
        for name in dirs + files:
            os.chown(Path(directory) / name, user.pw_uid, user.pw_gid, follow_symlinks=False)
        os.chown(directory, user.pw_uid, user.pw_gid, follow_symlinks=False)


def prepare_release(release, runner):
    (release / "frontend/.next/cache").mkdir(parents=True, exist_ok=True)
    set_owner(release)
    runner(["runuser", "-u", "horizon", "--", "python3", "-m", "venv", str(release / ".venv")])
    runner(["runuser", "-u", "horizon", "--", str(release / ".venv/bin/pip"), "install",
            "--disable-pip-version-check", "--cache-dir", "/var/lib/horizon/pip-cache",
            "-i", "https://mirrors.aliyun.com/pypi/simple", str(release / "backend")])


def switch_link(link, destination):
    temporary = link.with_name(".current-next")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(destination, target_is_directory=True)
    temporary.replace(link)


def database_copy(source, destination):
    with sqlite3.connect(str(source)) as src, sqlite3.connect(str(destination)) as dst:
        src.backup(dst)
        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Database integrity check failed")


def wait_healthy():
    for _ in range(45):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/healthz", timeout=3) as response:
                body = json.load(response)
                if body.get("status") != "ok":
                    raise RuntimeError("Database health check failed")
            with urllib.request.urlopen("http://127.0.0.1:3000/login", timeout=5) as response:
                if response.status == 200:
                    return
        except (OSError, ValueError, RuntimeError):
            time.sleep(1)
    raise RuntimeError("Release health check failed")


def deploy(sha, archive, digest, paths=None, runner=run):
    paths = paths or Paths()
    validate_sha(sha)
    if paths.state.exists() and json.loads(paths.state.read_text()).get("sha") == sha:
        return "unchanged"
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Expected SHA256 artifact digest")
    if hashlib.sha256(Path(archive).read_bytes()).hexdigest() != digest:
        raise ValueError("Artifact digest mismatch")
    release = paths.releases / sha / "horizon"
    if release.parent.exists():
        if paths.current.resolve() == release:
            raise RuntimeError("Unrecorded current release requires operator inspection")
        # A failed candidate can be retried without modifying the active release.
        shutil.rmtree(release.parent)
    extract_archive(archive, release)
    for required in ["backend/pyproject.toml", "frontend/server.js", "seed/sources.json"]:
        if not (release / required).is_file():
            raise ValueError("Incomplete release artifact")
    env = environment(paths)
    prepare_release(release, runner)
    previous = paths.current.resolve(strict=True)
    paths.backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot = paths.backups / f"before-{sha[:12]}-{stamp}.sqlite3"
    stopped = False
    backup_ready = False
    try:
        # Everything expensive above happens while the old application stays online.
        stopped = True
        runner(["systemctl", "stop", "horizon-web", "horizon-api"])
        database_copy(paths.database, snapshot)
        snapshot.chmod(0o600)
        backup_ready = True
        runner(["runuser", "-u", "horizon", "--", str(release / ".venv/bin/alembic"), "upgrade", "head"],
               cwd=release / "backend", env=env)
        switch_link(paths.current, release)
        runner(["systemctl", "start", "horizon-api", "horizon-web"])
        wait_healthy()
        state = {"sha": sha, "previous": str(previous), "deployed_at": stamp, "database_backup": str(snapshot)}
        temporary = paths.state.with_suffix(".next")
        temporary.write_text(json.dumps(state, indent=2) + "\n")
        temporary.replace(paths.state)
        return "deployed"
    except BaseException:
        if stopped:
            runner(["systemctl", "stop", "horizon-web", "horizon-api"])
            switch_link(paths.current, previous)
            if backup_ready:
                database_copy(snapshot, paths.database)
            runner(["systemctl", "start", "horizon-api", "horizon-web"])
        raise


def main():
    import fcntl
    if os.geteuid() != 0:
        raise SystemExit("Receiver must run via the configured sudo command")
    original = os.environ.get("SSH_ORIGINAL_COMMAND", "")
    args = shlex.split(original)
    paths = Paths()
    if args == ["status"]:
        print(paths.state.read_text() if paths.state.exists() else '{"sha":null}')
        return
    if len(args) != 3 or args[0] != "deploy":
        raise SystemExit("Only status or deploy SHA SHA256 is accepted")
    validate_sha(args[1])
    paths.base.mkdir(parents=True, exist_ok=True)
    with (paths.base / "deploy.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix="horizon-release-") as temp:
            archive = Path(temp) / "artifact.tgz"
            count = 0
            with archive.open("wb") as out:
                while chunk := sys.stdin.buffer.read(1024 * 1024):
                    count += len(chunk)
                    if count > 180 * 1024**2:
                        raise ValueError("Compressed artifact exceeds upload limit")
                    out.write(chunk)
            print(deploy(args[1], archive, args[2], paths), flush=True)


if __name__ == "__main__":
    main()
