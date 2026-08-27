#!/usr/bin/env python3
"""Deterministic synthetic decisions corpus — carried over at CP-29.

Byte-identical generation to the retired stdio stub's ``decisions.py`` (CP-03,
ADR-0007): same seed, same templates, same rng stream => the same 30
decisions the pinned episodes saw. The only change is the optional ``n``
parameter (defaulting to the same ``N_DECISIONS``) so the service's
``decisions.corpus_size`` config field is honest; ``n == N_DECISIONS``
reproduces the historical corpus exactly.

Each decision's opening sentence embeds a docket reference
`AZ-<year>-<court>-<k>` that is unique to it by construction, so exact-hit
verification needs no fuzzy matching.
"""

from __future__ import annotations

import random

DEFAULT_SEED = 20260204
N_DECISIONS = 30
YEARS = list(range(2019, 2026))
COURTS = ["LG-A", "OLG-B", "BGH-C"]

SUBJECTS = ["freight contract", "warehouse lease", "insurance claim",
            "customs bond", "charter agreement", "salvage award",
            "storage liability", "carriage dispute"]
CHAMBERS = ["first civil", "second civil", "commercial", "maritime",
            "appellate"]
PARTIES = ["claimant", "defendant", "intervener", "guarantor"]
OUTCOMES = ["allowed in part", "dismissed as unfounded",
            "remitted for retrial", "settled by consent", "upheld on appeal"]

OPENING = ("Decision {docket}: the {chamber} chamber of {court} ruled on a "
           "{subject} in {year}.")
BODY_TEMPLATES = [
    "The {party} prevailed on the principal head of claim, with costs "
    "divided {a}:{b}.",
    "An expert opinion on the {subject} was commissioned and adopted in "
    "full.",
    "The court held that notice under the {subject} had been served out of "
    "time.",
    "Security of {amount} marks was ordered pending enforcement.",
    "The counterclaim brought by the {party} was {outcome}.",
    "Interest was awarded at {rate} percent from the date of filing.",
    "The appeal against the interlocutory order was {outcome}.",
    "Witness testimony on the {subject} was found only partially credible.",
]


def decisions_corpus(seed: int = DEFAULT_SEED, n: int = N_DECISIONS) -> list[dict]:
    """The full corpus: [{decision_id, court, year, text}], generation order."""
    rng = random.Random(f"{seed}/decisions")
    counters: dict[tuple[int, str], int] = {}
    corpus: list[dict] = []
    for _ in range(n):
        year = rng.choice(YEARS)
        court = rng.choice(COURTS)
        k = counters[(year, court)] = counters.get((year, court), 0) + 1
        docket = f"AZ-{year}-{court}-{k}"
        subject = rng.choice(SUBJECTS)
        sentences = [OPENING.format(docket=docket, chamber=rng.choice(CHAMBERS),
                                    court=court, subject=subject, year=year)]
        for _ in range(rng.randint(1, 3)):
            sentences.append(rng.choice(BODY_TEMPLATES).format(
                party=rng.choice(PARTIES), subject=subject,
                outcome=rng.choice(OUTCOMES), a=rng.randint(1, 3),
                b=rng.randint(1, 3), amount=rng.randint(2, 80) * 500,
                rate=rng.randint(2, 9)))
        corpus.append({"decision_id": f"D-{year}-{court}-{k}", "court": court,
                       "year": year, "text": " ".join(sentences)})
    return corpus


if __name__ == "__main__":
    for d in decisions_corpus():
        print(f"{d['decision_id']}  [{d['court']} {d['year']}]  {d['text']}")
