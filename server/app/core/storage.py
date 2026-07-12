import asyncio

from minio import Minio


def create_storage_client(
    endpoint: str, access_key: str, secret_key: str, *, secure: bool
) -> Minio:
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)


class ObjectStorageProbe:
    def __init__(self, client: Minio, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    async def check(self) -> None:
        exists = await asyncio.to_thread(self._client.bucket_exists, self._bucket)
        if not exists:
            raise RuntimeError("required private bucket is unavailable")
