import json
import subprocess
import sys
from datetime import UTC, time
from pathlib import Path

import pytest

from pydantic import ValidationError

from sentinel.alertmanager_auth import AlertmanagerSource
from sentinel.config import (
    Config,
    ExplorerLinks,
    load_config_from_env,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_config_can_be_imported_cold():
    result = subprocess.run(
        [sys.executable, "-c", "import sentinel.config"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_load_config_accepts_legacy_provider_env(monkeypatch):
    monkeypatch.delenv("WEB3_SOCKET_PROVIDERS", raising=False)
    monkeypatch.setenv(
        "WEB3_SOCKET_PROVIDER",
        "wss://legacy-primary.invalid/ws,wss://legacy-fallback.invalid/ws",
    )
    monkeypatch.setenv("MODULE_ADDRESS", "0x0000000000000000000000000000000000000001")

    cfg = load_config_from_env()

    assert cfg.web3_socket_providers == (
        "wss://legacy-primary.invalid/ws",
        "wss://legacy-fallback.invalid/ws",
    )


def test_load_config_prefers_plural_provider_env(monkeypatch):
    monkeypatch.setenv("WEB3_SOCKET_PROVIDERS", "wss://plural.invalid/ws")
    monkeypatch.setenv("WEB3_SOCKET_PROVIDER", "wss://legacy.invalid/ws")
    monkeypatch.setenv("MODULE_ADDRESS", "0x0000000000000000000000000000000000000001")

    cfg = load_config_from_env()

    assert cfg.web3_socket_providers == ("wss://plural.invalid/ws",)


def test_load_config_reads_module_envs(monkeypatch):
    monkeypatch.setenv("WEB3_SOCKET_PROVIDERS", "wss://example.invalid/ws")
    monkeypatch.setenv("MODULE_ADDRESS", "0x0000000000000000000000000000000000000001")
    monkeypatch.setenv("MODULE_UI_URL", "https://module.example")

    cfg = load_config_from_env()

    assert cfg.module_address == "0x0000000000000000000000000000000000000001"
    assert cfg.module_ui_url == "https://module.example"


def test_load_config_reads_deposit_digest_time_as_utc(monkeypatch):
    monkeypatch.setenv("WEB3_SOCKET_PROVIDERS", "wss://example.invalid/ws")
    monkeypatch.setenv("MODULE_ADDRESS", "0x0000000000000000000000000000000000000001")
    monkeypatch.setenv("DEPOSIT_DIGEST_TIME", "17:45")

    cfg = load_config_from_env()

    assert cfg.deposit_digest_time == time(17, 45, tzinfo=UTC)


@pytest.mark.parametrize("value", ["17:45:01", "17:45+05:00", "midday"])
def test_load_config_rejects_invalid_deposit_digest_time(monkeypatch, value):
    monkeypatch.setenv("WEB3_SOCKET_PROVIDERS", "wss://example.invalid/ws")
    monkeypatch.setenv("MODULE_ADDRESS", "0x0000000000000000000000000000000000000001")
    monkeypatch.setenv("DEPOSIT_DIGEST_TIME", value)

    with pytest.raises(RuntimeError, match="DEPOSIT_DIGEST_TIME"):
        load_config_from_env()


def test_load_config_leaves_module_ui_unset(monkeypatch):
    monkeypatch.setenv("WEB3_SOCKET_PROVIDERS", "wss://example.invalid/ws")
    monkeypatch.setenv("MODULE_ADDRESS", "0x0000000000000000000000000000000000000001")
    monkeypatch.delenv("MODULE_UI_URL", raising=False)

    cfg = load_config_from_env()

    assert cfg.module_ui_url is None


def test_load_config_reads_healthcheck_envs(monkeypatch):
    monkeypatch.setenv("WEB3_SOCKET_PROVIDERS", "wss://example.invalid/ws")
    monkeypatch.setenv("MODULE_ADDRESS", "0x0000000000000000000000000000000000000001")
    monkeypatch.setenv("HEALTHCHECK_HOST", "127.0.0.1")
    monkeypatch.setenv("HEALTHCHECK_PORT", "18080")

    cfg = load_config_from_env()

    assert cfg.healthcheck_host == "127.0.0.1"
    assert cfg.healthcheck_port == 18080


@pytest.mark.parametrize("port", ["", "0", "65536", "abc", "1.5"])
def test_config_rejects_invalid_healthcheck_port(monkeypatch, port):
    monkeypatch.setenv("WEB3_SOCKET_PROVIDERS", "wss://one.invalid")
    monkeypatch.setenv("MODULE_ADDRESS", "0x1234")
    monkeypatch.setenv("HEALTHCHECK_PORT", port)

    with pytest.raises(RuntimeError, match="HEALTHCHECK_PORT"):
        load_config_from_env()


def test_alertmanager_is_disabled_without_registered_sources(monkeypatch):
    monkeypatch.setenv("WEB3_SOCKET_PROVIDERS", "wss://example.invalid/ws")
    monkeypatch.setenv("MODULE_ADDRESS", "0x0000000000000000000000000000000000000001")
    monkeypatch.delenv("ALERTMANAGER_WEBHOOK_SOURCES", raising=False)
    assert load_config_from_env().alertmanager_webhook_sources == ()


def test_alertmanager_configuration_is_loaded_without_exposing_keys(monkeypatch):
    monkeypatch.setenv("WEB3_SOCKET_PROVIDERS", "wss://example.invalid/ws")
    monkeypatch.setenv("MODULE_ADDRESS", "0x0000000000000000000000000000000000000001")
    key = "a" * 43
    monkeypatch.setenv("ALERTMANAGER_WEBHOOK_SOURCES", json.dumps({"evm": [key]}))
    monkeypatch.setenv("ALERTMANAGER_WEBHOOK_HOST", "127.0.0.1")
    monkeypatch.setenv("ALERTMANAGER_WEBHOOK_PORT", "18081")
    cfg = load_config_from_env()
    assert cfg.alertmanager_webhook_sources[0].source_id == "evm"
    assert cfg.alertmanager_webhook_sources[0].keys == (key,)
    assert cfg.alertmanager_webhook_host == "127.0.0.1"
    assert cfg.alertmanager_webhook_port == 18081
    assert key not in repr(cfg)


@pytest.mark.parametrize("port", ["", "0", "65536", "abc", "1.5"])
def test_alertmanager_rejects_invalid_port(monkeypatch, port):
    monkeypatch.setenv("WEB3_SOCKET_PROVIDERS", "wss://example.invalid/ws")
    monkeypatch.setenv("MODULE_ADDRESS", "0x0000000000000000000000000000000000000001")
    monkeypatch.setenv("ALERTMANAGER_WEBHOOK_PORT", port)
    with pytest.raises(RuntimeError, match="ALERTMANAGER_WEBHOOK_PORT"):
        load_config_from_env()


def test_environment_loader_uses_defaults_for_absent_settings_and_parses_lists(monkeypatch):
    monkeypatch.setenv(
        "WEB3_SOCKET_PROVIDERS", " wss://one.invalid , wss://one.invalid,wss://two.invalid "
    )
    monkeypatch.setenv("MODULE_ADDRESS", "0x1234")
    monkeypatch.delenv("BLOCK_FROM", raising=False)
    monkeypatch.delenv("PROCESS_BLOCKS_REQUESTS_PER_SECOND", raising=False)
    monkeypatch.setenv("ADMIN_IDS", "1,2 invalid 3,1")
    monkeypatch.delenv("HEALTHCHECK_PORT", raising=False)
    monkeypatch.delenv("ALERTMANAGER_WEBHOOK_PORT", raising=False)
    monkeypatch.delenv("DEPOSIT_DIGEST_TIME", raising=False)
    cfg = load_config_from_env()
    assert cfg.web3_socket_providers == ("wss://one.invalid", "wss://two.invalid")
    assert cfg.block_from is None
    assert cfg.process_blocks_requests_per_second is None
    assert cfg.admin_ids == {1, 2, 3}
    assert cfg.healthcheck_port == 8080
    assert cfg.alertmanager_webhook_port == 8081
    assert cfg.deposit_digest_time == time(9, tzinfo=UTC)


@pytest.mark.parametrize("value", ["nan", "inf", "0", "-1"])
def test_environment_rejects_invalid_rate(monkeypatch, value):
    monkeypatch.setenv("WEB3_SOCKET_PROVIDERS", "wss://one.invalid")
    monkeypatch.setenv("MODULE_ADDRESS", "0x1234")
    monkeypatch.setenv("PROCESS_BLOCKS_REQUESTS_PER_SECOND", value)
    with pytest.raises(RuntimeError, match="PROCESS_BLOCKS_REQUESTS_PER_SECOND"):
        load_config_from_env()


def test_environment_errors_do_not_include_secrets(monkeypatch):
    monkeypatch.setenv("WEB3_SOCKET_PROVIDERS", "wss://private-credential.invalid")
    monkeypatch.setenv("MODULE_ADDRESS", "0x1234")
    monkeypatch.setenv("BLOCK_FROM", "secret-invalid-block")
    monkeypatch.setenv("TOKEN", "secret-telegram-token")
    with pytest.raises(RuntimeError, match="BLOCK_FROM") as exc:
        load_config_from_env()
    assert "secret" not in str(exc.value)
    assert "credential" not in str(exc.value)


@pytest.mark.parametrize("port", ["1", "65535"])
def test_config_accepts_port_boundaries(monkeypatch, port):
    monkeypatch.setenv("WEB3_SOCKET_PROVIDERS", "wss://one.invalid")
    monkeypatch.setenv("MODULE_ADDRESS", "0x1234")
    monkeypatch.setenv("HEALTHCHECK_PORT", port)
    monkeypatch.setenv("ALERTMANAGER_WEBHOOK_PORT", port)
    cfg = load_config_from_env()
    assert cfg.healthcheck_port == int(port)
    assert cfg.alertmanager_webhook_port == int(port)


@pytest.mark.parametrize("value", ["", " , , "])
def test_provider_list_requires_at_least_one_endpoint(monkeypatch, value):
    monkeypatch.setenv("MODULE_ADDRESS", "0x1234")
    monkeypatch.setenv("WEB3_SOCKET_PROVIDERS", value)
    monkeypatch.delenv("WEB3_SOCKET_PROVIDER", raising=False)
    with pytest.raises(RuntimeError, match="WEB3_SOCKET_PROVIDERS"):
        load_config_from_env()


@pytest.mark.parametrize("missing", [None, ""])
def test_explorer_links_require_only_the_address_being_used(missing):
    execution = ExplorerLinks("https://etherscan.io", missing)
    assert execution.block(123) == "https://etherscan.io/block/123"
    assert execution.transaction("0xab") == "https://etherscan.io/tx/0xab"
    with pytest.raises(RuntimeError, match="BEACONCHAIN_URL"):
        execution.validator("0xcd")

    consensus = ExplorerLinks(missing, "https://beaconcha.in")
    assert consensus.validator("0xcd") == "https://beaconcha.in/validator/0xcd"
    with pytest.raises(RuntimeError, match="ETHERSCAN_URL"):
        consensus.block(123)
    with pytest.raises(RuntimeError, match="ETHERSCAN_URL"):
        consensus.transaction("0xab")


def test_config_accepts_typed_settings_and_round_trips_without_discovery():
    explorers = ExplorerLinks("https://etherscan.io", "https://beaconcha.in")
    source = AlertmanagerSource("evm", ("a" * 43,))
    cfg = Config(
        module_address="0x1234",
        web3_socket_providers=("wss://one.invalid",),
        explorers=explorers,
        admin_ids={1, 2},
        deposit_digest_time=time(17, 45, tzinfo=UTC),
        alertmanager_webhook_sources=(source,),
    )
    assert cfg.explorers is explorers
    assert cfg.explorers.transaction("0xab") == "https://etherscan.io/tx/0xab"
    assert cfg.alertmanager_webhook_sources == (source,)
    assert cfg.admin_ids == {1, 2}
    assert cfg.deposit_digest_time == time(17, 45, tzinfo=UTC)
    assert Config.model_validate(cfg.model_dump()) == cfg
    with pytest.raises(ValidationError, match="frozen"):
        cfg.module_address = "0x5678"


def test_environment_loader_returns_complete_config(monkeypatch):
    monkeypatch.setenv("MODULE_ADDRESS", "0x1234")
    monkeypatch.setenv("WEB3_SOCKET_PROVIDERS", "wss://one.invalid")
    monkeypatch.setenv("ETHERSCAN_URL", "https://etherscan.io")
    monkeypatch.setenv("BEACONCHAIN_URL", "https://beaconcha.in")
    cfg = load_config_from_env()
    assert isinstance(cfg, Config)
    assert cfg.explorers.block(123) == "https://etherscan.io/block/123"
    assert cfg.explorers.validator("0xcd") == "https://beaconcha.in/validator/0xcd"


@pytest.mark.parametrize(
    "name",
    [
        "BLOCK_FROM",
        "PROCESS_BLOCKS_REQUESTS_PER_SECOND",
        "BLOCK_BATCH_SIZE",
        "HEALTHCHECK_PORT",
        "ALERTMANAGER_WEBHOOK_PORT",
        "DEPOSIT_DIGEST_TIME",
    ],
)
def test_environment_rejects_empty_numeric_and_time_settings(monkeypatch, name):
    monkeypatch.setenv("MODULE_ADDRESS", "0x1234")
    monkeypatch.setenv("WEB3_SOCKET_PROVIDERS", "wss://one.invalid")
    monkeypatch.setenv(name, "")
    with pytest.raises(RuntimeError, match=name):
        load_config_from_env()
