"""Near-duplicate detection by MinHash over word shingles.

The same wire story runs in twenty outlets with the headline changed and a paragraph cut.
That is a near-duplicate, and collapsing it is cheap: shingle the text, estimate Jaccard
similarity from a small signature, and only compare pairs that share a band.

Written here rather than taken from a library because the whole of it is forty lines, the
hashing has to be deterministic across runs and machines for the stored clusters to mean
anything, and the deduplication numbers this project publishes should be reproducible from
code a reader can see.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence

# A 61-bit Mersenne prime: big enough that the permutations behave, small enough to stay in
# machine words.
MERSENNE = (1 << 61) - 1
MAX_HASH = (1 << 32) - 1

DEFAULT_PERMUTATIONS = 128
DEFAULT_BANDS = 32
DEFAULT_SHINGLE = 5
# Above this estimated Jaccard similarity two items are the same story told twice. Chosen
# to be strict: a missed duplicate costs one repeated item in a digest, a wrong merge hides
# a story entirely, and the labelled pairs measure both.
DEFAULT_THRESHOLD = 0.7

WORD = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    """Lower-case word tokens. Punctuation and case differ between outlets; words do not."""
    return WORD.findall(text.lower())


def shingles(text: str, size: int = DEFAULT_SHINGLE) -> frozenset[str]:
    """Overlapping word n-grams.

    Short text yields whatever it has rather than nothing, so a headline-only item still
    has a signature.
    """
    words = tokens(text)
    if len(words) < size:
        return frozenset({" ".join(words)}) if words else frozenset()
    return frozenset(
        " ".join(words[index : index + size]) for index in range(len(words) - size + 1)
    )


def _hash(shingle: str) -> int:
    """A stable 32-bit hash. `hash()` is salted per process and cannot be used here."""
    digest = hashlib.blake2b(shingle.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big")


def _coefficients(permutations: int) -> list[tuple[int, int]]:
    """Deterministic (a, b) pairs for the universal hash family h(x) = (a*x + b) mod p.

    Derived from a fixed digest rather than a random generator so that a signature computed
    today matches one computed next month on another machine.
    """
    pairs: list[tuple[int, int]] = []
    for index in range(permutations):
        digest = hashlib.blake2b(f"clippings/minhash/{index}".encode(), digest_size=16).digest()
        a = int.from_bytes(digest[:8], "big") % (MERSENNE - 1) + 1
        b = int.from_bytes(digest[8:], "big") % MERSENNE
        pairs.append((a, b))
    return pairs


COEFFICIENTS = _coefficients(DEFAULT_PERMUTATIONS)


def signature(text: str, permutations: int = DEFAULT_PERMUTATIONS) -> tuple[int, ...]:
    """The MinHash signature of a piece of text."""
    grams = shingles(text)
    if not grams:
        return tuple(MAX_HASH for _ in range(permutations))
    hashed = [_hash(gram) for gram in grams]
    return tuple(
        min((a * value + b) % MERSENNE % MAX_HASH for value in hashed)
        for a, b in COEFFICIENTS[:permutations]
    )


def similarity(left: Sequence[int], right: Sequence[int]) -> float:
    """The estimated Jaccard similarity of two signatures."""
    if not left or not right:
        return 0.0
    agree = sum(1 for a, b in zip(left, right, strict=True) if a == b)
    return agree / len(left)


def candidate_pairs(
    signatures: dict[str, tuple[int, ...]], bands: int = DEFAULT_BANDS
) -> set[tuple[str, str]]:
    """Pairs that agree on a whole band, which is what makes this cheaper than all-pairs.

    With 128 permutations in 32 bands of 4, a pair at 0.7 similarity shares a band with
    probability about 0.996, and a pair at 0.3 with probability about 0.25, which the exact
    similarity check then discards.
    """
    if not signatures:
        return set()
    width = len(next(iter(signatures.values()))) // bands
    if width < 1:
        raise ValueError("more bands than permutations")
    pairs: set[tuple[str, str]] = set()
    for band in range(bands):
        buckets: dict[tuple[int, ...], list[str]] = {}
        start = band * width
        for key, values in signatures.items():
            buckets.setdefault(values[start : start + width], []).append(key)
        for members in buckets.values():
            if len(members) < 2:
                continue
            members.sort()
            for index, left in enumerate(members):
                for right in members[index + 1 :]:
                    pairs.add((left, right))
    return pairs


def near_duplicates(
    texts: dict[str, str],
    threshold: float = DEFAULT_THRESHOLD,
    bands: int = DEFAULT_BANDS,
) -> set[tuple[str, str]]:
    """Every pair of ids whose texts are near-duplicates of one another."""
    signatures = {key: signature(text) for key, text in texts.items()}
    return {
        pair
        for pair in candidate_pairs(signatures, bands)
        if similarity(signatures[pair[0]], signatures[pair[1]]) >= threshold
    }


def connected_components(keys: Iterable[str], pairs: Iterable[tuple[str, str]]) -> list[list[str]]:
    """Group ids joined by pairs, transitively. Union-find without the class."""
    parent: dict[str, str] = {key: key for key in keys}

    def find(key: str) -> str:
        root = key
        while parent[root] != root:
            root = parent[root]
        while parent[key] != root:
            parent[key], key = root, parent[key]
        return root

    for left, right in pairs:
        if left not in parent or right not in parent:
            continue
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    groups: dict[str, list[str]] = {}
    for key in parent:
        groups.setdefault(find(key), []).append(key)
    return [sorted(members) for members in groups.values()]
