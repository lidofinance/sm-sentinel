import copy
import re

import pytest
from telegram.helpers import escape_markdown

from sentinel.alertmanager import (
    AlertStatus,
    InvalidAlertmanagerWebhook,
    OperatorAlert,
    parse_alertmanager_webhook,
    split_telegram_markdown,
)
from sentinel.modules.formatting import Bold, Text


@pytest.fixture
def alertmanager_payload():
    def make(operator_id="42", **label_overrides):
        return {
            "version": "4",
            "groupKey": '{}:{alertname="MissedAttestations"}',
            "status": "firing",
            "receiver": "sentinel",
            "truncatedAlerts": 0,
            "commonAnnotations": {"description": "Must not be forwarded to every operator"},
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "chain_id": "1",
                        "staking_module_id": "3",
                        "node_operator_id": operator_id,
                        "alertname": "MissedAttestations",
                        **label_overrides,
                    },
                    "annotations": {"title": "Missed duties", "description": "30 validators"},
                    "startsAt": "2026-10-29T10:00:00Z",
                    "endsAt": "2026-10-29T10:02:00Z",
                    "fingerprint": "abc123",
                    "generatorURL": "https://monitor.example/alerts",
                }
            ],
        }

    return make


def test_parse_standard_webhook_uses_each_alerts_routing_labels(alertmanager_payload):
    payload = alertmanager_payload()
    parsed = parse_alertmanager_webhook(payload)

    assert parsed == (
        OperatorAlert(
            1, 3, "42", "MissedAttestations", AlertStatus.FIRING, "Missed duties", "30 validators"
        ),
    )
    assert "Must not be forwarded" not in "".join(parsed[0].messages(source_id="evm"))


@pytest.mark.parametrize("operator_id, expected", [("0", "0"), ("00042", "42")])
def test_operator_zero_and_decimal_strings_are_supported(
    alertmanager_payload, operator_id, expected
):
    alerts = parse_alertmanager_webhook(alertmanager_payload(operator_id))
    assert alerts[0].node_operator_id == expected


@pytest.mark.parametrize(
    "field, value",
    [
        ("chain_id", "0"),
        ("staking_module_id", "0"),
        ("node_operator_id", "-1"),
        ("node_operator_id", "1.0"),
        ("node_operator_id", " 42"),
        ("node_operator_id", "٤٢"),
        ("node_operator_id", ""),
        ("node_operator_id", str(2**256)),
        ("node_operator_id", 42),
        ("node_operator_id", True),
        ("node_operator_id", None),
        ("alertname", "  "),
    ],
)
def test_invalid_routing_label_is_rejected(alertmanager_payload, field, value):
    with pytest.raises(InvalidAlertmanagerWebhook):
        parse_alertmanager_webhook(alertmanager_payload(**{field: value}))


@pytest.mark.parametrize("field", ["chain_id", "staking_module_id", "node_operator_id"])
def test_common_labels_cannot_replace_required_per_alert_labels(alertmanager_payload, field):
    payload = alertmanager_payload()
    labels = payload["alerts"][0]["labels"]
    payload["commonLabels"] = {field: labels.pop(field)}
    with pytest.raises(InvalidAlertmanagerWebhook, match=field):
        parse_alertmanager_webhook(payload)


def test_source_specific_label_names_are_not_aliases(alertmanager_payload):
    payload = alertmanager_payload()
    labels = payload["alerts"][0]["labels"]
    labels["nos_id"] = labels.pop("node_operator_id")
    labels["nos_module_id"] = labels.pop("staking_module_id")
    with pytest.raises(InvalidAlertmanagerWebhook, match="staking_module_id"):
        parse_alertmanager_webhook(payload)


@pytest.mark.parametrize(
    "payload", [None, [], {}, {"version": "3"}, {"version": "4", "alerts": []}]
)
def test_invalid_envelope_is_rejected(payload):
    with pytest.raises(InvalidAlertmanagerWebhook):
        parse_alertmanager_webhook(payload)


def test_truncated_batch_is_rejected(alertmanager_payload):
    payload = alertmanager_payload()
    payload["truncatedAlerts"] = 1
    with pytest.raises(InvalidAlertmanagerWebhook, match="Truncated"):
        parse_alertmanager_webhook(payload)


def visible_text(message: str) -> str:
    """Telegram's text after parsing the MarkdownV2 subset that alert messages use."""
    return re.sub(r"\\(.)|\*", lambda match: match.group(1) or "", message, flags=re.DOTALL)


def test_message_uses_bot_notification_style(alertmanager_payload):
    alert = parse_alertmanager_webhook(alertmanager_payload())[0]

    assert alert.messages(source_id="evm-1") == (
        "🚨 *Missed duties*\n\n30 validators\n\nnodeOperatorId: 42\nSource: evm\\-1",
    )


@pytest.mark.parametrize("title", [None, "", "  "])
def test_missing_title_falls_back_to_alertname(alertmanager_payload, title):
    payload = alertmanager_payload()
    annotations = payload["alerts"][0]["annotations"]
    if title is None:
        del annotations["title"]
    else:
        annotations["title"] = title
    alert = parse_alertmanager_webhook(payload)[0]

    assert alert.messages(source_id="evm")[0].startswith("🚨 *MissedAttestations*\n\n30 validators")


def test_only_title_and_description_annotations_are_forwarded(alertmanager_payload):
    payload = alertmanager_payload()
    payload["alerts"][0]["annotations"]["summary"] = "Not forwarded"
    alert = parse_alertmanager_webhook(payload)[0]

    assert "Not forwarded" not in alert.messages(source_id="evm")[0]


def test_message_without_annotations_has_title_and_footer(alertmanager_payload):
    payload = alertmanager_payload()
    payload["alerts"][0]["annotations"] = {}
    alert = parse_alertmanager_webhook(payload)[0]

    assert alert.messages(source_id="evm") == (
        "🚨 *MissedAttestations*\n\nnodeOperatorId: 42\nSource: evm",
    )


def test_resolved_is_preserved_as_source_status_without_inferred_recovery(alertmanager_payload):
    payload = alertmanager_payload()
    payload["alerts"][0]["status"] = "resolved"
    alert = parse_alertmanager_webhook(payload)[0]
    message = visible_text(alert.messages(source_id="evm")[0])
    assert message.startswith("ℹ️ Missed duties (resolved)\n")
    assert "recovered" not in message.lower()


def test_annotation_text_is_not_interpreted_as_telegram_markup(alertmanager_payload):
    payload = alertmanager_payload()
    annotation = "<b>30</b> [validators](tg://user?id=1) _*\\`~|>#+-=.!{}"
    payload["alerts"][0]["annotations"]["title"] = annotation
    payload["alerts"][0]["annotations"]["description"] = annotation
    alert = parse_alertmanager_webhook(payload)[0]
    message = alert.messages(source_id="evm")[0]

    assert f"*{escape_markdown(annotation, version=2)}*" in message
    assert visible_text(message).count(annotation) == 2


def test_long_unicode_messages_preserve_text_within_telegram_limits():
    alert = OperatorAlert(1, 3, "42", "Long_*name", AlertStatus.FIRING, "", "😀a." * 3000)
    expected = alert.messages(source_id="evm")
    chunks = split_telegram_markdown([(Bold, "Long_*name"), (Text, "😀a." * 3000)])

    assert len(expected) == 4
    assert "".join(visible_text(chunk) for chunk in chunks) == "Long_*name" + "😀a." * 3000
    for chunk in (*chunks, *expected):
        assert len(visible_text(chunk).encode("utf-16-le")) // 2 <= 4000
        # Each chunk has complete escapes and entities.
        assert not chunk.endswith("\\")
        assert len(re.findall(r"(?<!\\)\*", chunk)) % 2 == 0


@pytest.mark.parametrize("value", [True, False, "0", 0.0, None, -1])
def test_truncation_count_must_be_integer_zero(alertmanager_payload, value):
    payload = alertmanager_payload()
    payload["truncatedAlerts"] = value
    with pytest.raises(InvalidAlertmanagerWebhook, match="truncatedAlerts"):
        parse_alertmanager_webhook(payload)


@pytest.mark.parametrize("value", ["unknown-private-status", 1, True, None, b"firing"])
def test_status_is_a_closed_string_vocabulary(alertmanager_payload, value):
    payload = alertmanager_payload()
    payload["alerts"][0]["status"] = value
    with pytest.raises(InvalidAlertmanagerWebhook, match="status") as exc:
        parse_alertmanager_webhook(payload)
    assert "unknown-private-status" not in str(exc.value)


@pytest.mark.parametrize("field", ["labels", "annotations"])
@pytest.mark.parametrize("value", [42, True, None, ["value"], {"nested": "value"}])
def test_all_label_and_annotation_values_remain_strict_strings(alertmanager_payload, field, value):
    payload = alertmanager_payload()
    payload["alerts"][0][field]["extra"] = value
    with pytest.raises(InvalidAlertmanagerWebhook, match=field):
        parse_alertmanager_webhook(payload)


def test_uint256_labels_preserve_precision_through_domain_conversion(alertmanager_payload):
    maximum = 2**256 - 1
    payload = alertmanager_payload(
        str(maximum), chain_id=str(maximum), staking_module_id=str(maximum)
    )
    alert = parse_alertmanager_webhook(payload)[0]
    assert (alert.chain_id, alert.staking_module_id, alert.node_operator_id) == (
        maximum,
        maximum,
        str(maximum),
    )
    assert alert.status is AlertStatus.FIRING


def test_optional_wire_fields_keep_defaults(alertmanager_payload):
    payload = alertmanager_payload()
    del payload["truncatedAlerts"]
    del payload["alerts"][0]["annotations"]
    alert = parse_alertmanager_webhook(payload)[0]
    assert (alert.title, alert.description) == ("", "")


def test_wire_validation_preserves_original_payload_for_deduplication(alertmanager_payload):
    payload = alertmanager_payload("00042")
    payload["futureField"] = {"arbitrary": [1, None]}
    payload["alerts"][0]["futureField"] = [1, 2]
    original = copy.deepcopy(payload)
    alert = parse_alertmanager_webhook(payload)[0]
    assert alert.node_operator_id == "42"
    assert payload == original


@pytest.mark.parametrize("count, accepted", [(1000, True), (1001, False)])
def test_alert_batch_size_boundary(alertmanager_payload, count, accepted):
    payload = alertmanager_payload()
    payload["alerts"] *= count
    if accepted:
        assert len(parse_alertmanager_webhook(payload)) == count
    else:
        with pytest.raises(InvalidAlertmanagerWebhook):
            parse_alertmanager_webhook(payload)


def test_validation_error_does_not_echo_invalid_annotation_contents(alertmanager_payload):
    payload = alertmanager_payload()
    payload["alerts"][0]["annotations"]["description"] = {"private": "sensitive-content"}
    with pytest.raises(InvalidAlertmanagerWebhook, match="annotations.description") as exc:
        parse_alertmanager_webhook(payload)
    assert "sensitive-content" not in str(exc.value)


def test_parser_preserves_scope_without_applying_runtime_policy(alertmanager_payload):
    alert = parse_alertmanager_webhook(
        alertmanager_payload(chain_id="560048", staking_module_id="1")
    )[0]
    assert (alert.chain_id, alert.staking_module_id) == (560048, 1)
