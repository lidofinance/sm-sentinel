from enum import StrEnum

from aiogram.utils.formatting import Text, Bold, TextLink, Code
from web3.constants import ADDRESS_ZERO
from sentinel.config import get_config
from sentinel.modules.catalog import EventDefinition, build_grouped_event_list_text
from sentinel.modules.formatting import markdown, nl
from sentinel.modules.registry import RegisterEventMessage
from sentinel.modules.texts import BotTexts


COMMUNITY_EVENT_MESSAGES = {}


def register_event_message(event_name: str):
    return RegisterEventMessage(COMMUNITY_EVENT_MESSAGES, event_name)


class EventGroup(StrEnum):
    KEY_MANAGEMENT = "Key Management Events:"
    ADDRESS_AND_REWARD_CHANGES = "Address and Reward Changes:"
    SLASHING_AND_STEALING = "Slashing and Stealing Events:"
    WITHDRAWAL_AND_EXIT = "Withdrawal and Exit Requests:"
    COMMON_CSM = "Common CSM Events for all the Node Operators:"


GROUP_DESCRIPTIONS: dict[EventGroup, str] = {
    EventGroup.KEY_MANAGEMENT: "Changes related to keys and their status.",
    EventGroup.ADDRESS_AND_REWARD_CHANGES: "Changes or proposals regarding management and reward addresses.",
    EventGroup.SLASHING_AND_STEALING: "Alerts for validator status and delayed penalties.",
    EventGroup.WITHDRAWAL_AND_EXIT: "Notifications for exit requests and confirmation of exits.",
    EventGroup.COMMON_CSM: "",
}


COMMUNITY_EVENT_CATALOG: list[EventDefinition] = [
    EventDefinition(
        name="VettedSigningKeysCountDecreased",
        description="- 🚨 Uploaded invalid keys",
        group_title=EventGroup.KEY_MANAGEMENT,
    ),
    EventDefinition(
        name="DepositedSigningKeysCountChanged",
        description="- 🤩 Node Operator's keys received deposits",
        group_title=EventGroup.KEY_MANAGEMENT,
    ),
    EventDefinition(
        name="TotalSigningKeysCountChanged",
        description="- 👀 New keys uploaded or removed",
        group_title=EventGroup.KEY_MANAGEMENT,
    ),
    EventDefinition(
        name="KeyRemovalChargeApplied",
        description="- 🔑 Applied charge for key removal",
        group_title=EventGroup.KEY_MANAGEMENT,
    ),
    EventDefinition(
        name="KeyAllocatedBalanceChanged",
        description="- 👀 Key allocated bond balance changed",
        group_title=EventGroup.KEY_MANAGEMENT,
    ),
    EventDefinition(
        name="BondCurveSet",
        description="- ℹ️ Node Operator type changed",
        group_title=EventGroup.KEY_MANAGEMENT,
    ),
    EventDefinition(
        name="TargetValidatorsCountChanged",
        description="- 🚨 Target validators count changed",
        group_title=EventGroup.KEY_MANAGEMENT,
    ),
    EventDefinition(
        name="NodeOperatorManagerAddressChangeProposed",
        description="- ℹ️ New manager address proposed",
        group_title=EventGroup.ADDRESS_AND_REWARD_CHANGES,
    ),
    EventDefinition(
        name="NodeOperatorManagerAddressChanged",
        description="- ✅ Manager address changed",
        group_title=EventGroup.ADDRESS_AND_REWARD_CHANGES,
    ),
    EventDefinition(
        name="NodeOperatorRewardAddressChangeProposed",
        description="- ℹ️ New rewards address proposed",
        group_title=EventGroup.ADDRESS_AND_REWARD_CHANGES,
    ),
    EventDefinition(
        name="NodeOperatorRewardAddressChanged",
        description="- ✅ Rewards address changed",
        group_title=EventGroup.ADDRESS_AND_REWARD_CHANGES,
    ),
    EventDefinition(
        name="CustomRewardsClaimerSet",
        description="- ℹ️ Custom rewards claimer changed",
        group_title=EventGroup.ADDRESS_AND_REWARD_CHANGES,
    ),
    EventDefinition(
        name="FeeSplitsSet",
        description="- ℹ️ Reward fee splits changed",
        group_title=EventGroup.ADDRESS_AND_REWARD_CHANGES,
    ),
    EventDefinition(
        name="ELRewardsStealingPenaltyReported",
        description="- 🚨 Penalty for stealing EL rewards reported",
        group_title=EventGroup.SLASHING_AND_STEALING,
    ),
    EventDefinition(
        name="ELRewardsStealingPenaltySettled",
        description="- 🚨 EL rewards stealing penalty confirmed and applied",
        group_title=EventGroup.SLASHING_AND_STEALING,
    ),
    EventDefinition(
        name="ELRewardsStealingPenaltyCancelled",
        description="- 😮‍💨 Cancelled penalty for stealing EL rewards",
        group_title=EventGroup.SLASHING_AND_STEALING,
    ),
    EventDefinition(
        name="GeneralDelayedPenaltyReported",
        description="- 🚨 General delayed penalty reported",
        group_title=EventGroup.SLASHING_AND_STEALING,
    ),
    EventDefinition(
        name="GeneralDelayedPenaltySettled",
        description="- 🚨 General delayed penalty confirmed and applied",
        group_title=EventGroup.SLASHING_AND_STEALING,
    ),
    EventDefinition(
        name="GeneralDelayedPenaltyCancelled",
        description="- 😮‍💨 Cancelled general delayed penalty",
        group_title=EventGroup.SLASHING_AND_STEALING,
    ),
    EventDefinition(
        name="GeneralDelayedPenaltyCompensated",
        description="- ✅ General delayed penalty compensated",
        group_title=EventGroup.SLASHING_AND_STEALING,
    ),
    EventDefinition(
        name="ValidatorSlashingReported",
        description="- 🚨 Validator slashing reported",
        group_title=EventGroup.SLASHING_AND_STEALING,
    ),
    EventDefinition(
        name="BondDebtIncreased",
        description="- 🚨 Bond debt increased",
        group_title=EventGroup.SLASHING_AND_STEALING,
    ),
    EventDefinition(
        name="BondDebtCovered",
        description="- ✅ Bond debt covered",
        group_title=EventGroup.SLASHING_AND_STEALING,
    ),
    EventDefinition(
        name="ExpiredBondLockRemoved",
        description="- ✅ Expired bond lock removed",
        group_title=EventGroup.SLASHING_AND_STEALING,
    ),
    EventDefinition(
        name="ValidatorExitRequest",
        description="- 🚨 One of the validators requested to exit",
        group_title=EventGroup.WITHDRAWAL_AND_EXIT,
    ),
    EventDefinition(
        name="ValidatorExitDelayProcessed",
        description="- 🚨 Exit delay processed; penalty queued for withdrawal",
        group_title=EventGroup.WITHDRAWAL_AND_EXIT,
    ),
    EventDefinition(
        name="TriggeredExitFeeRecorded",
        description="- 🚨 Triggered exit fee recorded; penalty will be charged on exit",
        group_title=EventGroup.WITHDRAWAL_AND_EXIT,
    ),
    EventDefinition(
        name="StrikesPenaltyProcessed",
        description="- 🚨 Strikes penalty processed; validator exited for poor performance",
        group_title=EventGroup.WITHDRAWAL_AND_EXIT,
    ),
    EventDefinition(
        name="WithdrawalSubmitted",
        description="- 👀 Key withdrawal information submitted",
        group_title=EventGroup.WITHDRAWAL_AND_EXIT,
    ),
    EventDefinition(
        name="ValidatorWithdrawn",
        description="- 👀 Validator withdrawal confirmed",
        group_title=EventGroup.WITHDRAWAL_AND_EXIT,
    ),
    EventDefinition(
        name="DistributionLogUpdated",
        description="- 📈 New rewards distributed",
        group_title=EventGroup.COMMON_CSM,
    ),
    EventDefinition(
        name="Initialized",
        description="- 🎉 CSM v3 launched",
        group_title=EventGroup.COMMON_CSM,
    ),
]

COMMUNITY_EVENT_DESCRIPTIONS = {event.name: event.description for event in COMMUNITY_EVENT_CATALOG}


def build_event_list_text(catalog_events: set[str], module_ui_url: str | None = None) -> str:
    _ = module_ui_url
    return build_grouped_event_list_text(
        catalog_events=catalog_events,
        catalog=COMMUNITY_EVENT_CATALOG,
        group_descriptions=GROUP_DESCRIPTIONS,
    )


WELCOME_TEXT = (
    "Welcome to the CSM Sentinel! "
    + nl()
    + "Here you can follow Node Operators and receive notifications about their events."
    + nl()
    + "To get started, please use the buttons below."
    + nl()
)
START_BUTTON_FOLLOW = "Follow"
START_BUTTON_UNFOLLOW = "Unfollow"
START_BUTTON_EVENTS = "Events"
BUTTON_BACK = "Back"
START_BUTTON_ADMIN = "Admin"
ADMIN_BUTTON_SUBSCRIPTIONS = "Subscriptions"
ADMIN_MENU_TEXT = "Admin tools:"
ADMIN_BUTTON_BROADCAST = "Broadcast"
ADMIN_BROADCAST_MENU_TEXT = "Choose broadcast target:"
ADMIN_BROADCAST_ALL = "All subscribers"
ADMIN_BROADCAST_BY_NO = "By node operator"
ADMIN_BROADCAST_ENTER_MESSAGE_ALL = "Please enter the message to send to all subscribers:"
ADMIN_BROADCAST_ENTER_NO_IDS = "Please enter comma-separated node operator IDs (e.g., 1,2,3):"
ADMIN_BROADCAST_NO_IDS_INVALID = "No valid node operator IDs provided."
ADMIN_BROADCAST_CONFIRM_HINT = "Review the message below and confirm before broadcasting."
ADMIN_BROADCAST_PREVIEW_ALL = "Broadcast preview for all subscribers:"
ADMIN_BROADCAST_PREVIEW_SELECTED = "Broadcast preview for: {targets}"
BUTTON_SEND_BROADCAST = "Send broadcast"
ADMIN_PRIVATE_CHAT_REQUIRED = "Admin tools are only available in a private chat with the bot. Please open a private chat to continue."
NO_NEW_BLOCKS_ADMIN_ALERT = (
    "⚠️ No new blocks processed in the last {minutes} minutes. Latest block: {block}"
)
FOLLOW_NODE_OPERATOR_TEXT = (
    "Please enter one or more Node Operator IDs you want to follow, separated by commas:"
)
FOLLOW_NODE_OPERATOR_FOLLOWING = "Node Operator IDs you are following:\n{}" + nl(2)
UNFOLLOW_NODE_OPERATOR_TEXT = (
    "Please enter one or more Node Operator IDs you want to unfollow, separated by commas:"
)
UNFOLLOW_NODE_OPERATOR_NOT_FOLLOWING = "You are not following any Node Operators."
UNFOLLOW_NODE_OPERATOR_FOLLOWING = "Node Operator IDs you are following:\n{}" + nl(2)
NODE_OPERATOR_FOLLOWED = "You are now following Node Operator #{}"
NODE_OPERATOR_CANT_FOLLOW = "Invalid Node Operator id. Please enter the correct id."
NODE_OPERATOR_UNFOLLOWED = "You are no longer following Node Operator #{}"
NODE_OPERATOR_CANT_UNFOLLOW = (
    "Can't unfollow the Node Operator you are not following. \nPlease enter the correct id."
)


CommunityTexts = BotTexts(
    WELCOME_TEXT=WELCOME_TEXT,
    START_BUTTON_FOLLOW=START_BUTTON_FOLLOW,
    START_BUTTON_UNFOLLOW=START_BUTTON_UNFOLLOW,
    START_BUTTON_EVENTS=START_BUTTON_EVENTS,
    BUTTON_BACK=BUTTON_BACK,
    START_BUTTON_ADMIN=START_BUTTON_ADMIN,
    ADMIN_BUTTON_SUBSCRIPTIONS=ADMIN_BUTTON_SUBSCRIPTIONS,
    ADMIN_MENU_TEXT=ADMIN_MENU_TEXT,
    ADMIN_BUTTON_BROADCAST=ADMIN_BUTTON_BROADCAST,
    ADMIN_BROADCAST_MENU_TEXT=ADMIN_BROADCAST_MENU_TEXT,
    ADMIN_BROADCAST_ALL=ADMIN_BROADCAST_ALL,
    ADMIN_BROADCAST_BY_NO=ADMIN_BROADCAST_BY_NO,
    ADMIN_BROADCAST_ENTER_MESSAGE_ALL=ADMIN_BROADCAST_ENTER_MESSAGE_ALL,
    ADMIN_BROADCAST_ENTER_NO_IDS=ADMIN_BROADCAST_ENTER_NO_IDS,
    ADMIN_BROADCAST_NO_IDS_INVALID=ADMIN_BROADCAST_NO_IDS_INVALID,
    ADMIN_BROADCAST_CONFIRM_HINT=ADMIN_BROADCAST_CONFIRM_HINT,
    ADMIN_BROADCAST_PREVIEW_ALL=ADMIN_BROADCAST_PREVIEW_ALL,
    ADMIN_BROADCAST_PREVIEW_SELECTED=ADMIN_BROADCAST_PREVIEW_SELECTED,
    BUTTON_SEND_BROADCAST=BUTTON_SEND_BROADCAST,
    ADMIN_PRIVATE_CHAT_REQUIRED=ADMIN_PRIVATE_CHAT_REQUIRED,
    NO_NEW_BLOCKS_ADMIN_ALERT=NO_NEW_BLOCKS_ADMIN_ALERT,
    FOLLOW_NODE_OPERATOR_TEXT=FOLLOW_NODE_OPERATOR_TEXT,
    FOLLOW_NODE_OPERATOR_FOLLOWING=FOLLOW_NODE_OPERATOR_FOLLOWING,
    UNFOLLOW_NODE_OPERATOR_TEXT=UNFOLLOW_NODE_OPERATOR_TEXT,
    UNFOLLOW_NODE_OPERATOR_NOT_FOLLOWING=UNFOLLOW_NODE_OPERATOR_NOT_FOLLOWING,
    UNFOLLOW_NODE_OPERATOR_FOLLOWING=UNFOLLOW_NODE_OPERATOR_FOLLOWING,
    NODE_OPERATOR_FOLLOWED=NODE_OPERATOR_FOLLOWED,
    NODE_OPERATOR_CANT_FOLLOW=NODE_OPERATOR_CANT_FOLLOW,
    NODE_OPERATOR_UNFOLLOWED=NODE_OPERATOR_UNFOLLOWED,
    NODE_OPERATOR_CANT_UNFOLLOW=NODE_OPERATOR_CANT_UNFOLLOW,
    build_event_list_text=build_event_list_text,
)


EVENT_EMITS = "Event {} emitted with data: \n{}"


def event_message_footer(no_id, link) -> Text:
    return Text(nl(), f"nodeOperatorId: {no_id}\n", TextLink("Transaction", url=link))


def event_message_footer_tx_only(link) -> Text:
    return Text(nl(), TextLink("Transaction", url=link))


@register_event_message("DepositedSigningKeysCountChanged")
def deposited_signing_keys_count_changed(x):
    return markdown("🤩 ", Bold("Keys were deposited!"), nl(), f"New deposited keys count: {x}")


@register_event_message("ELRewardsStealingPenaltyCancelled")
def el_rewards_stealing_penalty_cancelled(remaining):
    return markdown(
        "😮‍💨 ",
        Bold("EL rewards stealing penalty cancelled"),
        nl(),
        "Remaining amount: ",
        Code(remaining),
    )


@register_event_message("ELRewardsStealingPenaltyReported")
def el_rewards_stealing_penalty_reported(rewards, block_link):
    return markdown(
        "🚨 ",
        Bold("Penalty for stealing EL rewards reported"),
        nl(),
        Code(rewards),
        " rewards from the ",
        TextLink("block", url=block_link),
        " were transferred to the wrong EL address",
        nl(1),
        "See the ",
        TextLink("guide", url="https://docs.lido.fi/staking-modules/csm/guides/mev-stealing"),
        " for more details",
    )


@register_event_message("ELRewardsStealingPenaltySettled")
def el_rewards_stealing_penalty_settled(burnt):
    return markdown(
        "🚨 ",
        Bold("EL rewards stealing penalty confirmed and applied"),
        nl(),
        Code(burnt),
        " burnt from bond",
    )


@register_event_message("GeneralDelayedPenaltyCancelled")
def general_delayed_penalty_cancelled(remaining):
    return markdown(
        "😮‍💨 ",
        Bold("General delayed penalty cancelled"),
        nl(),
        "Remaining amount: ",
        Code(remaining),
    )


@register_event_message("GeneralDelayedPenaltyCompensated")
def general_delayed_penalty_compensated(amount):
    return markdown(
        "✅ ",
        Bold("General delayed penalty compensated"),
        nl(),
        "Compensated amount: ",
        Code(amount),
    )


@register_event_message("GeneralDelayedPenaltyReported")
def general_delayed_penalty_reported(amount, additional_fine, details):
    return markdown(
        "🚨 ",
        Bold("General delayed penalty reported"),
        nl(),
        "Penalty amount: ",
        Code(amount),
        nl(1),
        "Additional fine: ",
        Code(additional_fine),
        nl(1),
        "Details: ",
        Code(details),
    )


@register_event_message("GeneralDelayedPenaltySettled")
def general_delayed_penalty_settled(amount):
    return markdown(
        "🚨 ",
        Bold("General delayed penalty confirmed and applied"),
        nl(),
        "Settled amount: ",
        Code(amount),
    )


@register_event_message("ValidatorSlashingReported")
def validator_slashing_reported(key, key_url, key_index):
    return markdown(
        "🚨 ",
        Bold("Validator slashing reported"),
        nl(),
        "Validator: ",
        TextLink(key, url=key_url),
        nl(1),
        "Key index: ",
        Code(str(key_index)),
        nl(),
        "Review the validator status and expected bond impact.",
    )


@register_event_message("BondDebtIncreased")
def bond_debt_increased(amount):
    return markdown(
        "🚨 ",
        Bold("Bond debt increased"),
        nl(),
        "Debt increase: ",
        Code(amount),
        nl(),
        "Future rewards or bond changes may be used to cover this debt.",
    )


@register_event_message("BondDebtCovered")
def bond_debt_covered(amount):
    return markdown("✅ ", Bold("Bond debt covered"), nl(), "Covered amount: ", Code(amount))


@register_event_message("CustomRewardsClaimerSet")
def custom_rewards_claimer_set(rewards_claimer, previous_rewards_claimer=None):
    if rewards_claimer == ADDRESS_ZERO:
        return markdown(
            "ℹ️ ",
            Bold("Custom rewards claimer removed"),
            nl(),
            "Custom rewards claimer was removed for this Node Operator.",
        )
    title = (
        "Custom rewards claimer set"
        if previous_rewards_claimer == ADDRESS_ZERO
        else "Custom rewards claimer changed"
    )
    return markdown(
        "ℹ️ ",
        Bold(title),
        nl(),
        "Rewards claimer: ",
        Code(rewards_claimer),
    )


def _fee_split_value(fee_split, field: str, index: int):
    if hasattr(fee_split, field):
        return getattr(fee_split, field)
    if isinstance(fee_split, dict):
        return fee_split[field]
    return fee_split[index]


def _format_fee_splits(fee_splits) -> str:
    if not fee_splits:
        return "none"
    return "; ".join(
        f"{_fee_split_value(fee_split, 'recipient', 0)}: {_fee_split_value(fee_split, 'share', 1)}"
        for fee_split in fee_splits
    )


@register_event_message("FeeSplitsSet")
def fee_splits_set(fee_splits):
    cfg = get_config()
    return markdown(
        "ℹ️ ",
        Bold("Fee splits changed"),
        nl(),
        "Fee splits: ",
        Code(_format_fee_splits(fee_splits)),
        nl(1),
        "Review the current rewards setup in the ",
        TextLink("CSM UI", url=cfg.module_ui_url or ""),
    )


@register_event_message("ExpiredBondLockRemoved")
def expired_bond_lock_removed():
    return markdown(
        "✅ ",
        Bold("Expired bond lock removed"),
        nl(),
        "More bond may now be available for normal operations.",
    )


@register_event_message("KeyAllocatedBalanceChanged")
def key_allocated_balance_changed(key_index, new_total):
    return markdown(
        "👀 ",
        Bold("Key balance increased"),
        nl(),
        "Key index: ",
        Code(str(key_index)),
        nl(1),
        "New allocated balance: ",
        Code(new_total),
    )


@register_event_message("KeyRemovalChargeApplied")
def key_removal_charge_applied(amount):
    return markdown(
        "🔑 ", Bold("Key removal charge applied"), nl(), "Amount of charge: ", Code(amount)
    )


@register_event_message("BondCurveSet")
def bond_curve_set(curve_id: int):
    cfg = get_config()
    return markdown(
        "ℹ️ ",
        Bold("Node Operator type changed"),
        nl(),
        "New type id: ",
        Code(str(curve_id)),
        nl(1),
        "Operational requirements may now differ. Check the ",
        TextLink("CSM UI", url=cfg.module_ui_url or ""),
        " for updated guidance",
    )


@register_event_message("NodeOperatorManagerAddressChangeProposed")
def node_operator_manager_address_change_proposed(address):
    if address == ADDRESS_ZERO:
        return markdown("ℹ️ ", Bold("Proposed manager address revoked"))
    else:
        return markdown(
            "ℹ️ ",
            Bold("New manager address proposed"),
            nl(),
            "Proposed address: ",
            Code(address),
            nl(1),
            "To complete the change, the Node Operator must confirm it from the new address.",
        )


@register_event_message("NodeOperatorManagerAddressChanged")
def node_operator_manager_address_changed(address):
    return markdown("✅ ", Bold("Manager address changed"), nl(), "New address: ", Code(address))


@register_event_message("NodeOperatorRewardAddressChangeProposed")
def node_operator_reward_address_change_proposed(address):
    if address == ADDRESS_ZERO:
        return markdown("ℹ️ ", Bold("Proposed reward address revoked"))
    else:
        return markdown(
            "ℹ️ ",
            Bold("New rewards address proposed"),
            nl(),
            "Proposed address: ",
            Code(address),
            nl(1),
            "To complete the change, the Node Operator must confirm it from the new address.",
        )


@register_event_message("NodeOperatorRewardAddressChanged")
def node_operator_reward_address_changed(address):
    return markdown("✅ ", Bold("Rewards address changed"), nl(), "New address: ", Code(address))


@register_event_message("VettedSigningKeysCountDecreased")
def vetted_signing_keys_count_decreased():
    cfg = get_config()
    return markdown(
        "🚨 ",
        Bold("Vetted keys count decreased"),
        nl(),
        "Consider removing invalid keys. Check ",
        TextLink("CSM UI", url=cfg.module_ui_url or ""),
        " for more details",
    )


@register_event_message("WithdrawalSubmitted")
def withdrawal_submitted(key, key_url, amount):
    cfg = get_config()
    return markdown(
        "👀 ",
        Bold("Information about validator withdrawal has been submitted"),
        nl(),
        "Withdrawn key: ",
        TextLink(key, url=key_url),
        " with exit balance: ",
        Code(amount),
        nl(),
        "Check the amount of the bond released at ",
        TextLink("CSM UI", url=cfg.module_ui_url or ""),
    )


@register_event_message("ValidatorWithdrawn")
def validator_withdrawn(key, key_url, balance, slashing_penalty):
    parts: list = [
        "👀 ",
        Bold("Validator withdrawal confirmed"),
        nl(),
        "Withdrawn key: ",
        TextLink(key, url=key_url),
        nl(1),
        "Exit balance: ",
        Code(balance),
    ]
    if slashing_penalty not in {"0 ether", "0 wei"}:
        parts.extend([nl(1), "Slashing penalty: ", Code(slashing_penalty)])
    return markdown(*parts)


@register_event_message("TotalSigningKeysCountChanged")
def total_signing_keys_count_changed(count, count_before):
    if count > count_before:
        return markdown(
            "👀 ",
            Bold("New keys uploaded"),
            nl(),
            "Keys count: ",
            Code(f"{count_before} -> {count}"),
        )
    else:
        return markdown("🚨 ", Bold("Key removed"), nl(), "Total keys: ", Code(count))


@register_event_message("ValidatorExitRequest")
def validator_exit_request(key, key_url, request_date, exit_until):
    return markdown(
        "🚨 ",
        Bold("Validator exit requested"),
        nl(),
        "Make sure to exit the key before ",
        exit_until,
        nl(1),
        "Check the ",
        TextLink(
            "Exiting CSM validators",
            url="https://dvt-homestaker.stakesaurus.com/bonded-validators-setup/lido-csm/exiting-csm-validators",
        ),
        " guide for more details",
        nl(1),
        "Requested key: ",
        TextLink(key, url=key_url),
        nl(1),
        "Request date: ",
        Code(request_date),
    )


@register_event_message("ValidatorExitDelayProcessed")
def validator_exit_delay_processed(key, key_url, penalty):
    return markdown(
        "🚨 ",
        Bold("Validator exit delay processed"),
        nl(),
        "Validator: ",
        TextLink(key, url=key_url),
        nl(1),
        "Delay penalty: ",
        Code(penalty),
        nl(),
        "Penalty will be applied when the validator exits",
    )


@register_event_message("TriggeredExitFeeRecorded")
def triggered_exit_fee_recorded(key, key_url, recorded_fee):
    return markdown(
        "🚨 ",
        Bold("Triggerable Withdrawal fee recorded"),
        nl(),
        "Validator: ",
        TextLink(key, url=key_url),
        nl(1),
        "Fee to be charged on exit: ",
        Code(recorded_fee),
        nl(),
        "Exit fee will be applied when the validator exits.",
    )


@register_event_message("StrikesPenaltyProcessed")
def strikes_penalty_processed(key, key_url, penalty):
    return markdown(
        "🚨 ",
        Bold("Strikes penalty processed"),
        nl(),
        "Validator: ",
        TextLink(key, url=key_url),
        nl(1),
        "Penalty amount: ",
        Code(penalty),
        nl(),
        "Penalty will be charged when the validator withdraws.",
    )


@register_event_message("DistributionLogUpdated")
def distribution_data_updated(
    node_operator_id: int | None = None, striked_validators: list | None = None
):
    cfg = get_config()
    base_message = Text(
        "📈 ",
        Bold("Rewards distributed!"),
        nl(),
        "Follow the ",
        TextLink("CSM UI", url=cfg.module_ui_url or ""),
        " to check new claimable rewards.",
    )

    if node_operator_id is not None and striked_validators:
        return Text(
            base_message,
            Text(
                nl(),
                "⚠️ ",
                Bold("Strikes detected for your validators"),
                nl(),
                "Node Operator ID: ",
                Code(str(node_operator_id)),
                nl(1),
                "Validators with strikes: ",
                Code(len(striked_validators)),
                nl(1),
            ),
        ).as_markdown()

    return base_message.as_markdown()


@register_event_message("TargetValidatorsCountChanged")
def target_validators_count_changed(mode_before, limit_before, mode_after, limit_after):
    match (mode_before, limit_before, mode_after, limit_after):
        case (_, _, 1, 0):
            return markdown(
                "🚨 ",
                Bold("Target validators count changed"),
                nl(),
                "The limit has been set to zero.",
                nl(1),
                "All keys will be requested to exit first.",
            )
        case (_, _, 2, 0):
            return markdown(
                "🚨 ",
                Bold("Target validators count changed"),
                nl(),
                "The limit has been set to zero.",
                nl(1),
                "All keys will be requested to exit immediately.",
            )
        case (1, _, 1, limit_after) if limit_after < limit_before:
            return markdown(
                "🚨 ",
                Bold("Target validators count changed"),
                nl(),
                f"The limit has been decreased from {limit_before} to {limit_after}.",
                nl(1),
                f"{limit_before - limit_after} more key(s) will be requested to exit first.",
            )
        case (2, _, 2, limit_after) if limit_after < limit_before:
            return markdown(
                "🚨 ",
                Bold("Target validators count changed"),
                nl(),
                f"The limit has been decreased from {limit_before} to {limit_after}.",
                nl(1),
                f"{limit_before - limit_after} more key(s) will be requested to exit immediately.",
            )
        case (_, _, 1, _):
            return markdown(
                "🚨 ",
                Bold("Target validators count changed"),
                nl(),
                f"The limit has been set to {limit_after}.",
                nl(1),
                f"{limit_after} keys will be requested to exit first.",
            )
        case (_, _, 2, _):
            return markdown(
                "🚨 ",
                Bold("Target validators count changed"),
                nl(),
                f"The limit has been set to {limit_after}.",
                nl(1),
                f"{limit_after} keys will be requested to exit immediately.",
            )
        case (_, _, 0, _):
            return markdown(
                "🚨 ",
                Bold("Target validators count changed"),
                nl(),
                "The limit has been set to zero. No keys will be requested to exit.",
            )
        case _:
            # is there any case for this?
            return markdown(
                "🚨 ",
                Bold("Target validators count changed"),
                nl(),
                f"Mode changed from {mode_before} to {mode_after}.",
                nl(1),
                f"Limit changed from {limit_before} to {limit_after}.",
            )


@register_event_message("Initialized")
def initialized():
    cfg = get_config()
    return markdown(
        "🎉 ",
        Bold("CSM v3 is live!"),
        nl(),
        "Check the ",
        TextLink("CSM UI", url=cfg.module_ui_url or ""),
        " for updated operator workflows and current module details.",
    )
