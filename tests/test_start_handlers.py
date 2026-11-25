from asyncio import Lock
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram import CallbackQuery, Update, User
from telegram.ext import ApplicationBuilder, ContextTypes, ExtBot

from sentinel.alertmanager_auth import AlertmanagerSource
from sentinel.app.alertmanager_storage import AlertmanagerPreferences
from sentinel.app.application import SentinelApplication
from sentinel.app.context import BotContext
from sentinel.handlers import build_conversation_handler
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


async def test_private_chat_can_disable_and_reenable_an_alertmanager_source(
    database_factory, monkeypatch
):
    database = await database_factory()
    send = AsyncMock()
    edit = AsyncMock()
    monkeypatch.setattr(ExtBot, "initialize", AsyncMock())
    monkeypatch.setattr(ExtBot, "bot", User(123, "Sentinel", True, username="sentinel_bot"))
    monkeypatch.setattr(ExtBot, "send_message", send)
    monkeypatch.setattr(CallbackQuery, "answer", AsyncMock())
    monkeypatch.setattr(CallbackQuery, "edit_message_text", edit)
    application = (
        ApplicationBuilder()
        .application_class(SentinelApplication)
        .context_types(ContextTypes(context=BotContext))
        .token("123:TEST")
        .build()
    )
    long_id = "z" * 64
    source_ids = [f"monitor-{n}" for n in range(8)] + [long_id]
    application.attach_runtime(
        SimpleNamespace(
            config=SimpleNamespace(
                alertmanager_webhook_sources=tuple(
                    AlertmanagerSource(source_id, (str(n) * 32,))
                    for n, source_id in enumerate(source_ids)
                )
            ),
            module_adapter=SimpleNamespace(texts=CuratedTexts),
            chat_migrations=SimpleNamespace(state_lock=Lock()),
            database=database,
        )
    )
    application.add_handler(build_conversation_handler())
    await application.initialize()

    user = {"id": 100, "first_name": "Reader", "is_bot": False}

    async def process_update(callback_data=None, *, private=True):
        chat = {"id": 100, "type": "private"} if private else {"id": -100, "type": "group"}
        message = {"message_id": 1, "date": 0, "chat": chat}
        if callback_data is None:
            message.update(
                {
                    "from": user,
                    "text": "/start",
                    "entities": [{"type": "bot_command", "offset": 0, "length": 6}],
                }
            )
            data = {"message": message}
        else:
            data = {
                "callback_query": {
                    "id": "query",
                    "chat_instance": "chat",
                    "from": user,
                    "message": message,
                    "data": callback_data,
                }
            }
        await application.process_update(Update.de_json({"update_id": 1, **data}, application.bot))

    await process_update()
    welcome_keyboard = send.await_args.kwargs["reply_markup"].inline_keyboard
    settings_button = welcome_keyboard[1][0]
    assert settings_button.text == "Alertmanager alerts"
    await process_update(settings_button.callback_data)
    keyboard = edit.await_args.kwargs["reply_markup"].inline_keyboard
    assert keyboard[0][0].text == "On · monitor-0"
    await process_update(keyboard[-2][-1].callback_data)
    source_button = edit.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
    assert source_button.text == f"On · {long_id}"
    assert len(source_button.callback_data.encode()) <= 64

    await process_update(source_button.callback_data)
    await process_update(source_button.callback_data)
    enable_button = edit.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
    assert enable_button.text == f"Off · {long_id}"
    await database.close()
    await database.open()
    async with database.session() as session:
        assert await AlertmanagerPreferences(session).disabled_sources(100) == {long_id}

    await process_update(enable_button.callback_data)
    async with database.session() as session:
        assert await AlertmanagerPreferences(session).disabled_sources(100) == set()

    await process_update(private=False)
    group_keyboard = send.await_args.kwargs["reply_markup"].inline_keyboard
    assert all(settings_button not in row for row in group_keyboard)
    await process_update(settings_button.callback_data, private=False)
    await process_update(source_button.callback_data, private=False)
    async with database.session() as session:
        assert await AlertmanagerPreferences(session).disabled_recipients(long_id) == set()
    await application.shutdown()
