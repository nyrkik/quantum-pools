# Gmail Pub/Sub Push Runbook

This is the cutover playbook for replacing 60s Gmail polling with Cloud Pub/Sub push notifications. It exists because the 2026-04-28 lockout proved the polling architecture is structurally unsafe — every poll burns user-rate-limit quota, and a misbehaving watermark caused 24h of dark mail.

The push architecture eliminates per-minute quota burn entirely. One `users.watch()` per day per integration, plus one `history.list()` per actual mailbox change. Per-user-rate-limit lockouts become impossible at our scale.

## Architecture

```
Gmail mailbox change
  → Gmail publishes to Cloud Pub/Sub topic
  → Pub/Sub HTTP-POSTs `https://app.quantumpoolspro.com/api/v1/public/gmail-pubsub-push`
  → QP verifies the JWT (signature + audience + service-account email)
  → QP calls `history.list(last_history_id)` and ingests via existing pipeline
```

Polling stays active during the cutover window (~1-2 weeks) for safety. Both paths share the same `_fetch_and_ingest` which is idempotent on `email_uid`.

## One-time GCP setup (Brian)

These steps require Brian's Google Cloud admin access — Claude can't do them.

### 1. Pick or create a GCP project

If we already have one for OAuth (`gmail/oauth.py` references `client_id`/`client_secret`), use the same project. Otherwise create a new one:

```
Console → Project picker → New Project
Name: quantum-pools-platform
Project ID: quantum-pools-platform-<suffix>   (Google generates if you don't pick)
```

Note the **project ID** — you need it for the topic path.

### 2. Enable Gmail API + Pub/Sub API

```
Console → APIs & Services → Library
- Gmail API → Enable (already enabled if OAuth works)
- Cloud Pub/Sub API → Enable
```

### 3. Create the Pub/Sub topic

```
Console → Pub/Sub → Topics → Create Topic
Topic ID: quantumpools-gmail-push
Add a default subscription: NO  (we'll create the push sub explicitly)
```

The full topic path becomes: `projects/<project-id>/topics/quantumpools-gmail-push`

### 4. Grant Gmail permission to publish to the topic

This is the step that's easy to forget — without it, `users.watch()` fails.

```
Console → Pub/Sub → Topics → quantumpools-gmail-push → Permissions tab
Add Principal: gmail-api-push@system.gserviceaccount.com
Role: Pub/Sub Publisher
```

### 5. Create the push subscription

```
Console → Pub/Sub → Subscriptions → Create Subscription
Subscription ID: quantumpools-gmail-push-sub
Topic: quantumpools-gmail-push
Delivery type: Push
Endpoint URL: https://app.quantumpoolspro.com/api/v1/public/gmail-pubsub-push
Enable authentication: YES
Service account: <create or pick a service account, e.g. qp-pubsub-push@<project>.iam.gserviceaccount.com>
Audience: https://app.quantumpoolspro.com/api/v1/public/gmail-pubsub-push
```

The service-account email above is what QP's webhook validates the JWT `email` claim against. It's a NEW service account you create just for push auth — different from the `gmail-api-push@system.gserviceaccount.com` that actually publishes to the topic.

If creating a new service account: GCP IAM → Service Accounts → Create. No keys needed; Pub/Sub uses workload identity to sign the JWT.

Subscription settings (defaults are fine, but worth knowing):
- **Acknowledgement deadline**: 10s default. Our webhook returns fast, so fine.
- **Retry policy**: exponential backoff up to 600s, max 7d retention. Means a transient outage on our side gets re-delivered automatically. Good.
- **Dead-letter topic**: not needed for v1.

### 6. Deploy env vars to QP

In `/srv/quantumpools/.env`:

```
GMAIL_PUBSUB_AUDIENCE=https://app.quantumpoolspro.com/api/v1/public/gmail-pubsub-push
GMAIL_PUBSUB_SERVICE_ACCOUNT=qp-pubsub-push@<project>.iam.gserviceaccount.com
GMAIL_PUBSUB_TOPIC=projects/<project-id>/topics/quantumpools-gmail-push
```

Then `/srv/quantumpools/scripts/deploy.sh` to restart with the new vars.

### 7. Enable the watch on Sapphire's integration

After env is deployed:

```bash
curl -X POST 'https://app.quantumpoolspro.com/api/v1/email-integrations/<sapphire-integration-id>/watch' \
  -H 'Cookie: <admin session cookie>' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

Response should include `watch_response.history_id` and `watch_response.expiration_ms`. Within ~30s the first push should arrive (any unread mail will trigger one). Confirm via:

```sql
SELECT account_email, last_pubsub_push_at, watch_expires_at
FROM email_integrations WHERE type='gmail_api';
```

`last_pubsub_push_at` should be recent. Subsequent inbound email lands within <1s of the user receiving it in Gmail.

## Daily refresh + heartbeat

`agent_poller.py` runs:
- `gmail_watch_refresh()` every 24h — calls users.watch again to roll the expiry forward.
- `gmail_push_heartbeat()` every cycle — alerts via ntfy if `last_pubsub_push_at` goes stale (>6h with watch still alive).

Do not skip the heartbeat. If the daily refresh ever lapses for >7 days, the watch expires hard and Gmail stops pushing. Without the heartbeat, mail goes silently dark.

## Incident response

### Push pipeline broken (heartbeat alert fires)

```
Symptom: ntfy "QP Gmail push silent: <email>"
First response:
  1. Check sudo journalctl -u quantumpools-backend --since "1h ago" | grep gmail-pubsub-push
     - 401s → JWT verification failing. Check GMAIL_PUBSUB_SERVICE_ACCOUNT matches the push sub.
     - 500s → ingest pipeline broken downstream.
     - No logs → push not arriving. Move to step 2.
  2. Check the Pub/Sub subscription dashboard for unacked messages or backlog.
  3. Re-run setup_watch via the admin endpoint to re-establish the watch.
  4. While debugging: polling fallback should still be ingesting (until it gets ripped). Verify
     last_sync_at is fresh: SELECT account_email, last_sync_at FROM email_integrations.
```

### Need to disable push without disabling inbound

```
POST /v1/email-integrations/<id>/watch/stop
```

This calls users.stop, clears the persisted watch state, and the heartbeat alert clears on its own once the watch_expires_at passes. Polling continues.

### Re-auth needs to re-arm the watch

OAuth disconnect/reconnect doesn't carry the watch over. After reconnect, POST `/watch` again. The integration's `last_history_id` is preserved across re-auth (when re-authenticating the same `integration_id`), so no double-ingest.

## Cutover plan

1. **Today**: ship the code (this PR). Push code is live but disabled — no env vars set, watch not called.
2. **Brian does GCP setup** (steps 1-5 above). ~20 min of console clicks.
3. **Set env + deploy** (step 6). Server starts honoring pushes the moment it's restarted.
4. **Enable watch** (step 7). Push and polling now run in parallel.
5. **Observe for 1 week**: watch the heartbeat dashboard, confirm `last_pubsub_push_at` is fresh, confirm no duplicate ingestion (the dedup absorbs but you want 0 errors).
6. **Rip polling** (separate PR): comment out `gmail_incremental_sync()` in `agent_poller.main`. Keep the function around for incident-response fallback.

## Why this can't lock us out the way polling did

The 2026-04-28 lockout was 60s polls × hours × broken watermark = catastrophic quota burn against a fixed-window bucket. Push has none of those properties:

- **No polls** during steady state — `users.watch()` runs once per 24h, costs ~1 quota unit.
- **`history.list()` is the only on-change call** and it's the same call polling already used (cheap).
- **Cross-path Retry-After parking** (already shipped) means even if push triggers a 429 on a watch refresh, every other Gmail path stops poking.
- **The heartbeat closes the only remaining failure mode** (silent watch expiry) by alerting before it becomes a 7-day outage.
