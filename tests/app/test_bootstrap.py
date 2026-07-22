import pytest

from sentinel.app.bootstrap import _resolve_backfill_start_block


@pytest.mark.parametrize(
    ("configured_block", "persisted_block", "expected"),
    [
        (None, None, 0),
        (None, 0, 0),
        (None, "0x0", 0),
        (None, 42, 43),
        (100, None, 100),
        (0, 42, 0),
    ],
)
def test_resolve_backfill_start_block(
    configured_block: int | None,
    persisted_block: object | None,
    expected: int,
):
    assert _resolve_backfill_start_block(configured_block, persisted_block) == expected
