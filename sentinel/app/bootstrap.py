import asyncio
import logging
from pathlib import Path
from contextlib import suppress

from telegram.ext import AIORateLimiter, ApplicationBuilder, ContextTypes
from web3 import AsyncWeb3, WebSocketProvider

from sentinel.app.context import BotContext
from sentinel.app.health import HealthServer, HealthState
from sentinel.app.module_adapter import build_module_adapter_from_config
from sentinel.app.runtime import BotRuntime, attach_runtime
from sentinel.app.storage import create_persistence
from sentinel.config import get_config, get_healthcheck_bind_from_env
from sentinel.utils import normalize_block_number
from sentinel.handlers.errors import error_handler, build_error_callback
from sentinel.services.subscription import TelegramSubscription
from sentinel.events import EventMessages
from sentinel.jobs import JobContext

logger = logging.getLogger(__name__)


def create_runtime() -> BotRuntime:
    health = HealthState()
    health_host, health_port = get_healthcheck_bind_from_env()
    health_server = HealthServer(health, host=health_host, port=health_port)
    health_server.start()

    try:
        cfg = get_config()
        if cfg.token is None:
            raise RuntimeError("TOKEN must be configured")

        storage_path = Path(cfg.filestorage_path)
        storage_path.mkdir(parents=True, exist_ok=True)

        persistence = create_persistence(storage_path)

        context_types = ContextTypes(context=BotContext)

        application = (
            ApplicationBuilder()
            .token(cfg.token)
            .context_types(context_types)
            .persistence(persistence)
            .rate_limiter(AIORateLimiter(max_retries=5))
            .build()
        )

        persistent_provider = AsyncWeb3(
            WebSocketProvider(cfg.web3_socket_provider, max_connection_retries=-1)
        )
        rpc_provider = AsyncWeb3(
            WebSocketProvider(cfg.web3_socket_provider, max_connection_retries=-1)
        )
        backfill_provider = AsyncWeb3(
            WebSocketProvider(cfg.web3_socket_provider, max_connection_retries=-1)
        )

        module_adapter = build_module_adapter_from_config(cfg, rpc_provider)

        async def switch_csm_version(csm_version: int) -> None:
            await subscription.handle_csm_version_changed(csm_version)

        event_messages = EventMessages(rpc_provider, module_adapter, switch_csm_version)
        subscription = TelegramSubscription(
            persistent_provider,
            application,
            event_messages,
            health=health,
            backfill_w3=backfill_provider,
            contract_abis=module_adapter.contract_abis,
        )
        job_context = JobContext(subscription)

        runtime = BotRuntime(
            config=cfg,
            application=application,
            subscription=subscription,
            event_messages=event_messages,
            job_context=job_context,
            module_adapter=module_adapter,
            health=health,
            health_server=health_server,
        )
        attach_runtime(runtime)
        return runtime
    except Exception as exc:
        health.mark_fatal_error(exc)
        health_server.stop()
        raise


async def _run(runtime: BotRuntime) -> None:
    application = runtime.application
    subscription = runtime.subscription
    job_context = runtime.job_context
    cfg = runtime.config

    updater = application.updater
    if updater is None:
        raise RuntimeError("Application updater is not configured; cannot start polling")

    await application.initialize()
    await application.start()
    application.add_error_handler(error_handler)

    subscription.ensure_state_containers()

    application.bot_data["admin_ids"] = cfg.admin_ids

    block_from = (
        cfg.block_from
        if cfg.block_from is not None
        else normalize_block_number(application.bot_data.get("block"))
    )

    logger.info(
        "Bot started. Latest processed block number: %s",
        block_from,
    )

    heartbeat_task = asyncio.create_task(runtime.health.heartbeat_loop())
    subscription_task: asyncio.Task[None] | None = None
    try:
        error_callback = build_error_callback(application)
        await updater.start_polling(error_callback=error_callback)
        runtime.health.mark_polling_started()
        subscription.setup_signal_handlers(asyncio.get_running_loop())

        # Start the live subscription first, then backfill up to a post-subscribe head.
        # This avoids missing blocks mined while historical catch-up is running.
        subscription_task = asyncio.create_task(subscription.subscribe())
        await subscription.wait_until_subscribed()
        runtime.health.mark_startup_complete()

        if block_from:
            catchup_head = await subscription.get_block_number()
            subscription.start_catchup(catchup_head)
            await subscription.process_blocks_from(block_from, end_block=catchup_head)
            subscription.finish_catchup()

        await job_context.schedule(application)

        await subscription_task
    except asyncio.CancelledError:  # pragma: no cover - shutdown guard
        pass
    except Exception as exc:
        runtime.health.mark_fatal_error(exc)
        raise
    finally:
        runtime.health.mark_shutdown_requested()
        # Ensure shutdown never hangs on unexpected failures (e.g., subscription startup timeouts).
        subscription.request_shutdown()
        if subscription_task is not None and not subscription_task.done():
            subscription_task.cancel()
            with suppress(asyncio.CancelledError):
                await subscription_task
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task
        await subscription.shutdown()
        await updater.stop()
        await application.stop()
        await application.shutdown()
        runtime.health_server.stop()


def run(runtime: BotRuntime) -> None:
    asyncio.run(_run(runtime))
