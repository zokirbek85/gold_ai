"""
Causal indicator series (value at index i depends only on bars 0..i).

Formulas follow the standard definitions:
  EMA  — SMA seed of the first ``n`` values, then alpha = 2/(n+1)
  ATR  — Wilder smoothing of True Range (seeded with SMA of first n TRs)
  RSI  — Wilder smoothing of gains/losses
  ADX  — Wilder: +DI/−DI from smoothed DM/TR, DX averaged with Wilder → 0..100
Values are NaN until enough history exists.
"""
from __future__ import annotations

import numpy as np


def ema(values: np.ndarray, n: int) -> np.ndarray:
    v = np.asarray(values, dtype=float)
    out = np.full(v.shape, np.nan)
    if len(v) < n:
        return out
    k = 2.0 / (n + 1)
    e = v[:n].mean()
    out[n - 1] = e
    for i in range(n, len(v)):
        e = v[i] * k + e * (1 - k)
        out[i] = e
    return out


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    h, l, c = (np.asarray(x, dtype=float) for x in (high, low, close))
    tr = h - l
    prev_c = np.roll(c, 1)
    tr[1:] = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - prev_c[1:]), np.abs(l[1:] - prev_c[1:])])
    return tr


def _wilder_mean(x: np.ndarray, n: int, start: int) -> np.ndarray:
    """Wilder average of x[start:], seeded with SMA of x[start:start+n]."""
    out = np.full(x.shape, np.nan)
    if len(x) - start < n:
        return out
    a = x[start:start + n].mean()
    out[start + n - 1] = a
    for i in range(start + n, len(x)):
        a = (a * (n - 1) + x[i]) / n
        out[i] = a
    return out


def atr(high, low, close, n: int = 14) -> np.ndarray:
    tr = true_range(high, low, close)
    # TR[0] has no previous close → start at index 1 (matches legacy services)
    return _wilder_mean(tr, n, start=1)


def rsi(close, n: int = 14) -> np.ndarray:
    c = np.asarray(close, dtype=float)
    out = np.full(c.shape, np.nan)
    if len(c) <= n:
        return out
    d = np.diff(c)
    gain = np.where(d > 0, d, 0.0)
    loss = np.where(d < 0, -d, 0.0)
    ag, al = gain[:n].mean(), loss[:n].mean()
    out[n] = 100.0 if al == 0 else 100.0 - 100.0 / (1 + ag / al)
    for i in range(n, len(d)):
        ag = (ag * (n - 1) + gain[i]) / n
        al = (al * (n - 1) + loss[i]) / n
        out[i + 1] = 100.0 if al == 0 else 100.0 - 100.0 / (1 + ag / al)
    return out


def adx(high, low, close, n: int = 14) -> np.ndarray:
    h, l = np.asarray(high, dtype=float), np.asarray(low, dtype=float)
    size = len(h)
    out = np.full(size, np.nan)
    if size < 2 * n + 1:
        return out
    up = np.zeros(size)
    dn = np.zeros(size)
    up[1:] = h[1:] - h[:-1]
    dn[1:] = l[:-1] - l[1:]
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = true_range(high, low, close)
    tr_s = _wilder_mean(tr, n, 1)
    pdm_s = _wilder_mean(plus_dm, n, 1)
    mdm_s = _wilder_mean(minus_dm, n, 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        pdi = 100 * pdm_s / tr_s
        mdi = 100 * mdm_s / tr_s
        dx = 100 * np.abs(pdi - mdi) / (pdi + mdi)
    dx = np.where(np.isfinite(dx), dx, 0.0)
    first = n  # first index where smoothed DI exist
    out_adx = _wilder_mean(dx, n, first)
    out[:] = out_adx
    return out


def rolling_median(x: np.ndarray, n: int) -> np.ndarray:
    """Causal rolling median (NaN until n non-NaN values are available)."""
    import pandas as pd
    return pd.Series(x).rolling(n, min_periods=n).median().to_numpy()


def rolling_min(x: np.ndarray, n: int) -> np.ndarray:
    import pandas as pd
    return pd.Series(x).rolling(n, min_periods=1).min().to_numpy()


def rolling_max(x: np.ndarray, n: int) -> np.ndarray:
    import pandas as pd
    return pd.Series(x).rolling(n, min_periods=1).max().to_numpy()
