from aiogram.utils.formatting import Text

from sentinel.modules.texts import BotTexts


CURATED_EVENT_MESSAGES = {}
CURATED_EVENT_DESCRIPTIONS = {}


def build_event_list_text(catalog_events: set[str], module_ui_url: str | None = None) -> str:
    _ = catalog_events
    _ = module_ui_url
    return Text("No Curated Module events are configured yet.").as_markdown()


CuratedTexts = BotTexts(
    WELCOME_TEXT=(
        "Welcome to the Curated Module Sentinel! "
        "\n\n"
        "Here you can follow operators and receive notifications about their events."
        "\n\n"
        "To get started, please use the buttons below."
        "\n"
    ),
    START_BUTTON_FOLLOW="Follow",
    START_BUTTON_UNFOLLOW="Unfollow",
    START_BUTTON_EVENTS="Events",
    BUTTON_BACK="Back",
    START_BUTTON_ADMIN="Admin",
    ADMIN_BUTTON_SUBSCRIPTIONS="Subscriptions",
    ADMIN_MENU_TEXT="Admin tools:",
    ADMIN_BUTTON_BROADCAST="Broadcast",
    ADMIN_BROADCAST_MENU_TEXT="Choose broadcast target:",
    ADMIN_BROADCAST_ALL="All subscribers",
    ADMIN_BROADCAST_BY_NO="By operator",
    ADMIN_BROADCAST_ENTER_MESSAGE_ALL="Please enter the message to send to all subscribers:",
    ADMIN_BROADCAST_ENTER_NO_IDS="Please enter comma-separated operator IDs (e.g., 1,2,3):",
    ADMIN_BROADCAST_NO_IDS_INVALID="No valid operator IDs provided.",
    ADMIN_BROADCAST_CONFIRM_HINT="Review the message below and confirm before broadcasting.",
    ADMIN_BROADCAST_PREVIEW_ALL="Broadcast preview for all subscribers:",
    ADMIN_BROADCAST_PREVIEW_SELECTED="Broadcast preview for: {targets}",
    BUTTON_SEND_BROADCAST="Send broadcast",
    ADMIN_PRIVATE_CHAT_REQUIRED=(
        "Admin tools are only available in a private chat with the bot. "
        "Please open a private chat to continue."
    ),
    NO_NEW_BLOCKS_ADMIN_ALERT=(
        "No new blocks processed in the last {minutes} minutes. Latest block: {block}"
    ),
    FOLLOW_NODE_OPERATOR_TEXT="Please enter the operator id you want to follow:",
    FOLLOW_NODE_OPERATOR_FOLLOWING="Operators you are following: {}\n",
    UNFOLLOW_NODE_OPERATOR_TEXT="Please enter the operator id you want to unfollow:",
    UNFOLLOW_NODE_OPERATOR_NOT_FOLLOWING="You are not following any operators.",
    UNFOLLOW_NODE_OPERATOR_FOLLOWING="Operators you are following: {}\n",
    NODE_OPERATOR_FOLLOWED="You are now following operator #{}",
    NODE_OPERATOR_CANT_FOLLOW="Invalid operator id. Please enter the correct id.",
    NODE_OPERATOR_UNFOLLOWED="You are no longer following operator #{}",
    NODE_OPERATOR_CANT_UNFOLLOW=(
        "Can't unfollow an operator you are not following. Please enter the correct id."
    ),
    build_event_list_text=build_event_list_text,
)
