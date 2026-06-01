import asyncio
import subprocess
import sys

import pytest

from sentinel.config import clear_config, get_config_async, get_healthcheck_bind_from_env
from sentinel.module_types import ModuleType


def test_config_can_be_imported_cold():
    result = subprocess.run(
        [sys.executable, "-c", "import sentinel.config"],
        cwd="/Users/skhomuti/csm-bot/csm-watcher",
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_get_config_async_retries_when_rpc_times_out(monkeypatch, fake_contract_addresses):
    clear_config()

    monkeypatch.setenv("WEB3_SOCKET_PROVIDER", "wss://example.invalid/ws")
    monkeypatch.setenv("MODULE_ADDRESS", "0x0000000000000000000000000000000000000001")

    attempts = 0

    async def fake_discover_contract_addresses(provider_url: str, module_address: str):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise asyncio.TimeoutError
        return fake_contract_addresses(module_address)

    monkeypatch.setattr(
        "sentinel.config._discover_contract_addresses",
        fake_discover_contract_addresses,
    )
    monkeypatch.setattr("sentinel.config.RPC_DISCOVERY_RETRY_DELAY_SECONDS", 0)

    cfg = await get_config_async()

    assert attempts == 2
    assert cfg.contract_addresses.module == "0x0000000000000000000000000000000000000001"
    clear_config()


@pytest.mark.asyncio
async def test_get_config_async_prefers_module_envs(monkeypatch, stub_discover_contract_addresses):
    clear_config()

    monkeypatch.setenv("WEB3_SOCKET_PROVIDER", "wss://example.invalid/ws")
    monkeypatch.setenv("MODULE_ADDRESS", "0x0000000000000000000000000000000000000001")
    monkeypatch.setenv("MODULE_UI_URL", "https://module.example")

    cfg = await get_config_async()

    assert cfg.contract_addresses.module == "0x0000000000000000000000000000000000000001"
    assert cfg.module_ui_url == "https://module.example"
    assert cfg.contract_addresses.module_type == ModuleType.COMMUNITY
    clear_config()


@pytest.mark.asyncio
async def test_get_config_async_leaves_module_ui_unset(
    monkeypatch, stub_discover_contract_addresses
):
    clear_config()

    monkeypatch.setenv("WEB3_SOCKET_PROVIDER", "wss://example.invalid/ws")
    monkeypatch.setenv("MODULE_ADDRESS", "0x0000000000000000000000000000000000000001")
    monkeypatch.delenv("MODULE_UI_URL", raising=False)

    cfg = await get_config_async()

    assert cfg.module_ui_url is None
    clear_config()


@pytest.mark.asyncio
async def test_get_config_async_reads_healthcheck_envs(
    monkeypatch, stub_discover_contract_addresses
):
    clear_config()

    monkeypatch.setenv("WEB3_SOCKET_PROVIDER", "wss://example.invalid/ws")
    monkeypatch.setenv("MODULE_ADDRESS", "0x0000000000000000000000000000000000000001")
    monkeypatch.setenv("HEALTHCHECK_HOST", "127.0.0.1")
    monkeypatch.setenv("HEALTHCHECK_PORT", "18080")

    cfg = await get_config_async()

    assert cfg.healthcheck_host == "127.0.0.1"
    assert cfg.healthcheck_port == 18080
    clear_config()


def test_get_healthcheck_bind_from_env_rejects_invalid_port(monkeypatch):
    monkeypatch.setenv("HEALTHCHECK_PORT", "70000")

    with pytest.raises(RuntimeError, match="HEALTHCHECK_PORT"):
        get_healthcheck_bind_from_env()
