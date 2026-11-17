"""按运行配置选择原文快照存储，密钥仅从服务端环境读取。"""
from pathlib import Path

from app.core.config import get_settings


class LocalStorage:
    name = "local"

    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ValueError("存储键必须指向存储目录内的文件")
        return path

    def save(self, key: str, content: str) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return str(path)

    def load(self, key: str) -> str:
        return self._path(key).read_text(encoding="utf-8")


class OSSStorage:
    name = "oss"

    def __init__(self, settings):
        import oss2

        self.bucket = oss2.Bucket(
            oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret),
            settings.oss_endpoint,
            settings.oss_bucket,
        )
        self.bucket_name = settings.oss_bucket

    def save(self, key: str, content: str) -> str:
        self.bucket.put_object(key, content.encode("utf-8"))
        return f"oss://{self.bucket_name}/{key}"

    def load(self, key: str) -> str:
        return self.bucket.get_object(key).read().decode("utf-8")


def get_storage() -> LocalStorage | OSSStorage:
    settings = get_settings()
    if settings.storage_backend == "local":
        return LocalStorage(settings.storage_dir)
    if settings.storage_backend == "oss":
        if not all((settings.oss_bucket, settings.oss_endpoint,
                    settings.oss_access_key_id, settings.oss_access_key_secret)):
            raise ValueError("OSS 配置不完整")
        return OSSStorage(settings)
    raise ValueError(f"未知存储后端：{settings.storage_backend}")
