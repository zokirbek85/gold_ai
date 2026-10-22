"""
Versioned strategy registry with champion / candidate / retired states.

Learning loop this supports:
  observation → hypothesis → research run (train) → OOS + walk-forward →
  register candidate → compare with champion on the SAME data → human promote
  → paper trading → health monitor → (rollback if needed)

Nothing is promoted automatically: ``compare`` only produces a recommendation;
``promote`` requires an explicit call (CLI/admin) and refuses an ineligible
candidate unless ``force=True`` is given with a reason.

Storage: JSON files in $STRATEGY_REGISTRY_DIR (default $ML_MODEL_DIR/strategy_registry).

CLI:
    python -m strategy.registry list
    python -m strategy.registry seed                     # register the built-in baseline
    python -m strategy.registry register --research docs/research/research_h4_d1.json --name x
    python -m strategy.registry compare <candidate_id>
    python -m strategy.registry promote <candidate_id> --by "name"
    python -m strategy.registry rollback --by "name"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, fields
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy import STRATEGY_VERSION  # noqa: E402
from strategy.config import StrategyConfig  # noqa: E402

# Reference statistics of the built-in v2.0.0 champion (docs/research/research_h4_d1.json,
# test period 2024-07…2026-10). std_r = SE·√n = 0.261·√42.
BASELINE_REFERENCE = {"expectancy_r": 0.492, "std_r": 1.69, "max_drawdown_r": 6.09,
                      "max_consecutive_losses": 6, "trades": 42}

# promotion criteria (candidate vs champion, same data)
MIN_TEST_TRADES = 30
MIN_WF_TRADES = 60


def _dir() -> str:
    d = os.getenv("STRATEGY_REGISTRY_DIR") or os.path.join(
        os.getenv("ML_MODEL_DIR", "/app/ml_models"), "strategy_registry")
    os.makedirs(d, exist_ok=True)
    return d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state() -> Dict[str, Any]:
    p = os.path.join(_dir(), "state.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {"champion": None, "history": []}


def _save_state(st: Dict[str, Any]) -> None:
    tmp = os.path.join(_dir(), "state.json.tmp")
    with open(tmp, "w") as f:
        json.dump(st, f, indent=2)
    os.replace(tmp, os.path.join(_dir(), "state.json"))


def get(entry_id: str) -> Optional[Dict[str, Any]]:
    p = os.path.join(_dir(), f"{entry_id}.json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def _put(entry: Dict[str, Any]) -> None:
    with open(os.path.join(_dir(), f"{entry['id']}.json"), "w") as f:
        json.dump(entry, f, indent=2, default=str)


def list_entries() -> List[Dict[str, Any]]:
    out = []
    for fn in sorted(os.listdir(_dir())):
        if fn.endswith(".json") and fn != "state.json":
            e = get(fn[:-5])
            out.append({k: e.get(k) for k in ("id", "name", "status", "created_at", "strategy_version")})
    return out


def register(name: str, params: Dict[str, Any], metrics: Dict[str, Any], reference: Dict[str, float],
             data: Dict[str, Any], notes: str = "") -> Dict[str, Any]:
    known = {f.name for f in fields(StrategyConfig)}
    unknown = set(params) - known
    if unknown:
        raise ValueError(f"Unknown StrategyConfig params: {sorted(unknown)}")
    cfg = StrategyConfig(**params)
    entry_id = f"{STRATEGY_VERSION}-{cfg.version_hash()}"
    if get(entry_id):
        return get(entry_id)
    entry = {"id": entry_id, "name": name, "status": "candidate", "created_at": _now(),
             "strategy_version": STRATEGY_VERSION, "params": asdict(cfg), "metrics": metrics,
             "reference": reference, "data": data, "notes": notes}
    _put(entry)
    return entry


def champion() -> Optional[Dict[str, Any]]:
    cid = _state().get("champion")
    return get(cid) if cid else None


def active_config() -> StrategyConfig:
    """Champion parameters, or code defaults when the registry is empty/unreadable."""
    try:
        ch = champion()
    except OSError:
        ch = None
    if not ch:
        return StrategyConfig()
    known = {f.name for f in fields(StrategyConfig)}
    return StrategyConfig(**{k: v for k, v in ch["params"].items() if k in known})


def active_reference() -> Dict[str, float]:
    try:
        ch = champion()
    except OSError:
        ch = None
    return (ch or {}).get("reference") or BASELINE_REFERENCE


def compare(candidate_id: str) -> Dict[str, Any]:
    cand, champ = get(candidate_id), champion()
    if not cand:
        raise KeyError(candidate_id)
    reasons, ok = [], True
    ct = cand["metrics"].get("test", {})
    wf = cand["metrics"].get("walk_forward", {})
    if (ct.get("trades") or 0) < MIN_TEST_TRADES:
        ok = False
        reasons.append(f"Test savdolari {ct.get('trades')} < {MIN_TEST_TRADES}")
    if (wf.get("pooled_oos_trades") or 0) < MIN_WF_TRADES:
        ok = False
        reasons.append(f"Walk-forward OOS savdolari {wf.get('pooled_oos_trades')} < {MIN_WF_TRADES}")
    ci = ct.get("expectancy_r_ci95") or [None, None]
    if ci[0] is None or ci[0] <= 0:
        ok = False
        reasons.append(f"Test expectancy CI95 pastki chegarasi {ci[0]} ≤ 0")
    if champ and champ["id"] != cand["id"]:
        same_data = champ.get("data", {}).get("fingerprint") == cand.get("data", {}).get("fingerprint")
        if not same_data:
            ok = False
            reasons.append("Champion bilan bir xil ma'lumotda solishtirilmagan (fingerprint farq qiladi)")
        cw = champ["metrics"].get("walk_forward", {}).get("pooled_oos_expectancy_r")
        if cw is not None and (wf.get("pooled_oos_expectancy_r") or -9) <= cw:
            ok = False
            reasons.append(f"Walk-forward expectancy {wf.get('pooled_oos_expectancy_r')} ≤ champion {cw}")
        cdd = champ["metrics"].get("test", {}).get("max_drawdown_r")
        if cdd and (ct.get("max_drawdown_r") or 0) > 1.5 * cdd:
            ok = False
            reasons.append(f"Test drawdown {ct.get('max_drawdown_r')}R > 1.5 × champion {cdd}R")
    return {"candidate": cand["id"], "champion": champ["id"] if champ else None,
            "eligible": ok, "reasons": reasons or ["Barcha mezonlar bajarildi"]}


def promote(candidate_id: str, approved_by: str, force: bool = False, reason: str = "") -> Dict[str, Any]:
    if not approved_by:
        raise ValueError("approved_by is required — promotion is a human decision")
    verdict = compare(candidate_id)
    if not verdict["eligible"] and not (force and reason):
        raise PermissionError(f"Candidate not eligible: {verdict['reasons']}")
    st = _state()
    prev = st.get("champion")
    if prev and prev != candidate_id:
        e = get(prev)
        e["status"] = "retired"
        _put(e)
    e = get(candidate_id)
    e["status"], e["approved_by"], e["promoted_at"] = "champion", approved_by, _now()
    if force:
        e["forced_reason"] = reason
    _put(e)
    st["history"].append({"at": _now(), "action": "promote", "from": prev, "to": candidate_id,
                          "by": approved_by, "forced": bool(force), "reason": reason})
    st["champion"] = candidate_id
    _save_state(st)
    return {"champion": candidate_id, "previous": prev, "verdict": verdict}


def rollback(approved_by: str) -> Dict[str, Any]:
    st = _state()
    promos = [h for h in st["history"] if h["action"] in ("promote", "seed")]
    if len(promos) < 2:
        raise RuntimeError("No previous champion to roll back to")
    current, previous = st["champion"], promos[-1]["from"]
    if not previous:
        raise RuntimeError("Previous champion unknown")
    for eid, status in ((current, "retired"), (previous, "champion")):
        e = get(eid)
        e["status"] = status
        _put(e)
    st["champion"] = previous
    st["history"].append({"at": _now(), "action": "rollback", "from": current, "to": previous, "by": approved_by})
    _save_state(st)
    return {"champion": previous, "rolled_back": current}


def seed_baseline() -> Dict[str, Any]:
    """Register the code-default config as the first champion (idempotent)."""
    st = _state()
    if st.get("champion"):
        return champion()
    e = register("v2 trend_pullback H4/D1 (baseline)", asdict(StrategyConfig()),
                 {"test": {"trades": 42, "expectancy_r": 0.492, "expectancy_r_ci95": [0.002, 0.992],
                           "max_drawdown_r": 6.09},
                  "walk_forward": {"pooled_oos_trades": 120, "pooled_oos_expectancy_r": 0.273}},
                 BASELINE_REFERENCE,
                 {"source": "Twelvedata XAU/USD 4h 2020-11…2026-10", "fingerprint": "td_4h_2026-10-22"},
                 "See docs/GOLD_AI_AUDIT_2026-10.md")
    e["status"], e["approved_by"], e["promoted_at"] = "champion", "seed", _now()
    _put(e)
    st["champion"] = e["id"]
    st["history"].append({"at": _now(), "action": "seed", "from": None, "to": e["id"], "by": "seed"})
    _save_state(st)
    return e


def register_from_research(path: str, name: str, fingerprint: str) -> Dict[str, Any]:
    with open(path) as f:
        r = json.load(f)
    v2 = r["v2"]
    params = {**{k: v for k, v in asdict(StrategyConfig()).items()}, **v2["chosen_params"]}
    m_te = v2["test"]["metrics"]
    se, n = m_te.get("expectancy_r_se") or 0.3, m_te.get("trades") or 1
    ref = {"expectancy_r": m_te.get("expectancy_r") or 0.0, "std_r": round(se * n ** 0.5, 3),
           "max_drawdown_r": m_te.get("max_drawdown_r") or 6.0,
           "max_consecutive_losses": m_te.get("max_consecutive_losses") or 6, "trades": n}
    metrics = {"train": v2["train"]["metrics"], "test": m_te, "walk_forward": r.get("walk_forward", {})}
    metrics["walk_forward"] = {k: v for k, v in metrics["walk_forward"].items() if k != "windows"}
    return register(name, params, metrics, ref, {"fingerprint": fingerprint, "source": path})


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("seed")
    rg = sub.add_parser("register")
    rg.add_argument("--research", required=True)
    rg.add_argument("--name", required=True)
    rg.add_argument("--fingerprint", required=True)
    for c in ("compare", "show"):
        x = sub.add_parser(c)
        x.add_argument("id")
    pr = sub.add_parser("promote")
    pr.add_argument("id")
    pr.add_argument("--by", required=True)
    pr.add_argument("--force", action="store_true")
    pr.add_argument("--reason", default="")
    rb = sub.add_parser("rollback")
    rb.add_argument("--by", required=True)
    a = ap.parse_args()
    out = {"list": lambda: list_entries(), "seed": seed_baseline,
           "register": lambda: register_from_research(a.research, a.name, a.fingerprint),
           "compare": lambda: compare(a.id), "show": lambda: get(a.id),
           "promote": lambda: promote(a.id, a.by, a.force, a.reason),
           "rollback": lambda: rollback(a.by)}[a.cmd]()
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
