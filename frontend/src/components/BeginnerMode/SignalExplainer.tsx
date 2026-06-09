"use client";

import { useState } from "react";
import { TermTooltip } from "./TermTooltip";
import { ActionPanel } from "./ActionPanel";
import type { Signal } from "@/types";

interface SignalExplainerProps {
  signal: Signal & { [key: string]: unknown };
}

const UZ_TYPE: Record<string, string> = {
  BUY:       "SOTIB OLING",
  SELL:      "SOTING",
  NEUTRAL:   "KUTING",
  "NO TRADE": "KUTING",
};

function ConfidenceBar({ confidence }: { confidence: number }) {
  const color =
    confidence >= 70 ? "#22c55e" : confidence >= 50 ? "#facc15" : "#ef4444";
  return (
    <div className="mt-2">
      <div className="flex justify-between text-xs mb-1" style={{ color: "var(--text-muted)" }}>
        <span>Ishonch darajasi</span>
        <span className="font-mono" style={{ color }}>{confidence.toFixed(1)}%</span>
      </div>
      <div className="h-2.5 rounded-full overflow-hidden" style={{ background: "var(--surface-2)" }}>
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${confidence}%`, background: color }}
        />
      </div>
    </div>
  );
}

function PriceCard({
  label,
  price,
  diff,
  diffPct,
  color,
}: {
  label: string;
  price: number | null;
  diff?: number;
  diffPct?: number;
  color: string;
}) {
  return (
    <div
      className="flex flex-col items-center rounded-xl p-3 text-center"
      style={{ background: "var(--surface-2)" }}
    >
      <p className="text-[11px] mb-1" style={{ color: "var(--text-muted)" }}>{label}</p>
      <p className="text-xl font-bold font-mono" style={{ color }}>
        {price !== null ? `$${price.toFixed(2)}` : "—"}
      </p>
      {diff !== undefined && diffPct !== undefined && (
        <p className="text-[10px] mt-0.5" style={{ color: "var(--text-faint)" }}>
          ({diff > 0 ? "+" : ""}{diff.toFixed(2)} | {diffPct > 0 ? "+" : ""}{diffPct.toFixed(2)}%)
        </p>
      )}
    </div>
  );
}

export function SignalExplainer({ signal }: SignalExplainerProps) {
  const [reasoningOpen, setReasoningOpen] = useState(false);

  const {
    signal_type, signal_emoji, entry, stop_loss, tp1,
    lot_size, risk_amount_usd, sl_distance_pct, tp1_distance_pct, reasoning,
  } = signal;
  const confidence: number = (signal.confidence ?? 0) as number;

  const uzType   = UZ_TYPE[signal_type] ?? signal_type;
  const emoji    = signal_emoji ?? (signal_type === "BUY" ? "🟢" : signal_type === "SELL" ? "🔴" : "⚪");
  const isActive = signal_type === "BUY" || signal_type === "SELL";

  const slDiff  = entry && stop_loss  ? stop_loss  - entry : undefined;
  const tp1Diff = entry && tp1        ? tp1        - entry : undefined;

  const reasoningBullets = (reasoning ?? "")
    .split("|")
    .map((s) => s.trim())
    .filter(Boolean);

  return (
    <div className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--surface-2)" }}>
      {/* Header */}
      <div
        className={`px-5 py-4 flex items-center justify-between ${
          signal_type === "BUY"
            ? "bg-green-500/10 border-b border-green-500/20"
            : signal_type === "SELL"
            ? "bg-red-500/10 border-b border-red-500/20"
            : "bg-gray-500/10 border-b border-gray-500/15"
        }`}
      >
        <div className="flex items-center gap-3">
          <span className="text-5xl">{emoji}</span>
          <div>
            <p className={`text-3xl font-black tracking-wide ${
              signal_type === "BUY"
                ? "text-green-400"
                : signal_type === "SELL"
                ? "text-red-400"
                : "text-gray-400"
            }`}>
              {uzType}
            </p>
            <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
              XAUUSD · H1 savdo signali
            </p>
          </div>
        </div>
        {confidence < 60 && isActive && (
          <div className="flex items-center gap-1.5 rounded-lg px-3 py-2 bg-red-500/10 border border-red-500/30">
            <span>⚠️</span>
            <span className="text-xs text-red-400 font-medium">Ishonch past</span>
          </div>
        )}
      </div>

      <div className="p-4 space-y-4">
        {/* Confidence bar */}
        <ConfidenceBar confidence={confidence} />

        {/* Low confidence warning */}
        {confidence < 60 && isActive && (
          <div className="rounded-lg px-3 py-2 text-sm text-red-400 bg-red-500/10 border border-red-500/20">
            ⚠️ Ishonch past — bu signalda savdo qilmaslikni tavsiya etamiz
          </div>
        )}

        {/* Price grid */}
        {isActive && (
          <div className="grid grid-cols-3 gap-2">
            <PriceCard label="Kirish narxi" price={entry} color="white" />
            <PriceCard
              label="Stop Loss"
              price={stop_loss}
              diff={slDiff}
              diffPct={sl_distance_pct !== null ? (signal_type === "BUY" ? -(sl_distance_pct ?? 0) : (sl_distance_pct ?? 0)) : undefined}
              color="#ef4444"
            />
            <PriceCard
              label="Take Profit 1"
              price={tp1}
              diff={tp1Diff}
              diffPct={tp1_distance_pct ?? undefined}
              color="#22c55e"
            />
          </div>
        )}

        {/* Lot size card */}
        {lot_size !== null && lot_size !== undefined && (
          <div
            className="rounded-xl px-4 py-3 flex items-center justify-between"
            style={{ background: "var(--surface-2)" }}
          >
            <div>
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                <TermTooltip term="Lot">Lot hajmi</TermTooltip>
              </p>
              <p className="text-2xl font-bold font-mono" style={{ color: "var(--gold)" }}>
                {lot_size} lot
              </p>
            </div>
            {risk_amount_usd !== null && risk_amount_usd !== undefined && (
              <div className="text-right">
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>Risk summasi</p>
                <p className="text-base font-mono text-red-400">${risk_amount_usd.toFixed(2)}</p>
              </div>
            )}
          </div>
        )}

        {/* Reasoning accordion */}
        {reasoningBullets.length > 0 && (
          <div className="rounded-lg overflow-hidden" style={{ border: "1px solid var(--surface-2)" }}>
            <button
              onClick={() => setReasoningOpen((o) => !o)}
              className="w-full flex items-center justify-between px-3 py-2 text-sm font-medium"
              style={{ background: "var(--surface-2)", color: "var(--text)" }}
            >
              <span>🔍 Nima uchun bu signal?</span>
              <span>{reasoningOpen ? "▲" : "▼"}</span>
            </button>
            {reasoningOpen && (
              <ul className="px-3 py-2 space-y-1.5">
                {reasoningBullets.map((bullet, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs" style={{ color: "var(--text-muted)" }}>
                    <span className="shrink-0 mt-0.5">•</span>
                    <span>{bullet}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Action panel */}
        <ActionPanel signal={signal} />
      </div>
    </div>
  );
}
