"""Alertmanager's webhook format with Sentinel's fixed operator routing labels."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator

MAX_ALERTS_PER_REQUEST = 1000
TELEGRAM_MESSAGE_UNITS = 4000


class InvalidAlertmanagerWebhook(ValueError):
    """The entire webhook must be rejected before any notifications are queued."""


class AlertStatus(StrEnum):
    FIRING = "firing"
    RESOLVED = "resolved"


def _decimal_label(value: object) -> int:
    if (
        not isinstance(value, str)
        or not value.isascii()
        or not value.isdecimal()
        or len(value) > 78
    ):
        raise ValueError("Expected a decimal integer string")
    return int(value)


UInt256Label = Annotated[
    int,
    BeforeValidator(_decimal_label, json_schema_input_type=str),
    Field(ge=0, lt=2**256),
]


class AlertmanagerLabels(BaseModel):
    """Required routing labels; additional Alertmanager labels remain strings."""

    model_config = ConfigDict(strict=True, extra="allow")
    __pydantic_extra__: dict[str, str] = Field(init=False)

    chain_id: Annotated[UInt256Label, Field(ge=1)]
    staking_module_id: Annotated[UInt256Label, Field(ge=1)]
    node_operator_id: UInt256Label
    alertname: str

    @field_validator("alertname")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("alertname is required")
        return value


class AlertmanagerAlert(BaseModel):
    """The per-alert wire fields consumed by Sentinel."""

    model_config = ConfigDict(strict=True, extra="ignore")

    status: AlertStatus
    labels: AlertmanagerLabels
    annotations: dict[str, str] = Field(default_factory=dict)

    @field_validator("status", mode="before")
    @classmethod
    def parse_status(cls, value: object) -> AlertStatus:
        if isinstance(value, str):
            try:
                return AlertStatus(value)
            except ValueError:
                pass
        raise ValueError("status must be firing or resolved")


class AlertmanagerWebhook(BaseModel):
    """Validate the supported v4 subset without requiring unused protocol fields."""

    model_config = ConfigDict(strict=True, extra="ignore")

    version: Literal["4"]
    truncated_alerts: int = Field(default=0, alias="truncatedAlerts")
    alerts: list[AlertmanagerAlert] = Field(min_length=1, max_length=MAX_ALERTS_PER_REQUEST)

    @field_validator("truncated_alerts", mode="before")
    @classmethod
    def complete_batch(cls, value: object) -> int:
        if type(value) is not int or value != 0:
            raise ValueError("Truncated alert batches are not supported; use max_alerts: 0")
        return 0


@dataclass(frozen=True, slots=True)
class OperatorAlert:
    chain_id: int
    staking_module_id: int
    node_operator_id: str
    name: str
    status: AlertStatus
    summary: str
    description: str

    def messages(self, *, source_id: str) -> tuple[str, ...]:
        # Annotations are plain text, never Telegram Markdown or HTML.
        parts = [
            f"Alert: {self.name}",
            f"Source: {source_id}",
            f"Status: {self.status}",
            f"Node operator: {self.node_operator_id} · "
            f"Staking module: {self.staking_module_id} · Chain: {self.chain_id}",
        ]
        if self.summary:
            parts.append(self.summary)
        if self.description:
            parts.append(self.description)
        return split_telegram_text("\n\n".join(parts))


def parse_alertmanager_webhook(payload: object) -> tuple[OperatorAlert, ...]:
    try:
        webhook = AlertmanagerWebhook.model_validate(payload)
    except ValidationError as exc:
        # HTTP errors identify the field without reflecting raw labels or annotations.
        error = exc.errors(include_input=False, include_context=False, include_url=False)[0]
        location = ".".join(str(part) for part in error["loc"]) or "webhook"
        raise InvalidAlertmanagerWebhook(f"{location}: {error['msg']}") from exc

    result: list[OperatorAlert] = []
    for alert in webhook.alerts:
        labels = alert.labels
        result.append(
            OperatorAlert(
                chain_id=labels.chain_id,
                staking_module_id=labels.staking_module_id,
                node_operator_id=str(labels.node_operator_id),
                name=labels.alertname,
                status=alert.status,
                summary=alert.annotations.get("summary", ""),
                description=alert.annotations.get("description", ""),
            )
        )
    return tuple(result)


def split_telegram_text(text: str) -> tuple[str, ...]:
    """Respect Telegram's UTF-16 length limit, including supplementary characters."""
    chunks: list[str] = []
    start = 0
    units = 0
    for index, char in enumerate(text):
        char_units = 2 if ord(char) > 0xFFFF else 1
        if units + char_units > TELEGRAM_MESSAGE_UNITS:
            chunks.append(text[start:index])
            start = index
            units = 0
        units += char_units
    if start < len(text):
        chunks.append(text[start:])
    return tuple(chunks)
