"""Loading audience files from a directory.

An audience file is data a department writes, so a bad one fails loudly and names itself.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from clippings.config.audience import Audience

EXAMPLES = Path(__file__).parent / "examples"


class AudienceFileError(ValueError):
    """An audience file that does not load, named so the department can find it."""


def load_audience(path: Path) -> Audience:
    """Load and validate one audience file."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AudienceFileError(f"{path}: not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise AudienceFileError(f"{path}: expected a mapping at the top level")
    try:
        audience = Audience.model_validate(raw)
    except ValidationError as exc:
        raise AudienceFileError(f"{path}: {exc}") from exc
    if audience.id != path.stem:
        raise AudienceFileError(
            f"{path}: id is {audience.id!r} but the file is named {path.stem!r}; "
            "the file name is the audience id"
        )
    return audience


def load_audiences(directory: Path = EXAMPLES) -> tuple[Audience, ...]:
    """Load every audience file in a directory, in file-name order."""
    paths = sorted(p for p in directory.glob("*.yaml") if p.is_file())
    if not paths:
        raise AudienceFileError(f"{directory}: no audience files found")
    return tuple(load_audience(path) for path in paths)
