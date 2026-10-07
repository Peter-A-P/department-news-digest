"""The verifier: every sentence cites, every citation resolves, every quote is verbatim.

PLAN.md section 2.4. It is not optional in production and there is no flag that turns it
off: the only path from a summariser's answer to a digest runs through `verify_story`.

Five checks per sentence, every one of them mechanical, so a sentence that fails is wrong
for a reason anyone can reproduce:

1. **It cites at least one source.** An uncited sentence is the model's own opinion.
2. **Every citation is a source of this story.** The ids are local to the story (`s1`,
   `s2`, ...), so a citation to anything else is an invented citation.
3. **Every quotation mark is paired.** A quote whose extent cannot be read cannot be checked.
4. **Every quote is at most twenty-five words** (`constants.QUOTE_MAX_WORDS`). A digest
   quotes; it does not republish.
5. **Every quote appears verbatim in a source the sentence cites.** Not in any source of
   the story: in one this sentence cites, because a quote attributed to the wrong outlet is
   a wrong citation even when the words exist somewhere.

And one more that is not in the plan's list and earns its place, the same check project 13
found most useful: **every number in the sentence appears in a source it cites.** A summary
that paraphrases well will still write 30 where the source says 60, and that is both the
most damaging error in a news brief and the easiest to catch.

"Verbatim" is defined in `words`: Unicode compatibility folding, case folding, and every run
of punctuation and whitespace treated as one word boundary. So a curly apostrophe matches a
straight one and a line break matches a space, and one word changed, added, dropped or
reordered inside the quotation marks fails. An ellipsis inside a quote fails too, on purpose:
a quote with words left out is not the quote.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from clippings.constants import QUOTE_MAX_WORDS
from clippings.summarise.cite import CitedSentence, Source, StoryDraft

WORD = re.compile(r"\w+")
# A number as written in news copy: 1,200 and 3.5 and 60 are one number each. The comma and
# the point are dropped before comparison, so "1,200" in a sentence matches "1200" in a feed.
NUMBER = re.compile(r"\d[\d,.]*\d|\d")


class Failure(StrEnum):
    """Why a sentence was refused. Each is counted in the published table."""

    UNCITED = "uncited"
    UNKNOWN_CITATION = "citation outside the story"
    UNBALANCED_QUOTES = "unpaired quotation mark"
    QUOTE_TOO_LONG = "quote over twenty-five words"
    QUOTE_NOT_VERBATIM = "quote not verbatim in a cited source"
    NUMBER_NOT_IN_SOURCE = "number not in a cited source"


@dataclass(frozen=True)
class Finding:
    failure: Failure
    detail: str

    def describe(self) -> str:
        return f"{self.failure.value}: {self.detail}" if self.detail else self.failure.value


@dataclass(frozen=True)
class SentenceCheck:
    sentence: CitedSentence
    findings: tuple[Finding, ...]

    @property
    def passed(self) -> bool:
        return not self.findings


@dataclass(frozen=True)
class StoryCheck:
    """Every sentence of one draft, checked."""

    story_id: str
    checks: tuple[SentenceCheck, ...]

    @property
    def kept(self) -> tuple[CitedSentence, ...]:
        return tuple(check.sentence for check in self.checks if check.passed)

    @property
    def failed(self) -> tuple[SentenceCheck, ...]:
        return tuple(check for check in self.checks if not check.passed)

    @property
    def quotes(self) -> int:
        return sum(len(check.sentence.quotes) for check in self.checks)

    @property
    def quotes_verbatim(self) -> int:
        """Quotes that were found verbatim in a cited source, whatever else the sentence did."""
        return sum(
            len(check.sentence.quotes)
            - sum(1 for f in check.findings if f.failure is Failure.QUOTE_NOT_VERBATIM)
            for check in self.checks
        )

    @property
    def cited(self) -> int:
        """Sentences that carried at least one citation, before any were refused."""
        return sum(1 for check in self.checks if check.sentence.cites)


def words(text: str) -> list[str]:
    """The comparison form of a text: folded, cased down, split on everything but letters
    and digits."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    return WORD.findall(folded)


def contains_verbatim(haystack: str, quote: str) -> bool:
    """True when the quote's words appear in the haystack contiguously and in order."""
    needle = words(quote)
    if not needle:
        return False
    hay = words(haystack)
    width = len(needle)
    first = needle[0]
    return any(
        hay[index : index + width] == needle
        for index, word in enumerate(hay[: len(hay) - width + 1])
        if word == first
    )


def numbers(text: str) -> set[str]:
    return {match.group(0).replace(",", "").rstrip(".") for match in NUMBER.finditer(text)}


def verify_sentence(sentence: CitedSentence, sources: Mapping[str, Source]) -> SentenceCheck:
    findings: list[Finding] = []
    if not sentence.cites:
        findings.append(Finding(Failure.UNCITED, ""))
    unknown = [cite for cite in sentence.cites if cite not in sources]
    if unknown:
        findings.append(Finding(Failure.UNKNOWN_CITATION, ", ".join(unknown)))
    cited = [sources[cite] for cite in sentence.cites if cite in sources]
    cited_text = "\n".join(source.text for source in cited)

    if not sentence.balanced:
        findings.append(Finding(Failure.UNBALANCED_QUOTES, ""))
    else:
        for quote in sentence.quotes:
            length = len(words(quote))
            if length > QUOTE_MAX_WORDS:
                findings.append(Finding(Failure.QUOTE_TOO_LONG, f"{length} words"))
            if not cited or not contains_verbatim(cited_text, quote):
                findings.append(Finding(Failure.QUOTE_NOT_VERBATIM, f'"{quote}"'))

    if cited:
        missing = sorted(numbers(sentence.text) - numbers(cited_text))
        if missing:
            findings.append(Finding(Failure.NUMBER_NOT_IN_SOURCE, ", ".join(missing)))
    return SentenceCheck(sentence=sentence, findings=tuple(findings))


def verify_story(draft: StoryDraft, sources: Sequence[Source]) -> StoryCheck:
    by_sid = {source.sid: source for source in sources}
    return StoryCheck(
        story_id=draft.story_id,
        checks=tuple(verify_sentence(sentence, by_sid) for sentence in draft.sentences),
    )
