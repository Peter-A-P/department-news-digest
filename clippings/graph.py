"""The pipeline as a graph: fetch to publish for one audience's day.

PLAN.md section 4. There is no send node, and nothing a node here can reach opens a mail
connection; `tests/test_no_send.py` asserts that against the import graph.

    ingest -> rank -+- no model client -------------------------------------------> END
                    +- rerank -> select -> summarise -> verify -+- refused, first pass -> repair -> verify
                                                                +- otherwise -> assemble -> publish -> END

Two properties the shape gives, rather than code inside a node:

- **The model never sees the pool.** `rank` is the last node that holds it; `rerank` is
  handed the candidate slice and nothing else, and `summarise` the chosen stories.
- **Repair runs at most once.** The only edge into `repair` is from `verify` when a story
  has a refused sentence and has not been repaired, and repairing marks it repaired. The
  second `verify` therefore always goes on to `assemble`.

The state is a plain TypedDict and every node is an ordinary function of it, so a node can be
tested without the graph. Every decision lives in the functions the nodes call
(`ingest.pipeline`, `rank`, `summarise`, `assemble`); the graph decides only what runs next.
"""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, TypedDict

from clippings.assemble.digest import Digest, build_digest
from clippings.assemble.publish import Site, publish_digest
from clippings.cluster.embed import Embedder
from clippings.config.audience import Audience
from clippings.gateway import ModelClient
from clippings.ingest.pipeline import RunReport, choose, ingest, rank_day
from clippings.ingest.store import Store
from clippings.models import Item
from clippings.rank.rerank import Rerank, rerank
from clippings.rank.score import ScoredStory
from clippings.rank.select import candidates_for_rerank
from clippings.sources.base import FetchContext, Source
from clippings.summarise.run import (
    StoryWork,
    any_need_repair,
    draft_all,
    prepare,
    repair_all,
    verify_all,
)

# langgraph imports a langchain serializer that warns, at import, about a default it never
# uses here: no checkpointer is configured, so no pipeline state is ever serialised. Silenced
# for this one import and by its message, so any other warning still shows.
# langgraph carries LangSmith's tracing client, which sends a run's state, prompts included,
# to a third-party service when an environment variable asks it to. Nothing in this project
# leaves the machine except through the gateway and the publishers' own feeds, so tracing is
# switched off here, whatever the environment says.
for _variable in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING"):
    os.environ[_variable] = "false"

with warnings.catch_warnings():
    # langchain_core un-mutes its own warnings when it is imported, which would put its rule
    # ahead of this one, so it is imported first and the rule added after it.
    import langchain_core._api.deprecation  # noqa: F401

    warnings.filterwarnings("ignore", message="The default value of `allowed_objects`")
    from langgraph.graph import END, START, StateGraph


@dataclass
class Pipeline:
    """What the graph runs against. Constructing one reaches no network and spends nothing."""

    audience: Audience
    store: Store
    context: FetchContext
    embedder: Embedder
    run_id: str
    client: ModelClient | None = None
    site: Site | None = None
    sources: tuple[Source, ...] | None = None
    extract: bool = True
    window_hours: int = 48

    @property
    def day(self) -> str:
        return self.context.now.date().isoformat()


class State(TypedDict, total=False):
    pipeline: Pipeline
    report: RunReport
    pool: dict[str, Item]
    candidates: tuple[ScoredStory, ...]
    rerank: Rerank
    chosen: tuple[ScoredStory, ...]
    works: list[StoryWork]
    digest: Digest
    published: list[str]
    trace: tuple[str, ...]


def _trace(state: State, step: str) -> tuple[str, ...]:
    return (*state.get("trace", ()), step)


def node_ingest(state: State) -> State:
    p = state["pipeline"]
    report = ingest(p.audience, p.store, p.context, run_id=p.run_id, sources=p.sources)
    return {"report": report, "trace": _trace(state, f"ingest:{report.new_items} new")}


def node_rank(state: State) -> State:
    """Cluster and score the pool, then cut the slice a model may see."""
    p = state["pipeline"]
    report = state["report"]
    pool = rank_day(
        p.audience,
        p.store,
        p.context,
        p.embedder,
        report,
        extract=p.extract,
        window_hours=p.window_hours,
    )
    candidates = candidates_for_rerank(report.ranked, p.audience.digest.rerank_candidates)
    return {
        "pool": pool,
        "candidates": candidates,
        "trace": _trace(state, f"rank:{len(report.ranked)} stories, {len(candidates)} candidates"),
    }


def after_rank(state: State) -> Literal["rerank", "stop"]:
    """No client means no model may be called: stop with the free stages' report."""
    return "rerank" if state["pipeline"].client is not None else "stop"


def node_stop(state: State) -> State:
    """The pre-filter's own choice, so a run without a model still says what it would show."""
    p = state["pipeline"]
    report = state["report"]
    selection = choose(
        state["candidates"], state["pool"], p.embedder, p.audience.digest.max_stories
    )
    report.selected = list(selection.stories)
    report.displaced = len(selection.displaced)
    _save_ranking(p, report.ranked, None)
    report.finished_at = datetime.now(UTC)
    return {"trace": _trace(state, "stop:no model client")}


def node_rerank(state: State) -> State:
    p = state["pipeline"]
    assert p.client is not None
    result = rerank(p.audience, state["candidates"], p.client, run_id=p.run_id)
    _save_ranking(p, state["report"].ranked, result)
    step = "rerank:ok" if result.reranked else f"rerank:failed ({result.error})"
    return {"rerank": result, "trace": _trace(state, step)}


def node_select(state: State) -> State:
    """K stories from what the re-ranker did not exclude, with the diversity penalty."""
    p = state["pipeline"]
    result = state["rerank"]
    selection = choose(
        result.selectable(),
        state["pool"],
        p.embedder,
        p.audience.digest.max_stories,
        tiers=result.tiers() if result.reranked else None,
    )
    report = state["report"]
    report.selected = list(selection.stories)
    report.displaced = len(selection.displaced)
    return {
        "chosen": selection.stories,
        "trace": _trace(state, f"select:{len(selection.stories)}"),
    }


def node_summarise(state: State) -> State:
    p = state["pipeline"]
    assert p.client is not None
    chosen = state["chosen"]
    texts = p.store.texts_for(item_id for story in chosen for item_id in story.cluster.item_ids)
    works = prepare(chosen, state["pool"], texts, p.audience)
    draft_all(works, p.audience, p.client, run_id=p.run_id)
    return {"works": works, "trace": _trace(state, f"summarise:{len(works)}")}


def node_verify(state: State) -> State:
    works = state["works"]
    verify_all(works)
    kept = sum(len(work.kept) for work in works)
    return {"works": works, "trace": _trace(state, f"verify:{kept} kept")}


def after_verify(state: State) -> Literal["repair", "assemble"]:
    return "repair" if any_need_repair(state["works"]) else "assemble"


def node_repair(state: State) -> State:
    p = state["pipeline"]
    assert p.client is not None
    works = state["works"]
    repair_all(works, p.audience, p.client, run_id=p.run_id)
    repaired = sum(1 for work in works if work.repaired is not None)
    return {"works": works, "trace": _trace(state, f"repair:{repaired}")}


def node_assemble(state: State) -> State:
    p = state["pipeline"]
    report = state["report"]
    digest = build_digest(
        p.audience,
        day=p.day,
        run_id=p.run_id,
        generated_at=datetime.now(UTC),
        works=state["works"],
        rerank=state.get("rerank"),
        pool_items=report.clustered_items,
        pool_stories=report.clusters,
        embedder=report.embedder,
        model_client=p.client.name if p.client is not None else "none",
    )
    p.store.save_digest(digest)
    report.finished_at = datetime.now(UTC)
    return {"digest": digest, "trace": _trace(state, f"assemble:{len(digest.stories)} stories")}


def node_publish(state: State) -> State:
    """Write the page, the Markdown and the draft file. Writing, not sending."""
    p = state["pipeline"]
    if p.site is None:
        return {"published": [], "trace": _trace(state, "publish:no site")}
    paths = publish_digest(p.site, state["digest"])
    return {"published": paths, "trace": _trace(state, f"publish:{len(paths)} files")}


def _save_ranking(p: Pipeline, ranked: list[ScoredStory], result: Rerank | None) -> None:
    """The order the system put the whole pool in: the re-ranked candidates, then the rest
    in pre-filter order. This is what the labelling sample's top stratum is drawn from."""
    rows: list[tuple[str, float, int | None, float, str]] = []
    seen: set[str] = set()
    if result is not None:
        by_id = {score.story_id: score for score in result.scores}
        for story in result.stories:
            score = by_id[story.id]
            rows.append((story.id, score.prefilter, score.model_score, score.final, score.reason))
            seen.add(story.id)
    rows.extend(
        (story.id, story.score, None, story.score, "") for story in ranked if story.id not in seen
    )
    p.store.save_ranking(p.audience.id, p.day, p.run_id, rows)


def build_graph() -> Any:
    """The compiled graph. `Any` because langgraph's compiled type is generic over internals
    this package does not need to name."""
    graph = StateGraph(State)
    graph.add_node("ingest", node_ingest)
    graph.add_node("rank", node_rank)
    graph.add_node("stop", node_stop)
    graph.add_node("rerank", node_rerank)
    graph.add_node("select", node_select)
    graph.add_node("summarise", node_summarise)
    graph.add_node("verify", node_verify)
    graph.add_node("repair", node_repair)
    graph.add_node("assemble", node_assemble)
    graph.add_node("publish", node_publish)

    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", "rank")
    graph.add_conditional_edges("rank", after_rank, {"rerank": "rerank", "stop": "stop"})
    graph.add_edge("stop", END)
    graph.add_edge("rerank", "select")
    graph.add_edge("select", "summarise")
    graph.add_edge("summarise", "verify")
    graph.add_conditional_edges(
        "verify", after_verify, {"repair": "repair", "assemble": "assemble"}
    )
    graph.add_edge("repair", "verify")
    graph.add_edge("assemble", "publish")
    graph.add_edge("publish", END)
    return graph.compile()


def run(pipeline: Pipeline) -> State:
    """One audience's day through the graph."""
    result: State = build_graph().invoke({"pipeline": pipeline, "trace": ()})
    return result
