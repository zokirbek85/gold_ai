import logging
from typing import List, Dict, Any

try:
    import MetaTrader5 as mt5
except Exception:  # pragma: no cover - MT5 optional in CI
    mt5 = None

from src.config.settings import settings

log = logging.getLogger(__name__)


class MT5Connector:
    def __init__(self):
        self.connected = False

    def connect(self) -> bool:
        if mt5 is None:
            log.warning("MetaTrader5 package not available")
            return False
        if settings.MT5_LOGIN and settings.MT5_PASSWORD and settings.MT5_SERVER:
            ok = mt5.initialize()
            if not ok:
                log.error("MT5 initialize failed")
                return False
            authorized = mt5.login(int(settings.MT5_LOGIN), settings.MT5_PASSWORD, settings.MT5_SERVER)
            if not authorized:
                log.error("MT5 login failed")
                return False
            self.connected = True
            return True
        else:
            log.warning("MT5 credentials not configured")
            return False

    def shutdown(self):
        if mt5:
            mt5.shutdown()
        self.connected = False

    def get_ticks(self, symbol: str, n: int = 100) -> List[Dict[str, Any]]:
        if not mt5:
            return []
        ticks = mt5.copy_ticks_from(symbol, 0, n, mt5.COPY_TICKS_ALL)
        return [dict(t._asdict()) for t in ticks]

    def get_candles(self, symbol: str, timeframe: int, count: int = 100):
        if not mt5:
            return []
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        return [dict(r._asdict()) for r in rates]


mt5_connector = MT5Connector()
