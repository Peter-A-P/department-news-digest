"""The bills the gateway's ledger does not see: the cloud and X.

Model calls are costed per call from the gateway's ledger. Two other things cost money and
are billed elsewhere: Google Cloud (the job, the service, the bucket and the schedules), and
X's pay-per-use API for the day's X pick. Their totals are read by hand from each vendor's
own billing page and recorded in `docs/bills.yaml`, with the period, the page and the day
it was read, so the figure in the README is reproducible from the repository and a reader
can see where it came from.

A bill is a total the vendor charged, not an estimate from a sample, so it carries no
interval. It is spread over the days the service ran in the period to give a cost a day.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from clippings.constants import CAD_PER_USD

BILLS = Path("docs/bills.yaml")


class Bill(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    # The days the service ran within the billed period; the cost a day divides by these.
    first_day: date
    last_day: date
    amount: float = Field(ge=0)
    currency: Literal["USD", "CAD"]
    # Where the total was read, and when.
    source: str
    read_on: date
    note: str = ""

    @model_validator(mode="after")
    def _ordered(self) -> Bill:
        if self.last_day < self.first_day:
            raise ValueError(f"{self.name}: last_day is before first_day")
        return self

    @property
    def days(self) -> int:
        return (self.last_day - self.first_day).days + 1

    @property
    def cad(self) -> float:
        return self.amount * CAD_PER_USD if self.currency == "USD" else self.amount

    @property
    def cad_per_day(self) -> float:
        return self.cad / self.days


def load_bills(path: Path = BILLS) -> list[Bill]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [Bill.model_validate(entry) for entry in raw]
