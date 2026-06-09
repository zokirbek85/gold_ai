"""
Standalone training script for Gold AI ML models.

Usage:
    python scripts/train_model.py --symbol XAUUSD --days 730 --timeframe 60

Fetches historical candles via Twelvedata (primary) / yfinance (fallback),
computes features with build_ml_features(), trains XGBoost/LightGBM/CatBoost
ensemble, and saves to ML_MODEL_DIR.
"""
from __future__ import annotations

import argparse
import os
import pickle
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# Make backend and src importable from project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

import numpy as np
from sklearn.metrics import classification_report, accuracy_score
from sklearn.model_selection import train_test_split


# ── CLI args ──────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train Gold AI ML model")
    p.add_argument("--symbol",    default="XAUUSD",  help="Trading symbol")
    p.add_argument("--days",      type=int, default=730, help="Days of history to fetch")
    p.add_argument("--timeframe", default="60",        help="Timeframe in minutes (e.g. 60=H1)")
    return p.parse_args()


# ── Data fetching ─────────────────────────────────────────────────────────────

def _fetch_twelvedata(symbol: str, interval: str, outputsize: int) -> List[Dict]:
    """Fetch candles from Twelvedata REST API."""
    try:
        import httpx
        api_key = os.environ.get("TWELVEDATA_API_KEY", "")
        if not api_key:
            return []
        url    = "https://api.twelvedata.com/time_series"
        params = {
            "symbol":     symbol,
            "interval":   interval,
            "outputsize": outputsize,
            "apikey":     api_key,
        }
        r    = httpx.get(url, params=params, timeout=30)
        data = r.json()
        raw  = data.get("values", [])
        candles = []
        for row in reversed(raw):
            try:
                candles.append({
                    "timestamp": datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S"),
                    "open":   float(row["open"]),
                    "high":   float(row["high"]),
                    "low":    float(row["low"]),
                    "close":  float(row["close"]),
                    "volume": float(row.get("volume") or 0),
                })
            except (KeyError, ValueError):
                continue
        return candles
    except Exception as exc:
        print(f"[Twelvedata] Error: {exc}")
        return []


def _fetch_yfinance(symbol: str, period_days: int, interval: str) -> List[Dict]:
    """yfinance fallback."""
    try:
        import yfinance as yf
        yf_symbol = "GC=F" if symbol == "XAUUSD" else symbol
        end   = datetime.utcnow()
        start = end - timedelta(days=period_days)
        df    = yf.download(yf_symbol, start=start.strftime("%Y-%m-%d"),
                            end=end.strftime("%Y-%m-%d"), interval=interval,
                            progress=False)
        if df.empty:
            return []
        candles = []
        for ts, row in df.iterrows():
            candles.append({
                "timestamp": ts.to_pydatetime(),
                "open":  float(row["Open"]),
                "high":  float(row["High"]),
                "low":   float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row["Volume"]) if "Volume" in row else 0.0,
            })
        return candles
    except Exception as exc:
        print(f"[yfinance] Error: {exc}")
        return []


TF_TO_TD = {"1": "1min", "5": "5min", "15": "15min",
            "60": "1h",  "240": "4h", "1440": "1day"}
TF_TO_YF = {"1": "1m",  "5": "5m",  "15": "15m",
            "60": "60m", "240": "1h", "1440": "1d"}


def fetch_candles(symbol: str, timeframe: str, days: int) -> List[Dict]:
    td_interval  = TF_TO_TD.get(str(timeframe), "1h")
    yf_interval  = TF_TO_YF.get(str(timeframe), "60m")
    outputsize   = min(days * (1440 // int(timeframe)), 5000)

    print(f"Fetching {outputsize} candles via Twelvedata ({td_interval})…")
    candles = _fetch_twelvedata(symbol, td_interval, outputsize)

    if len(candles) < 200:
        print(f"Twelvedata returned only {len(candles)}. Trying yfinance ({yf_interval})…")
        candles = _fetch_yfinance(symbol, days, yf_interval)

    print(f"Fetched {len(candles)} candles total.")
    return candles


# ── Feature labelling ─────────────────────────────────────────────────────────

def build_dataset(candles: List[Dict], lookahead: int = 3) -> tuple:
    """
    Build X, y arrays.
    Label: +1 if close[i+lookahead] > close[i] * 1.003,
           -1 if close[i+lookahead] < close[i] * 0.997,
            0 (skip) otherwise.
    """
    from backend.services.indicator_service import build_ml_features
    from backend.services import smc_service

    FEATURE_NAMES = [
        "rsi", "macd", "macd_signal", "macd_hist",
        "ema_20_dist", "ema_50_dist", "ema_200_dist",
        "atr_pct", "bb_position",
        "candle_body_ratio", "upper_wick_ratio", "lower_wick_ratio",
        "volume_ratio", "smc_score",
    ]

    X: List[List[float]] = []
    y: List[int]         = []
    n = len(candles)

    for i in range(50, n - lookahead - 1):
        window = candles[:i + 1]
        smc_val = smc_service.score(window[-100:]).get("score", 50)
        feats   = build_ml_features(window, smc_score=smc_val)
        if not feats:
            continue

        close_now   = float(candles[i]["close"])
        close_later = float(candles[i + lookahead]["close"])

        if close_later > close_now * 1.003:
            label = 1
        elif close_later < close_now * 0.997:
            label = -1
        else:
            continue   # skip neutral labels

        X.append([feats.get(k, 0.0) for k in FEATURE_NAMES])
        y.append(label)

    return np.array(X), np.array(y)


# ── Training ──────────────────────────────────────────────────────────────────

def train_and_save(X, y, symbol: str, timeframe: str) -> Dict[str, Any]:
    """Train ensemble and save to ML_MODEL_DIR."""
    from sklearn.ensemble import RandomForestClassifier

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)
    print(f"Train: {len(X_tr)} | Test: {len(X_te)}")

    model = RandomForestClassifier(n_estimators=200, max_depth=10, random_state=42, n_jobs=-1)
    model.fit(X_tr, y_tr)
    preds   = model.predict(X_te)
    acc     = accuracy_score(y_te, preds)
    report  = classification_report(y_te, preds, target_names=["SELL(-1)", "BUY(+1)"],
                                    labels=[-1, 1], output_dict=True)

    model_dir = os.environ.get("ML_MODEL_DIR", os.path.join(PROJECT_ROOT, "models"))
    os.makedirs(model_dir, exist_ok=True)

    pkl_name = f"{symbol.lower()}_{timeframe}.pkl"
    main_path = os.path.join(model_dir, pkl_name)
    payload   = {
        "model":    model,
        "accuracy": acc,
        "trained_at": datetime.utcnow().isoformat(),
        "symbol":   symbol,
        "timeframe": timeframe,
        "samples":  len(X_tr) + len(X_te),
    }

    with open(main_path, "wb") as f:
        pickle.dump(payload, f)
    print(f"Model saved → {main_path}")

    # Also copy to backend/models/ for docker deployments
    alt_dir  = os.path.join(PROJECT_ROOT, "backend", "models")
    alt_path = os.path.join(alt_dir, pkl_name)
    if os.path.abspath(alt_dir) != os.path.abspath(model_dir):
        os.makedirs(alt_dir, exist_ok=True)
        with open(alt_path, "wb") as f:
            pickle.dump(payload, f)
        print(f"Copy saved  → {alt_path}")

    return {"accuracy": acc, "report": report, "samples": len(X)}


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    print(f"\n=== Gold AI ML Trainer ===")
    print(f"Symbol: {args.symbol} | Timeframe: {args.timeframe}m | Days: {args.days}\n")

    candles = fetch_candles(args.symbol, args.timeframe, args.days)
    if len(candles) < 200:
        print(f"ERROR: Need at least 200 candles, got {len(candles)}. Aborting.")
        sys.exit(1)

    print("Building feature dataset…")
    X, y = build_dataset(candles)
    print(f"Dataset: {len(X)} samples | BUY={sum(y==1)} | SELL={sum(y==-1)}")

    if len(X) < 50:
        print("ERROR: Too few labelled samples. Try more days or a different timeframe.")
        sys.exit(1)

    print("Training model…")
    result = train_and_save(X, y, args.symbol, args.timeframe)

    print(f"\n=== Results ===")
    print(f"Accuracy:  {result['accuracy'] * 100:.1f}%")
    print(f"Samples:   {result['samples']}")
    rep = result["report"]
    for cls, metrics in rep.items():
        if isinstance(metrics, dict):
            print(f"  {cls}: precision={metrics['precision']:.2f} recall={metrics['recall']:.2f} f1={metrics['f1-score']:.2f}")
    print("\nTraining complete.")


if __name__ == "__main__":
    main()
