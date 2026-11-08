"""Local filesystem storage. Files are stored under random UUID names outside any web root
and only served through authenticated API endpoints."""
import hashlib
import os
import uuid
from pathlib import Path

from app.core.config import settings


class LocalStorage:
    def __init__(self, root: str | None = None):
        self.root = Path(root or settings.storage_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:  # path traversal guard
            raise ValueError("Invalid storage key")
        return p

    def save(self, data: bytes, ext: str, folder: str = "originals") -> str:
        key = f"{folder}/{uuid.uuid4().hex[:2]}/{uuid.uuid4().hex}{ext.lower()}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)  # atomic
        return key

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def path(self, key: str) -> Path:
        return self._path(key)

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink()
        except FileNotFoundError:
            pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_storage: LocalStorage | None = None


def get_storage() -> LocalStorage:
    global _storage
    if _storage is None:
        _storage = LocalStorage()
    return _storage
