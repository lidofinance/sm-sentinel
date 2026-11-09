import os
from dataclasses import dataclass
from datetime import time, timezone

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from sentinel.alertmanager_auth import AlertmanagerSource, parse_alertmanager_sources


def _parse_admin_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for token in raw.replace(" ", ",").split(","):
        if not token:
            continue
        try:
            ids.add(int(token))
        except ValueError:
            # Ignore invalid entries silently at config load time
            continue
    return ids


@dataclass(frozen=True)
class ExplorerLinks:
    """Build explorer links and require a configured address only when used."""

    etherscan_url: str | None
    beaconchain_url: str | None

    def block(self, number: int) -> str:
        if not self.etherscan_url:
            raise RuntimeError("ETHERSCAN_URL must be configured")
        return f"{self.etherscan_url}/block/{number}"

    def transaction(self, tx_hash: str) -> str:
        if not self.etherscan_url:
            raise RuntimeError("ETHERSCAN_URL must be configured")
        return f"{self.etherscan_url}/tx/{tx_hash}"

    def validator(self, pubkey: str) -> str:
        if not self.beaconchain_url:
            raise RuntimeError("BEACONCHAIN_URL must be configured")
        return f"{self.beaconchain_url}/validator/{pubkey}"


def _parse_deposit_digest_time(raw: str) -> time:
    try:
        parsed = time.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("DEPOSIT_DIGEST_TIME must use HH:MM format") from exc
    if parsed.tzinfo is not None or parsed.second or parsed.microsecond:
        raise ValueError("DEPOSIT_DIGEST_TIME must use HH:MM format")
    return parsed.replace(tzinfo=timezone.utc)


def _parse_provider_urls(raw: str) -> tuple[str, ...]:
    providers: list[str] = []
    for token in raw.split(","):
        provider = token.strip()
        if provider and provider not in providers:
            providers.append(provider)
    return tuple(providers)


class Config(BaseModel):
    """Validated application settings, independent of contract discovery."""

    model_config = ConfigDict(
        alias_generator=str.upper,
        extra="ignore",
        hide_input_in_errors=True,
        frozen=True,
        validate_by_name=True,
    )

    healthcheck_host: str = "0.0.0.0"
    healthcheck_port: int = Field(default=8080, ge=1, le=65535)
    filestorage_path: str = ".storage"
    token: str | None = Field(default=None, repr=False)
    web3_socket_providers: tuple[str, ...] = Field(min_length=1)
    module_address: str = Field(min_length=1)
    explorers: ExplorerLinks = Field(default_factory=lambda: ExplorerLinks(None, None))
    module_ui_url: str | None = None
    block_batch_size: int = 10_000
    process_blocks_requests_per_second: float | None = Field(
        default=None, gt=0, allow_inf_nan=False
    )
    block_from: int | None = None
    admin_ids: set[int] = Field(default_factory=set)
    deposit_digest_time: time = time(9, tzinfo=timezone.utc)
    alertmanager_webhook_sources: tuple[AlertmanagerSource, ...] = Field(default=(), repr=False)
    alertmanager_webhook_host: str = "0.0.0.0"
    alertmanager_webhook_port: int = Field(default=8081, ge=1, le=65535)

    @field_validator("web3_socket_providers", mode="before")
    @classmethod
    def parse_providers(cls, value: str | tuple[str, ...]) -> tuple[str, ...]:
        return _parse_provider_urls(value) if isinstance(value, str) else value

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admins(cls, value: str | set[int]) -> set[int]:
        return _parse_admin_ids(value) if isinstance(value, str) else value

    @field_validator("deposit_digest_time", mode="before")
    @classmethod
    def parse_digest_time(cls, value: str | time) -> time:
        return _parse_deposit_digest_time(value) if isinstance(value, str) else value

    @field_validator("alertmanager_webhook_sources", mode="before")
    @classmethod
    def parse_sources(
        cls, value: str | tuple[AlertmanagerSource, ...]
    ) -> tuple[AlertmanagerSource, ...]:
        return parse_alertmanager_sources(value) if isinstance(value, str) else value


_CONFIG: Config | None = None


def _environment_error(exc: ValidationError) -> RuntimeError:
    # Environment values may contain credentials; only report the failing names.
    fields = ", ".join(str(error["loc"][0]) for error in exc.errors(include_input=False))
    return RuntimeError(f"Invalid environment configuration: {fields}")


def load_config_from_env() -> Config:
    values = dict(os.environ)
    values["WEB3_SOCKET_PROVIDERS"] = values.get("WEB3_SOCKET_PROVIDERS") or values.get(
        "WEB3_SOCKET_PROVIDER", ""
    )
    data = dict(
        values, EXPLORERS=ExplorerLinks(values.get("ETHERSCAN_URL"), values.get("BEACONCHAIN_URL"))
    )
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        raise _environment_error(exc) from None


def get_config() -> Config:
    if _CONFIG is None:
        raise RuntimeError("Runtime config has not been loaded")
    return _CONFIG


def set_config(config: Config) -> None:
    global _CONFIG
    _CONFIG = config


def clear_config() -> None:
    """Basically for tests."""
    global _CONFIG
    _CONFIG = None
