from unittest.mock import MagicMock

import pytest
from telegram.ext import ApplicationBuilder

from sentinel.app.application import SentinelApplication
from sentinel.app.runtime import BotRuntime


def test_sentinel_application_exposes_attached_runtime():
    application = (
        ApplicationBuilder().application_class(SentinelApplication).token("123:TEST").build()
    )
    runtime = MagicMock(spec=BotRuntime)

    assert isinstance(application, SentinelApplication)
    with pytest.raises(RuntimeError, match="Bot runtime is not attached"):
        _ = application.runtime

    application.attach_runtime(runtime)

    assert application.runtime is runtime
