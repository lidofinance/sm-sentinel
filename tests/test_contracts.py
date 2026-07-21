import web3.exceptions
import pytest
from unittest.mock import AsyncMock


def test_find_staking_module_id_success():
    from sentinel.app.contracts import _find_staking_module_id

    modules = [
        (1, "0x1234567890123456789012345678901234567890"),
        (2, "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"),
    ]

    assert _find_staking_module_id(modules, "0xABCDefAbcdefABCDefABCDEFabcdefABCDefAbcd") == 2


def test_find_staking_module_id_returns_none_when_module_is_not_registered():
    from sentinel.app.contracts import _find_staking_module_id

    modules = [
        (1, "0x1234567890123456789012345678901234567890"),
        (2, "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"),
    ]

    assert _find_staking_module_id(modules, "0x0000000000000000000000000000000000000000") is None


@pytest.mark.asyncio
async def test_discover_csm_version_detects_v3():
    from sentinel.app.contracts import _discover_csm_version

    module_contract = type("ModuleContract", (), {})()
    module_contract.functions = type("Functions", (), {})()
    module_contract.functions.getInitializedVersion = lambda: type(
        "Call",
        (),
        {"call": AsyncMock(return_value=3)},
    )()

    assert await _discover_csm_version(module_contract) == 3


@pytest.mark.asyncio
async def test_discover_csm_version_falls_back_to_v2():
    from sentinel.app.contracts import _discover_csm_version

    module_contract = type("ModuleContract", (), {})()
    module_contract.functions = type("Functions", (), {})()
    module_contract.functions.getInitializedVersion = lambda: type(
        "Call",
        (),
        {"call": AsyncMock(side_effect=web3.exceptions.ContractLogicError("missing selector"))},
    )()

    assert await _discover_csm_version(module_contract) == 2
