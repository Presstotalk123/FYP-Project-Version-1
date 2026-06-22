import uuid
from pathlib import Path
from typing import Protocol, Tuple

from fastapi import UploadFile

from app.config import settings


class ERStorageProvider(Protocol):
    def save(self, file: UploadFile) -> Tuple[str, str]:
        ...

    def delete(self, storage_key: str) -> None:
        ...


class LocalERStorageProvider:
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(self, file: UploadFile) -> Tuple[str, str]:
        ext = Path(file.filename or "").suffix or ".bin"
        storage_key = f"{uuid.uuid4().hex}{ext}"
        destination = self.base_path / storage_key

        with destination.open("wb") as target:
            target.write(file.file.read())

        return storage_key, str(destination)

    def delete(self, storage_key: str) -> None:
        destination = self.base_path / storage_key
        if destination.exists():
            destination.unlink()


class AzureBlobERStorageProvider:
    def __init__(
        self,
        container: str,
        connection_string: str | None = None,
        account_url: str | None = None,
        account_key: str | None = None,
    ):
        try:
            from azure.storage.blob import BlobServiceClient  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("azure-storage-blob is required for ER_STORAGE_PROVIDER=azure") from exc

        if not container:
            raise RuntimeError("ER_AZURE_CONTAINER must be configured for azure storage provider")

        if connection_string:
            blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        elif account_url and account_key:
            blob_service_client = BlobServiceClient(account_url=account_url, credential=account_key)
        else:
            raise RuntimeError(
                "Either ER_AZURE_CONNECTION_STRING or both ER_AZURE_ACCOUNT_URL and ER_AZURE_ACCOUNT_KEY must be configured"
            )

        self.container_client = blob_service_client.get_container_client(container)

    def save(self, file: UploadFile) -> Tuple[str, str]:
        ext = Path(file.filename or "").suffix or ".bin"
        storage_key = f"{uuid.uuid4().hex}{ext}"
        blob_client = self.container_client.get_blob_client(storage_key)
        blob_client.upload_blob(file.file.read(), overwrite=True)
        return storage_key, blob_client.url

    def delete(self, storage_key: str) -> None:
        blob_client = self.container_client.get_blob_client(storage_key)
        blob_client.delete_blob(delete_snapshots="include")


def get_er_storage_provider() -> ERStorageProvider:
    provider = settings.ER_STORAGE_PROVIDER.lower().strip()
    if provider == "azure":
        return AzureBlobERStorageProvider(
            container=settings.ER_AZURE_CONTAINER or "",
            connection_string=settings.ER_AZURE_CONNECTION_STRING,
            account_url=settings.ER_AZURE_ACCOUNT_URL,
            account_key=settings.ER_AZURE_ACCOUNT_KEY,
        )
    if provider == "local":
        return LocalERStorageProvider(settings.ER_DIAGRAM_UPLOAD_PATH)
    raise RuntimeError(f"Unsupported ER_STORAGE_PROVIDER: {provider}")
