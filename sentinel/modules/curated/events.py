from sentinel.models import Event
from sentinel.modules.curated.texts import (
    CURATED_EVENT_DESCRIPTIONS,
    CURATED_EVENT_MESSAGES,
)
from sentinel.notifications import NotificationPlan

CURATED_EVENTS_TO_FOLLOW = {}


def assert_event_mappings() -> None:
    events = set(CURATED_EVENTS_TO_FOLLOW.keys())
    messages = set(CURATED_EVENT_MESSAGES.keys())
    descriptions = set(CURATED_EVENT_DESCRIPTIONS.keys())
    assert events == messages, "Missed events: " + str(events.symmetric_difference(messages))
    assert events == descriptions, "Missed events: " + str(
        events.symmetric_difference(descriptions)
    )


class CuratedEventMessages:
    def __init__(self, module_adapter):
        self.module_adapter = module_adapter

    def reconfigure(self, module_adapter) -> None:
        self.module_adapter = module_adapter

    async def get_notification_plan(self, event: Event) -> NotificationPlan | None:
        _ = event
        return None
