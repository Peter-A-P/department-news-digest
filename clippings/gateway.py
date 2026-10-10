"""The one place a model call can happen.

Every call in this package goes through `ModelClient.complete`. Two implementations exist:

- `GatewayClient` hands the call to the portfolio gateway, `boundary` (project 04). It is the
  only module in `clippings` that imports `boundary`, and a test asserts that, so there is
  exactly one door a request to a vendor can leave by. Every call declares the `public` data
  class: everything this project sends a model is a published headline, a feed summary or
  text from a page whose terms allowed it.
- `ScriptedClient` answers from a function and has no transport at all. It is what the test
  suite uses, so no test can spend money.

**Spending is two deliberate acts.** `open_client` refuses unless `CLIPPINGS_ALLOW_SPEND` is
set, and the gateway then refuses any call that would pass a cap in `caps.yaml`. The first is
the switch a person flips; the second is the limit that holds when nobody is watching.

**Cost per digest comes from the ledger.** Each reply carries the gateway's `call_uid` and
cost, the store keeps one row per call joined on that uid, and the purpose written to the
ledger names the audience, so `boundary ledger report` and this project's own report can be
checked against each other.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

from boundary import BoundaryError, ChatRequest, DataClass, Gateway, SpendCapExceeded

from clippings.constants import GATEWAY_DATA_CLASS, GATEWAY_PROJECT

CONFIG = Path(__file__).resolve().parent / "config" / "gateway" / "boundary.yaml"

# The switch. Unset, the pipeline stops after the free ranking stage and says so.
ALLOW_SPEND_ENV = "CLIPPINGS_ALLOW_SPEND"


class Purpose(StrEnum):
    """What a call is for. Each maps to one alias in the gateway configuration."""

    RERANK = "rerank"
    SUMMARISE = "summarise"
    REPAIR = "repair"
    # Scoring the day's most discussed Bluesky posts against the rubric (rank/spotlight.py).
    SPOTLIGHT = "spotlight"


ALIASES: dict[Purpose, str] = {
    Purpose.RERANK: "clippings-rerank",
    Purpose.SUMMARISE: "clippings-summarise",
    Purpose.REPAIR: "clippings-repair",
    # The same small classifier as re-ranking: it is a score per line against the rubric.
    Purpose.SPOTLIGHT: "clippings-rerank",
}


class SpendNotAllowed(RuntimeError):
    """A model call was asked for without the spend switch set."""


class SpendCapReached(RuntimeError):
    """The gateway refused a call because it would pass a cap. No request was made.

    Raised rather than recorded: a cap being hit says the run should stop, and carrying on
    would write a refusal into every remaining story.
    """


class ModelCallFailed(RuntimeError):
    """The call was made and failed after the gateway's retries, or was refused upstream.

    The pipeline treats this as one story or one stage failing, not the run: a timeout says
    nothing about the next story.
    """


@dataclass(frozen=True, slots=True)
class ModelCall:
    """One request, and who it is for."""

    purpose: Purpose
    audience_id: str
    system: str
    user: str
    max_tokens: int = 1024
    # None leaves it to the model's default and sends nothing. Sonnet 5.5 refuses the field
    # outright ("`temperature` is deprecated for this model", HTTP 400, found on the first
    # live run, 2026-10-07), so it is opt-in per call rather than a default every call sends.
    temperature: float | None = None

    @property
    def ledger_purpose(self) -> str:
        """The purpose column in the gateway's ledger: what, and for which audience."""
        return f"{self.purpose.value}/{self.audience_id}"


@dataclass(frozen=True, slots=True)
class ModelReply:
    """One answer, and what it cost."""

    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    # The gateway's identifier for the row it wrote, which survives a ledger merge. None for
    # a scripted reply, which wrote no row.
    call_uid: str | None = None
    finish_reason: str | None = None


@runtime_checkable
class ModelClient(Protocol):
    """What every model-calling stage is given. Nothing reaches a vendor another way."""

    @property
    def name(self) -> str:
        """What goes in the run record next to the numbers this client produced."""
        ...

    def complete(self, call: ModelCall, *, run_id: str) -> ModelReply: ...


@dataclass
class GatewayClient:
    """Calls a vendor through `boundary`, declaring the public data class on every call."""

    gateway: Gateway

    @property
    def name(self) -> str:
        return f"boundary gateway, project {GATEWAY_PROJECT}, data class {GATEWAY_DATA_CLASS}"

    def complete(self, call: ModelCall, *, run_id: str) -> ModelReply:
        request = ChatRequest(
            model=ALIASES[call.purpose],
            system=call.system,
            messages=[{"role": "user", "content": call.user}],
            max_tokens=call.max_tokens,
            temperature=call.temperature,
        )
        try:
            response = self.gateway.chat(
                request,
                purpose=call.ledger_purpose,
                run_id=run_id,
                data_class=DataClass(GATEWAY_DATA_CLASS),
            )
        except SpendCapExceeded as exc:
            raise SpendCapReached(
                f"{exc.scope} cap of US${exc.cap_usd:.2f} reached "
                f"(spent US${exc.spent_usd:.4f}, this call estimated US${exc.estimate_usd:.4f})"
            ) from exc
        except BoundaryError as exc:
            raise ModelCallFailed(f"{call.ledger_purpose}: {type(exc).__name__}: {exc}") from exc
        if not response.ok or response.text is None:
            raise ModelCallFailed(f"{call.ledger_purpose}: status {response.status}, no text")
        return ModelReply(
            text=response.text,
            model=response.model_returned or response.model_requested,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_usd=response.cost_usd,
            call_uid=response.call_uid,
            finish_reason=response.finish_reason,
        )

    def close(self) -> None:
        self.gateway.close()


@dataclass
class ScriptedClient:
    """Answers from a function of the call. No transport, no ledger, no cost.

    `calls` records every call in order, which is how the tests assert what the model was
    shown: that the re-ranker never sees more than the candidate slice, and that repair runs
    at most once.
    """

    answer: Callable[[ModelCall], str]
    calls: list[ModelCall] = field(default_factory=list)

    @property
    def name(self) -> str:
        return "scripted (no model)"

    def complete(self, call: ModelCall, *, run_id: str) -> ModelReply:
        self.calls.append(call)
        return ModelReply(text=self.answer(call), model="scripted")


def spend_allowed() -> bool:
    return os.environ.get(ALLOW_SPEND_ENV, "").strip().lower() in {"1", "true", "yes"}


def open_client(*, ledger_path: Path | None = None, config: Path = CONFIG) -> GatewayClient:
    """A gateway client, or a refusal saying what is missing.

    Constructing the gateway reads the configuration and the caps and opens the ledger; it
    does not make a call.
    """
    if not spend_allowed():
        raise SpendNotAllowed(
            f"model calls spend money; set {ALLOW_SPEND_ENV}=1 to allow them, and check the "
            f"caps in {config.parent / 'caps.yaml'} are what you meant"
        )
    gateway = Gateway.from_config(config, project=GATEWAY_PROJECT, ledger_path=ledger_path)
    return GatewayClient(gateway=gateway)
