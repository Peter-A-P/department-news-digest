"""Keeping a shown post honest after the day it was picked.

A digest page is permanent, and a post is its author's to delete. So each run looks back
over the Bluesky picks of the last thirty days: a post that no longer exists has its words
removed and the page says it was deleted, and a pick older than thirty days keeps only its
twenty-five-word quote, the same retention as everything else this project holds
(PLAN.md section 2.3, Peter, 2026-10-10). The same free lookup gives the author's display
name and picture, so a pick made before the post card (2026-10-13) gains them on the next
run.

An X pick is not checked, because every check is a paid read. Its words, its author's name
and picture are removed from every stored copy and its page once it is
`X_POST_SHOWN_HOURS` old, by the next daily run, whether or not the post still exists. What
is left is the link, the handle, the counts at the time and why it was picked.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta

import httpx

from clippings.assemble.digest import Digest, Spotlight
from clippings.assemble.publish import Site, publish_digest
from clippings.config.audience import Audience
from clippings.constants import RETENTION_DAYS, X_POST_SHOWN_HOURS
from clippings.ingest.store import Store
from clippings.sources.bluesky import PostView, post_view

Lookup = Callable[[str], PostView]


def _updated_post(
    pick: Spotlight, digest: Digest, now: datetime, lookup: Lookup
) -> Spotlight | None:
    """One pick deleted, trimmed or given its author, or None if it does not change."""
    if pick.deleted:
        return None
    if now - digest.generated_at > timedelta(days=RETENTION_DAYS):
        if not pick.full_text:
            return None
        return pick.model_copy(update={"full_text": "", "name": "", "image_url": ""})
    if not pick.full_text:
        return None
    view = lookup(pick.url)
    if view.found and not pick.name and not pick.image_url and (view.name or view.image_url):
        return pick.model_copy(
            update={"name": view.name, "image_url": view.image_url, "reposts": view.reposts}
        )
    if view.found is not False:
        return None
    return pick.model_copy(
        update={"deleted": True, "quote": "", "full_text": "", "name": "", "image_url": ""}
    )


def updated_pick(digest: Digest, now: datetime, lookup: Lookup) -> Digest | None:
    """The digest with its picks deleted, trimmed or given their authors, or None if nothing
    changes."""
    updates = [_updated_post(pick, digest, now, lookup) for pick in digest.spotlights]
    if all(update is None for update in updates):
        return None
    picks = tuple(
        update if update is not None else pick
        for pick, update in zip(digest.spotlights, updates, strict=True)
    )
    return digest.model_copy(update={"spotlights": picks})


def recheck_picks(
    store: Store,
    site: Site,
    audiences: Sequence[Audience],
    client: httpx.Client,
    now: datetime,
    panels: dict[str, str],
) -> list[str]:
    """Re-render every page whose pick was deleted, aged out or given its author. Returns
    the pages changed."""
    changed = []
    for audience in audiences:
        for day in store.digest_days(audience.id):
            digest = store.digest_for(audience.id, day)
            if digest is None:
                continue
            update = updated_pick(digest, now, lambda url: post_view(client, url))
            if update is None:
                continue
            store.save_digest(update)
            publish_digest(site, update, audience.description, panels.get(audience.id, ""))
            changed.append(f"{audience.id}/{day}")
    return changed


def expired_x_pick(digest: Digest, now: datetime) -> Digest | None:
    """The digest with its X picks' words removed if it is old enough, or None."""
    if all(pick.expired for pick in digest.x_picks):
        return None
    if now - digest.generated_at < timedelta(hours=X_POST_SHOWN_HOURS):
        return None
    gone = tuple(
        pick.model_copy(update={"expired": True, "text": "", "name": "", "image_url": ""})
        for pick in digest.x_picks
    )
    return digest.model_copy(update={"x_picks": gone})


def expire_x_picks(
    store: Store,
    site: Site,
    audiences: Sequence[Audience],
    now: datetime,
    panels: dict[str, str],
) -> list[str]:
    """Remove the words of every X pick past its day, from every stored run and the page.

    Runs whatever the terms record says about X, so a source dropped later still has what it
    left behind cleared. Returns the pages changed.
    """
    changed = []
    for audience in audiences:
        for day in store.digest_days(audience.id):
            runs = store.digest_runs(audience.id, day)
            updates = [update for digest in runs if (update := expired_x_pick(digest, now))]
            for update in updates:
                store.save_digest(update)
            if updates:
                shown = store.digest_for(audience.id, day)
                if shown is not None:
                    publish_digest(site, shown, audience.description, panels.get(audience.id, ""))
                changed.append(f"{audience.id}/{day}")
    return changed
