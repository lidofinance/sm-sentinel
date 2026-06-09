from aiogram.utils.formatting import Text, TextLink


def markdown(*args, **kwargs) -> str:
    return Text(*args, **kwargs).as_markdown()


def nl(x: int = 2) -> str:
    return "\n" * x


def read_field(value, field: str, index: int):
    if hasattr(value, field):
        return getattr(value, field)
    if isinstance(value, dict):
        return value[field]
    return value[index]


def transaction_footer(node_operator_line: str, tx_link: str) -> Text:
    return Text(nl(), node_operator_line, nl(1), TextLink("Transaction", url=tx_link))


def transaction_footer_tx_only(tx_link: str) -> Text:
    return Text(nl(), TextLink("Transaction", url=tx_link))


def block_footer(node_operator_line: str, block_links: list[tuple[str, str]]) -> Text:
    return Text(nl(), node_operator_line, nl(1), *_block_links(block_links))


def block_footer_tx_only(block_links: list[tuple[str, str]]) -> Text:
    return Text(nl(), *_block_links(block_links))


def _block_links(block_links: list[tuple[str, str]]) -> list:
    if len(block_links) == 1:
        label, url = block_links[0]
        return ["Block: ", TextLink(label, url=url)]

    first_label, first_url = block_links[0]
    last_label, last_url = block_links[-1]
    return [
        "Blocks: ",
        TextLink(first_label, url=first_url),
        " ... ",
        TextLink(last_label, url=last_url),
    ]
