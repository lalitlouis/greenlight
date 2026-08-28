#!/usr/bin/env python3
"""B2+B3+B4: fit descriptors -> rating, wrap in Mondrian split conformal,
report Brier and a reliability table. Pure Python (no numpy/sklearn): ~1-6k
rows x ~80 features needs nothing more, and the runtime stays dependency-free
— coefficients ship as data, inference is a dot product.

  .venv/bin/python scripts/rating_model.py
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / ".cache" / "ratings_ingest" / "descriptor_table.json"
OUT = ROOT / ".cache" / "ratings_ingest" / "rating_model.json"

CLASSES = ["G", "PG", "PG-13", "R", "NC-17"]
ALPHA = 0.10  # 90% target coverage
EPOCHS, LR, L2 = 220, 0.25, 1e-3
MIN_FEATURE_N = 8


def featurize(films: list[dict]) -> tuple[list[str], list[list[float]], list[int]]:
    counts: Counter = Counter()
    for f in films:
        for intensity, cat in f["pairs"]:
            counts[f"{intensity} {cat}"] += 1
            counts[cat] += 1
    feats = sorted(k for k, n in counts.items() if n >= MIN_FEATURE_N)
    idx = {k: i for i, k in enumerate(feats)}
    xs, ys = [], []
    for f in films:
        v = [0.0] * (len(feats) + 1)
        v[-1] = 1.0  # bias
        for intensity, cat in f["pairs"]:
            for key in (f"{intensity} {cat}", cat):
                if key in idx:
                    v[idx[key]] = 1.0
        xs.append(v)
        ys.append(CLASSES.index(f["rating"]))
    return feats, xs, ys


def softmax(z: list[float]) -> list[float]:
    m = max(z)
    e = [math.exp(x - m) for x in z]
    s = sum(e)
    return [x / s for x in e]


def fit(xs: list[list[float]], ys: list[int], k: int) -> list[list[float]]:
    d = len(xs[0])
    w = [[0.0] * d for _ in range(k)]
    n = len(xs)
    order = list(range(n))
    rng = random.Random(7)
    for _ in range(EPOCHS):
        rng.shuffle(order)
        for i in order:
            x, y = xs[i], ys[i]
            p = softmax([sum(wc[j] * x[j] for j in range(d) if x[j]) for wc in w])
            for c in range(k):
                g = p[c] - (1.0 if c == y else 0.0)
                for j in range(d):
                    if x[j]:
                        w[c][j] -= LR * (g * x[j] + L2 * w[c][j])
    return w


def predict(w: list[list[float]], x: list[float]) -> list[float]:
    d = len(x)
    return softmax([sum(wc[j] * x[j] for j in range(d) if x[j]) for wc in w])


def split_key(title: str) -> float:
    return int(hashlib.sha1(title.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def main() -> int:
    data = json.loads(SRC.read_text())
    films = [f for f in data["films"] if f["rating"] in CLASSES]
    feats, xs, ys = featurize(films)
    keys = [split_key(f["title"]) for f in films]
    tr = [i for i, k in enumerate(keys) if k < 0.6]
    ca = [i for i, k in enumerate(keys) if 0.6 <= k < 0.8]
    te = [i for i, k in enumerate(keys) if k >= 0.8]
    print(
        f"films {len(films)} | features {len(feats)} | train {len(tr)} cal {len(ca)} test {len(te)}"
    )

    w = fit([xs[i] for i in tr], [ys[i] for i in tr], len(CLASSES))

    # Mondrian (class-conditional) split conformal
    q: dict[int, float] = {}
    for c in range(len(CLASSES)):
        scores = sorted(1.0 - predict(w, xs[i])[c] for i in ca if ys[i] == c)
        if not scores:
            q[c] = 1.0
            continue
        m = len(scores)
        rank = min(m - 1, math.ceil((m + 1) * (1 - ALPHA)) - 1)
        q[c] = scores[rank]

    covered = 0
    set_sizes = Counter()
    brier = 0.0
    bins: dict[int, list[int]] = defaultdict(list)
    correct_top = 0
    for i in te:
        p = predict(w, xs[i])
        pred_set = [c for c in range(len(CLASSES)) if 1.0 - p[c] <= q[c]]
        covered += ys[i] in pred_set
        set_sizes[len(pred_set)] += 1
        brier += sum((p[c] - (1.0 if c == ys[i] else 0.0)) ** 2 for c in range(len(CLASSES)))
        top = max(range(len(CLASSES)), key=lambda c: p[c])
        correct_top += top == ys[i]
        bins[int(p[top] * 10)].append(1 if top == ys[i] else 0)

    n = len(te)
    print(f"\ntop-1 accuracy: {correct_top / n:.3f}")
    print(f"conformal coverage (target {1 - ALPHA:.0%}): {covered / n:.3f}")
    print(f"prediction-set sizes: {dict(sorted(set_sizes.items()))}")
    print(f"multiclass Brier: {brier / n:.3f}")
    print("reliability (top-prob bin -> observed accuracy, n):")
    for b in sorted(bins):
        obs = bins[b]
        print(f"  {b / 10:.1f}-{(b + 1) / 10:.1f}: {sum(obs) / len(obs):.2f} (n={len(obs)})")

    OUT.write_text(
        json.dumps(
            {
                "classes": CLASSES,
                "features": feats,
                "weights": w,
                "conformal_q": q,
                "alpha": ALPHA,
                "test_metrics": {
                    "n": n,
                    "top1": correct_top / n,
                    "coverage": covered / n,
                    "brier": brier / n,
                },
            }
        )
    )
    print(f"\nsaved: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
