"""The audience schema: one YAML file per department, and the product itself.

PLAN.md section 2.1. Everything downstream reads from this. Unknown fields are rejected
rather than ignored, so a typo in a department's file fails at load instead of quietly
changing what that department reads.
"""

from __future__ import annotations

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
LANGUAGE = re.compile(r"^[a-z]{2}$")
DOMAIN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")
HHMM = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")


class Strict(BaseModel):
    """Every model in the audience file forbids unknown fields and is immutable once loaded."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Entities(Strict):
    """Named entities the audience cares about: ranking features, and GDELT queries."""

    organisations: tuple[str, ...] = ()
    people: tuple[str, ...] = ()
    places: tuple[str, ...] = ()

    def all(self) -> tuple[str, ...]:
        return self.organisations + self.people + self.places


class Feed(Strict):
    """One RSS or Atom feed. `terms` is the key into docs/sources.md, dated there."""

    url: str
    publisher: str
    terms: str
    # False for a feed whose terms were cleared for the feed itself and not for its article
    # pages: a publisher paywalled in part, where the feed's own title and summary and a link
    # are usable and a request for the page is not. The item still reaches a digest, and the
    # summariser and verifier work from what the publisher put in the feed.
    extract: bool = True

    @field_validator("url")
    @classmethod
    def _https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("feed URLs must be https")
        return value


class RedditSource(Strict):
    """Public subreddits, read through a registered application on the free tier."""

    subreddits: tuple[str, ...] = ()
    listing: str = "new"
    limit: int = Field(default=50, ge=1, le=100)

    @field_validator("subreddits")
    @classmethod
    def _bare_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for name in value:
            if name.startswith(("r/", "/r/")):
                raise ValueError(f"give the bare subreddit name, not {name!r}")
        return value

    @field_validator("listing")
    @classmethod
    def _known_listing(cls, value: str) -> str:
        if value not in {"new", "hot", "top"}:
            raise ValueError("listing must be one of: new, hot, top")
        return value


class BlueskySource(Strict):
    """Public AT Protocol search terms."""

    queries: tuple[str, ...] = ()
    limit: int = Field(default=50, ge=1, le=100)


class GdeltSource(Strict):
    """GDELT document API queries for global coverage of the audience's entities."""

    queries: tuple[str, ...] = ()
    limit: int = Field(default=75, ge=1, le=250)


class Sources(Strict):
    """Where this audience's pool comes from.

    Any subset may be empty: the pipeline runs with whatever sources are configured, which is
    what makes dropping a source that changes its terms cheap (PLAN.md section 8).
    """

    feeds: tuple[Feed, ...] = ()
    gdelt: GdeltSource = GdeltSource()
    reddit: RedditSource = RedditSource()
    bluesky: BlueskySource = BlueskySource()


class Digest(Strict):
    """Length budget, and how many candidates the model is allowed to see.

    `rerank_candidates` is the cost control of the whole project: the model never sees the
    day's pool, only this many items (PLAN.md section 2.3).
    """

    max_stories: int = Field(default=10, ge=1, le=40)
    rerank_candidates: int = Field(default=60, ge=1, le=200)
    max_sentences_per_story: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def _candidates_cover_the_digest(self) -> Digest:
        if self.rerank_candidates < self.max_stories:
            raise ValueError("rerank_candidates must be at least max_stories")
        return self


class Delivery(Strict):
    """When the digest is built. Nothing is sent: delivery is a page and a draft file."""

    time_local: str = "07:00"
    timezone: str = "America/St_Johns"

    @field_validator("time_local")
    @classmethod
    def _hhmm(cls, value: str) -> str:
        if not HHMM.fullmatch(value):
            raise ValueError("time_local must be HH:MM in 24-hour time")
        return value

    @field_validator("timezone")
    @classmethod
    def _real_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone {value!r}") from exc
        return value


class Audience(Strict):
    """One department's configuration. Adding a department is adding one of these."""

    id: str
    name: str
    description: str
    rubric: str
    topics: tuple[str, ...]
    entities: Entities = Entities()
    geography: tuple[str, ...] = ()
    languages: tuple[str, ...] = ("en",)
    sources: Sources = Sources()
    trusted_sources: tuple[str, ...] = ()
    blocked_sources: tuple[str, ...] = ()
    digest: Digest = Digest()
    delivery: Delivery = Delivery()

    @field_validator("id")
    @classmethod
    def _slug(cls, value: str) -> str:
        if not SLUG.fullmatch(value):
            raise ValueError("id must be a lower-case slug, for example 'ai-policy'")
        return value

    @field_validator("topics")
    @classmethod
    def _at_least_one_topic(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("an audience needs at least one topic")
        return value

    @field_validator("rubric")
    @classmethod
    def _rubric_says_something(cls, value: str) -> str:
        # The rubric is published with the results so a reader can see what "relevant" meant
        # for this audience (PLAN.md section 8). A placeholder would make the labels unreadable.
        if len(value.split()) < 10:
            raise ValueError("the rubric must say what relevant means in at least ten words")
        return value

    @field_validator("languages")
    @classmethod
    def _iso_639_1(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for code in value:
            if not LANGUAGE.fullmatch(code):
                raise ValueError(f"{code!r} is not a two-letter ISO 639-1 language code")
        return value

    @field_validator("trusted_sources", "blocked_sources")
    @classmethod
    def _domains(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for domain in value:
            if not DOMAIN.fullmatch(domain):
                raise ValueError(f"{domain!r} is not a bare domain, for example 'example.org'")
        return value

    @model_validator(mode="after")
    def _no_domain_both_trusted_and_blocked(self) -> Audience:
        both = set(self.trusted_sources) & set(self.blocked_sources)
        if both:
            raise ValueError(f"domains both trusted and blocked: {sorted(both)}")
        return self

    def profile_text(self) -> str:
        """The audience as one string, embedded once per run as the ranking target."""
        parts = [self.description, *self.topics, *self.entities.all(), *self.geography]
        return ". ".join(part.strip() for part in parts if part.strip())
