import re
from collections.abc import Mapping

class UnsafePayload(ValueError): pass

_SENSITIVE = re.compile(r"(resume|contact|email|phone|address|secret|password|api.?key|token|exception|error)", re.I)
_SCALARS = (str, int, float, bool, type(None))

def sanitize_payload(payload: Mapping[str, object]) -> dict[str, object]:
    def clean(value: object, key: str = "") -> object:
        if _SENSITIVE.search(key): raise UnsafePayload(f"sensitive payload field: {key}")
        if isinstance(value, Mapping): return {str(k): clean(v, str(k)) for k, v in value.items()}
        if isinstance(value, list): return [clean(item, key) for item in value]
        if not isinstance(value, _SCALARS): raise UnsafePayload("payload must contain JSON values only")
        if isinstance(value, str) and len(value) > 1024: raise UnsafePayload("payload string is too long")
        return value
    return clean(payload)  # type: ignore[return-value]
