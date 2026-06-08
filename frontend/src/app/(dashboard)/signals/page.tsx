"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { signalApi } from "@/lib/api";
import { formatPrice } from "@/lib/utils";
import {
  Card, CardHeader, PageHeader, SignalBadge, ScoreBar,
  Select, EmptyState, SkeletonRow,
} from "@/components/ui";
import { Zap, RefreshCw, TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { Signal } from "@/types";

const SYMBOLS = [
  { value: "XAUUSD", label: "XAUUSD" },
  { value: "EURUSD", label: "EURUSD" },
  { value: "GBPUSD", label: "GBPUSD" },
];
const TIMEFRAMES = [
  { value: "1", label: "M1" }, { value: "5", label: "M5" },
  { value: "15", label: "M15" }, { value: "60", label: "H1" },
  { value: "240", label: "H4" },
];
const SCORE_WEIGHTS = [
  { key: "technical_score", label: "Technical", w: 35 },
  { key: "smc_score",       label: "SMC",       w: 25 },
  { key: "ml_score",        label: "ML",        w: 20 },
  { key: "news_score",      label: "News",      w: 10 },
  { key: "economic_score",  label: "Economic",  w: 10 },
];

export default function SignalsPage() {
  const [symbol, setSymbol] = useState("XAUUSD");
  const [timeframe, setTimeframe] = useState("60");
  const qc = useQueryClient();

  const { data: signals, isLoading } = useQuery({
    queryKey: ["signals", symbol, timeframe],
    queryFn: () => signalApi.list(symbol, timeframe, 50).then(r => r.data),
  });

  const generateMut = useMutation({
    mutationFn: () => signalApi.generate(symbol, timeframe).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["signals"] }),
  });

  const latest = generateMut.data;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-5">
      <PageHeader
        title="Trading Signals"
        subtitle="AI-generated XAUUSD signals combining TA + SMC + ML + News"
        action={
          <div className="flex items-center gap-2">
            <Select options={SYMBOLS} value={symbol} onChange={e => setSymbol(e.target.value)} className="w-28" />
            <Select options={TIMEFRAMES} value={timeframe} onChange={e => setTimeframe(e.target.value)} className="w-20" />
            <button
              onClick={() => generateMut.mutate()}
              disabled={generateMut.isPending}
              className="btn btn-gold"
            >
              {generateMut.isPending ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Zap className="w-3.5 h-3.5" />
              )}
              {generateMut.isPending ? "Generating…" : "Generate"}
            </button>
          </div>
        }
      />

      {/* Generated signal result */}
      {latest && (
        <Card className={
          latest.signal_type === "BUY"  ? "border-green-500/40" :
          latest.signal_type === "SELL" ? "border-red-500/40"   : ""
        }>
          <div className="p-5">
            {/* ── Signal type banner ── */}
            <div className={`rounded-xl px-5 py-4 mb-5 flex items-center justify-between ${
              latest.signal_type === "BUY"
                ? "bg-green-500/10 border border-green-500/30"
                : latest.signal_type === "SELL"
                ? "bg-red-500/10 border border-red-500/30"
                : "bg-gray-500/10 border border-gray-500/20"
            }`}>
              <div className="flex items-center gap-3">
                {latest.signal_type === "BUY"  && <TrendingUp  className="w-7 h-7 text-green-400" />}
                {latest.signal_type === "SELL" && <TrendingDown className="w-7 h-7 text-red-400"   />}
                {latest.signal_type === "NO TRADE" && <Minus   className="w-7 h-7 text-gray-400"   />}
                <div>
                  <p className={`text-2xl font-black tracking-wide ${
                    latest.signal_type === "BUY"  ? "text-green-400" :
                    latest.signal_type === "SELL" ? "text-red-400"   : "text-gray-400"
                  }`}>
                    {latest.signal_type}
                  </p>
                  <p className="text-[12px] font-medium" style={{ color: "var(--text-muted)" }}>
                    {latest.symbol} · {latest.timeframe === "60" ? "H1" : latest.timeframe === "240" ? "H4" : `${latest.timeframe}m`}
                  </p>
                </div>
              </div>
              <div className="text-right">
                <p className={`text-xl font-bold font-mono ${
                  latest.confidence > 70 ? "text-green-400" :
                  latest.confidence > 50 ? "text-yellow-400" : "text-red-400"
                }`}>
                  {latest.confidence?.toFixed(1)}%
                </p>
                <p className="text-[11px]" style={{ color: "var(--text-faint)" }}>
                  confidence
                </p>
              </div>
            </div>

            {/* Trade plan */}
            {latest.signal_type !== "NO TRADE" ? (
              <div className="grid grid-cols-4 gap-3 mb-5">
                {[
                  { label: "Entry",       value: formatPrice(latest.entry, 2),       color: "text-white" },
                  { label: "Stop Loss",   value: formatPrice(latest.stop_loss, 2),   color: "text-red-400" },
                  { label: "Take Profit", value: formatPrice(latest.take_profit, 2), color: "text-green-400" },
                  { label: "Risk/Reward", value: latest.risk_reward ? `${latest.risk_reward?.toFixed(2)} R` : "—", color: "text-[var(--gold)]" },
                ].map(f => (
                  <div key={f.label}
                    className="rounded-lg p-3 text-center"
                    style={{ background: "var(--surface-2)" }}
                  >
                    <p className="text-[10px] mb-1" style={{ color: "var(--text-muted)" }}>{f.label}</p>
                    <p className={`text-base font-bold font-mono ${f.color}`}>{f.value}</p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-lg px-4 py-3 mb-5 text-center"
                style={{ background: "var(--surface-2)", color: "var(--text-muted)" }}>
                <p className="text-sm">Bozor yo'nalishi aniq emas — hozircha savdo ochish tavsiya etilmaydi.</p>
                <p className="text-xs mt-1" style={{ color: "var(--text-faint)" }}>
                  Multi-timeframe tahlillar orasida ziddiyat aniqlandi.
                </p>
              </div>
            )}

            {/* Score breakdown */}
            <div className="space-y-2 mb-4">
              {SCORE_WEIGHTS.map(sw => {
                const score = latest[sw.key as keyof typeof latest] as number ?? 50;
                const dir = score > 55 ? "bullish" : score < 45 ? "bearish" : "neutral";
                return (
                  <div key={sw.key} className="flex items-center gap-3">
                    <span className="text-[11px] w-20 shrink-0" style={{ color: "var(--text-muted)" }}>
                      {sw.label} {sw.w}%
                    </span>
                    <ScoreBar score={score} direction={dir} className="flex-1" />
                    <span className="text-[11px] font-mono w-10 text-right" style={{ color: "var(--text)" }}>
                      {score?.toFixed(0)}
                    </span>
                  </div>
                );
              })}
            </div>

            {/* Reasoning */}
            {latest.reasoning && (
              <p className="text-[12px] leading-relaxed rounded-lg p-3"
                style={{ background: "var(--surface-2)", color: "var(--text-muted)" }}>
                {latest.reasoning}
              </p>
            )}
          </div>
        </Card>
      )}

      {/* Signals history table */}
      <Card>
        <div className="p-4 pb-0">
          <CardHeader icon={<Zap className="w-4 h-4" />} title="Signal History" />
        </div>
        {isLoading ? (
          <div className="divide-y" style={{ borderColor: "var(--surface-2)" }}>
            {Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)}
          </div>
        ) : signals?.length ? (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Signal</th>
                  <th>Symbol</th>
                  <th className="text-right">Entry</th>
                  <th className="text-right">SL</th>
                  <th className="text-right">TP</th>
                  <th className="text-right">R:R</th>
                  <th className="text-right">Conf</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((s: Signal) => (
                  <tr key={s.id} className={
                    s.signal_type === "BUY"  ? "bg-green-500/5 hover:bg-green-500/10" :
                    s.signal_type === "SELL" ? "bg-red-500/5 hover:bg-red-500/10"     :
                    "hover:bg-[var(--surface-2)]"
                  }>
                    <td>
                      <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-sm font-black tracking-wide ${
                        s.signal_type === "BUY"
                          ? "bg-green-500/15 text-green-400 border border-green-500/30"
                          : s.signal_type === "SELL"
                          ? "bg-red-500/15 text-red-400 border border-red-500/30"
                          : "bg-gray-500/10 text-gray-400 border border-gray-500/20"
                      }`}>
                        {s.signal_type === "BUY"  && <TrendingUp  className="w-3.5 h-3.5" />}
                        {s.signal_type === "SELL" && <TrendingDown className="w-3.5 h-3.5" />}
                        {s.signal_type === "NO TRADE" && <Minus   className="w-3.5 h-3.5" />}
                        {s.signal_type}
                      </span>
                    </td>
                    <td className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                      {s.symbol} {s.timeframe}m
                    </td>
                    <td className="text-right font-mono text-xs text-white">{formatPrice(s.entry)}</td>
                    <td className="text-right font-mono text-xs text-red-400">{formatPrice(s.stop_loss)}</td>
                    <td className="text-right font-mono text-xs text-green-400">{formatPrice(s.take_profit)}</td>
                    <td className="text-right font-mono text-xs" style={{ color: "var(--gold)" }}>
                      {s.rr?.toFixed(2) ?? "—"}
                    </td>
                    <td className="text-right text-xs" style={{ color: "var(--text-muted)" }}>
                      {s.confidence?.toFixed(1)}%
                    </td>
                    <td className="text-xs" style={{ color: "var(--text-faint)" }}>
                      {new Date(s.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            icon={<Zap className="w-8 h-8" />}
            title="No signals yet"
            description="Click Generate to create the first signal"
          />
        )}
      </Card>
    </div>
  );
}
