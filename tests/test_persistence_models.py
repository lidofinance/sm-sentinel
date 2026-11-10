import copy
from dataclasses import replace

import pytest
from hexbytes import HexBytes
from pydantic import ValidationError

from sentinel.app.storage import AggregationWindowStore, RuntimeIdentity
from sentinel.models import Event, EventRecord
from sentinel.module_types import ModuleType
from sentinel.modules.aggregation import AggregationKey, AggregationWindow


@pytest.fixture
def stored_event():
    return Event(
        event="Example",
        args={"amount": 2**256 - 1, "nested": {"proof": HexBytes("0xff00")}},
        block=123,
        tx=HexBytes("0x" + "ab" * 32),
        address="0x" + "12" * 20,
        log_index=2,
        transaction_index=1,
    )


def test_event_record_preserves_binary_arguments_and_uint256(stored_event):
    record = stored_event.to_dict()
    original = copy.deepcopy(record)
    restored = Event.from_dict(record)
    assert restored == stored_event
    assert isinstance(restored.tx, HexBytes)
    assert isinstance(restored.args["nested"]["proof"], HexBytes)
    assert restored.to_dict() == original
    assert record == original
    serialized = EventRecord.model_validate(original).model_dump()
    assert serialized == original
    assert isinstance(serialized["args"]["nested"]["proof"], HexBytes)


def test_event_record_accepts_legacy_integer_strings(stored_event):
    record = stored_event.to_dict()
    for name in ("block", "log_index", "transaction_index"):
        record[name] = str(record[name])
    record["future_field"] = {"ignored": True}
    assert Event.from_dict(record) == stored_event


@pytest.mark.parametrize(
    "field,value", [("event", None), ("args", []), ("block", 1.5), ("address", "bad-address")]
)
def test_event_record_rejects_malformed_fields(stored_event, field, value):
    record = stored_event.to_dict()
    record[field] = value
    with pytest.raises(ValidationError):
        Event.from_dict(record)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("chain_id", True),
        ("chain_id", "1"),
        ("module_type", "unknown"),
        ("module_address", ""),
    ],
)
def test_runtime_identity_record_remains_strict(field, value):
    identity = RuntimeIdentity(1, "0x1234", ModuleType.COMMUNITY)
    record = identity.to_dict()
    record[field] = value
    with pytest.raises(RuntimeError, match="malformed"):
        RuntimeIdentity.from_dict(record)


def test_aggregation_records_restore_domain_objects_and_skip_bad_records(stored_event):
    window = AggregationWindow(
        "group", AggregationKey("operator", "42"), 123, 124, frozenset({"Example"}), (stored_event,)
    )
    data = {}
    store = AggregationWindowStore(data)
    store.upsert_pending(window)
    valid = copy.deepcopy(data)
    bad = copy.deepcopy(next(iter(data["aggregation_windows"].values())))
    bad["events"][0]["block"] = None
    data["aggregation_windows"]["bad"] = bad
    restored = AggregationWindowStore(data)
    assert restored.pending() == [window]
    assert data == valid
    assert restored.pending_for("group", AggregationKey("operator", "42"), 123) == window
    restored.upsert_pending(replace(window, end_block=125))
    assert len(restored.pending()) == 2


def test_saving_and_normalizing_windows_does_not_reconstruct_domain_events(
    stored_event, monkeypatch
):
    window = AggregationWindow(
        "group", AggregationKey("operator", "42"), 123, 124, frozenset({"Example"}), (stored_event,)
    )

    def unexpected_conversion(self):
        raise AssertionError("Domain events should only be reconstructed when read")

    monkeypatch.setattr(EventRecord, "to_event", unexpected_conversion)
    data = {}
    store = AggregationWindowStore(data)
    store.upsert_pending(window)
    expected = copy.deepcopy(data)
    AggregationWindowStore(data)
    assert data == expected
    record = next(iter(data["aggregation_windows"].values()))
    assert record["events"] == [stored_event.to_dict()]
