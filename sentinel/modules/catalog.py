from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from aiogram.utils.formatting import Bold

from sentinel.modules.formatting import markdown, nl


@dataclass(frozen=True, slots=True)
class EventDefinition:
    name: str
    description: str
    group_title: StrEnum


def group_event_catalog(
    catalog: Iterable[EventDefinition],
) -> list[tuple[StrEnum, list[EventDefinition]]]:
    grouped: dict[StrEnum, list[EventDefinition]] = {}
    for event in catalog:
        grouped.setdefault(event.group_title, []).append(event)
    return list(grouped.items())


def build_grouped_event_list_text(
    *,
    catalog_events: set[str],
    catalog: Iterable[EventDefinition],
    group_descriptions: Mapping[Any, str],
) -> str:
    parts: list = [
        "Here is the list of events you will receive notifications for:",
        nl(1),
        "A 🚨 means urgent action is required from you",
        nl(),
    ]

    for group_title, events in group_event_catalog(catalog):
        active_events = [event for event in events if event.name in catalog_events]
        if not active_events:
            continue
        parts.extend([Bold(group_title.value), nl(1)])
        description = group_descriptions.get(group_title, "")
        if description:
            parts.extend([description, nl(1)])
        for event in active_events:
            parts.extend([event.description, nl(1)])
        parts.append(nl())

    return markdown(*parts)
