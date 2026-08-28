#!/usr/bin/env python3
"""B4 drift: do CARA standards move over time?

Fit on pre-2010 films, test on post-2015 (Year Rated where the register
gave it, release year otherwise), and compare against the same-size
random-split baseline. Degradation across the boundary = standards moved,
and by how much — evidence for recency weighting instead of a guess.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from rating_model import CLASSES, featurize, fit, predict, split_key  # noqa: E402

SRC = ROOT / ".cache" / "ratings_ingest" / "descriptor_table.json"


def year_of(f: dict) -> int:
    yr = str(f.get("year_rated") or "")
    return int(yr) if yr.isdigit() else int(f["year"])


def evaluate(w, xs, ys, idxs) -> float:
    ok = 0
    for i in idxs:
        p = predict(w, xs[i])
        ok += max(range(len(CLASSES)), key=lambda c: p[c]) == ys[i]
    return ok / len(idxs)


def main() -> int:
    films = [f for f in json.loads(SRC.read_text())["films"] if f["rating"] in CLASSES]
    _feats, xs, ys = featurize(films)
    years = [year_of(f) for f in films]

    old_i = [i for i, y in enumerate(years) if y < 2010]
    new_i = [i for i, y in enumerate(years) if y >= 2015]
    print(f"pre-2010: {len(old_i)} films | post-2015: {len(new_i)} films")

    w_old = fit([xs[i] for i in old_i], [ys[i] for i in old_i], len(CLASSES))
    acc_cross = evaluate(w_old, xs, ys, new_i)

    # baseline: random split of the SAME training size, tested in-era
    keys = [split_key(f["title"]) for f in films]
    # order by the deterministic hash, not list order — the films list is not
    # randomly ordered, and a truncated head is a biased training sample
    pool = sorted((i for i, k in enumerate(keys) if k < 0.8), key=lambda i: keys[i])
    tr = pool[: len(old_i)]
    te = [i for i, k in enumerate(keys) if k >= 0.8]
    w_rand = fit([xs[i] for i in tr], [ys[i] for i in tr], len(CLASSES))
    acc_base = evaluate(w_rand, xs, ys, te)

    drift = acc_base - acc_cross
    print(f"in-era baseline accuracy:      {acc_base:.3f}")
    print(f"pre-2010 -> post-2015 accuracy: {acc_cross:.3f}")
    print(
        f"drift penalty: {drift:+.3f} "
        + (
            "(standards moved — weight recency)"
            if drift > 0.02
            else "(stable — recency weighting optional)"
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
