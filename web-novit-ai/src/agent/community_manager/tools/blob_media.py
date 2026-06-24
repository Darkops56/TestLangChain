"""Temporary Azure Blob media hosting with read-only SAS URLs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from community_manager.config.settings import get_settings


class AzureBlobMediaPublisher:
    """Uploads generated media to Azure Blob Storage and returns short-lived SAS URLs."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.is_blob_media_hosting_configured:
            raise RuntimeError("Azure Blob media hosting is not configured")

        from azure.storage.blob import BlobSasPermissions, ContentSettings, generate_blob_sas
        from azure.storage.blob.aio import BlobServiceClient

        self.account_name = settings.azure_blob_storage_account_name
        self.account_key = settings.azure_blob_storage_account_key
        self.container_name = settings.azure_blob_storage_container_name
        self.sas_expiry_hours = max(settings.azure_blob_storage_sas_expiry_hours, 1)
        self._blob_sas_permissions = BlobSasPermissions
        self._content_settings = ContentSettings
        self._generate_blob_sas = generate_blob_sas
        self._service_client = BlobServiceClient(
            account_url=f"https://{self.account_name}.blob.core.windows.net",
            credential=self.account_key,
        )

    async def upload_bytes(self, blob_name: str, data: bytes, *, content_type: str) -> str:
        blob_client = self._service_client.get_blob_client(
            container=self.container_name,
            blob=blob_name,
        )
        await blob_client.upload_blob(
            data,
            overwrite=True,
            content_settings=self._content_settings(
                content_type=content_type,
                content_disposition="inline",
            ),
        )

        expiry = datetime.now(timezone.utc) + timedelta(hours=self.sas_expiry_hours)
        sas = self._generate_blob_sas(
            account_name=self.account_name,
            container_name=self.container_name,
            blob_name=blob_name,
            account_key=self.account_key,
            permission=self._blob_sas_permissions(read=True),
            expiry=expiry,
            protocol="https",
        )
        encoded_blob_name = quote(blob_name, safe="/")
        return (
            f"https://{self.account_name}.blob.core.windows.net/"
            f"{quote(self.container_name)}/{encoded_blob_name}?{sas}"
        )

    async def delete_blob(self, blob_name: str) -> None:
        blob_client = self._service_client.get_blob_client(
            container=self.container_name,
            blob=blob_name,
        )
        await blob_client.delete_blob(delete_snapshots="include")

    async def close(self) -> None:
        await self._service_client.close()