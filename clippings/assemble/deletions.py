"""Keeping a shown Bluesky post honest after the day it was picked.

A digest page is permanent, and a post is its author's to delete. So each run looks back
over the picks of the last thirty days: a post that no longer exists has its words removed
and the page says it was deleted, and a pick older than thirty days keeps only its
twenty-five-word quote, the same retention as everything else this project holds
(PLAN.md section 2.3, Peter, 2026-10-10).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta

import httpx

from clippings.assemble.digest import Digest
from clippings.assemble.publish import Site, publish_digest
from clippings.config.audience import Audience
from clippings.constants import RETENTION_DAYS
from clippings.ingest.store import Store
from clippings.sources.bluesky import post_exists

Exists = Callable[[str], bool | None]


def updated_pick(digest: Digest, now: datetime, exists: Exists) -> Digest | None:
    """The digest with its pick deleted or trimmed, or None if nothing changes."""
    pick = digest.spotlight
    if pick is None or pick.deleted:
        return None
    if now - digest.generated_at > timedelta(days=RETENTION_DAYS):
        if not pick.full_text:
            return None
        trimmed = pick.model_copy(update={"full_text": ""})
        return digest.model_copy(update={"spotlight": trimmed})
    if not pick.full_text:
        return None
    if exists(pick.url) is not False:
        return None
    gone = pick.model_copy(update={"deleted": True, "quote": "", "full_text": ""})
    return digest.model_copy(update={"spotlight": gone})


def recheck_picks(
    store: Store,
    site: Site,
    audiences: Sequence[Audience],
    client: httpx.Client,
    now: datetime,
    panels: dict[str, str],
) -> list[str]:
    """Re-render every page whose pick was deleted or aged out. Returns the pages changed."""
    changed = []
    for audience in audiences:
        for day in store.digest_days(audience.id):
            digest = store.digest_for(audience.id, day)
            if digest is None:
                continue
            update = updated_pick(digest, now, lambda url: post_exists(client, url))
            if update is None:
                continue
            store.save_digest(update)
            publish_digest(site, update, audience.description, panels.get(audience.id, ""))
            changed.append(f"{audience.id}/{day}")
    return changed
