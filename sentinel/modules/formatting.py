from aiogram.utils.formatting import Text


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
