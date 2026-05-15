from sentinel.handlers.start import (
    FOLLOW_OPERATOR_PAGE_PREFIX,
    FOLLOW_OPERATOR_PREFIX,
    _build_operator_keyboard,
    _format_following,
    _followed_operator_options,
    _parse_node_operator_ids,
)
from sentinel.modules.base import NodeOperatorOption
from sentinel.modules.curated.texts import CuratedTexts


class _FakeModuleAdapter:
    async def node_operator_label(self, operator_id: int) -> str:
        return {
            0: "#0 - Attestant (BVI) Limited",
            1: "#1 - Attestant (BVI) Limited - IODC",
            2: "#2 - Develp PTO",
        }[operator_id]


class _FakeRuntime:
    module_adapter = _FakeModuleAdapter()


class _FakeContext:
    runtime = _FakeRuntime()


class _FakeGenericModuleAdapter:
    async def node_operator_label(self, operator_id: int) -> str:
        return f"#{operator_id}"


class _FakeGenericRuntime:
    module_adapter = _FakeGenericModuleAdapter()


class _FakeGenericContext:
    runtime = _FakeGenericRuntime()


def test_parse_node_operator_ids_accepts_hashes_and_commas():
    assert _parse_node_operator_ids("#1, 2, #3, 2") == ["1", "2", "3"]


def test_parse_node_operator_ids_rejects_empty_comma_items():
    assert _parse_node_operator_ids("1, , 2") == []


async def test_format_following_renders_labeled_operators_as_list():
    assert await _format_following(_FakeContext(), {"2", "0", "1"}) == (
        "- #0 - Attestant (BVI) Limited\n- #1 - Attestant (BVI) Limited - IODC\n- #2 - Develp PTO"
    )


async def test_format_following_renders_plain_operator_ids_compactly():
    assert await _format_following(_FakeGenericContext(), {"2", "0", "1"}) == "#0, #1, #2"


async def test_followed_operator_options_builds_button_options_from_followed_ids():
    assert await _followed_operator_options(_FakeContext(), {"2", "0", "1"}) == (
        NodeOperatorOption(id=0, label="#0 - Attestant (BVI) Limited"),
        NodeOperatorOption(id=1, label="#1 - Attestant (BVI) Limited - IODC"),
        NodeOperatorOption(id=2, label="#2 - Develp PTO"),
    )


def test_operator_keyboard_uses_paginated_curated_options():
    options = tuple(NodeOperatorOption(id=i, label=f"#{i} - Operator {i}") for i in range(10))

    markup = _build_operator_keyboard(
        texts=CuratedTexts,
        options=options,
        operator_prefix=FOLLOW_OPERATOR_PREFIX,
        page_prefix=FOLLOW_OPERATOR_PAGE_PREFIX,
    )

    keyboard = markup.inline_keyboard
    assert keyboard[0][0].text == "#0 - Operator 0"
    assert keyboard[0][0].callback_data == "follow_no:0"
    assert keyboard[7][0].callback_data == "follow_no:7"
    assert keyboard[8][0].text == "Next"
    assert keyboard[8][0].callback_data == "follow_no_page:1"
    assert keyboard[9][0].text == CuratedTexts.BUTTON_BACK
