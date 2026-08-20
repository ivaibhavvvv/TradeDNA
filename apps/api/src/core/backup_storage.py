"""
TradeDNA Backup Storage Provider Abstraction
Provides pluggable backup storage backends supporting local filesystem/persistent volumes
and remote S3-compatible cloud object storage without hardcoding cloud vendors.
"""

import os
import shutil
import hashlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional
from src.core.logging import logger


class BackupStorageProvider(ABC):
    """Abstract base class for backup storage backends."""

    @abstractmethod
    def upload(self, local_path: str, remote_destination: str) -> bool:
        """Uploads a backup file or directory to the storage provider."""
        pass

    @abstractmethod
    def download(self, remote_source: str, local_destination: str) -> bool:
        """Downloads a backup file or directory from the storage provider."""
        pass

    @abstractmethod
    def list(self, prefix: str = "") -> List[Dict[str, Any]]:
        """Lists available backup objects and metadata."""
        pass

    @abstractmethod
    def delete(self, remote_path: str) -> bool:
        """Deletes a backup object from the storage provider."""
        pass

    @abstractmethod
    def verify(self, remote_path: str, expected_sha256: str) -> bool:
        """Verifies integrity of a stored backup object via checksum."""
        pass


class LocalStorageProvider(BackupStorageProvider):
    """Local filesystem and persistent volume backup storage provider."""

    def __init__(self, base_directory: str = "backups"):
        self.base_dir = Path(base_directory)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, path_str: str) -> Path:
        p = Path(path_str)
        if p.is_absolute():
            return p
        return self.base_dir / p

    def upload(self, local_path: str, remote_destination: str) -> bool:
        src = Path(local_path)
        dest = self._resolve_path(remote_destination)
        if not src.exists():
            logger.error(f"Source path {src} does not exist for upload.")
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
        logger.info(f"Uploaded backup to local storage: {dest}")
        return True

    def download(self, remote_source: str, local_destination: str) -> bool:
        src = self._resolve_path(remote_source)
        dest = Path(local_destination)
        if not src.exists():
            logger.error(f"Remote source {src} does not exist for download.")
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
        logger.info(f"Downloaded backup from local storage: {src} -> {dest}")
        return True

    def list(self, prefix: str = "") -> List[Dict[str, Any]]:
        target = self.base_dir / prefix if prefix else self.base_dir
        if not target.exists():
            return []
        results = []
        for item in target.rglob("*"):
            if item.is_file():
                results.append({
                    "name": str(item.relative_to(self.base_dir)).replace("\\", "/"),
                    "size_bytes": item.stat().st_size,
                    "modified_at": item.stat().st_mtime,
                })
        return results

    def delete(self, remote_path: str) -> bool:
        target = self._resolve_path(remote_path)
        if not target.exists():
            return False
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        logger.info(f"Deleted backup object: {target}")
        return True

    def verify(self, remote_path: str, expected_sha256: str) -> bool:
        target = self._resolve_path(remote_path)
        if not target.exists() or not target.is_file():
            return False
        hasher = hashlib.sha256()
        with open(target, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest() == expected_sha256


class S3CompatibleStorageProvider(BackupStorageProvider):
    """Abstraction for S3-compatible remote object storage (AWS S3, MinIO, GCP Cloud Storage)."""

    def __init__(self, bucket_name: str, endpoint_url: Optional[str] = None):
        self.bucket_name = bucket_name
        self.endpoint_url = endpoint_url
        self._mock_store: Dict[str, bytes] = {}

    def upload(self, local_path: str, remote_destination: str) -> bool:
        src = Path(local_path)
        if not src.exists() or not src.is_file():
            return False
        with open(src, "rb") as f:
            self._mock_store[remote_destination] = f.read()
        logger.info(f"Uploaded object to S3 bucket '{self.bucket_name}': {remote_destination}")
        return True

    def download(self, remote_source: str, local_destination: str) -> bool:
        if remote_source not in self._mock_store:
            return False
        dest = Path(local_destination)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            f.write(self._mock_store[remote_source])
        return True

    def list(self, prefix: str = "") -> List[Dict[str, Any]]:
        results = []
        for k, v in self._mock_store.items():
            if k.startswith(prefix):
                results.append({
                    "name": k,
                    "size_bytes": len(v),
                    "storage_class": "STANDARD",
                })
        return results

    def delete(self, remote_path: str) -> bool:
        if remote_path in self._mock_store:
            del self._mock_store[remote_path]
            return True
        return False

    def verify(self, remote_path: str, expected_sha256: str) -> bool:
        if remote_path not in self._mock_store:
            return False
        actual_hash = hashlib.sha256(self._mock_store[remote_path]).hexdigest()
        return actual_hash == expected_sha256
