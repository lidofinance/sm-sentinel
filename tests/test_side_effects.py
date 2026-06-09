from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

from hexbytes import HexBytes
import pytest

from sentinel.models import Event
from sentinel.modules.curated.adapter import CuratedModuleAdapter
from sentinel.modules.side_effects import (
    CuratedMetadataCacheProcessor,
    ModuleEventSideEffects,
    NodeOperatorCountProcessor,
)


def _event(event: str, args: dict, address: str) -> Event:
    return Event(
        event=event,
        args=args,
        block=1,
        tx=HexBytes("0xdeadbeef"),
        address=address,
        log_index=0,
        transaction_index=0,
    )


@pytest.mark.asyncio
async def test_curated_metadata_side_effect_updates_label_cache_from_event():
    remembered: list[tuple[int, str | None]] = []
    adapter = SimpleNamespace(
        remember_node_operator_label=lambda operator_id, name: remembered.append(
            (operator_id, name)
        )
    )
    processor = CuratedMetadataCacheProcessor(cast(CuratedModuleAdapter, adapter))

    await processor.process_event(
        _event(
            "OperatorMetadataSet",
            {
                "nodeOperatorId": 7,
                "metadata": {
                    "name": "Operator Seven",
                    "description": "",
                    "ownerEditsRestricted": False,
                },
            },
            "0x0000000000000000000000000000000000000abc",
        )
    )

    assert remembered == [(7, "Operator Seven")]


@pytest.mark.asyncio
async def test_node_operator_count_side_effect_updates_count_cache_from_added_event():
    remembered: list[int] = []
    adapter = SimpleNamespace(
        remember_node_operator_added=lambda operator_id: remembered.append(operator_id)
    )
    processor = NodeOperatorCountProcessor(adapter)

    await processor.process_event(
        _event(
            "NodeOperatorAdded",
            {"nodeOperatorId": 9},
            "0x0000000000000000000000000000000000000abc",
        )
    )

    assert remembered == [9]


@pytest.mark.asyncio
async def test_module_event_side_effects_exposes_raw_event_consumer_handle_event():
    processor = SimpleNamespace(process_event=AsyncMock())
    side_effects = ModuleEventSideEffects.__new__(ModuleEventSideEffects)
    side_effects._processors = (processor,)
    event = _event(
        "AnyEvent",
        {},
        "0x0000000000000000000000000000000000000abc",
    )

    await side_effects.process_event(event)

    processor.process_event.assert_awaited_once_with(event)
