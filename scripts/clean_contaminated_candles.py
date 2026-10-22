"""
Find (and optionally delete) candles that belong to a foreign price series.

The ``candles`` table contains a second series interleaved with the real
Twelvedata series (≈$2 300 vs ≈$4 000 on the same dates, volume > 0, D1 bars
stamped 08:00). The v2 engine already drops these rows at read time; this
script removes them from the database so other endpoints (charts, legacy
engine, ML training) stop using them.

DRY-RUN BY DEFAULT. Nothing is deleted without --apply.

    # inside the backend container (DATABASE_URL from env):
    python scripts/clean_contaminated_candles.py               # report only
    python scripts/clean_contaminated_candles.py --export bad.csv
    python scripts/clean_contaminated_candles.py --apply       # delete (asks to confirm)

Take a database backup first (e.g. ``pg_dump -t candles``).
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from database import SessionLocal  # noqa: E402
from models.candle import Candle  # noqa: E402
from strategy.data_quality import clean_candles  # noqa: E402

MAX_DEVIATION = 0.08  # 8 % away from the clean series at the same time → foreign


def find_foreign(rows: list, timeframe: int) -> pd.DataFrame:
    raw = pd.DataFrame([{"id": r.id, "timestamp": r.timestamp, "open": r.open, "high": r.high,
                         "low": r.low, "close": r.close, "volume": r.volume} for r in rows])
    if raw.empty:
        return raw
    clean, _ = clean_candles(raw.drop(columns="id"), timeframe, drop_forming=False)
    if clean.empty:
        return raw.iloc[0:0]
    ref = clean[["timestamp", "close"]].rename(columns={"close": "ref_close"}).sort_values("timestamp")
    cand = raw[~raw["timestamp"].isin(set(clean["timestamp"]))].sort_values("timestamp")
    if cand.empty:
        return cand
    m = pd.merge_asof(cand, ref, on="timestamp", direction="nearest")
    m["deviation"] = (m["close"] / m["ref_close"] - 1).abs()
    return m[m["deviation"] > MAX_DEVIATION]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--apply", action="store_true", help="delete the rows (default: report only)")
    ap.add_argument("--yes", action="store_true", help="skip the interactive confirmation")
    ap.add_argument("--export", default=None, help="write flagged rows to this CSV")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        tfs = [t for (t,) in db.query(Candle.timeframe).filter(Candle.symbol == args.symbol).distinct()]
        flagged = []
        for tf in sorted(tfs, key=lambda x: int(x)):
            rows = db.query(Candle).filter(Candle.symbol == args.symbol, Candle.timeframe == tf).all()
            bad = find_foreign(rows, int(tf))
            print(f"tf={tf:>5}: {len(rows):6d} rows, {len(bad):5d} flagged as foreign"
                  + (f" ({bad['timestamp'].min()} … {bad['timestamp'].max()})" if len(bad) else ""))
            if len(bad):
                flagged.append(bad.assign(timeframe=tf))
        if not flagged:
            print("Nothing to clean.")
            return
        allbad = pd.concat(flagged)
        if args.export:
            allbad.to_csv(args.export, index=False)
            print(f"Flagged rows written to {args.export}")
        if not args.apply:
            print(f"DRY RUN — {len(allbad)} rows would be deleted. Re-run with --apply to delete.")
            return
        if not args.yes and input(f"Delete {len(allbad)} rows? Type DELETE to confirm: ") != "DELETE":
            print("Aborted.")
            return
        ids = [int(x) for x in allbad["id"]]
        for k in range(0, len(ids), 1000):
            db.query(Candle).filter(Candle.id.in_(ids[k:k + 1000])).delete(synchronize_session=False)
        db.commit()
        print(f"Deleted {len(ids)} rows.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
