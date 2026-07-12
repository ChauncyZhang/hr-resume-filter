from tempfile import SpooledTemporaryFile
class StorageWriteFailed(Exception): pass
class QuarantineStorage:
    """Keys are UUID-only quarantine prefixes, enabling deterministic orphan sweeps."""
    def __init__(self,client,bucket): self.client=client; self.bucket=bucket
    def write(self,stream,storage_key,content_type,max_bytes):
        spool=SpooledTemporaryFile(max_size=min(max_bytes,1024*1024),mode="w+b"); total=0
        try:
            stream.seek(0)
            while chunk:=stream.read(64*1024):
                total+=len(chunk)
                if total>max_bytes: raise StorageWriteFailed("file_too_large")
                spool.write(chunk)
            spool.seek(0); self.client.put_object(self.bucket,storage_key,spool,total,content_type=content_type)
        except StorageWriteFailed: raise
        except Exception: raise StorageWriteFailed("storage_write_failed") from None
        finally: spool.close()
    def delete(self,storage_key):
        try: self.client.remove_object(self.bucket,storage_key)
        except Exception: pass
