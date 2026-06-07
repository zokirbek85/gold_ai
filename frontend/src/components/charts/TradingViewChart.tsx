"use client";
import { memo, useEffect, useRef, useState } from "react";

const TF_MAP: Record<string, string> = {
  "1": "1",
  "5": "5",
  "15": "15",
  "60": "60",
  "240": "240",
  "1440": "D",
};

const SYM_MAP: Record<string, string> = {
  XAUUSD: "OANDA:XAUUSD",
  EURUSD: "FX:EURUSD",
  GBPUSD: "FX:GBPUSD",
  USDJPY: "FX:USDJPY",
  BTCUSD: "BINANCE:BTCUSDT",
};

interface Props {
  symbol?: string;
  timeframe?: string;
  height?: number;
  showIndicators?: boolean;
}

let _scriptLoaded = false;
const _callbacks: Array<() => void> = [];

function loadTVScript(onLoad: () => void) {
  if (_scriptLoaded) { onLoad(); return; }
  _callbacks.push(onLoad);
  if (document.querySelector('script[src="https://s3.tradingview.com/tv.js"]')) return;
  const s = document.createElement("script");
  s.src = "https://s3.tradingview.com/tv.js";
  s.async = true;
  s.onload = () => {
    _scriptLoaded = true;
    _callbacks.splice(0).forEach(cb => cb());
  };
  document.head.appendChild(s);
}

export const TradingViewChart = memo(function TradingViewChart({
  symbol = "XAUUSD",
  timeframe = "60",
  height = 600,
  showIndicators = true,
}: Props) {
  const [uid] = useState(
    () => `tv_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`
  );
  const activeRef = useRef(true);

  useEffect(() => {
    activeRef.current = true;
    loadTVScript(() => {
      if (!activeRef.current || !(window as any).TradingView) return;
      const el = document.getElementById(uid);
      if (!el) return;
      new (window as any).TradingView.widget({
        container_id: uid,
        autosize: true,
        symbol: SYM_MAP[symbol] ?? `FX:${symbol}`,
        interval: TF_MAP[timeframe] ?? "60",
        timezone: "Etc/UTC",
        theme: "dark",
        style: "1",
        locale: "en",
        enable_publishing: false,
        withdateranges: true,
        hide_side_toolbar: false,
        allow_symbol_change: false,
        save_image: false,
        studies: showIndicators
          ? ["RSI@tv-basicstudies", "MACD@tv-basicstudies", "BB@tv-basicstudies"]
          : [],
        overrides: {
          "paneProperties.background": "#0d0d14",
          "paneProperties.backgroundType": "solid",
          "paneProperties.vertGridProperties.color": "#1a1a2e",
          "paneProperties.horzGridProperties.color": "#1a1a2e",
          "symbolWatermarkProperties.transparency": 90,
          "scalesProperties.textColor": "#6b7280",
          "mainSeriesProperties.candleStyle.upColor": "#22c55e",
          "mainSeriesProperties.candleStyle.downColor": "#ef4444",
          "mainSeriesProperties.candleStyle.wickUpColor": "#22c55e",
          "mainSeriesProperties.candleStyle.wickDownColor": "#ef4444",
          "mainSeriesProperties.candleStyle.borderUpColor": "#22c55e",
          "mainSeriesProperties.candleStyle.borderDownColor": "#ef4444",
        },
      });
    });
    return () => { activeRef.current = false; };
  }, [uid, symbol, timeframe, showIndicators]);

  return <div id={uid} style={{ height }} className="w-full" />;
});
