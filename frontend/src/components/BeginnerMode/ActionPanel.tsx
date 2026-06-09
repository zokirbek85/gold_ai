"use client";

import type { Signal } from "@/types";

interface ActionPanelProps {
  signal: Signal & { [key: string]: unknown };
}

export function ActionPanel({ signal }: ActionPanelProps) {
  const { signal_type, entry, stop_loss, tp1, lot_size } = signal;

  if (signal_type === "NEUTRAL" || signal_type === "NO TRADE") {
    return (
      <div
        className="rounded-xl p-4 mt-4"
        style={{ background: "var(--surface-2)", border: "1px solid var(--surface-3)" }}
      >
        <p className="text-base font-semibold mb-1" style={{ color: "var(--text)" }}>
          🕐 Nima qilish kerak?
        </p>
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          Hozircha kuting. Yangi signal kelgunicha savdo qilmang.
        </p>
      </div>
    );
  }

  const isBuy  = signal_type === "BUY";
  const action = isBuy ? "XAUUSD sotib oling" : "XAUUSD soting";

  const steps = [
    {
      icon: "✅",
      text: entry
        ? `$${entry.toFixed(2)} narxda ${action}`
        : action,
    },
    {
      icon: "🛑",
      text: stop_loss
        ? `Stop Loss: $${stop_loss.toFixed(2)} ga o'rnating (broker platformasida)`
        : "Stop Loss: broker platformasida o'rnating",
    },
    {
      icon: "🎯",
      text: tp1
        ? `Take Profit 1: $${tp1.toFixed(2)} ga o'rnating`
        : "Take Profit 1 ni o'rnating",
    },
    {
      icon: "📊",
      text: lot_size
        ? `Lot hajmi: ${lot_size} lot (hisobingiz uchun xavfsiz)`
        : "Lot hajmini hisoblang",
    },
    {
      icon: "⏰",
      text: "Signal yaroqlilik muddati: 4 soat",
    },
  ];

  return (
    <div
      className="rounded-xl p-4 mt-4"
      style={{
        background: isBuy ? "rgba(34,197,94,0.05)" : "rgba(239,68,68,0.05)",
        border: `1px solid ${isBuy ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)"}`,
      }}
    >
      <p className="text-base font-semibold mb-3" style={{ color: "var(--text)" }}>
        📋 Nima qilish kerak?
      </p>
      <ol className="space-y-2">
        {steps.map((step, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <span className="shrink-0">{step.icon}</span>
            <span style={{ color: "var(--text-muted)" }}>
              <span className="font-medium" style={{ color: "var(--text)" }}>{i + 1}.</span>{" "}
              {step.text}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
