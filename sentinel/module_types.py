from enum import StrEnum

from hexbytes import HexBytes


class ModuleType(StrEnum):
    COMMUNITY = "community-onchain-v1"
    CURATED = "curated-onchain-v2"


def decode_module_type(raw: bytes | HexBytes) -> ModuleType:
    raw_bytes = bytes(raw)
    decoded = raw_bytes.rstrip(b"\x00").decode("utf-8")
    try:
        return ModuleType(decoded)
    except ValueError as exc:
        raise RuntimeError(f"Unknown module type '{decoded}' (raw: {raw_bytes.hex()})") from exc
