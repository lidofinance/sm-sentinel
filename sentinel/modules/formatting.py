from aiogram.utils.formatting import Text, TextLink


def markdown(*args, **kwargs) -> str:
    return Text(*args, **kwargs).as_markdown()


def nl(x: int = 2) -> str:
    return "\n" * x


def event_footer(node_operator_id: int | None, tx_link: str) -> str:
    if node_operator_id is None:
        return Text(nl(), TextLink("Transaction", url=tx_link)).as_markdown()
    return Text(
        nl(),
        f"nodeOperatorId: {node_operator_id}\n",
        TextLink("Transaction", url=tx_link),
    ).as_markdown()


def read_field(value, field: str, index: int):
    if hasattr(value, field):
        return getattr(value, field)
    if isinstance(value, dict):
        return value[field]
    return value[index]
