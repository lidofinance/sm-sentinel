import json

import pytest

from sentinel.alertmanager_auth import (
    AlertmanagerAuthenticator,
    AlertmanagerSource,
    parse_alertmanager_sources,
)

KEY_A = "a" * 43
KEY_B = "b" * 43
KEY_C = "c" * 43


def test_two_keys_during_rotation_identify_the_same_source():
    sources = parse_alertmanager_sources(json.dumps({"evm": [KEY_A, KEY_B], "other": [KEY_C]}))
    authenticator = AlertmanagerAuthenticator(sources)
    assert authenticator.authenticate(f"Bearer {KEY_A}") == "evm"
    assert authenticator.authenticate(f"bearer {KEY_B}") == "evm"
    assert authenticator.authenticate(f"Bearer {KEY_C}") == "other"


def test_removing_a_key_revokes_only_that_key_after_reloading_configuration():
    authenticator = AlertmanagerAuthenticator(
        parse_alertmanager_sources(json.dumps({"evm": [KEY_B], "other": [KEY_C]}))
    )
    assert authenticator.authenticate(f"Bearer {KEY_A}") is None
    assert authenticator.authenticate(f"Bearer {KEY_B}") == "evm"
    assert authenticator.authenticate(f"Bearer {KEY_C}") == "other"


@pytest.mark.parametrize(
    "authorization", ["", "Bearer", "Basic value", "Bearer wrong", "Bearer " + "a" * 513]
)
def test_invalid_credentials_are_rejected(authorization):
    authenticator = AlertmanagerAuthenticator((AlertmanagerSource("evm", (KEY_A,)),))
    assert authenticator.authenticate(authorization) is None


@pytest.mark.parametrize("raw", [None, "", "{}"])
def test_empty_registry_disables_webhook(raw):
    assert parse_alertmanager_sources(raw) == ()


@pytest.mark.parametrize(
    "raw",
    [
        "{broken",
        "null",
        "[]",
        '"text"',
        json.dumps({"evm": KEY_A}),
        json.dumps({"evm": []}),
        json.dumps({"evm": [None]}),
        json.dumps({"evm": [123]}),
        json.dumps({"evm": ["short"]}),
        json.dumps({"evm": ["a" * 32 + " "]}),
        json.dumps({"evm": ["a" * 32 + "\x00"]}),
        json.dumps({"evm": ["я" * 43]}),
        json.dumps({"evm": ["a" * 513]}),
        json.dumps({"evm": [KEY_A, KEY_B, KEY_C]}),
        json.dumps({"evm": [KEY_A, KEY_A]}),
        json.dumps({"evm": [KEY_A], "other": [KEY_A]}),
        json.dumps({"_invalid": [KEY_A]}),
        json.dumps({"EVM": [KEY_A]}),
        json.dumps({"source with spaces": [KEY_A]}),
        '{"evm":["' + KEY_A + '"],"evm":["' + KEY_B + '"]}',
    ],
)
def test_invalid_registry_fails_closed_without_echoing_secret_values(raw):
    with pytest.raises(RuntimeError, match="ALERTMANAGER_WEBHOOK_SOURCES") as caught:
        parse_alertmanager_sources(raw)
    assert KEY_A not in str(caught.value)
    assert KEY_B not in str(caught.value)
    assert caught.value.__suppress_context__ is True


def test_source_repr_does_not_disclose_keys():
    source = AlertmanagerSource("evm", (KEY_A, KEY_B))
    assert "evm" in repr(source)
    assert KEY_A not in repr(source)
    assert KEY_B not in repr(source)
