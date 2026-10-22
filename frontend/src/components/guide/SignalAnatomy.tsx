"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

interface Field { key: string; label: string; value: string; color?: string; explain: string; tip: string }

const FIELDS: Field[] = [
  { key: "type", label: "Yo‘nalish", value: "BUY", color: "var(--green)",
    explain: "Tizim narx ko‘tariladi deb hisoblaydi. SELL bo‘lsa — tushadi deb, NO TRADE bo‘lsa — hech narsa qilmang.",
    tip: "Brokerda «Buy» tugmasini tanlaysiz." },
  { key: "time", label: "Vaqt", value: "2026-10-22 08:00 UTC",
    explain: "4 soatlik sham yopilgan vaqt. UTC dagi vaqt — Toshkent vaqti uchun 5 soat qo‘shing (13:00).",
    tip: "Signal faqat yopilgan sham bo‘yicha hisoblanadi — u «o‘zgarib ketmaydi»." },
  { key: "entry", label: "Kirish", value: "4 000.00",
    explain: "Signal hisoblangan narx. Real kirishingiz shu narxga yaqin bo‘lishi kerak.",
    tip: "Market buyurtma bilan, narx zona ichida bo‘lsa." },
  { key: "zone", label: "Kirish zonasi", value: "3 994 – 4 002",
    explain: "Kirish uchun ruxsat etilgan oraliq. Narx bu oraliqdan chiqib ketgan bo‘lsa — kirmang.",
    tip: "Brokerdagi joriy narxni zona bilan solishtiring." },
  { key: "sl", label: "Stop Loss", value: "3 980.00", color: "var(--red)",
    explain: "Narx shu yerga tushsa, savdo avtomatik zarar bilan yopiladi. Bu sizning «xavfsizlik kamaringiz».",
    tip: "Buyurtma oynasidagi «S/L» maydoniga yozing." },
  { key: "tp1", label: "TP1 (1R)", value: "4 020.00", color: "rgba(34,197,94,0.75)",
    explain: "Oraliq foyda nuqtasi. Xohlasangiz bu yerda pozitsiyaning bir qismini yopishingiz mumkin.",
    tip: "Majburiy emas. Natijalar asosiy TP bo‘yicha hisoblangan." },
  { key: "tp", label: "Take Profit", value: "4 050.00", color: "var(--green)",
    explain: "Asosiy maqsad. Narx shu yerga yetsa, savdo avtomatik foyda bilan yopiladi.",
    tip: "Buyurtma oynasidagi «T/P» maydoniga yozing." },
  { key: "rr", label: "R/R", value: "2.5 (net 2.4)",
    explain: "Foyda zararning 2.5 barobari. «Net» — spread va slippage chegirilgandan keyingi qiymat.",
    tip: "Shuning uchun 10 ta savdodan 4 tasi yutsa ham natija musbat bo‘lishi mumkin." },
  { key: "score", label: "Signal score", value: "72 / 100",
    explain: "Setup qoidalari qanchalik yaxshi bajarilgani. YUTISH EHTIMOLI EMAS.",
    tip: "Score ga qarab lotni oshirmang." },
  { key: "regime", label: "Rejim", value: "TREND_UP · D1: UP",
    explain: "4 soatlik grafikda ko‘tarilish trendi, kunlik grafik ham tasdiqlaydi.",
    tip: "Ikkalasi mos kelmasa, tizim signal bermaydi." },
  { key: "lot", label: "Lot", value: "0.02",
    explain: "Taklif etilgan hajm: 10 000 $ hisobda 0.5% risk. SL ishlasa, zarar ≈ 40 $ bo‘ladi.",
    tip: "Brokeringizdagi kontrakt hajmini tekshiring (odatda 1 lot = 100 oz)." },
  { key: "expires", label: "Amal qiladi", value: "16:00 UTC gacha",
    explain: "Shu vaqtgacha kirilmasa — signal eskirgan, kirmang.",
    tip: "Kech qolgan bo‘lsangiz, keyingi signalni kuting." },
];

export function SignalAnatomy() {
  const [active, setActive] = useState<string>("type");
  const f = FIELDS.find(x => x.key === active)!;
  return (
    <div className="grid md:grid-cols-2 gap-4">
      <div className="card p-4">
        <p className="text-xs mb-3" style={{ color: "var(--text-faint)" }}>Namuna signal — istalgan qatorni bosing</p>
        <div className="space-y-1">
          {FIELDS.map(x => (
            <button key={x.key} onClick={() => setActive(x.key)}
                    className={cn("w-full flex items-center justify-between px-3 py-2 rounded-md text-sm transition-colors text-left")}
                    style={active === x.key
                      ? { background: "rgba(245,166,35,0.1)", outline: "1px solid rgba(245,166,35,0.4)" }
                      : { background: "transparent" }}>
              <span style={{ color: "var(--text-muted)" }}>{x.label}</span>
              <span className="font-mono font-semibold" style={{ color: x.color ?? "var(--text)" }}>{x.value}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="card p-5 md:sticky md:top-4 self-start">
        <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--gold)" }}>{f.label}</p>
        <p className="font-mono text-xl font-bold mb-3" style={{ color: f.color ?? "var(--text)" }}>{f.value}</p>
        <p className="text-sm leading-relaxed mb-3" style={{ color: "var(--text)" }}>{f.explain}</p>
        <p className="text-sm leading-relaxed rounded-md px-3 py-2" style={{ background: "var(--surface-2)", color: "var(--text-muted)" }}>
          <b style={{ color: "var(--text)" }}>Amalda: </b>{f.tip}
        </p>
      </div>
    </div>
  );
}
