"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ForecastChart, type OverlayToggles, type ForecastData } from "@/components/charts/ForecastChart";
import { Card, CardHeader, PageHeader, Select, DirectionBadge } from "@/components/ui";
import {
  RefreshCw, TrendingUp, TrendingDown, Layers, Activity,
  Wifi, WifiOff, BarChart3, Target, Minus,
} from "lucide-react";

// ── constants ──────────────────────────────────────────────────────────────────

const SYMBOLS   = [{ value: "XAUUSD", label: "XAUUSD" }, { value: "EURUSD", label: "EURUSD" }];
const TIMEFRAMES = [
  { value: "1",    label: "M1"  },
  { value: "15",   label: "M15" },
  { value: "60",   label: "H1"  },
  { value: "240",  label: "H4"  },
  { value: "1440", label: "D1"  },
];

/** Auto-refresh interval per timeframe (ms) */
const REFRESH_MS: Record<string, number> = {
  "1": 30_000, "15": 60_000, "60": 120_000, "240": 300_000, "1440": 600_000,
};

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

// ── hooks ──────────────────────────────────────────────────────────────────────

function useLivePrice(symbol: string) {
  const [price,     setPrice]     = useState<number | null>(null);
  const [trend,     setTrend]     = useState<"up" | "down" | null>(null);
  const [connected, setConnected] = useState(false);
  const prevRef = useRef<number | null>(null);

  useEffect(() => {
    const es = new EventSource(`/api/stream?symbol=${symbol}`);
    es.onopen    = () => setConnected(true);
    es.onerror   = () => setConnected(false);
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        const p = parseFloat(d.price ?? d.close ?? 0);
        if (!p) return;
        setConnected(true);
        setTrend(prevRef.current !== null
          ? p > prevRef.current ? "up" : p < prevRef.current ? "down" : null
          : null);
        prevRef.current = p;
        setPrice(p);
      } catch {}
    };
    return () => { es.close(); setConnected(false); };
  }, [symbol]);

  return { price, trend, connected };
}

function useCountdown(targetMs: number, resetKey: unknown) {
  const [remaining, setRemaining] = useState(targetMs);

  useEffect(() => {
    setRemaining(targetMs);
    const id = setInterval(() => {
      setRemaining(prev => {
        const next = prev - 1000;
        return next < 0 ? targetMs : next;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [targetMs, resetKey]);

  return remaining;
}

// ── components ────────────────────────────────────────────────────────────────

function LiveTicker({ price, trend, connected }: { price: number | null; trend: "up" | "down" | null; connected: boolean }) {
  return (
    <div className="flex items-center gap-2">
      {connected
        ? <span className="flex items-center gap-1 text-[10px] text-green-400"><Wifi className="w-3 h-3" /> LIVE</span>
        : <span className="flex items-center gap-1 text-[10px] text-gray-500"><WifiOff className="w-3 h-3" /> offline</span>
      }
      {price !== null && (
        <span className={`font-mono font-bold text-sm tabular-nums transition-colors ${
          trend === "up" ? "text-green-400" : trend === "down" ? "text-red-400" : "text-white"
        }`}>
          {price.toFixed(2)}
        </span>
      )}
    </div>
  );
}

function CountdownBar({ remaining, total }: { remaining: number; total: number }) {
  const pct = Math.max(0, Math.min(100, (remaining / total) * 100));
  const sec = Math.ceil(remaining / 1000);
  return (
    <div className="flex items-center gap-2 text-[10px]" style={{ color: "var(--text-faint)" }}>
      <span>Yangilanish: {sec}s</span>
      <div className="w-16 h-1 rounded-full overflow-hidden" style={{ background: "var(--surface-2)" }}>
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, background: pct > 30 ? "var(--gold)" : "#ef4444" }}
        />
      </div>
    </div>
  );
}

// ── main page ─────────────────────────────────────────────────────────────────

export default function ForecastPage() {
  const [symbol,    setSymbol]    = useState("XAUUSD");
  const [timeframe, setTimeframe] = useState("60");
  const [overlays,  setOverlays]  = useState<OverlayToggles>(DEFAULT_OVERLAYS);

  const toggle = useCallback((key: keyof OverlayToggles) => {
    setOverlays(prev => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const refreshMs = REFRESH_MS[timeframe] ?? 120_000;
  const { price: livePrice, trend: liveTrend, connected } = useLivePrice(symbol);

  const { data, isLoading, isError, refetch, isFetching, dataUpdatedAt } = useQuery<ForecastData>({
    queryKey:       ["forecast", symbol, timeframe],
    queryFn:        () => api.get("/forecast", { params: { symbol, timeframe } }).then(r => r.data),
    staleTime:      refreshMs / 2,
    refetchInterval: refreshMs,
  });

  const remaining = useCountdown(refreshMs, dataUpdatedAt);

  const ml  = data?.ml_forecast;
  const sig = data?.latest_signal;
  const obs  = data?.overlays?.order_blocks  ?? [];
  const fvgs = data?.overlays?.fvg           ?? [];
  const srs  = data?.overlays?.support_resistance ?? [];
  const fib  = data?.overlays?.fibonacci;

  const seasonality  = (data as Record<string, unknown> | undefined)?.seasonality  as Record<string, unknown> | undefined;
  const eventImpact  = (data as Record<string, unknown> | undefined)?.event_impact  as Record<string, unknown> | undefined;
  const zoneAnalysis = (data as Record<string, unknown> | undefined)?.zone_analysis as Record<string, unknown> | undefined;

  const bullObs = obs.filter(o => o.type === "bullish").length;
  const bearObs = obs.filter(o => o.type === "bearish").length;
  const bullFvg = fvgs.filter(f => f.type === "bullish").length;
  const bearFvg = fvgs.filter(f => f.type === "bearish").length;
  const supports = srs.filter(s => s.type === "support").length;
  const resists  = srs.filter(s => s.type === "resistance").length;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-4">
      <PageHeader
        title="Forecast Chart"
        subtitle="Real-time candlestick + TA + SMC + ML projection"
        action={
          <div className="flex items-center gap-3">
            <LiveTicker price={livePrice} trend={liveTrend} connected={connected} />
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
          {/* Chart header with countdown */}
          <div className="flex items-center justify-between px-3 pt-3 pb-1">
            <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
              {symbol} · {TIMEFRAMES.find(t => t.value === timeframe)?.label}
            </span>
            {!isLoading && !isError && (
              <CountdownBar remaining={remaining} total={refreshMs} />
            )}
          </div>

          <div className="p-2">
            {isLoading ? (
              <div className="flex flex-col items-center justify-center gap-3" style={{ height: 520 }}>
                <RefreshCw className="w-6 h-6 animate-spin" style={{ color: "var(--gold)" }} />
                <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                  Ma'lumotlar yuklanmoqda…
                </span>
              </div>
            ) : isError ? (
              <div className="flex items-center justify-center text-red-400 text-sm" style={{ height: 520 }}>
                Ma'lumot yuklanmadi. Twelvedata API tekshiring.
              </div>
            ) : data ? (
              <ForecastChart data={data} overlays={overlays} height={520} livePrice={livePrice} />
            ) : null}
          </div>
        </Card>
      </div>

      {/* ── Info panels row ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">

        {/* ML Forecast */}
        <Card>
          <div className="p-4">
            <CardHeader icon={<Activity className="w-4 h-4" />} title="ML Forecast" />
            {ml ? (
              <div className="mt-3 space-y-3">
                <div className="flex items-center justify-between">
                  <DirectionBadge direction={
                    ml.direction === "bullish" ? "bullish" :
                    ml.direction === "bearish" ? "bearish" : "neutral"
                  } />
                  <span className="text-lg font-bold font-mono" style={{ color: "var(--text)" }}>
                    {ml.confidence.toFixed(1)}%
                  </span>
                </div>
                {/* Confidence bar */}
                <div className="space-y-1.5">
                  {[
                    { label: "BUY",  pct: ml.buy_pct,  color: "#22c55e" },
                    { label: "SELL", pct: ml.sell_pct, color: "#ef4444" },
                  ].map(({ label, pct, color }) => (
                    <div key={label}>
                      <div className="flex justify-between text-[10px] mb-0.5" style={{ color: "var(--text-muted)" }}>
                        <span>{label}</span><span>{pct.toFixed(1)}%</span>
                      </div>
                      <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--surface-2)" }}>
                        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
                      </div>
                    </div>
                  ))}
                </div>
                <p className="text-[10px]" style={{ color: "var(--text-faint)" }}>
                  Keyingi {data?.ml_forecast?.projection?.length ?? 0} candle proyeksiyasi
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
            <CardHeader icon={<Target className="w-4 h-4" />} title="So'nggi Signal" />
            {sig ? (
              <div className="mt-3 space-y-2">
                <div className="flex items-center gap-2">
                  {sig.type === "BUY"  && <span className="flex items-center gap-1 text-sm font-black text-green-400"><TrendingUp className="w-4 h-4" /> BUY</span>}
                  {sig.type === "SELL" && <span className="flex items-center gap-1 text-sm font-black text-red-400"><TrendingDown className="w-4 h-4" /> SELL</span>}
                  <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                    {sig.confidence?.toFixed(1)}% ishonch
                  </span>
                </div>
                <div className="space-y-1">
                  {[
                    { label: "Entry",       val: sig.entry, color: "var(--gold)" },
                    { label: "Stop Loss",   val: sig.sl,    color: "#ef4444" },
                    { label: "Take Profit", val: sig.tp,    color: "#22c55e" },
                  ].map(({ label, val, color }) => val ? (
                    <div key={label} className="flex justify-between text-xs">
                      <span style={{ color: "var(--text-muted)" }}>{label}</span>
                      <span className="font-mono" style={{ color }}>{val.toFixed(2)}</span>
                    </div>
                  ) : null)}
                  {sig.rr && (
                    <div className="flex justify-between text-xs">
                      <span style={{ color: "var(--text-muted)" }}>R/R</span>
                      <span className="font-mono" style={{ color: "var(--gold)" }}>{sig.rr.toFixed(2)}R</span>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>Hali signal yo'q</p>
            )}
          </div>
        </Card>

        {/* SMC Patterns */}
        <Card>
          <div className="p-4">
            <CardHeader icon={<BarChart3 className="w-4 h-4" />} title="SMC Patternlar" />
            <div className="mt-3 space-y-2">
              {/* Order Blocks */}
              <div>
                <p className="text-[10px] font-medium mb-1" style={{ color: "var(--text-muted)" }}>Order Blocks</p>
                <div className="flex gap-2">
                  <span className="flex items-center gap-1 text-[11px] font-mono text-green-400">
                    <span className="w-2 h-2 rounded-sm" style={{ background: "#22c55e" }} />
                    Bull: {bullObs}
                  </span>
                  <span className="flex items-center gap-1 text-[11px] font-mono text-red-400">
                    <span className="w-2 h-2 rounded-sm" style={{ background: "#ef4444" }} />
                    Bear: {bearObs}
                  </span>
                </div>
              </div>

              {/* FVG */}
              <div>
                <p className="text-[10px] font-medium mb-1" style={{ color: "var(--text-muted)" }}>Fair Value Gaps</p>
                <div className="flex gap-2">
                  <span className="flex items-center gap-1 text-[11px] font-mono text-green-400">
                    <span className="w-2 h-2 rounded-sm" style={{ background: "#22c55e" }} />
                    Bull: {bullFvg}
                  </span>
                  <span className="flex items-center gap-1 text-[11px] font-mono text-red-400">
                    <span className="w-2 h-2 rounded-sm" style={{ background: "#ef4444" }} />
                    Bear: {bearFvg}
                  </span>
                </div>
              </div>

              {/* S/R levels */}
              <div>
                <p className="text-[10px] font-medium mb-1" style={{ color: "var(--text-muted)" }}>Support / Resistance</p>
                <div className="flex gap-2">
                  <span className="text-[11px] font-mono text-green-400">S: {supports}</span>
                  <span className="text-[11px] font-mono text-red-400">R: {resists}</span>
                </div>
              </div>

              {/* Overall SMC bias */}
              {(bullObs + bullFvg) !== (bearObs + bearFvg) && (
                <div className={`rounded-lg px-2 py-1 text-center text-[11px] font-medium mt-1 ${
                  (bullObs + bullFvg) > (bearObs + bearFvg)
                    ? "bg-green-500/10 text-green-400"
                    : "bg-red-500/10 text-red-400"
                }`}>
                  SMC Bias: {(bullObs + bullFvg) > (bearObs + bearFvg) ? "Bullish" : "Bearish"}
                </div>
              )}
            </div>
          </div>
        </Card>

        {/* Fibonacci Key Levels */}
        <Card>
          <div className="p-4">
            <CardHeader icon={<Layers className="w-4 h-4" />} title="Fibonacci" />
            {fib?.levels ? (
              <div className="mt-3 space-y-1">
                {fib.trend && (
                  <div className={`text-[10px] mb-2 font-medium ${fib.trend === "up" ? "text-green-400" : "text-red-400"}`}>
                    Trend: {fib.trend === "up" ? "↑ Yuqori" : "↓ Pastga"}
                  </div>
                )}
                {Object.entries(fib.levels).map(([ratio, level]) => {
                  const isKey = ["0.382", "0.5", "0.618"].includes(ratio);
                  return (
                    <div key={ratio} className="flex justify-between text-[11px]">
                      <span style={{ color: isKey ? "#a78bfa" : "var(--text-faint)" }}>
                        {isKey ? "★ " : "  "}Fib {ratio}
                      </span>
                      <span className="font-mono" style={{ color: isKey ? "#c4b5fd" : "var(--text-muted)" }}>
                        {(level as number).toFixed(2)}
                      </span>
                    </div>
                  );
                })}
                {fib.swing_high && (
                  <div className="border-t mt-2 pt-2 space-y-1" style={{ borderColor: "var(--surface-2)" }}>
                    <div className="flex justify-between text-[10px]">
                      <span style={{ color: "var(--text-faint)" }}>Swing High</span>
                      <span className="font-mono text-green-400">{fib.swing_high.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between text-[10px]">
                      <span style={{ color: "var(--text-faint)" }}>Swing Low</span>
                      <span className="font-mono text-red-400">{fib.swing_low.toFixed(2)}</span>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>Yuklanmoqda…</p>
            )}
          </div>
        </Card>
      </div>

      {/* ── Order Blocks & FVG detail table ── */}
      {(obs.length > 0 || fvgs.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

          {/* Order Blocks detail */}
          {obs.length > 0 && (
            <Card>
              <div className="p-4 pb-0">
                <CardHeader icon={<BarChart3 className="w-4 h-4" />} title="Order Blocks" />
              </div>
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Tur</th>
                      <th className="text-right">Yuqori</th>
                      <th className="text-right">Past</th>
                      <th className="text-right">Kenglik</th>
                    </tr>
                  </thead>
                  <tbody>
                    {obs.map((ob, i) => (
                      <tr key={i} className={ob.type === "bullish" ? "bg-green-500/5" : "bg-red-500/5"}>
                        <td>
                          <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded ${
                            ob.type === "bullish"
                              ? "bg-green-500/15 text-green-400"
                              : "bg-red-500/15 text-red-400"
                          }`}>
                            {ob.type === "bullish" ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                            {ob.type === "bullish" ? "Bullish" : "Bearish"}
                          </span>
                        </td>
                        <td className="text-right font-mono text-xs text-green-400">{ob.high.toFixed(2)}</td>
                        <td className="text-right font-mono text-xs text-red-400">{ob.low.toFixed(2)}</td>
                        <td className="text-right font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                          {(ob.high - ob.low).toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {/* FVG detail */}
          {fvgs.length > 0 && (
            <Card>
              <div className="p-4 pb-0">
                <CardHeader icon={<Minus className="w-4 h-4" />} title="Fair Value Gaps" />
              </div>
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Tur</th>
                      <th className="text-right">Yuqori</th>
                      <th className="text-right">Past</th>
                      <th className="text-right">Gap</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fvgs.map((fvg, i) => (
                      <tr key={i} className={fvg.type === "bullish" ? "bg-green-500/5" : "bg-red-500/5"}>
                        <td>
                          <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded ${
                            fvg.type === "bullish"
                              ? "bg-green-500/15 text-green-400"
                              : "bg-red-500/15 text-red-400"
                          }`}>
                            {fvg.type === "bullish" ? "Bullish" : "Bearish"} FVG
                          </span>
                        </td>
                        <td className="text-right font-mono text-xs text-green-400">{fvg.high.toFixed(2)}</td>
                        <td className="text-right font-mono text-xs text-red-400">{fvg.low.toFixed(2)}</td>
                        <td className="text-right font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                          {(fvg.high - fvg.low).toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      )}

      {/* ── Support / Resistance levels ── */}
      {srs.length > 0 && (
        <Card>
          <div className="p-4 pb-0">
            <CardHeader icon={<Target className="w-4 h-4" />} title="Support & Resistance Levellar" />
          </div>
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Tur</th>
                  <th className="text-right">Narx</th>
                  {livePrice && <th className="text-right">Joriy narxdan farq</th>}
                </tr>
              </thead>
              <tbody>
                {[...srs]
                  .sort((a, b) => b.level - a.level)
                  .map((sr, i) => {
                    const diff = livePrice ? (sr.level - livePrice) : null;
                    return (
                      <tr key={i} className={sr.type === "support" ? "bg-green-500/5" : "bg-red-500/5"}>
                        <td>
                          <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                            sr.type === "support"
                              ? "bg-green-500/15 text-green-400"
                              : "bg-red-500/15 text-red-400"
                          }`}>
                            {sr.type === "support" ? "Support" : "Resistance"}
                          </span>
                        </td>
                        <td className={`text-right font-mono text-sm font-bold ${
                          sr.type === "support" ? "text-green-400" : "text-red-400"
                        }`}>
                          {sr.level.toFixed(2)}
                        </td>
                        {livePrice && diff !== null && (
                          <td className="text-right font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                            {diff > 0 ? "+" : ""}{diff.toFixed(2)}
                          </td>
                        )}
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* ── Tarixiy tahlil (Historical Analysis) ── */}
      {(seasonality || eventImpact || zoneAnalysis) && (
        <div>
          <h2 className="text-sm font-semibold mb-3" style={{ color: "var(--text-muted)" }}>
            📅 Tarixiy tahlil
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

            {/* Seasonality */}
            {seasonality && !seasonality.insufficient_data && (
              <Card>
                <div className="p-4">
                  <p className="text-xs font-semibold mb-2" style={{ color: "var(--text-muted)" }}>
                    🗓 Oylik mavsumiylik
                  </p>
                  <p className="text-sm" style={{ color: "var(--text)" }}>
                    Bu oyda oltin tarixan:{" "}
                    <span className={`font-bold ${(seasonality.avg_change_pct as number) >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {(seasonality.avg_change_pct as number) >= 0 ? "↑" : "↓"}{" "}
                      {(seasonality.win_rate_pct as number).toFixed(0)}% hollarda ko'tarilgan
                    </span>
                    {", o'rtacha "}
                    <span className="font-mono font-bold" style={{ color: "var(--gold)" }}>
                      {(seasonality.avg_change_pct as number) >= 0 ? "+" : ""}
                      {(seasonality.avg_change_pct as number).toFixed(2)}%
                    </span>
                  </p>
                  <p className="text-[10px] mt-2" style={{ color: "var(--text-faint)" }}>
                    {seasonality.years_analyzed as number} yil tahlil qilindi
                  </p>
                </div>
              </Card>
            )}

            {/* Event impact */}
            {eventImpact && !eventImpact.insufficient_data && (
              <Card>
                <div className="p-4">
                  <p className="text-xs font-semibold mb-2" style={{ color: "var(--text-muted)" }}>
                    📰 NFP / FOMC ta'siri
                  </p>
                  <p className="text-sm" style={{ color: "var(--text)" }}>
                    Voqealardan keyin o'rtacha harakat:{" "}
                    <span className={`font-bold font-mono ${(eventImpact.avg_post_24h_move as number) >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {(eventImpact.avg_post_24h_move as number) >= 0 ? "+" : ""}
                      {(eventImpact.avg_post_24h_move as number).toFixed(2)}$
                    </span>
                  </p>
                  <p className="text-[10px] mt-2" style={{ color: "var(--text-faint)" }}>
                    Bullish: {(eventImpact.bullish_after_pct as number).toFixed(0)}% |{" "}
                    {eventImpact.events_analyzed as number} ta voqea
                  </p>
                </div>
              </Card>
            )}

            {/* Zone analysis */}
            {zoneAnalysis && !zoneAnalysis.insufficient_data && (zoneAnalysis.touches as number) > 0 && (
              <Card>
                <div className="p-4">
                  <p className="text-xs font-semibold mb-2" style={{ color: "var(--text-muted)" }}>
                    🎯 Zona sinovi
                  </p>
                  <p className="text-sm" style={{ color: "var(--text)" }}>
                    <span className="font-mono font-bold" style={{ color: "var(--gold)" }}>
                      ${(zoneAnalysis.zone_price as number).toFixed(2)}
                    </span>{" "}
                    zona{" "}
                    <span className="font-bold">{zoneAnalysis.touches as number} marta</span> sinaldi —{" "}
                    <span className="text-green-400 font-bold">
                      {(zoneAnalysis.bounce_rate_pct as number).toFixed(0)}%
                    </span>{" "}
                    hollarda qaytgan
                  </p>
                  {Boolean(zoneAnalysis.last_touch_date) && (
                    <p className="text-[10px] mt-2" style={{ color: "var(--text-faint)" }}>
                      Oxirgi sinov: {String(zoneAnalysis.last_touch_date)}
                    </p>
                  )}
                </div>
              </Card>
            )}

          </div>
        </div>
      )}
    </div>
  );
}
