"""Read-only paper-trading, learning and execution-readiness endpoints."""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models.paper import PaperTrade

router = APIRouter()


@router.get("/paper/stats")
def paper_stats(db: Session = Depends(get_db)) -> Dict[str, Any]:
    from paper import service
    return {**service.stats(db), "health": service.health(db)}


@router.get("/paper/trades")
def paper_trades(limit: int = Query(50, le=500), db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = db.query(PaperTrade).order_by(PaperTrade.created_at.desc()).limit(limit).all()
    return [{c.name: getattr(r, c.name) for c in PaperTrade.__table__.columns} for r in rows]


@router.get("/paper/analysis")
def paper_analysis(db: Session = Depends(get_db)) -> Dict[str, Any]:
    from paper import service
    from strategy.learning import analyse
    return analyse(service.trades_for_analysis(db))


@router.get("/execution/readiness")
def execution_readiness(db: Session = Depends(get_db)) -> Dict[str, Any]:
    from execution.gate import readiness
    from paper import service
    return readiness(service.stats(db), service.health(db))


@router.get("/strategy/registry")
def strategy_registry() -> Dict[str, Any]:
    from strategy import registry
    ch = registry.champion()
    return {"champion": ch["id"] if ch else None, "entries": registry.list_entries(),
            "active_config_hash": registry.active_config().version_hash()}
