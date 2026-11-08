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
3. Nothing local for the image: it is built on Cloud Build (`deploy/cloudbuild.yaml`) as its
   own `clippings-build` service account. `BUILDER=local` builds with local Docker instead;
   that was the default until 2026-10-08, when the images it left behind filled the
   laptop's disk.

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
read -rs "KEY?Paste the Anthropic API key, then Enter: " && echo && printf %s "$KEY" | gcloud secrets versions add anthropic-api-key --data-file=-
```

| Secret | Needed for | Required |
|---|---|---|
| `anthropic-api-key` | Re-ranking and summaries, through the gateway | yes |
| `bluesky-handle`, `bluesky-app-password` | The Bluesky sources; an app password, revocable on its own | no |
| `x-bearer-token` | The day's X pick: the app-only bearer token of an X developer account on pay-per-use pricing. Set the account's monthly spend limit in X's developer console first; the code's own cap is US$10 a month | no |

A source whose credential is absent reports itself unavailable and the run carries on.

### The X token

X is pay-per-use, so the spend limit goes on before the token goes in. From X's own
documentation ([getting access](https://docs.x.com/x-api/getting-started/getting-access),
[pricing](https://docs.x.com/x-api/getting-started/pricing)):

1. Sign in at https://console.x.com with the X account that will own the app, accept the
   Developer Agreement and Policy, and describe the use: a daily public news digest that
   reads one search of ten posts and one user per audience a day, shows at most one post a
   day in full with its author, and is not used by or for any government body.
2. Create an app. The console generates its keys and tokens, the app-only Bearer Token among
   them; that is the only credential this project uses. Copy it when it is shown.
3. Buy credits in the console and set the spending limit per billing cycle to US$10; when it
   is reached, X blocks requests until the next cycle. Leave auto-recharge off, so the limit
   and the balance are both hard stops.
4. Check the token with one user read (US$0.01), without it touching the shell history:

```
read -rs "X_BEARER_TOKEN?Paste the X Bearer Token, then Enter: " && echo && curl -s -H "Authorization: Bearer $X_BEARER_TOKEN" \
  https://api.x.com/2/users/by/username/XDevelopers
```

   A JSON `data` object with a `username` is a working token; 401 is a wrong token, 402 is no
   credits.
5. Store it and redeploy, so the job maps the new secret. The secret is created first if a
   deploy has not made it yet; the billing account is read from the project rather than
   typed:

```
gcloud secrets describe x-bearer-token >/dev/null 2>&1 || \
  gcloud secrets create x-bearer-token --replication-policy=automatic
printf %s "$X_BEARER_TOKEN" | gcloud secrets versions add x-bearer-token --data-file=-
unset X_BEARER_TOKEN
PROJECT=clippings-digest BILLING_ACCOUNT="$(gcloud billing projects describe clippings-digest \
  --format='value(billingAccountName)' | cut -d/ -f2)" deploy/deploy.sh
```

The next morning's run prints an `x pick` line per audience: the post and its cost, or why
there was none. To add a pick to the digests already published today instead of waiting,
run the job once with the `x-pick` command; it leaves the digests otherwise as they are:

```
gcloud run jobs execute clippings-daily --region=us-east1 --args=x-pick --wait
```

## After the deploy

```
gcloud run jobs execute clippings-daily --region=us-east1 --wait     # one run, now
gcloud run jobs executions list --job=clippings-daily --region=us-east1
```

The pages are at the service URL the script prints. `digest.peterparker.ca` takes three
steps, two of them at the domain's owner's accounts:

1. Verify the domain for the Google account that deploys, once:
   `gcloud domains verify peterparker.ca` opens Search Console, which asks for a `TXT`
   record at the domain's DNS host (Cloudflare). Verifying the apex covers `digest.`.
2. Map it to the service:

   ```
   gcloud beta run domain-mappings create --service=clippings-web \
     --domain=digest.peterparker.ca --region=us-east1 --project=clippings-digest
   ```

3. At Cloudflare, a `CNAME` from `digest` to `ghs.googlehosted.com`, **DNS only** (grey
   cloud, not proxied): Google issues the certificate only when it sees its own front end
   answer for the name, which a proxied record hides. The certificate takes from a few
   minutes to an hour after the record resolves.

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

A second schedule, `clippings-gdelt`, runs the same job as `clippings fetch gdelt` at half
past every third hour (`GDELT_SCHEDULE`, default `30 1-22/3 * * *`), because GDELT refuses
most requests from Cloud Run's shared addresses and eight tries a day get through where one
does not. It stores items and nothing else, and steps aside if the daily run holds the lock.

`SCHEDULE="30 8 * * *" deploy/deploy.sh` redeploys with a new cron (UTC). One run serves
every audience, so the time is the earliest delivery time among them: 07:00 in St. John's
is 09:30 UTC in summer and 10:30 in winter, and 09:00 UTC is before both.
