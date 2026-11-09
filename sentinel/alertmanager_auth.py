"""Secret-configured publisher identities for the common Alertmanager endpoint."""

import hashlib
import json
import re
import secrets
from dataclasses import dataclass, field
from typing import cast

MAX_SOURCES = 64
MAX_KEYS_PER_SOURCE = 2
MAX_KEY_LENGTH = 512
SOURCE_ID_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")


@dataclass(frozen=True, slots=True)
class AlertmanagerSource:
    source_id: str
    keys: tuple[str, ...] = field(repr=False)

    def __post_init__(self) -> None:
        if not SOURCE_ID_PATTERN.fullmatch(self.source_id):
            raise ValueError(
                "Source IDs must use lowercase letters, digits, underscores or hyphens"
            )
        if not 1 <= len(self.keys) <= MAX_KEYS_PER_SOURCE:
            raise ValueError("Each source must have one or two active keys")
        if any(
            not isinstance(key, str)
            or not 32 <= len(key) <= MAX_KEY_LENGTH
            or not all(33 <= ord(char) <= 126 for char in key)
            for key in self.keys
        ):
            raise ValueError(
                "Keys must contain 32 to 512 printable ASCII characters without spaces"
            )


class AlertmanagerAuthenticator:
    def __init__(self, sources: tuple[AlertmanagerSource, ...]) -> None:
        if len(sources) > MAX_SOURCES:
            raise ValueError(f"Configure at most {MAX_SOURCES} sources")
        self.source_ids = frozenset(source.source_id for source in sources)
        if len(self.source_ids) != len(sources):
            raise ValueError("Source IDs must be unique")
        entries: list[tuple[str, bytes]] = []
        seen: set[bytes] = set()
        for source in sources:
            for key in source.keys:
                digest = hashlib.sha256(key.encode()).digest()
                if digest in seen:
                    raise ValueError("Every active key must be unique")
                seen.add(digest)
                entries.append((source.source_id, digest))
        self._entries = tuple(entries)

    def authenticate(self, authorization: str) -> str | None:
        scheme, _, key = authorization.partition(" ")
        if scheme.lower() != "bearer" or not key or len(key) > MAX_KEY_LENGTH:
            return None
        digest = hashlib.sha256(key.encode(errors="surrogatepass")).digest()
        identity = None
        for source_id, expected in self._entries:
            if secrets.compare_digest(digest, expected):
                identity = source_id
        return identity


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate source IDs are not allowed")
        result[key] = value
    return result


def parse_alertmanager_sources(raw: str | None) -> tuple[AlertmanagerSource, ...]:
    if not raw:
        return ()
    try:
        data = json.loads(raw, object_pairs_hook=_unique_object)
        if not isinstance(data, dict):
            raise ValueError("Expected an object mapping source IDs to lists of keys")
        mapping = cast(dict[str, object], data)
        sources: list[AlertmanagerSource] = []
        for source_id, keys in mapping.items():
            if not isinstance(keys, list) or not all(isinstance(key, str) for key in keys):
                raise ValueError("Each source must map to a list of keys")
            sources.append(AlertmanagerSource(source_id, cast(tuple[str, ...], tuple(keys))))
        if sources:
            AlertmanagerAuthenticator(tuple(sources))
        return tuple(sources)
    except (ValueError, TypeError, RecursionError):
        # Configuration errors must never echo the secret JSON or its key values.
        raise RuntimeError(
            "Invalid ALERTMANAGER_WEBHOOK_SOURCES: expected a JSON object of unique source IDs "
            "and one or two unique keys each (32 to 512 printable ASCII characters without spaces)"
        ) from None
