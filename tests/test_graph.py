"""The whole graph for one audience's day, with a scripted model and no network.

What it pins down: the model is shown the candidate slice and never the pool, the summariser
is called once per chosen story, repair runs at most once per story whatever the repair
returns, a refused sentence never reaches the page, and the run ends in files written, not
anything sent.
"""

from __future__ import annotations

import json
import re
from email import message_from_bytes
from email.policy import default
from pathlib import Path

import pytest

from clippings import graph
from clippings.cluster.embed import Hashing
from clippings.config.audience import Audience, Digest
from clippings.gateway import ModelCall, Purpose, ScriptedClient
from clippings.graph import Pipeline
from clippings.ingest.store import Store
from clippings.sources.base import FetchContext
from tests.test_pipeline import FixtureSource, raw_item, result

HEADLINES = [
    (
        "https://gov.example/budget",
        "Council passes the transit budget",
        "Council approved the transit budget of 40 million on Tuesday.",
    ),
    (
        "https://gov.example/crash",
        "Fatal collision on the parkway",
        "Police said one person died in a collision.",
    ),
    (
        "https://gov.example/ferry",
        "Ferry service cut for the winter",
        "The operator said the ferry would run twice a week from December.",
    ),
    (
        "https://gov.example/film",
        "Film star visits the festival",
        "A film star visited the festival on Saturday.",
    ),
    (
        "https://gov.example/school",
        "School board closes two schools",
        "The board voted to close two schools in June.",
    ),
    (
        "https://gov.example/clinic",
        "Clinic hours extended",
        "The health authority extended clinic hours to 9 pm.",
    ),
]
EXCLUDED = {"Fatal collision on the parkway", "Film star visits the festival"}


def candidate_titles(call: ModelCall) -> dict[str, str]:
    """The candidate lines the re-ranker was shown: local id to headline."""
    shown = {}
    for line in call.user.splitlines():
        match = re.match(r"^(c\d+) \| [^|]+ \| ([^|]+)", line)
        if match:
            shown[match.group(1)] = match.group(2).strip()
    return shown


def source_titles(call: ModelCall) -> list[str]:
    return re.findall(r"^\[s\d+\] [^\n]+\n([^\n]+)", call.user, flags=re.MULTILINE)


class Model:
    """A scripted model with a policy per purpose, and a record of what it was asked."""

    def __init__(self, *, misquote_first: bool = False, repair_fixes: bool = True) -> None:
        self.misquote_first = misquote_first
        self.repair_fixes = repair_fixes

    def __call__(self, call: ModelCall) -> str:
        if call.purpose is Purpose.RERANK:
            return "\n".join(
                json.dumps({"id": cid, "score": 0 if title in EXCLUDED else 2, "reason": "r"})
                for cid, title in candidate_titles(call).items()
            )
        title = source_titles(call)[0]
        good = {"text": f'The report is headed "{title}".', "sources": ["s1"]}
        bad = {"text": f'The report is headed "{title} today".', "sources": ["s1"]}
        if call.purpose is Purpose.SUMMARISE:
            first = bad if self.misquote_first else good
            return json.dumps({"sentences": [first, {"text": "Uncited opinion.", "sources": []}]})
        return json.dumps({"sentences": [good if self.repair_fixes else bad]})


@pytest.fixture
def small_audience(audience: Audience) -> Audience:
    return audience.model_copy(
        update={"digest": Digest(max_stories=2, rerank_candidates=4, max_sentences_per_story=3)}
    )


def run(
    audience: Audience, store: Store, context: FetchContext, client: ScriptedClient, site: Path
) -> graph.State:
    from clippings.assemble.publish import LocalSite

    source = FixtureSource(
        result(*(raw_item(url, title, summary) for url, title, summary in HEADLINES))
    )
    return graph.run(
        Pipeline(
            audience=audience,
            store=store,
            context=context,
            embedder=Hashing(),
            run_id="20260912T120000Z-test",
            client=client,
            site=LocalSite(site),
            sources=(source,),
            extract=False,
        )
    )


def test_the_model_sees_the_slice_and_the_digest_obeys_the_rubric(
    small_audience: Audience, store: Store, context: FetchContext, tmp_path: Path
) -> None:
    client = ScriptedClient(Model())
    state = run(small_audience, store, context, client, tmp_path)

    reranks = [call for call in client.calls if call.purpose is Purpose.RERANK]
    assert len(reranks) == 1
    assert len(candidate_titles(reranks[0])) == 4, "the re-ranker sees rerank_candidates, no more"
    summaries = [call for call in client.calls if call.purpose is Purpose.SUMMARISE]
    assert len(summaries) == 2, "one summary call per chosen story"

    digest = state["digest"]
    assert len(digest.stories) <= 2
    assert not {story.headline for story in digest.stories} & EXCLUDED
    assert digest.reranked
    assert store.digest_for(small_audience.id, digest.day) == digest
    assert store.ranking_for(small_audience.id, digest.day)[:1] == [digest.stories[0].story_id]


def test_a_refused_sentence_never_reaches_the_page(
    small_audience: Audience, store: Store, context: FetchContext, tmp_path: Path
) -> None:
    state = run(small_audience, store, context, ScriptedClient(Model()), tmp_path)
    digest = state["digest"]
    for story in digest.stories:
        assert [s.text for s in story.sentences] == [f'The report is headed "{story.headline}".']
    page = (tmp_path / small_audience.id / digest.day / "index.html").read_text()
    assert "Uncited opinion" not in page
    assert digest.counts.refusals == {"uncited": 2}


def test_repair_fixes_a_misquote_and_is_counted(
    small_audience: Audience, store: Store, context: FetchContext, tmp_path: Path
) -> None:
    client = ScriptedClient(Model(misquote_first=True, repair_fixes=True))
    digest = run(small_audience, store, context, client, tmp_path)["digest"]
    counts = digest.counts
    assert (counts.quotes_first, counts.quotes_verbatim_first) == (2, 0)
    assert (counts.quotes_after_repair, counts.quotes_verbatim_after_repair) == (2, 2)
    assert counts.sentences_repaired_ok == 2
    assert counts.sentences_dropped == 2, "the uncited sentences are not rewritten into being"
    assert all(story.status == "repaired" for story in digest.stories)


def test_repair_runs_once_and_a_second_failure_is_dropped(
    small_audience: Audience, store: Store, context: FetchContext, tmp_path: Path
) -> None:
    client = ScriptedClient(Model(misquote_first=True, repair_fixes=False))
    state = run(small_audience, store, context, client, tmp_path)
    repairs = [call for call in client.calls if call.purpose is Purpose.REPAIR]
    assert len(repairs) == len(state["digest"].stories), "one repair per story, never a second"
    assert all(not story.sentences for story in state["digest"].stories)
    assert state["trace"].count("verify:0 kept") == 2


def test_the_run_ends_in_files_not_messages(
    small_audience: Audience, store: Store, context: FetchContext, tmp_path: Path
) -> None:
    state = run(small_audience, store, context, ScriptedClient(Model()), tmp_path)
    day = state["digest"].day
    folder = tmp_path / small_audience.id / day
    assert sorted(path.name for path in folder.iterdir()) == [
        "digest.eml",
        "digest.md",
        "index.html",
    ]

    draft = message_from_bytes((folder / "digest.eml").read_bytes(), policy=default)
    assert draft["X-Unsent"] == "1"
    assert draft["To"] is None and draft["Cc"] is None and draft["Bcc"] is None
    assert draft["From"] is None


def test_without_a_model_client_the_run_stops_after_the_free_stages(
    small_audience: Audience, store: Store, context: FetchContext, tmp_path: Path
) -> None:
    from clippings.assemble.publish import LocalSite

    source = FixtureSource(
        result(*(raw_item(url, title, summary) for url, title, summary in HEADLINES))
    )
    state = graph.run(
        Pipeline(
            audience=small_audience,
            store=store,
            context=context,
            embedder=Hashing(),
            run_id="r",
            client=None,
            site=LocalSite(tmp_path),
            sources=(source,),
            extract=False,
        )
    )
    assert "digest" not in state
    assert state["trace"][-1] == "stop:no model client"
    assert len(state["report"].selected) == 2
    assert not any(tmp_path.iterdir())


def test_a_day_with_nothing_to_rank_publishes_an_empty_digest(
    small_audience: Audience, store: Store, context: FetchContext, tmp_path: Path
) -> None:
    # Nothing new to rank, as public health had on 2026-10-25: the run must still publish
    # the day's (empty) digest rather than stop.
    from clippings.assemble.publish import LocalSite

    state = graph.run(
        Pipeline(
            audience=small_audience,
            store=store,
            context=context,
            embedder=Hashing(),
            run_id="20260912T120000Z-test",
            client=ScriptedClient(Model()),
            site=LocalSite(tmp_path),
            sources=(FixtureSource(result()),),
            extract=False,
        )
    )
    assert not state["report"].ranked
    digest = store.digest_for(small_audience.id, "2026-09-12")
    assert digest is not None and digest.stories == ()


def test_saving_an_empty_ranking_is_a_no_op(store: Store) -> None:
    store.save_ranking("a", "2026-10-25", "r", [])
    assert store.ranking_for("a", "2026-10-25") == []
