# External operator alerts (Alertmanager)

Set `ALERTMANAGER_WEBHOOK_SOURCES` to a secret JSON object mapping publisher IDs to lists
of active bearer keys. An unset/empty value or `{}` disables `POST /webhooks/alertmanager`.
`ALERTMANAGER_WEBHOOK_HOST` defaults to `0.0.0.0` and `ALERTMANAGER_WEBHOOK_PORT` to `8081`.
Send a publisher's key as `Authorization: Bearer <key>`.

An infrastructure administrator generates each key using a cryptographic random generator:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Store the generated values in your secret manager, not in the repository. Sentinel receives
the registry below; replace the placeholders with generated values. Each publisher receives
only its own key, for example through Alertmanager's `credentials_file`.

```dotenv
ALERTMANAGER_WEBHOOK_SOURCES='{"evm":["<generated-key>"],"other-monitor":["<another-generated-key>"]}'
```

Publisher IDs start with a lowercase letter and use lowercase letters, digits, `_` or `-`
(up to 64 characters). Configure up to 64 publishers, with one or two unique keys each.
Keys contain 32 to 512 printable ASCII characters without spaces; the command above generates
32 random bytes encoded as a URL-safe key. Keys cannot be reused across publishers.
No Telegram command or registration API is involved.

The registry is read at process startup. After updating a Kubernetes Secret injected into
the environment, restart the Pod or use your existing secret reloader. With the existing
`SECRETS_FILE_PATH` dotenv bundle, update the JSON value and increment `SECRET_VERSION` to
request a graceful restart. Merely changing a Secret does not update an existing environment.

For rotation, first register `["<old-key>", "<new-key>"]` under the same publisher ID and
restart Sentinel. Then switch the sender to the new key using its normal credential reload
procedure. Finally remove the old key and restart Sentinel again. Both keys identify the
same publisher and share receipts/limits. Removing a publisher rejects its credentials and
pauses its pending deliveries after restart; adding that ID back resumes them. Review queued
messages before re-enabling a compromised publisher. Changing a publisher ID creates a new
identity and does not transfer its pending queue.

Each registered publisher is trusted to send alerts for any subscribed operator of this
instance's chain/module. Identity comes from the authenticated key, never from payload labels.
The publisher ID appears in notifications and admission/delivery logs; keys are redacted.
When several tools share one Alertmanager, that Alertmanager is the authenticated publisher;
an upstream `source` label does not prove which tool originally produced an alert.

Expose a public listener through your HTTPS reverse proxy. For a local Docker proxy, publish
it with `-p 127.0.0.1:8081:8081` (or the equivalent Compose `ports` entry). In Kubernetes, add
a ClusterIP Service for `8081`; an in-cluster Alertmanager can use that Service directly.
An external sender needs a TLS Ingress/Gateway routing only `/webhooks/alertmanager` to that
Service and preserving `Authorization`. Keep health/metrics on `8080` internal. `/ready`
requires the Alertmanager component to finish `start()`, including its no-op when disabled.
The health response's `alertmanager_ready` is always a boolean; `/startup` and `/live` remain
independent of webhook startup/catch-up. Preserve the existing PVC and one active bot process
per instance, including during rollouts; overlapping processes are not supported.

The receiver accepts the standard Alertmanager version `4` webhook JSON. Each item in `alerts`
must contain these fixed labels with decimal integer **string** values:

| Label | Meaning |
| --- | --- |
| `chain_id` | Execution chain ID, checked against the RPC chain validated on startup |
| `staking_module_id` | Module ID, checked against the module discovered through Staking Router |
| `node_operator_id` | Node Operator ID within that module; `0` is valid |

There is no configurable label mapping or fallback to `commonLabels`, `nos_id`, or `nos_module_id`.
If no registered module ID is discovered, the application and webhook listener still start.
Authenticated valid webhooks return `503` without queuing messages.
Previously accepted notifications continue to be delivered from the runtime-owned database.
Once the module adapter discovers the registration ID (including a refresh on `Resumed`),
new webhooks can be validated and accepted without restarting Sentinel.
Application readiness is not blocked by the missing ID once the listener has started.
The entire request is validated before any notifications are queued, so a missing/invalid label
or a different chain/module rejects the whole batch. Route each chain/module to its own
Sentinel instance.

For example, the relevant fields of a webhook are:

```json
{
  "version": "4",
  "status": "firing",
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "MissedAttestations",
        "chain_id": "1",
        "staking_module_id": "3",
        "node_operator_id": "42"
      },
      "annotations": {
        "summary": "Missed attestations",
        "description": "30 validators missed attestations in the last 3 epochs"
      }
    }
  ]
}
```

Sentinel sends each alert only to existing subscribers of its Node Operator. It forwards
`alertname`, the per-alert `status`, `annotations.summary`, and `annotations.description` as
plain text, together with the authenticated publisher ID, without interpreting Telegram
HTML/Markdown. Group annotations are not forwarded.
Long text is split to fit Telegram's message limit. `resolved` is displayed as the source's
status, not interpreted as proof of operator recovery.

Example Alertmanager configuration for one network/module (adapt the URL and existing routes):

```yaml
route:
  receiver: sentinel
  group_by: [chain_id, staking_module_id, node_operator_id, alertname]
  group_wait: 10s
  group_interval: 1m
  repeat_interval: 1h

receivers:
  - name: sentinel
    webhook_configs:
      - url: https://sentinel.example/webhooks/alertmanager
        send_resolved: false
        max_alerts: 0
        http_config:
          authorization:
            type: Bearer
            credentials_file: /run/secrets/sentinel_webhook_token
```

For Ethereum Validators Monitoring, add the required routing labels at the source. Critical
notifications that combine several operators into a textual description must first be split
into one alert per operator. Its epoch-gated Prometheus rules and short-lived critical alerts
can resolve without operator recovery; keep `send_resolved: false` for those rules. A new
firing occurrence is not necessarily throttled by Alertmanager's `repeat_interval`.

Sentinel does not recalculate metrics, sum snapshots, or aggregate alerts across requests.
Grouping, thresholds, and reminder cadence belong to the monitoring source/Alertmanager.
Repeated requests from the same publisher with the same JSON content (ignoring object key
order) are deduplicated for 60 seconds, and while their deliveries remain pending. Different
publishers have independent receipts. Later identical reminders are allowed; an alert
fingerprint is never treated as a permanent notification ID.

An HTTP `202` acknowledges a committed outbox in `FILESTORAGE_PATH/sentinel.sqlite3`,
not completed Telegram delivery. Pending messages survive restarts and cancellation;
subscriptions are rechecked before sending. Sending relies on PTB and the shared
`AIORateLimiter(max_retries=5)`, which retries `RetryAfter` and can pause all bot sends.
Sentinel adds no delivery retries: a final Telegram error is logged, counted as `failed`,
and removed from the outbox. The message may remain undelivered. A crash after Telegram
accepts a message but before its acknowledgement is stored can produce a duplicate.
Keep the persistence directory mounted, and run one bot process per directory. The shared
database identity binds all persisted state, including the outbox, to the instance's chain
and module. Telegram chat migration updates subscriptions and all pending deliveries,
whether discovered through a migration update or `ChatMigrated` during sending.
Queue ordering is preserved; a result from an in-flight send to the old chat cannot delete
a delivery already moved to the new chat.
The shared `chat_migrations` journal commits the old/new chat IDs in the same transaction as
moving the queue. Startup replays this journal against loaded pickle subscriptions before
polling or delivery starts, so a crash before the next pickle flush does not discard the queue.
Journal entries are retained to support recovery from an older pickle snapshot.

The request limit is 1 MiB and 1000 alerts. There are at most 120 authenticated requests per
publisher per rolling minute, 4 in-flight requests per publisher, and 16 in-flight requests
overall. Reading a request body has a 5-second deadline. The outbox holds up to 1000 pending
message deliveries per publisher and 10,000 overall. The complete batch must fit an empty
queue after subscriber fan-out and text splitting; exceeding this capacity returns `422`
without queuing any messages. Reduce the alert group size or annotation length before
resubmitting; an unchanged oversized batch will not succeed on retry. Use Alertmanager
grouping to reduce batches, not `max_alerts`, which truncates notifications.
A retry of an already accepted batch acknowledges its original recipient snapshot, even if
subscriptions have changed.
A malformed body returns `400`, invalid routing/payload or a truncated batch `422`,
missing/incorrect authorization `401`, an oversized body `413`, and an unsupported content type
`415`. Temporary request/concurrency limits, body-read timeouts, and a temporarily
full/unavailable outbox return `503` so Alertmanager can retry. Its generic webhook retries
`5xx`, not ordinary `429` or `401` responses: account for this in proxy rate limits and
rotate keys with overlap.
Set `max_alerts: 0` to avoid dropping alerts from webhook batches.

The existing `/metrics` endpoint also exports these feature metrics:

| Metric | Labels | Meaning |
| --- | --- | --- |
| `sentinel_alertmanager_webhooks_total` | `source_id`, `status` | Webhook responses by HTTP status, including rejections |
| `sentinel_alertmanager_batches_total` | `source_id`, `outcome` | Acknowledged batches: `accepted` or `duplicate` |
| `sentinel_alertmanager_pending_deliveries` | `source_id` | Persisted messages awaiting completion, including paused sources |
| `sentinel_alertmanager_oldest_pending_age_seconds` | `source_id` | Age since enqueue of the oldest pending message; zero when empty |
| `sentinel_alertmanager_deliveries_total` | `source_id`, `outcome` | Outbox outcomes: `sent`, `failed`, `migrated`, or `unsubscribed` |

Source labels come from authenticated identities; unauthenticated requests use an empty
`source_id`. Keys, chat IDs, and payload labels are never metric labels. Queue gauges are
restored from SQLite at startup, and retries do not reset message age. Counters reset on
process restart. If the SQL read used to refresh queue gauges fails, the previous values remain
until a successful refresh; the worker retries the refresh every five seconds even when the
queue is empty. Committed requests and delivery continue. Delivery outcomes count calls after
PTB returns, while the existing
`sentinel_telegram_*` metrics continue to measure individual HTTP attempts within PTB.

## Shared SQLite storage

`BotRuntime.database` owns the SQLAlchemy async engine for `sentinel.sqlite3`, SQLite settings,
and chain/module runtime identity. Startup checks existing database ownership before running
Alembic. Schema upgrades and initial identity binding share one transaction, including when
the webhook receiver is disabled. Repositories receive a session and use namespaced tables;
the Alertmanager outbox is its first consumer with
`alertmanager_requests` and `alertmanager_deliveries`.
Stopping the webhook listener does not close the application database.

Use `async with database.transaction() as session` and pass the same session to participating
repositories to atomically commit or roll back their writes. This reserves the SQLite writer
with `BEGIN IMMEDIATE` before checking deduplication or queue quotas. Use
`session.begin_nested()` for explicit savepoints. Each concurrent operation gets its own
session. Close transactions before Telegram/RPC calls; the worker sends detached delivery
snapshots. SQLite I/O uses aiosqlite background threads, so lock waits do not block the event loop.

Schema revisions live in `sentinel/migrations/versions`; do not create tables in repositories
or edit a revision after release. Generate a revision with
`uv run alembic revision --autogenerate -m "describe schema change"`, review it, and test both
upgrade and rollback behavior. Initialize a new database by starting Sentinel: it validates the
RPC identity and binds that identity atomically with the initial schema. The Alembic CLI only
operates on an already-bound database; it rejects an uninitialized database before changing
its schema. Offline SQL generation does not initialize or bind a database.
The CLI defaults to `.storage/sentinel.sqlite3`; for another
path, supply an Alembic config with the corresponding `sqlalchemy.url`. Runtime startup uses
`FILESTORAGE_PATH` and does not depend on the CLI config. SQLite table alterations use Alembic
batch migrations. The unreleased pre-Alembic prototype schema is not a supported migration source.
The Docker image includes the CLI config; `docker compose exec csm-sentinel alembic current`
reports the revision of the default database. Normal startup applies migrations automatically.

Subscriptions, chain checkpoints, aggregation windows, and digests still use
`persistence.pkl`. Moving them into explicit SQLite tables, migrating existing data,
and committing chain notifications with checkpoints are a separate change. This foundation
does not yet make those writes atomic with the outbox. Event, aggregation-window, and runtime-identity
records are validated with Pydantic before conversion into the existing domain dataclasses. Environment configuration
uses one Pydantic `Config` throughout the application, with an `ExplorerLinks` dataclass for
building explorer URLs. Discovered `ContractAddresses` are passed separately to the module
adapter; they are not settings. The OS-environment loader is explicit and does not use
`pydantic-settings`.

[Back to README](../README.md#external-operator-alerts-alertmanager)
