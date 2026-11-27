import time

from prometheus_client import CollectorRegistry, Counter, Gauge

from sentinel.metrics.constants import METRICS_NAMESPACE


class AlertmanagerMetrics:
    def __init__(self, registry: CollectorRegistry) -> None:
        self.webhooks = Counter(
            "webhooks",
            "Alertmanager webhook responses; empty source_id means unauthenticated.",
            ("source_id", "status"),
            namespace=METRICS_NAMESPACE,
            subsystem="alertmanager",
            registry=registry,
        )
        self.batches = Counter(
            "batches",
            "Acknowledged Alertmanager batches, accepted or duplicate.",
            ("source_id", "outcome"),
            namespace=METRICS_NAMESPACE,
            subsystem="alertmanager",
            registry=registry,
        )
        self.deliveries = Counter(
            "deliveries",
            "Outbox delivery outcomes after PTB returns; excludes PTB's internal retries.",
            ("source_id", "outcome"),
            namespace=METRICS_NAMESPACE,
            subsystem="alertmanager",
            registry=registry,
        )
        self.pending = Gauge(
            "pending_deliveries",
            "Persisted deliveries awaiting completion, including paused sources.",
            ("source_id",),
            namespace=METRICS_NAMESPACE,
            subsystem="alertmanager",
            registry=registry,
        )
        self.oldest_age = Gauge(
            "oldest_pending_age_seconds",
            "Age since enqueue of the oldest pending delivery; zero when empty.",
            ("source_id",),
            namespace=METRICS_NAMESPACE,
            subsystem="alertmanager",
            registry=registry,
        )

    def update_queue(self, source_id: str, count: int, oldest_enqueued_at: float | None) -> None:
        self.pending.labels(source_id=source_id).set(count)
        # Scrapes run in the health server's thread. Capture a value, never a SQLite callback.
        self.oldest_age.labels(source_id=source_id).set_function(
            lambda: (
                0.0 if oldest_enqueued_at is None else max(0.0, time.time() - oldest_enqueued_at)
            )
        )
