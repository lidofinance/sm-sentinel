from types import SimpleNamespace
from typing import cast

from hexbytes import HexBytes
import pytest

from sentinel.models import Event
from sentinel.modules.community.adapter import CommunityModuleAdapter
from sentinel.modules.curated.adapter import CuratedModuleAdapter
from sentinel.modules.side_effects import (
    CsmInitializedVersionSwitchProcessor,
    CuratedMetadataCacheProcessor,
    NodeOperatorCountProcessor,
)


def _event(event: str, args: dict, address: str) -> Event:
    return Event(
        event=event,
        args=args,
        block=1,
        tx=HexBytes("0xdeadbeef"),
        address=address,
    )


@pytest.mark.asyncio
async def test_csm_initialized_side_effect_switches_from_v2_to_v3():
    switched_versions: list[int] = []
    adapter = SimpleNamespace(
        csm_version=2,
        addresses=SimpleNamespace(module="0x0000000000000000000000000000000000000abc"),
    )

    async def switch_csm_version(csm_version: int) -> None:
        switched_versions.append(csm_version)

    processor = CsmInitializedVersionSwitchProcessor(
        cast(CommunityModuleAdapter, adapter),
        switch_csm_version,
    )

    await processor.process_event(
        _event(
            "Initialized",
            {"version": 3},
            "0x0000000000000000000000000000000000000abc",
        )
    )

    assert switched_versions == [3]


@pytest.mark.asyncio
async def test_csm_initialized_side_effect_ignores_non_matching_events():
    switched_versions: list[int] = []
    adapter = SimpleNamespace(
        csm_version=2,
        addresses=SimpleNamespace(module="0x0000000000000000000000000000000000000abc"),
    )

    async def switch_csm_version(csm_version: int) -> None:
        switched_versions.append(csm_version)

    processor = CsmInitializedVersionSwitchProcessor(
        cast(CommunityModuleAdapter, adapter),
        switch_csm_version,
    )

    await processor.process_event(
        _event(
            "Initialized",
            {"version": 2},
            "0x0000000000000000000000000000000000000abc",
        )
    )
    await processor.process_event(
        _event(
            "Initialized",
            {"version": 3},
            "0x0000000000000000000000000000000000000def",
        )
    )

    assert switched_versions == []


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
