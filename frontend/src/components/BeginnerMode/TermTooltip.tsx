"use client";

import { useState, useRef } from "react";

const TERMS: Record<string, string> = {
  "Stop Loss":    "Zarar chegarasi — narx bu darajaga tushsa, savdo avtomatik yopiladi",
  "Take Profit":  "Foyda olish darajasi — narx bu darajaga yetsa, savdo yopiladi",
  "Lot":          "Savdo hajmi birligi. 0.01 lot = 1 oz oltin ≈ $3 ta narx o'zgarishi",
  "RSI":          "Narxning haddan tashqari yuqori yoki pastligini ko'rsatuvchi indikator (0–100)",
  "MACD":         "Trend yo'nalishini ko'rsatuvchi indikator",
  "ATR":          "Bozorning o'rtacha harakat amplitudasi — volatillik o'lchovi",
  "Confluence":   "Bir nechta indikator bir xil yo'nalishni ko'rsatganda — kuchli signal",
  "SMC":          "Smart Money Concepts — yirik investorlar qayerda savdo qilishini aniqlash usuli",
  "Order Block":  "Yirik investorlar savdo qilgan narx zonasi — kuchli support/resistance",
  "FVG":          "Fair Value Gap — narx tez harakat qilganda qoldirgan bo'sh zona",
  "Swing High":   "So'nggi eng yuqori narx nuqtasi",
  "Swing Low":    "So'nggi eng past narx nuqtasi",
};

interface TermTooltipProps {
  term: string;
  children?: React.ReactNode;
}

export function TermTooltip({ term, children }: TermTooltipProps) {
  const [visible, setVisible] = useState(false);
  const definition = TERMS[term];
  const ref = useRef<HTMLSpanElement>(null);

  if (!definition) {
    return <>{children ?? term}</>;
  }

  return (
    <span
      ref={ref}
      className="relative inline-block cursor-help border-b border-dashed"
      style={{ borderColor: "var(--gold)" }}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onClick={() => setVisible((v) => !v)}
    >
      {children ?? term}
      {visible && (
        <span
          className="absolute z-50 bottom-full left-0 mb-1 w-64 rounded-lg px-3 py-2 text-xs shadow-lg"
          style={{
            background:  "var(--surface-1)",
            border:      "1px solid var(--surface-2)",
            color:       "var(--text)",
            lineHeight:  "1.5",
          }}
        >
          <strong className="block mb-0.5" style={{ color: "var(--gold)" }}>{term}</strong>
          {definition}
        </span>
      )}
    </span>
  );
}
