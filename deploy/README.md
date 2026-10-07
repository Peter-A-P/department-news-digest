# Deploying to Google Cloud Run

PLAN.md section 2.5: a Cloud Run job per day, triggered by Cloud Scheduler, runs the graph
for every audience; a Cloud Run service serves the pages read-only. State is one DuckDB file
and the gateway's ledger, kept in a Cloud Storage bucket and copied down and back up by the
job inside a run lock.

```
Cloud Scheduler (09:00 UTC) --> Cloud Run job  clippings run
                                   |  takes gs://BUCKET/locks/run.lock
                                   |  pulls  gs://BUCKET/state/{clippings.duckdb,boundary.sqlite}
                                   |  fetches feeds, ranks, calls the model through the gateway
                                   |  writes gs://BUCKET/site/<audience>/<day>/{index.html,digest.md,digest.eml}
                                   |  deletes items past thirty days
                                   |  pushes the state back, releases the lock
                                   v
                     Cloud Run service  clippings serve  (reads gs://BUCKET/site/, GET only)
```

Nothing is sent. The `.eml` is a draft file in the bucket and on the page; nobody is
emailed.

## Before the first deploy

1. A Google Cloud project with billing, and `gcloud auth login` on the machine that deploys.
2. **The spend caps.** `clippings/config/gateway/caps.yaml` holds this project's caps in
   the gateway: US$2 a run, US$5 a day, US$60 a month, confirmed by Peter on 2026-10-07.
   Mirror the project line in the gateway repository's own caps file. The Anthropic console's hard cap is the
   first line of defence; these are the second.
3. Docker, for building the image locally (Cloud Build is not used, so nothing is built on
   a machine this project does not control).

## Deploy

```
PROJECT=your-project BILLING_ACCOUNT=XXXXXX-XXXXXX-XXXXXX deploy/deploy.sh
```

The script creates, in this order: the budget alert (before anything can cost money), the
bucket (private, uniform access), three service accounts (the job may write the bucket and
read its secrets; the service may only read the bucket; the scheduler may only start the
job), the secret names, the image, the job, the schedule and the service.

It stops before the job if the `anthropic-api-key` secret has no value. Add it, and any of
the optional ones, without the value touching the shell history:

```
read -rs KEY && printf %s "$KEY" | gcloud secrets versions add anthropic-api-key --data-file=-
```

| Secret | Needed for | Required |
|---|---|---|
| `anthropic-api-key` | Re-ranking and summaries, through the gateway | yes |
| `reddit-client-id`, `reddit-client-secret` | The Reddit sources, from a registered application on the free tier | no |
| `bluesky-handle`, `bluesky-app-password` | The Bluesky sources; an app password, revocable on its own | no |

A source whose credential is absent reports itself unavailable and the run carries on.

## After the deploy

```
gcloud run jobs execute clippings-daily --region=us-east1 --wait     # one run, now
gcloud run jobs executions list --job=clippings-daily --region=us-east1
```

The pages are at the service URL the script prints. `digest.peterparker.ca` is a domain
mapping on the service plus a DNS record at the registrar:

```
gcloud beta run domain-mappings create --service=clippings-web \
  --domain=digest.peterparker.ca --region=us-east1
```

then a `CNAME` from `digest` to `ghs.googlehosted.com.`, which only the domain's owner can
add.

## What it costs

Inside the free tiers at this volume: a daily job of a few minutes on one vCPU, a service
that scales to zero, and a bucket of a few megabytes in `us-east1`, which is a free-tier
region. The model calls are the cost, about US$0.13 per audience-day (PLAN.md section 6),
and they are on the gateway's ledger in `gs://BUCKET/state/boundary.sqlite`:

```
gcloud storage cp gs://BUCKET/state/boundary.sqlite /tmp/ && \
  uv run boundary --config clippings/config/gateway/boundary.yaml \
    ledger report --ledger /tmp/boundary.sqlite
```

## Changing the schedule

`SCHEDULE="30 8 * * *" deploy/deploy.sh` redeploys with a new cron (UTC). One run serves
every audience, so the time is the earliest delivery time among them: 07:00 in St. John's
is 09:30 UTC in summer and 10:30 in winter, and 09:00 UTC is before both.
