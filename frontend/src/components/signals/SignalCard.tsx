"use client";

import { useState } from "react";
import {
  CheckCircle2,
  XCircle,
  MinusCircle,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Minus,
} from "lucide-react";

// ── Types ────────────────────────────────────────────────────────────────────

interface ReasoningLayer {
  name: string;
  score: number;
  direction: string;
  status: "confirm" | "conflict" | "neutral";
  bullets: string[];
}

interface ReasoningStructured {
  summary: string;
  layers: ReasoningLayer[];
  risk_summary: string;
  caution: string | null;
}

export interface Signal {
  id: string;
  signal_type: "BUY" | "SELL" | "NO TRADE";
  symbol: string;
  timeframe: string;
  composite_score: number;
  confidence: number;
  entry: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  risk_reward: number | null;
  lot_size: number | null;
  reasoning_structured?: ReasoningStructured;
  reasoning: string;
  timestamp: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatPrice(price: number | null): string {
  if (price === null || price === undefined) return "—";
  return price.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function timeAgo(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function buildCopyText(signal: Signal): string {
  const rr = signal.risk_reward != null ? `1:${signal.risk_reward.toFixed(1)}` : "N/A";
  const lots = signal.lot_size != null ? signal.lot_size.toFixed(2) : "N/A";
  return [
    "GOLD AI SIGNAL",
    `${signal.signal_type} ${signal.symbol}`,
    `Entry: ${formatPrice(signal.entry)}`,
    `SL: ${formatPrice(signal.stop_loss)}`,
    `TP: ${formatPrice(signal.take_profit)}`,
    `R/R: ${rr}`,
    `Lots: ${lots}`,
  ].join("\n");
}

// ── Sub-components ────────────────────────────────────────────────────────────

const BADGE: Record<Signal["signal_type"], string> = {
  BUY:       "bg-green-100 text-green-800",
  SELL:      "bg-red-100 text-red-800",
  "NO TRADE":"bg-gray-100 text-gray-700",
};

const SIGNAL_ICON: Record<Signal["signal_type"], JSX.Element> = {
  BUY:       <TrendingUp  className="w-4 h-4" />,
  SELL:      <TrendingDown className="w-4 h-4" />,
  "NO TRADE":<Minus        className="w-4 h-4" />,
};

function StatusIcon({ status }: { status: ReasoningLayer["status"] }) {
  if (status === "confirm")
    return <CheckCircle2 className="w-4 h-4 shrink-0 text-green-500" />;
  if (status === "conflict")
    return <XCircle      className="w-4 h-4 shrink-0 text-red-500"   />;
  return       <MinusCircle  className="w-4 h-4 shrink-0 text-gray-500"  />;
}

function ScorePill({ score, status }: { score: number; status: ReasoningLayer["status"] }) {
  const color =
    status === "confirm" ? "bg-green-900/40 text-green-400" :
    status === "conflict" ? "bg-red-900/40 text-red-400"    :
    "bg-gray-800 text-gray-400";
  return (
    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${color}`}>
      {score.toFixed(0)}
    </span>
  );
}

function LayerRow({ layer }: { layer: ReasoningLayer }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-[var(--border)] rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-[var(--surface-2)] transition-colors"
      >
        <StatusIcon status={layer.status} />
        <span className="flex-1 text-xs font-medium text-[var(--text-muted)]">
          {layer.name}
        </span>
        <ScorePill score={layer.score} status={layer.status} />
        {open
          ? <ChevronUp   className="w-3.5 h-3.5 text-[var(--text-faint)] ml-1" />
          : <ChevronDown className="w-3.5 h-3.5 text-[var(--text-faint)] ml-1" />}
      </button>

      {open && layer.bullets.length > 0 && (
        <ul className="px-4 pb-3 pt-1 space-y-1 bg-[var(--surface-2)]">
          {layer.bullets.map((b, i) => (
            <li key={i} className="text-[11px] text-[var(--text-muted)] flex gap-1.5 leading-relaxed">
              <span className="text-[var(--text-faint)] shrink-0 mt-0.5">·</span>
              {b}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function SignalCard({ signal }: { signal: Signal }) {
  const [reasoningOpen, setReasoningOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const rs = signal.reasoning_structured;
  const caution = rs?.caution ?? null;
  const isActionable = signal.signal_type !== "NO TRADE";

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(buildCopyText(signal));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard may be blocked in non-HTTPS context
    }
  }

  // Confidence bar colour: green > 70, amber > 50, red otherwise
  const confColor =
    signal.confidence > 70 ? "#16a34a" :
    signal.confidence > 50 ? "#ca8a04" : "#dc2626";

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 space-y-4 transition-colors hover:border-[var(--border-2)]">

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          {/* Signal type badge */}
          <span className={`inline-flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-full ${BADGE[signal.signal_type]}`}>
            {SIGNAL_ICON[signal.signal_type]}
            {signal.signal_type}
          </span>

          {/* Symbol + timeframe */}
          <span className="text-sm font-semibold text-[var(--text)]">
            {signal.symbol}
          </span>
          <span className="text-[11px] text-[var(--text-faint)] bg-[var(--surface-2)] px-2 py-0.5 rounded">
            {signal.timeframe === "60" ? "H1" :
             signal.timeframe === "240" ? "H4" :
             signal.timeframe === "1440" ? "D1" :
             signal.timeframe === "15" ? "M15" :
             `${signal.timeframe}m`}
          </span>
        </div>

        {/* Timestamp */}
        <span className="text-[11px] text-[var(--text-faint)] shrink-0 mt-0.5">
          {timeAgo(signal.timestamp)}
        </span>
      </div>

      {/* ── Caution banner ──────────────────────────────────────────────────── */}
      {caution && (
        <div className="flex items-start gap-2 rounded-lg bg-yellow-500/10 border border-yellow-500/25 px-3 py-2.5">
          <AlertTriangle className="w-4 h-4 text-yellow-500 shrink-0 mt-0.5" />
          <p className="text-xs text-yellow-400 leading-relaxed">{caution}</p>
        </div>
      )}

      {/* ── Price grid ──────────────────────────────────────────────────────── */}
      {isActionable && (
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "Entry",       value: signal.entry,       accent: "text-[var(--gold)]" },
            { label: "Stop Loss",   value: signal.stop_loss,   accent: "text-red-400"       },
            { label: "Take Profit", value: signal.take_profit, accent: "text-green-400"     },
          ].map(({ label, value, accent }) => (
            <div key={label} className="rounded-lg bg-[var(--surface-2)] p-3 text-center">
              <p className="text-[10px] uppercase tracking-wider text-[var(--text-faint)] mb-1">
                {label}
              </p>
              <p className={`text-base font-bold font-mono leading-tight ${accent}`}>
                {formatPrice(value)}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* ── R/R + Composite score ────────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        {signal.risk_reward != null && (
          <div className="flex items-center gap-1.5 rounded-lg bg-[var(--surface-2)] px-3 py-2">
            <span className="text-[10px] text-[var(--text-faint)] uppercase tracking-wider">R/R</span>
            <span className="text-sm font-bold font-mono text-[var(--gold)]">
              1:{signal.risk_reward.toFixed(1)}
            </span>
          </div>
        )}
        {signal.lot_size != null && (
          <div className="flex items-center gap-1.5 rounded-lg bg-[var(--surface-2)] px-3 py-2">
            <span className="text-[10px] text-[var(--text-faint)] uppercase tracking-wider">Lots</span>
            <span className="text-sm font-bold font-mono text-[var(--text)]">
              {signal.lot_size.toFixed(2)}
            </span>
          </div>
        )}
        <div className="flex items-center gap-1.5 rounded-lg bg-[var(--surface-2)] px-3 py-2">
          <span className="text-[10px] text-[var(--text-faint)] uppercase tracking-wider">Score</span>
          <span className="text-sm font-bold font-mono text-[var(--text)]">
            {signal.composite_score.toFixed(0)}
          </span>
        </div>
      </div>

      {/* ── Confidence bar ──────────────────────────────────────────────────── */}
      <div className="space-y-1.5">
        <div className="flex justify-between items-center">
          <span className="text-[10px] uppercase tracking-wider text-[var(--text-faint)]">
            Confidence
          </span>
          <span className="text-xs font-mono font-semibold" style={{ color: confColor }}>
            {signal.confidence.toFixed(1)}%
          </span>
        </div>
        <div className="h-2 rounded-full bg-[var(--surface-3)] overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${Math.min(100, Math.max(0, signal.confidence))}%`,
              background: confColor,
            }}
          />
        </div>
      </div>

      {/* ── Action buttons ──────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 pt-0.5">
        {/* Copy trade details */}
        {isActionable && (
          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text)] hover:border-[var(--border-2)] transition-colors"
          >
            {copied
              ? <><Check className="w-3.5 h-3.5 text-green-500" /><span className="text-green-500">Copied!</span></>
              : <><Copy  className="w-3.5 h-3.5" />Copy trade details</>
            }
          </button>
        )}

        {/* Why this signal? toggle */}
        <button
          onClick={() => setReasoningOpen(o => !o)}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text)] hover:border-[var(--border-2)] transition-colors ml-auto"
        >
          Why this signal?
          {reasoningOpen
            ? <ChevronUp   className="w-3.5 h-3.5" />
            : <ChevronDown className="w-3.5 h-3.5" />}
        </button>
      </div>

      {/* ── Reasoning accordion ──────────────────────────────────────────────── */}
      {reasoningOpen && (
        <div className="space-y-3 pt-1">
          {/* Summary line */}
          {rs?.summary && (
            <p className="text-xs text-[var(--text-muted)] font-medium">{rs.summary}</p>
          )}

          {/* Layer rows */}
          {rs?.layers && rs.layers.length > 0 ? (
            <div className="space-y-1.5">
              {rs.layers.map((layer) => (
                <LayerRow key={layer.name} layer={layer} />
              ))}
            </div>
          ) : (
            /* Fallback to plain reasoning text when structured data isn't available */
            <p className="text-xs text-[var(--text-muted)] leading-relaxed bg-[var(--surface-2)] rounded-lg px-3 py-2.5">
              {signal.reasoning}
            </p>
          )}

          {/* Risk summary */}
          {rs?.risk_summary && (
            <p className="text-[11px] text-[var(--text-faint)] bg-[var(--surface-2)] rounded-lg px-3 py-2">
              {rs.risk_summary}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
