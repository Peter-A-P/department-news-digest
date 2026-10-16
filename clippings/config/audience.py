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


class Sitemap(Strict):
    """A publisher's sitemap, for a news section that has no feed.

    Some publishers (Anthropic, measured 2026-10-08) post news with no RSS or Atom feed but
    list every page in a sitemap, the machine-readable index a site publishes for crawlers.
    The adapter reads the sitemap, takes pages under `include` it has not seen, and reads
    each page's own title, description and publication date. `terms` is the key into
    docs/sources.md, exactly as for a feed.
    """

    url: str
    publisher: str
    terms: str
    # The path prefix of the news pages, for example "/news/". The section's index page
    # itself is never an item.
    include: str
    extract: bool = True

    @field_validator("url")
    @classmethod
    def _https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("sitemap URLs must be https")
        return value

    @field_validator("include")
    @classmethod
    def _path(cls, value: str) -> str:
        if not value.startswith("/") or not value.endswith("/"):
            raise ValueError("include must be a path prefix such as '/news/'")
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
    """Public AT Protocol search terms, and people whose posts are read directly."""

    queries: tuple[str, ...] = ()
    # Handles of people in public roles (reporters, officials, researchers) whose own recent
    # posts are read from their public author feed, as candidates for the day's pick beside
    # the search results (2026-10-13). Replies and reposts are left out.
    people: tuple[str, ...] = ()
    limit: int = Field(default=50, ge=1, le=100)
    # "top" since 2026-10-08. Posts now count only as corroboration of a news story, and the
    # top posts are the substantial ones; "latest" returned the first minutes of replies.
    sort: str = "top"

    @field_validator("sort")
    @classmethod
    def _known_sort(cls, value: str) -> str:
        if value not in {"top", "latest"}:
            raise ValueError("sort must be one of: top, latest")
        return value

    @field_validator("people")
    @classmethod
    def _handles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for handle in value:
            if handle.startswith("@") or not DOMAIN.fullmatch(handle):
                raise ValueError(
                    f"give a Bluesky handle without the @, such as 'name.bsky.social': {handle!r}"
                )
        return value


class XSource(Strict):
    """One X search a day, for the day's single most discussed post (rank/x_pick.py).

    X is read for the pick and nothing else: its posts never join a story, because X's
    display rules allow a post to be shown only whole, never as a quote. Each candidate read
    is billed, so `candidates` is the cost: 10, X's minimum, is about US$0.06 an audience-day
    with the one author lookup. An empty `query` leaves X off for this audience, which is
    the default.

    X's Developer Agreement (section XIV.C) requires an Enterprise plan before X content is
    shown to anyone who is, or acts for, a government body. An audience file for a
    government team leaves `query` empty unless that plan is in place.
    """

    # X's own search syntax. Retweets and replies are excluded, and the audience's language
    # added, by the adapter. `query` names people; `topics` is a second search by subject,
    # for the popular posts of the day from people nobody listed (Peter, 2026-10-15). Each
    # is billed for its own `candidates`.
    query: str = ""
    candidates: int = Field(default=10, ge=10, le=100)
    topics: str = ""
    topic_candidates: int = Field(default=10, ge=10, le=100)

    @field_validator("query", "topics")
    @classmethod
    def _fits(cls, value: str) -> str:
        # X refuses a query over 512 characters; the adapter adds up to about 40.
        if len(value) > 460:
            raise ValueError("an X query must be at most 460 characters")
        return value.strip()

    @property
    def searches(self) -> tuple[tuple[str, int], ...]:
        """Each search a day makes, as (query, posts read). Empty when X is off."""
        return tuple(
            (query, count)
            for query, count in (
                (self.query, self.candidates),
                (self.topics, self.topic_candidates),
            )
            if query
        )

    @property
    def reads(self) -> int:
        """Posts billed a day: the cost of X for this audience, before the author lookup."""
        return sum(count for _, count in self.searches)


class GdeltSource(Strict):
    """GDELT document API queries for global coverage of the audience's entities."""

    queries: tuple[str, ...] = ()
    limit: int = Field(default=75, ge=1, le=250)

    @field_validator("queries")
    @classmethod
    def _or_in_parentheses(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        # GDELT refuses a query with an OR outside parentheses, and it says so only at fetch
        # time: '"large language model" OR "generative AI"' failed every run from 2026-10-07
        # until it was found in the run log on 2026-10-08. Checked here, it fails at load.
        for query in value:
            depth = 0
            for token in (
                re.sub(r'"[^"]*"', '""', query).replace("(", " ( ").replace(")", " ) ").split()
            ):
                depth += {"(": 1, ")": -1}.get(token, 0)
                if token == "OR" and depth == 0:
                    raise ValueError(f"GDELT needs OR'd terms in parentheses: {query!r}")
        return value


class Sources(Strict):
    """Where this audience's pool comes from.

    Any subset may be empty: the pipeline runs with whatever sources are configured, which is
    what makes dropping a source that changes its terms cheap (PLAN.md section 8).
    """

    feeds: tuple[Feed, ...] = ()
    sitemaps: tuple[Sitemap, ...] = ()
    gdelt: GdeltSource = GdeltSource()
    reddit: RedditSource = RedditSource()
    bluesky: BlueskySource = BlueskySource()
    x: XSource = XSource()


class Digest(Strict):
    """Length budget, and how many candidates the model is allowed to see.

    `rerank_candidates` is the cost control of the whole project: the model never sees the
    day's pool, only this many items (PLAN.md section 2.3).
    """

    max_stories: int = Field(default=10, ge=1, le=40)
    rerank_candidates: int = Field(default=60, ge=1, le=200)
    max_sentences_per_story: int = Field(default=3, ge=1, le=10)
    # The lowest rubric score a story may be shown with: 1 "marginal", 2 "relevant", 3 "must
    # read". At 2 a digest shows fewer stories rather than fill its length with marginal ones,
    # which is what an audience of busy readers asked for (the AI audience, 2026-10-10).
    min_rubric_score: int = Field(default=1, ge=1, le=3)
    # How many Bluesky posts, and separately how many X posts, below the stories: each the
    # most engaged the rubric scores at least 2, from different authors. One unless the pool
    # is wide enough to have more worth showing (AI, two since 2026-10-15).
    post_picks: int = Field(default=1, ge=1, le=3)

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
    # The first day whose digest was made under this rubric. Labels and relevance numbers
    # start here: a day judged against a rubric its digest was not chosen by measures the
    # change, not the system.
    measure_from: str | None = None
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

    def terms_keys(self) -> set[str]:
        """Every key this audience needs allowed in docs/sources.md."""
        keys = {feed.terms for feed in self.sources.feeds}
        keys |= {sitemap.terms for sitemap in self.sources.sitemaps}
        if self.sources.gdelt.queries:
            keys.add("gdelt")
        if self.sources.reddit.subreddits:
            keys.add("reddit")
        if self.sources.bluesky.queries or self.sources.bluesky.people:
            keys.add("bluesky")
        if self.sources.x.searches:
            keys.add("x")
        return keys

    def profile_text(self) -> str:
        """The audience as one string, embedded once per run as the ranking target."""
        parts = [self.description, *self.topics, *self.entities.all(), *self.geography]
        return ". ".join(part.strip() for part in parts if part.strip())
