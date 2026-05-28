from typing import TYPE_CHECKING

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest

from sentinel.handlers.state import Callback, States
from sentinel.handlers.tracking import add_user_if_required
from sentinel.handlers.utils import is_admin, reply_with_markup
from sentinel.modules.base import NodeOperatorOption

if TYPE_CHECKING:
    from sentinel.app.context import BotContext


OPERATOR_BUTTON_PAGE_SIZE = 8
FOLLOW_OPERATOR_PREFIX = "follow_no:"
FOLLOW_OPERATOR_PAGE_PREFIX = "follow_no_page:"
UNFOLLOW_OPERATOR_PREFIX = "unfollow_no:"
UNFOLLOW_OPERATOR_PAGE_PREFIX = "unfollow_no_page:"


def _is_message_not_modified(exc: BadRequest) -> bool:
    return "message is not modified" in str(exc).lower()


async def _edit_message_text(
    query: CallbackQuery,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
    parse_mode: str | None = None,
) -> None:
    try:
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    except BadRequest as exc:
        if _is_message_not_modified(exc):
            return
        raise


def _parse_node_operator_ids(raw_text: str) -> list[str]:
    ids: list[str] = []
    for item in raw_text.split(","):
        node_operator_id = item.strip()
        if node_operator_id.startswith("#"):
            node_operator_id = node_operator_id[1:].strip()
        if not node_operator_id:
            return []
        ids.append(node_operator_id)
    return list(dict.fromkeys(ids))


def _format_node_operator_ids(node_operator_ids: list[str]) -> str:
    return ", ".join(f"#{node_operator_id}" for node_operator_id in node_operator_ids)


def _sort_node_operator_ids(node_operator_ids: set[str]) -> list[str]:
    return sorted(
        node_operator_ids,
        key=lambda node_operator_id: (
            (
                0,
                int(node_operator_id),
            )
            if node_operator_id.isdigit()
            else (1, node_operator_id)
        ),
    )


def _operator_button_text(label: str) -> str:
    if len(label) <= 58:
        return label
    return f"{label[:55]}..."


def _build_operator_keyboard(
    *,
    texts,
    options: tuple[NodeOperatorOption, ...],
    operator_prefix: str,
    page_prefix: str,
    page: int = 0,
) -> InlineKeyboardMarkup:
    page_count = max(1, (len(options) + OPERATOR_BUTTON_PAGE_SIZE - 1) // OPERATOR_BUTTON_PAGE_SIZE)
    page = min(max(page, 0), page_count - 1)
    page_start = page * OPERATOR_BUTTON_PAGE_SIZE
    page_options = options[page_start : page_start + OPERATOR_BUTTON_PAGE_SIZE]

    keyboard = [
        [
            InlineKeyboardButton(
                _operator_button_text(option.label),
                callback_data=f"{operator_prefix}{option.id}",
            )
        ]
        for option in page_options
    ]
    if page_count > 1:
        navigation = []
        if page > 0:
            navigation.append(
                InlineKeyboardButton("Previous", callback_data=f"{page_prefix}{page - 1}")
            )
        if page + 1 < page_count:
            navigation.append(
                InlineKeyboardButton("Next", callback_data=f"{page_prefix}{page + 1}")
            )
        keyboard.append(navigation)
    keyboard.append([InlineKeyboardButton(texts.BUTTON_BACK, callback_data=Callback.BACK.value)])
    return InlineKeyboardMarkup(keyboard)


async def _format_following(context: "BotContext", node_operator_ids: set[str]) -> str:
    labels = []
    for node_operator_id in _sort_node_operator_ids(node_operator_ids):
        if node_operator_id.isdigit():
            labels.append(
                await context.runtime.module_adapter.node_operator_label(int(node_operator_id))
            )
        else:
            labels.append(f"#{node_operator_id}")
    if all(label.startswith("#") and label[1:].isdigit() for label in labels):
        return ", ".join(labels)
    return "\n".join(f"- {label}" for label in labels)


async def _followed_operator_options(
    context: "BotContext", node_operator_ids: set[str]
) -> tuple[NodeOperatorOption, ...]:
    options = []
    for node_operator_id in _sort_node_operator_ids(node_operator_ids):
        if not node_operator_id.isdigit():
            continue
        numeric_id = int(node_operator_id)
        options.append(
            NodeOperatorOption(
                id=numeric_id,
                label=await context.runtime.module_adapter.node_operator_label(numeric_id),
            )
        )
    return tuple(options)


async def _build_follow_prompt(
    context: "BotContext", page: int = 0
) -> tuple[str, InlineKeyboardMarkup]:
    texts = context.runtime.module_adapter.texts
    chat_storage = context.chat_storage()
    node_operator_ids = chat_storage.node_operators.ids()
    text = texts.FOLLOW_NODE_OPERATOR_TEXT
    if node_operator_ids:
        text = (
            texts.FOLLOW_NODE_OPERATOR_FOLLOWING.format(
                await _format_following(context, node_operator_ids)
            )
            + text
        )

    options = await context.runtime.module_adapter.node_operator_options()
    options = tuple(option for option in options if str(option.id) not in node_operator_ids)
    return text, _build_operator_keyboard(
        texts=texts,
        options=options,
        operator_prefix=FOLLOW_OPERATOR_PREFIX,
        page_prefix=FOLLOW_OPERATOR_PAGE_PREFIX,
        page=page,
    )


async def _build_unfollow_prompt(
    context: "BotContext", page: int = 0
) -> tuple[str, InlineKeyboardMarkup]:
    texts = context.runtime.module_adapter.texts
    chat_storage = context.chat_storage()
    node_operator_ids = chat_storage.node_operators.ids()
    if node_operator_ids:
        text = texts.UNFOLLOW_NODE_OPERATOR_FOLLOWING.format(
            await _format_following(context, node_operator_ids)
        )
        text += texts.UNFOLLOW_NODE_OPERATOR_TEXT
    else:
        text = texts.UNFOLLOW_NODE_OPERATOR_NOT_FOLLOWING

    options = await _followed_operator_options(context, node_operator_ids)
    return text, _build_operator_keyboard(
        texts=texts,
        options=options,
        operator_prefix=UNFOLLOW_OPERATOR_PREFIX,
        page_prefix=UNFOLLOW_OPERATOR_PAGE_PREFIX,
        page=page,
    )


async def _valid_node_operator_ids(
    context: "BotContext", ids: list[str]
) -> tuple[list[str], list[str]]:
    valid_ids: list[str] = []
    invalid_ids: list[str] = []
    for node_operator_id in ids:
        if node_operator_id.isdigit() and await context.runtime.module_adapter.is_valid_operator_id(
            int(node_operator_id)
        ):
            valid_ids.append(str(int(node_operator_id)))
        else:
            invalid_ids.append(node_operator_id)
    return valid_ids, invalid_ids


async def start(update: Update, context: "BotContext") -> States:
    await add_user_if_required(update, context)
    effective_user = update.effective_user
    effective_chat = update.effective_chat
    if effective_user is None or effective_chat is None:
        return States.WELCOME

    texts = context.runtime.module_adapter.texts
    chat_storage = context.chat_storage()
    keyboard = [
        [
            InlineKeyboardButton(
                texts.START_BUTTON_FOLLOW, callback_data=Callback.FOLLOW_TO_NODE_OPERATOR.value
            ),
            InlineKeyboardButton(
                texts.START_BUTTON_UNFOLLOW,
                callback_data=Callback.UNFOLLOW_FROM_NODE_OPERATOR.value,
            ),
            InlineKeyboardButton(
                texts.START_BUTTON_EVENTS, callback_data=Callback.FOLLOWED_EVENTS.value
            ),
        ],
    ]
    if is_admin(effective_user.id, context):
        keyboard.append(
            [InlineKeyboardButton(texts.START_BUTTON_ADMIN, callback_data=Callback.ADMIN.value)]
        )

    text = texts.WELCOME_TEXT
    node_operator_ids = sorted(chat_storage.node_operators.ids())
    if node_operator_ids:
        text += texts.FOLLOW_NODE_OPERATOR_FOLLOWING.format(
            await _format_following(context, set(node_operator_ids))
        )

    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=effective_chat.id,
        text=text,
        reply_markup=reply_markup,
    )
    return States.WELCOME


async def start_over(update: Update, context: "BotContext") -> States:
    query = update.callback_query
    effective_user = update.effective_user
    if query is None or effective_user is None:
        return States.WELCOME

    texts = context.runtime.module_adapter.texts
    keyboard = [
        [
            InlineKeyboardButton(
                texts.START_BUTTON_FOLLOW, callback_data=Callback.FOLLOW_TO_NODE_OPERATOR.value
            ),
            InlineKeyboardButton(
                texts.START_BUTTON_UNFOLLOW,
                callback_data=Callback.UNFOLLOW_FROM_NODE_OPERATOR.value,
            ),
            InlineKeyboardButton(
                texts.START_BUTTON_EVENTS, callback_data=Callback.FOLLOWED_EVENTS.value
            ),
        ],
    ]
    if is_admin(effective_user.id, context):
        keyboard.append(
            [InlineKeyboardButton(texts.START_BUTTON_ADMIN, callback_data=Callback.ADMIN.value)]
        )

    text = texts.WELCOME_TEXT
    chat_storage = context.chat_storage()
    node_operator_ids = sorted(chat_storage.node_operators.ids())
    if node_operator_ids:
        text += texts.FOLLOW_NODE_OPERATOR_FOLLOWING.format(
            await _format_following(context, set(node_operator_ids))
        )

    reply_markup = InlineKeyboardMarkup(keyboard)
    await _edit_message_text(
        query,
        text=text,
        reply_markup=reply_markup,
    )
    return States.WELCOME


async def follow_node_operator(update: Update, context: "BotContext") -> States:
    query = update.callback_query
    if query is None:
        return States.FOLLOW_NODE_OPERATOR
    await query.answer()

    text, reply_markup = await _build_follow_prompt(context)
    await _edit_message_text(query, text=text, reply_markup=reply_markup)
    return States.FOLLOW_NODE_OPERATOR


async def follow_node_operator_message(update: Update, context: "BotContext") -> States:
    texts = context.runtime.module_adapter.texts
    keyboard = [InlineKeyboardButton(texts.BUTTON_BACK, callback_data=Callback.BACK.value)]
    message = update.message
    if message is None or not message.text:
        await reply_with_markup(
            update,
            context,
            texts.NODE_OPERATOR_CANT_FOLLOW,
            InlineKeyboardMarkup([keyboard]),
        )
        return States.FOLLOW_NODE_OPERATOR

    node_operator_ids = _parse_node_operator_ids(message.text)
    valid_ids, invalid_ids = await _valid_node_operator_ids(context, node_operator_ids)
    if valid_ids and not invalid_ids:
        chat_storage = context.chat_storage()
        for node_operator_id in valid_ids:
            context.bot_storage.node_operator_chats.subscribe(node_operator_id, message.chat_id)
            chat_storage.node_operators.follow(node_operator_id)
        followed_text = (
            texts.NODE_OPERATOR_FOLLOWED.format(valid_ids[0])
            if len(valid_ids) == 1
            else f"You are now following Node Operators {_format_node_operator_ids(valid_ids)}"
        )
        await reply_with_markup(
            update,
            context,
            followed_text,
            InlineKeyboardMarkup([keyboard]),
        )
        return States.FOLLOW_NODE_OPERATOR

    invalid_text = f"\nInvalid: {_format_node_operator_ids(invalid_ids)}" if invalid_ids else ""
    await reply_with_markup(
        update,
        context,
        f"{texts.NODE_OPERATOR_CANT_FOLLOW}{invalid_text}",
        InlineKeyboardMarkup([keyboard]),
    )
    return States.FOLLOW_NODE_OPERATOR


async def follow_node_operator_page(update: Update, context: "BotContext") -> States:
    query = update.callback_query
    if query is None or query.data is None:
        return States.FOLLOW_NODE_OPERATOR
    await query.answer()

    page = int(query.data.removeprefix(FOLLOW_OPERATOR_PAGE_PREFIX))
    text, reply_markup = await _build_follow_prompt(context, page)
    await _edit_message_text(query, text=text, reply_markup=reply_markup)
    return States.FOLLOW_NODE_OPERATOR


async def follow_node_operator_button(update: Update, context: "BotContext") -> States:
    query = update.callback_query
    effective_chat = update.effective_chat
    if query is None or query.data is None or effective_chat is None:
        return States.FOLLOW_NODE_OPERATOR
    await query.answer()

    texts = context.runtime.module_adapter.texts
    node_operator_id = query.data.removeprefix(FOLLOW_OPERATOR_PREFIX)
    valid_ids, invalid_ids = await _valid_node_operator_ids(context, [node_operator_id])
    if valid_ids and not invalid_ids:
        chat_storage = context.chat_storage()
        context.bot_storage.node_operator_chats.subscribe(node_operator_id, effective_chat.id)
        chat_storage.node_operators.follow(node_operator_id)
        await _edit_message_text(
            query,
            text=texts.NODE_OPERATOR_FOLLOWED.format(node_operator_id),
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(texts.BUTTON_BACK, callback_data=Callback.BACK.value)]]
            ),
        )
        return States.FOLLOW_NODE_OPERATOR

    await _edit_message_text(
        query,
        text=texts.NODE_OPERATOR_CANT_FOLLOW,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton(texts.BUTTON_BACK, callback_data=Callback.BACK.value)]]
        ),
    )
    return States.FOLLOW_NODE_OPERATOR


async def unfollow_node_operator(update: Update, context: "BotContext") -> States:
    query = update.callback_query
    if query is None:
        return States.UNFOLLOW_NODE_OPERATOR
    await query.answer()

    text, reply_markup = await _build_unfollow_prompt(context)
    await _edit_message_text(query, text=text, reply_markup=reply_markup)
    return States.UNFOLLOW_NODE_OPERATOR


async def unfollow_node_operator_message(update: Update, context: "BotContext") -> States:
    texts = context.runtime.module_adapter.texts
    keyboard = [InlineKeyboardButton(texts.BUTTON_BACK, callback_data=Callback.BACK.value)]
    message = update.message
    if message is None or not message.text:
        await reply_with_markup(
            update,
            context,
            texts.NODE_OPERATOR_CANT_UNFOLLOW,
            InlineKeyboardMarkup([keyboard]),
        )
        return States.UNFOLLOW_NODE_OPERATOR

    chat_storage = context.chat_storage()
    node_operator_ids = _parse_node_operator_ids(message.text)
    followed_ids = chat_storage.node_operators.ids()
    missing_ids = [
        node_operator_id
        for node_operator_id in node_operator_ids
        if not node_operator_id.isdigit() or node_operator_id not in followed_ids
    ]

    if node_operator_ids and not missing_ids:
        for node_operator_id in node_operator_ids:
            chat_storage.node_operators.unfollow(node_operator_id)
            context.bot_storage.node_operator_chats.unsubscribe(node_operator_id, message.chat_id)
        unfollowed_text = (
            texts.NODE_OPERATOR_UNFOLLOWED.format(node_operator_ids[0])
            if len(node_operator_ids) == 1
            else f"You are no longer following Node Operators {_format_node_operator_ids(node_operator_ids)}"
        )
        await reply_with_markup(
            update,
            context,
            unfollowed_text,
            InlineKeyboardMarkup([keyboard]),
        )
        return States.UNFOLLOW_NODE_OPERATOR

    invalid_text = f"\nInvalid: {_format_node_operator_ids(missing_ids)}" if missing_ids else ""
    await reply_with_markup(
        update,
        context,
        f"{texts.NODE_OPERATOR_CANT_UNFOLLOW}{invalid_text}",
        InlineKeyboardMarkup([keyboard]),
    )
    return States.UNFOLLOW_NODE_OPERATOR


async def unfollow_node_operator_page(update: Update, context: "BotContext") -> States:
    query = update.callback_query
    if query is None or query.data is None:
        return States.UNFOLLOW_NODE_OPERATOR
    await query.answer()

    page = int(query.data.removeprefix(UNFOLLOW_OPERATOR_PAGE_PREFIX))
    text, reply_markup = await _build_unfollow_prompt(context, page)
    await _edit_message_text(query, text=text, reply_markup=reply_markup)
    return States.UNFOLLOW_NODE_OPERATOR


async def unfollow_node_operator_button(update: Update, context: "BotContext") -> States:
    query = update.callback_query
    effective_chat = update.effective_chat
    if query is None or query.data is None or effective_chat is None:
        return States.UNFOLLOW_NODE_OPERATOR
    await query.answer()

    texts = context.runtime.module_adapter.texts
    node_operator_id = query.data.removeprefix(UNFOLLOW_OPERATOR_PREFIX)
    chat_storage = context.chat_storage()
    if chat_storage.node_operators.unfollow(node_operator_id):
        context.bot_storage.node_operator_chats.unsubscribe(node_operator_id, effective_chat.id)
        text = texts.NODE_OPERATOR_UNFOLLOWED.format(node_operator_id)
    else:
        text = texts.NODE_OPERATOR_CANT_UNFOLLOW

    await _edit_message_text(
        query,
        text=text,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton(texts.BUTTON_BACK, callback_data=Callback.BACK.value)]]
        ),
    )
    return States.UNFOLLOW_NODE_OPERATOR


async def followed_events(update: Update, context: "BotContext") -> States:
    query = update.callback_query
    if query is None:
        return States.FOLLOWED_EVENTS
    await query.answer()

    texts = context.runtime.module_adapter.texts
    keyboard = [InlineKeyboardButton(texts.BUTTON_BACK, callback_data=Callback.BACK.value)]
    await _edit_message_text(
        query,
        text=context.runtime.module_adapter.build_event_list_text(),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([keyboard]),
    )
    return States.FOLLOWED_EVENTS
