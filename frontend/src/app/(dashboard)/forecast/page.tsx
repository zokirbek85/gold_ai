"use client";

import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ForecastChart, type OverlayToggles, type ForecastData } from "@/components/charts/ForecastChart";
import { Card, CardHeader, PageHeader, Select, DirectionBadge } from "@/components/ui";
import { RefreshCw, TrendingUp, Layers } from "lucide-react";

const SYMBOLS   = [{ value: "XAUUSD", label: "XAUUSD" }, { value: "EURUSD", label: "EURUSD" }];
const TIMEFRAMES = [
  { value: "15",   label: "M15" },
  { value: "60",   label: "H1"  },
  { value: "240",  label: "H4"  },
  { value: "1440", label: "D1"  },
];

const OVERLAY_CONFIG: { key: keyof OverlayToggles; label: string; color: string }[] = [
  { key: "ema",         label: "EMA 20/50/200",   color: "#3b82f6" },
  { key: "bb",          label: "Bollinger Bands",  color: "#60a5fa" },
  { key: "signals",     label: "BUY/SELL Signals", color: "#22c55e" },
  { key: "orderBlocks", label: "Order Blocks",     color: "#f97316" },
  { key: "fvg",         label: "Fair Value Gap",   color: "#a78bfa" },
  { key: "sltp",        label: "SL / TP Lines",    color: "#ef4444" },
  { key: "sr",          label: "Support/Resist",   color: "#facc15" },
  { key: "fibonacci",   label: "Fibonacci Levels", color: "#c4b5fd" },
  { key: "mlForecast",  label: "ML Forecast",      color: "#f59e0b" },
  { key: "volume",      label: "Volume",           color: "#6b7280" },
  { key: "rsi",         label: "RSI Panel",        color: "#a78bfa" },
];

const DEFAULT_OVERLAYS: OverlayToggles = {
  ema: true, bb: true, signals: true, orderBlocks: true, fvg: false,
  sltp: true, sr: true, fibonacci: false, mlForecast: true, volume: true, rsi: false,
};

export default function ForecastPage() {
  const [symbol,    setSymbol]    = useState("XAUUSD");
  const [timeframe, setTimeframe] = useState("60");
  const [overlays,  setOverlays]  = useState<OverlayToggles>(DEFAULT_OVERLAYS);

  const toggle = useCallback((key: keyof OverlayToggles) => {
    setOverlays(prev => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const { data, isLoading, isError, refetch, isFetching } = useQuery<ForecastData>({
    queryKey: ["forecast", symbol, timeframe],
    queryFn:  () => api.get("/forecast", { params: { symbol, timeframe } }).then(r => r.data),
    staleTime: 60_000,
  });

  const ml  = data?.ml_forecast;
  const sig = data?.latest_signal;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-4">
      <PageHeader
        title="Forecast Chart"
        subtitle="Technical analysis overlays + ML projection on real Twelvedata candles"
        action={
          <div className="flex items-center gap-2">
            <Select options={SYMBOLS}    value={symbol}    onChange={e => setSymbol(e.target.value)}    className="w-28" />
            <Select options={TIMEFRAMES} value={timeframe} onChange={e => setTimeframe(e.target.value)} className="w-20" />
            <button onClick={() => refetch()} className="btn btn-ghost" disabled={isFetching}>
              <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? "animate-spin" : ""}`} />
              Yangilash
            </button>
          </div>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* ── Layer toggles ── */}
        <Card className="lg:col-span-1">
          <div className="p-4">
            <CardHeader icon={<Layers className="w-4 h-4" />} title="Qatlamlar" />
            <div className="space-y-1.5 mt-2">
              {OVERLAY_CONFIG.map(({ key, label, color }) => (
                <label key={key} className="flex items-center gap-2.5 cursor-pointer group">
                  <div
                    onClick={() => toggle(key)}
                    className={`w-9 h-5 rounded-full flex items-center transition-colors ${
                      overlays[key] ? "bg-[var(--gold)]" : "bg-[#2a2a3a]"
                    }`}
                  >
                    <div className={`w-3.5 h-3.5 rounded-full bg-white shadow transition-transform mx-0.5 ${
                      overlays[key] ? "translate-x-4" : "translate-x-0"
                    }`} />
                  </div>
                  <span className="flex items-center gap-1.5 text-xs" style={{ color: "var(--text-muted)" }}>
                    <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: color }} />
                    {label}
                  </span>
                </label>
              ))}
            </div>

            {/* Legend */}
            <div className="mt-4 pt-3 border-t space-y-1" style={{ borderColor: "var(--surface-2)" }}>
              <p className="text-[10px] text-gray-600 mb-2">Ranglar</p>
              {[
                { color: "#3b82f6", label: "EMA 20" },
                { color: "#f97316", label: "EMA 50" },
                { color: "#ef4444", label: "EMA 200" },
                { color: "#22c55e", label: "Bullish" },
                { color: "#ef4444", label: "Bearish" },
                { color: "#f59e0b", label: "ML Forecast" },
              ].map(({ color, label }) => (
                <div key={label} className="flex items-center gap-1.5 text-[10px]" style={{ color: "var(--text-faint)" }}>
                  <span className="w-5 h-0.5 flex-shrink-0" style={{ background: color }} />
                  {label}
                </div>
              ))}
            </div>
          </div>
        </Card>

        {/* ── Chart ── */}
        <Card className="lg:col-span-3">
          <div className="p-2">
            {isLoading ? (
              <div className="flex items-center justify-center" style={{ height: 520 }}>
                <RefreshCw className="w-6 h-6 animate-spin" style={{ color: "var(--gold)" }} />
              </div>
            ) : isError ? (
              <div className="flex items-center justify-center text-red-400 text-sm" style={{ height: 520 }}>
                Ma'lumot yuklanmadi. Twelvedata API tekshiring.
              </div>
            ) : data ? (
              <ForecastChart data={data} overlays={overlays} height={520} />
            ) : null}
          </div>
        </Card>
      </div>

      {/* ── Info panels ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* ML Forecast */}
        <Card>
          <div className="p-4">
            <CardHeader icon={<TrendingUp className="w-4 h-4" />} title="ML Forecast" />
            {ml ? (
              <div className="mt-3 space-y-2">
                <div className="flex items-center gap-3">
                  <DirectionBadge direction={ml.direction === "bullish" ? "bullish" : ml.direction === "bearish" ? "bearish" : "neutral"} />
                  <span className="text-lg font-bold font-mono" style={{ color: "var(--text)" }}>
                    {ml.confidence.toFixed(1)}%
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2 mt-2">
                  {[
                    { label: "BUY",  val: ml.buy_pct,  color: "#22c55e" },
                    { label: "SELL", val: ml.sell_pct, color: "#ef4444" },
                  ].map(({ label, val, color }) => (
                    <div key={label} className="rounded-lg p-2 text-center" style={{ background: "var(--surface-2)" }}>
                      <p className="text-[10px] mb-0.5" style={{ color: "var(--text-muted)" }}>{label}</p>
                      <p className="text-sm font-mono font-bold" style={{ color }}>{val.toFixed(1)}%</p>
                    </div>
                  ))}
                </div>
                <p className="text-[10px] mt-1" style={{ color: "var(--text-faint)" }}>
                  RandomForest — keyingi 7 ta candle proyeksiyasi
                </p>
              </div>
            ) : (
              <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>ML model topilmadi</p>
            )}
          </div>
        </Card>

        {/* Latest Signal */}
        <Card>
          <div className="p-4">
            <CardHeader icon={<TrendingUp className="w-4 h-4" />} title="So'nggi Signal" />
            {sig ? (
              <div className="mt-3 space-y-2">
                <div className="flex items-center gap-2">
                  <DirectionBadge direction={sig.type === "BUY" ? "bullish" : "bearish"} />
                  <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {sig.confidence?.toFixed(1)}% ishonch
                  </span>
                </div>
                {[
                  { label: "Entry",       val: sig.entry, color: "var(--gold)" },
                  { label: "Stop Loss",   val: sig.sl,    color: "#ef4444" },
                  { label: "Take Profit", val: sig.tp,    color: "#22c55e" },
                ].map(({ label, val, color }) => (
                  <div key={label} className="flex justify-between text-xs">
                    <span style={{ color: "var(--text-muted)" }}>{label}</span>
                    <span className="font-mono" style={{ color }}>{val?.toFixed(2) ?? "—"}</span>
                  </div>
                ))}
                {sig.rr && (
                  <div className="flex justify-between text-xs">
                    <span style={{ color: "var(--text-muted)" }}>R/R</span>
                    <span className="font-mono" style={{ color: "var(--gold)" }}>{sig.rr.toFixed(2)}R</span>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>Signal yo'q</p>
            )}
          </div>
        </Card>

        {/* Fibonacci & S/R summary */}
        <Card>
          <div className="p-4">
            <CardHeader icon={<Layers className="w-4 h-4" />} title="Key Levellar" />
            {data?.overlays?.fibonacci?.levels ? (
              <div className="mt-3 space-y-1">
                {Object.entries(data.overlays.fibonacci.levels).map(([ratio, level]) => (
                  <div key={ratio} className="flex justify-between text-xs">
                    <span style={{ color: "#a78bfa" }}>Fib {ratio}</span>
                    <span className="font-mono" style={{ color: "var(--text)" }}>{(level as number).toFixed(2)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>Yuklanmoqda…</p>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
