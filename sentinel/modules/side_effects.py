from collections.abc import Awaitable, Callable
from typing import Protocol

from sentinel.models import Event
from sentinel.modules.community.adapter import CommunityModuleAdapter
from sentinel.modules.curated.adapter import CuratedModuleAdapter
from sentinel.modules.formatting import read_field

CsmVersionSwitcher = Callable[[int], Awaitable[None]]


class EventSideEffectProcessor(Protocol):
    async def process_event(self, event: Event) -> None: ...


class CsmInitializedVersionSwitchProcessor:
    def __init__(
        self,
        module_adapter: CommunityModuleAdapter,
        csm_version_switcher: CsmVersionSwitcher,
    ) -> None:
        self.module_adapter = module_adapter
        self._csm_version_switcher = csm_version_switcher

    async def process_event(self, event: Event) -> None:
        if event.event != "Initialized":
            return
        if event.args.get("version") != 3:
            return
        if event.address.lower() != self.module_adapter.addresses.module.lower():
            return
        if self.module_adapter.csm_version < 3:
            await self._csm_version_switcher(3)


class NodeOperatorCountProcessor:
    def __init__(self, module_adapter) -> None:
        self.module_adapter = module_adapter

    async def process_event(self, event: Event) -> None:
        if event.event != "NodeOperatorAdded":
            return
        self.module_adapter.remember_node_operator_added(int(event.args["nodeOperatorId"]))


class CuratedMetadataCacheProcessor:
    def __init__(self, module_adapter: CuratedModuleAdapter) -> None:
        self.module_adapter = module_adapter

    async def process_event(self, event: Event) -> None:
        if event.event != "OperatorMetadataSet":
            return

        self.module_adapter.remember_node_operator_label(
            int(event.args["nodeOperatorId"]),
            read_field(event.args["metadata"], "name", 0) or None,
        )


class ModuleEventSideEffects:
    def __init__(
        self,
        module_adapter,
        csm_version_switcher: CsmVersionSwitcher,
    ) -> None:
        self._csm_version_switcher = csm_version_switcher
        self._processors: tuple[EventSideEffectProcessor, ...] = ()
        self.reconfigure(module_adapter)

    def reconfigure(self, module_adapter) -> None:
        if isinstance(module_adapter, CommunityModuleAdapter):
            self._processors = (
                CsmInitializedVersionSwitchProcessor(
                    module_adapter,
                    self._csm_version_switcher,
                ),
                NodeOperatorCountProcessor(module_adapter),
            )
            return

        if isinstance(module_adapter, CuratedModuleAdapter):
            self._processors = (
                CuratedMetadataCacheProcessor(module_adapter),
                NodeOperatorCountProcessor(module_adapter),
            )
            return

        self._processors = ()

    async def process_event(self, event: Event) -> None:
        for processor in self._processors:
            await processor.process_event(event)
