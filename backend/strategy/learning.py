"""
Post-trade analysis → hypotheses. It never changes the strategy by itself.

Each finding states the evidence (n, mean R) and the test a hypothesis must pass
before it can become a registry candidate. Groups with fewer than ``min_n``
trades are reported as "insufficient" instead of being interpreted.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List

import numpy as np


def _group(trades, key):
    g = defaultdict(list)
    for t in trades:
        g[str(t.get(key))].append(t)
    return g


def analyse(trades: Iterable[Dict[str, Any]], min_n: int = 20) -> Dict[str, Any]:
    tr = [t for t in trades if t.get("r") is not None]
    n = len(tr)
    out: Dict[str, Any] = {"trades": n, "groups": {}, "hypotheses": [], "ready_for_learning": n >= 50}
    if n == 0:
        out["note"] = "Yopilgan savdo yo'q — o'rganish uchun ma'lumot yo'q"
        return out
    rs = np.array([t["r"] for t in tr])
    out["expectancy_r"] = round(float(rs.mean()), 3)
    for key in ("regime", "direction", "session", "exit_reason"):
        grp = {}
        for k, items in _group(tr, key).items():
            r = np.array([x["r"] for x in items])
            grp[k] = {"n": len(r), "expectancy_r": round(float(r.mean()), 3),
                      "status": "ok" if len(r) >= min_n else "insufficient"}
        out["groups"][key] = grp

    losers = [t for t in tr if t["r"] <= 0 and t.get("mfe_r") is not None]
    if len(losers) >= min_n:
        share = float(np.mean([t["mfe_r"] >= 1.0 for t in losers]))
        if share >= 0.3:
            out["hypotheses"].append({
                "finding": f"Zararli savdolarning {share:.0%} qismi avval ≥1R foydada bo'lgan",
                "hypothesis": "1R da SL'ni breakeven'ga ko'chirish expectancy'ni oshiradi",
                "required_test": "Train'da sinash → OOS + walk-forward → champion bilan bir xil ma'lumotda compare()"})
    winners = [t for t in tr if t["r"] > 0 and t.get("mae_r") is not None]
    if len(winners) >= min_n and float(np.median([t["mae_r"] for t in winners])) < 0.3:
        out["hypotheses"].append({
            "finding": "Yutgan savdolar odatda deyarli salbiyga tushmagan (median MAE < 0.3R)",
            "hypothesis": "Torroq SL RR'ni oshirishi mumkin (lekin zarar ehtimoli ham oshadi)",
            "required_test": "sl_min_atr / sl_buffer_atr sezgirlik tahlili, faqat train'da tanlash"})
    gross = np.array([t["r"] + t.get("cost_r", 0.0) for t in tr])
    if gross.mean() > 0 and (gross.mean() - rs.mean()) / gross.mean() > 0.2:
        out["hypotheses"].append({
            "finding": f"Xarajatlar yalpi natijaning {(gross.mean() - rs.mean()) / gross.mean():.0%} qismini yeydi",
            "hypothesis": "Spread yuqori sessiyalarni filtrlash yoki kengroq SL bilan xarajat ulushini kamaytirish",
            "required_test": "Sessiya bo'yicha real spread ma'lumoti bilan qayta backtest"})
    for k, v in out["groups"].get("direction", {}).items():
        if v["status"] == "ok" and v["expectancy_r"] < 0:
            out["hypotheses"].append({
                "finding": f"{k} savdolari salbiy: {v['expectancy_r']}R (n={v['n']})",
                "hypothesis": f"{k} tomonini o'chirish yoki qo'shimcha filtr",
                "required_test": "Oldindan e'lon qilingan qoida bilan forward/paper davrida tasdiqlash (bitta namunada tanlangan qoida = data snooping)"})
    if not out["ready_for_learning"]:
        out["note"] = f"{n} savdo — statistik o'rganish uchun kamida 50 ta kerak; gipotezalar faqat kuzatuv"
    return out
