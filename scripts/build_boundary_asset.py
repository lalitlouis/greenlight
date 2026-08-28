"""Assemble the runtime rating-boundary asset from the harvest derivatives.

src/greenlight/data/rating_boundary.json = descriptor marginals (n >= MIN_N,
so no thin-sample folklore ships) + the fitted conformal model. Rerun after
any rating_table.py / rating_model.py regeneration so the runtime asset and
the published methodology numbers come from the same artifacts.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

CACHE = Path(__file__).resolve().parents[1] / ".cache" / "ratings_ingest"
OUT = Path(__file__).resolve().parents[1] / "src" / "greenlight" / "data" / "rating_boundary.json"
MIN_N = 20  # a marginal below this is an anecdote, not a base rate


def main() -> int:
    table = json.loads((CACHE / "descriptor_table.json").read_text())
    model = json.loads((CACHE / "rating_model.json").read_text())
    marginals = {k: v for k, v in table["descriptors"].items() if sum(v.values()) >= MIN_N}
    today = dt.date.today().isoformat()
    OUT.write_text(
        json.dumps(
            {
                "source": f"official CARA rating rationales, filmratings.com (harvested {today})",
                "scope": f"post-{table['min_year']} wide releases, "
                f"{table['films_parsed']} films parsed",
                "marginals": marginals,
                "model": model,
            }
        )
    )
    print(f"saved: {OUT} | {len(marginals)} marginals (n>={MIN_N}) + model")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
