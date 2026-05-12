from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode

from sentinel.handlers.state import Callback, States
from sentinel.handlers.tracking import add_user_if_required
from sentinel.handlers.utils import is_admin, reply_with_markup

if TYPE_CHECKING:
    from sentinel.app.context import BotContext


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
            ", ".join(f"#{x}" for x in node_operator_ids)
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
            ", ".join(f"#{x}" for x in node_operator_ids)
        )

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text=text,
        reply_markup=reply_markup,
    )
    return States.WELCOME


async def follow_node_operator(update: Update, context: "BotContext") -> States:
    query = update.callback_query
    if query is None:
        return States.FOLLOW_NODE_OPERATOR
    await query.answer()

    texts = context.runtime.module_adapter.texts
    chat_storage = context.chat_storage()
    node_operator_ids = sorted(chat_storage.node_operators.ids())
    keyboard = [InlineKeyboardButton(texts.BUTTON_BACK, callback_data=Callback.BACK.value)]
    text = texts.FOLLOW_NODE_OPERATOR_TEXT
    if node_operator_ids:
        text = (
            texts.FOLLOW_NODE_OPERATOR_FOLLOWING.format(
                ", ".join(f"#{x}" for x in node_operator_ids)
            )
            + text
        )
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup([keyboard]))
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

    node_operator_id = message.text
    if node_operator_id.startswith("#"):
        node_operator_id = node_operator_id[1:]

    if node_operator_id.isdigit() and await context.runtime.module_adapter.is_valid_operator_id(
        int(node_operator_id)
    ):
        chat_storage = context.chat_storage()
        context.bot_storage.node_operator_chats.subscribe(node_operator_id, message.chat_id)
        chat_storage.node_operators.follow(node_operator_id)
        await reply_with_markup(
            update,
            context,
            texts.NODE_OPERATOR_FOLLOWED.format(node_operator_id),
            InlineKeyboardMarkup([keyboard]),
        )
        return States.FOLLOW_NODE_OPERATOR

    await reply_with_markup(
        update,
        context,
        texts.NODE_OPERATOR_CANT_FOLLOW,
        InlineKeyboardMarkup([keyboard]),
    )
    return States.FOLLOW_NODE_OPERATOR


async def unfollow_node_operator(update: Update, context: "BotContext") -> States:
    query = update.callback_query
    if query is None:
        return States.UNFOLLOW_NODE_OPERATOR
    await query.answer()

    texts = context.runtime.module_adapter.texts
    chat_storage = context.chat_storage()
    node_operator_ids = sorted(chat_storage.node_operators.ids())
    keyboard = [InlineKeyboardButton(texts.BUTTON_BACK, callback_data=Callback.BACK.value)]
    if node_operator_ids:
        text = texts.UNFOLLOW_NODE_OPERATOR_FOLLOWING.format(
            ", ".join(f"#{x}" for x in node_operator_ids)
        )
        text += texts.UNFOLLOW_NODE_OPERATOR_TEXT
    else:
        text = texts.UNFOLLOW_NODE_OPERATOR_NOT_FOLLOWING
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup([keyboard]))
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

    node_operator_id = message.text
    if node_operator_id.startswith("#"):
        node_operator_id = node_operator_id[1:]
    chat_storage = context.chat_storage()
    if chat_storage.node_operators.unfollow(node_operator_id):
        context.bot_storage.node_operator_chats.unsubscribe(node_operator_id, message.chat_id)
        await reply_with_markup(
            update,
            context,
            texts.NODE_OPERATOR_UNFOLLOWED.format(node_operator_id),
            InlineKeyboardMarkup([keyboard]),
        )
        return States.UNFOLLOW_NODE_OPERATOR

    await reply_with_markup(
        update,
        context,
        texts.NODE_OPERATOR_CANT_UNFOLLOW,
        InlineKeyboardMarkup([keyboard]),
    )
    return States.UNFOLLOW_NODE_OPERATOR


async def followed_events(update: Update, context: "BotContext") -> States:
    query = update.callback_query
    if query is None:
        return States.FOLLOWED_EVENTS
    await query.answer()

    texts = context.runtime.module_adapter.texts
    keyboard = [InlineKeyboardButton(texts.BUTTON_BACK, callback_data=Callback.BACK.value)]
    await query.edit_message_text(
        text=context.runtime.module_adapter.build_event_list_text(),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([keyboard]),
    )
    return States.FOLLOWED_EVENTS
