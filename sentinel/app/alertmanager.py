"""Authenticated Alertmanager HTTP receiver."""

import asyncio
import hashlib
import json
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from http import HTTPStatus

from aiohttp import hdrs, web
from sqlalchemy.exc import SQLAlchemyError

from sentinel.alertmanager import InvalidAlertmanagerWebhook, parse_alertmanager_webhook
from sentinel.alertmanager_auth import AlertmanagerAuthenticator, AlertmanagerSource
from sentinel.app.alertmanager_storage import AlertmanagerOutboxFull
from sentinel.metrics.alertmanager import AlertmanagerMetrics
from sentinel.services.alertmanager import (
    AlertmanagerBatchTooLarge,
    AlertmanagerDeliveryService,
    AlertmanagerScopeMismatch,
    AlertmanagerScopeUnavailable,
)

logger = logging.getLogger(__name__)
MAX_WEBHOOK_BYTES = 1024 * 1024
REQUEST_BODY_TIMEOUT_SECONDS = 5
MAX_REQUESTS_PER_SOURCE_PER_MINUTE = 120
REQUEST_RATE_WINDOW_SECONDS = 60
MAX_IN_FLIGHT_PER_SOURCE = 4
MAX_IN_FLIGHT_REQUESTS = 16
SOURCE_ID_KEY = web.RequestKey("alertmanager.source_id", str)


class AlertmanagerWebhookServer:
    def __init__(
        self,
        *,
        sources: tuple[AlertmanagerSource, ...],
        metrics: AlertmanagerMetrics,
        service: AlertmanagerDeliveryService,
        host: str,
        port: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._authenticator = AlertmanagerAuthenticator(sources)
        self._metrics = metrics
        self._clock = clock
        self._request_windows: dict[str, deque[float]] = {
            source_id: deque() for source_id in self._authenticator.source_ids
        }
        self._in_flight: dict[str, int] = dict.fromkeys(self._authenticator.source_ids, 0)
        self._service = service
        self._host = host
        self._port = port
        self._runner: web.AppRunner | None = None

    @property
    def port(self) -> int:
        return self._port

    async def start(self) -> None:
        if not self._authenticator.source_ids:
            return
        try:
            app = web.Application(
                client_max_size=MAX_WEBHOOK_BYTES,
                middlewares=[self._observe_webhook, self._authenticate_webhook],
            )
            app.router.add_post("/webhooks/alertmanager", self._receive_webhook)
            self._runner = web.AppRunner(app, access_log=None, shutdown_timeout=5)
            await self._runner.setup()
            site = web.TCPSite(self._runner, self._host, self._port)
            await site.start()
            self._port = self._runner.addresses[0][1]
            logger.info("Alertmanager webhook listening on %s:%s", self._host, self._port)
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        try:
            if self._runner is not None:
                await self._runner.cleanup()
        finally:
            self._runner = None

    @web.middleware
    async def _observe_webhook(
        self, request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        status: int | None = None
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            status = exc.status
            raise
        except Exception:
            status = HTTPStatus.INTERNAL_SERVER_ERROR
            raise
        else:
            status = response.status
            return response
        finally:
            if status is not None:
                self._metrics.webhooks.labels(
                    source_id=request.get(SOURCE_ID_KEY, ""), status=str(status)
                ).inc()

    @web.middleware
    async def _authenticate_webhook(
        self, request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        source_id = self._authenticator.authenticate(request.headers.get("Authorization", ""))
        if source_id is None:
            return web.json_response(
                {"error": "Unauthorized"},
                status=HTTPStatus.UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"},
            )
        request[SOURCE_ID_KEY] = source_id
        if not self._admit(source_id):
            # Alertmanager's generic webhook retries 5xx, not 429.
            return web.json_response(
                {"error": "Source request limit reached"},
                status=HTTPStatus.SERVICE_UNAVAILABLE,
                headers={hdrs.RETRY_AFTER: str(REQUEST_RATE_WINDOW_SECONDS)},
            )
        try:
            return await handler(request)
        finally:
            self._in_flight[source_id] -= 1

    def _admit(self, source_id: str) -> bool:
        now = self._clock()
        window = self._request_windows[source_id]
        while window and window[0] <= now - REQUEST_RATE_WINDOW_SECONDS:
            window.popleft()
        if (
            len(window) >= MAX_REQUESTS_PER_SOURCE_PER_MINUTE
            or self._in_flight[source_id] >= MAX_IN_FLIGHT_PER_SOURCE
            or sum(self._in_flight.values()) >= MAX_IN_FLIGHT_REQUESTS
        ):
            return False
        window.append(now)
        self._in_flight[source_id] += 1
        return True

    async def _receive_webhook(self, request: web.Request) -> web.Response:
        source_id = request[SOURCE_ID_KEY]
        if request.content_type != "application/json":
            return web.json_response(
                {"error": "Expected application/json"}, status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE
            )
        try:
            async with asyncio.timeout(REQUEST_BODY_TIMEOUT_SECONDS):
                payload = await request.json()
            canonical = json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            ).encode("utf-8")
        except (ValueError, UnicodeError, RecursionError):
            return web.json_response({"error": "Invalid JSON body"}, status=HTTPStatus.BAD_REQUEST)
        except TimeoutError:
            return web.json_response(
                {"error": "Request body read timed out"}, status=HTTPStatus.SERVICE_UNAVAILABLE
            )
        try:
            alerts = parse_alertmanager_webhook(payload)
        except InvalidAlertmanagerWebhook as exc:
            return web.json_response({"error": str(exc)}, status=HTTPStatus.UNPROCESSABLE_ENTITY)
        digest = hashlib.sha256(canonical).hexdigest()
        try:
            accepted = await self._service.submit(source_id, digest, alerts)
        except AlertmanagerScopeUnavailable as exc:
            return web.json_response({"error": str(exc)}, status=HTTPStatus.SERVICE_UNAVAILABLE)
        except AlertmanagerScopeMismatch as exc:
            return web.json_response({"error": str(exc)}, status=HTTPStatus.UNPROCESSABLE_ENTITY)
        except AlertmanagerBatchTooLarge as exc:
            logger.warning(
                "Alertmanager batch exceeds the delivery limit", extra={"source_id": source_id}
            )
            return web.json_response({"error": str(exc)}, status=HTTPStatus.UNPROCESSABLE_ENTITY)
        except (AlertmanagerOutboxFull, SQLAlchemyError):
            logger.warning("Unable to persist Alertmanager webhook", extra={"source_id": source_id})
            return web.json_response(
                {"error": "Delivery queue is unavailable"}, status=HTTPStatus.SERVICE_UNAVAILABLE
            )
        logger.info(
            "Alertmanager webhook accepted",
            extra={"source_id": source_id, "alert_count": len(alerts), "accepted": accepted},
        )
        self._metrics.batches.labels(
            source_id=source_id, outcome="accepted" if accepted else "duplicate"
        ).inc()
        return web.json_response(
            {"accepted": accepted, "alerts": len(alerts)}, status=HTTPStatus.ACCEPTED
        )
