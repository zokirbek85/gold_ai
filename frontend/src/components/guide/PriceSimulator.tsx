"use client";

import { useMemo, useState } from "react";
import { Callout, Tabs, fmt } from "./Basics";

type Side = "BUY" | "SELL";
type Scenario = "win" | "loss" | "chase";

// Price paths as offsets from entry in units of risk (1 = SL distance), one point per step.
const PATHS: Record<Scenario, number[]> = {
  win:   [0, 0.2, -0.3, -0.5, 0.1, 0.6, 0.4, 1.0, 1.4, 1.1, 1.8, 2.2, 1.9, 2.6, 2.4],
  loss:  [0, 0.3, 0.5, 0.2, -0.2, -0.4, 0.1, -0.3, -0.7, -0.6, -1.1, -0.9, -1.3, -1.2, -1.0],
  chase: [0.9, 1.1, 1.3, 1.0, 0.6, 0.2, -0.3, -0.6, -1.1, -0.8, -0.5, -0.7, -0.9, -0.6, -0.4],
};
const SCEN_LABEL: Record<Scenario, string> = {
  win: "TP ga yetadi", loss: "SL ga yetadi", chase: "Kech kirish (quvlash)",
};

const ENTRY = 4000, RISK = 20, RR = 2.5;

export function PriceSimulator() {
  const [side, setSide] = useState<Side>("BUY");
  const [scen, setScen] = useState<Scenario>("win");
  const [t, setT] = useState(0);
  const [lots, setLots] = useState(0.02);

  const s = side === "BUY" ? 1 : -1;
  const sl = ENTRY - s * RISK, tp = ENTRY + s * RR * RISK, tp1 = ENTRY + s * RISK;
  const zone = side === "BUY" ? [ENTRY - 6, ENTRY + 2] : [ENTRY - 2, ENTRY + 6];
  const path = useMemo(() => PATHS[scen].map(x => ENTRY + s * x * RISK), [scen, s]);
  // In the "chase" scenario the trader enters at the first point, which is outside the zone.
  const entryPx = path[0];

  // Walk the path up to t; the first touch of SL or TP closes the trade.
  let closed: null | "SL" | "TP" = null, closeIdx = -1;
  for (let i = 0; i <= t; i++) {
    const p = path[i];
    if (s * (p - sl) <= 0) { closed = "SL"; closeIdx = i; break; }
    if (s * (p - tp) >= 0) { closed = "TP"; closeIdx = i; break; }
  }
  const px = closed ? (closed === "SL" ? sl : tp) : path[t];
  const perOz = s * (px - entryPx);
  const usd = perOz * 100 * lots;
  const riskUsd = Math.abs(entryPx - sl) * 100 * lots;
  const rMult = perOz / RISK;

  // SVG geometry
  const W = 640, H = 260, pad = 36;
  const lo = Math.min(sl, tp, ...path) - 8, hi = Math.max(sl, tp, ...path) + 8;
  const y = (p: number) => pad + (hi - p) / (hi - lo) * (H - 2 * pad);
  const x = (i: number) => 50 + i * ((W - 140) / (path.length - 1));
  const last = closed ? closeIdx : t;
  const pts = path.slice(0, last + 1).map((p, i) => `${x(i)},${y(i === closeIdx && closed ? px : p)}`).join(" ");

  const line = (p: number, color: string, label: string, dash = "") => (
    <g>
      <line x1={40} x2={W - 90} y1={y(p)} y2={y(p)} stroke={color} strokeWidth={1.5} strokeDasharray={dash} />
      <text x={W - 86} y={y(p) + 4} fontSize={11} fill={color} fontFamily="JetBrains Mono, monospace">{label} {fmt(p, 0)}</text>
    </g>
  );

  const inZone = entryPx >= zone[0] && entryPx <= zone[1];

  return (
    <div className="card p-4 space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Tabs value={side} onChange={v => { setSide(v); setT(0); }} options={[{ value: "BUY", label: "BUY misoli" }, { value: "SELL", label: "SELL misoli" }]} />
        <Tabs value={scen} onChange={v => { setScen(v); setT(0); }} options={(Object.keys(SCEN_LABEL) as Scenario[]).map(k => ({ value: k, label: SCEN_LABEL[k] }))} />
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Narx harakati diagrammasi">
        <rect x={40} width={W - 130} y={Math.min(y(zone[0]), y(zone[1]))} height={Math.abs(y(zone[0]) - y(zone[1]))} fill="rgba(245,166,35,0.12)" />
        <text x={44} y={Math.min(y(zone[0]), y(zone[1])) - 4} fontSize={10} fill="var(--gold)">kirish zonasi</text>
        {line(tp, "var(--green)", "TP")}
        {line(tp1, "rgba(34,197,94,0.6)", "TP1", "3 4")}
        {line(ENTRY, "var(--gold)", "Kirish", "6 4")}
        {line(sl, "var(--red)", "SL")}
        <polyline points={pts} fill="none" stroke="var(--text)" strokeWidth={2} strokeLinejoin="round" />
        <circle cx={x(last)} cy={y(px)} r={5} fill={closed === "TP" ? "var(--green)" : closed === "SL" ? "var(--red)" : "var(--blue)"} />
        <circle cx={x(0)} cy={y(entryPx)} r={4} fill="none" stroke="var(--gold)" strokeWidth={2} />
        <text x={x(0) - 4} y={H - 10} fontSize={10} fill="var(--text-faint)">kirish vaqti</text>
        <text x={W - 150} y={H - 10} fontSize={10} fill="var(--text-faint)">vaqt →</text>
      </svg>

      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <label className="text-xs shrink-0" style={{ color: "var(--text-muted)" }}>Vaqtni suring ▸</label>
        <input type="range" min={0} max={path.length - 1} value={t} onChange={e => setT(+e.target.value)}
               className="flex-1 accent-[var(--gold)]" aria-label="Vaqt" />
        <label className="text-xs shrink-0 flex items-center gap-2" style={{ color: "var(--text-muted)" }}>
          Lot
          <select className="input py-1 text-xs" value={lots} onChange={e => setLots(+e.target.value)}>
            {[0.01, 0.02, 0.05, 0.1].map(l => <option key={l} value={l}>{l}</option>)}
          </select>
        </label>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-center">
        {[
          ["Narx", fmt(px)],
          ["Natija ($)", `${usd >= 0 ? "+" : ""}${fmt(usd)}`],
          ["Natija (R)", `${rMult >= 0 ? "+" : ""}${fmt(rMult, 2)}R`],
          ["Tavakkal (1R)", `$${fmt(riskUsd)}`],
        ].map(([k, v]) => (
          <div key={k} className="rounded-lg py-2" style={{ background: "var(--surface-2)" }}>
            <p className="text-[11px]" style={{ color: "var(--text-faint)" }}>{k}</p>
            <p className="font-mono font-semibold" style={{ color: k.startsWith("Natija") ? (usd >= 0 ? "var(--green)" : "var(--red)") : "var(--text)" }}>{v}</p>
          </div>
        ))}
      </div>

      {closed === "TP" && <Callout tone="ok" title="Take Profit ishladi">Savdo avtomatik foyda bilan yopildi: +{fmt(rMult, 2)}R. Siz ekran oldida bo‘lmasangiz ham, broker buni o‘zi bajaradi.</Callout>}
      {closed === "SL" && <Callout tone="danger" title="Stop Loss ishladi">Zarar oldindan rejalashtirilgan miqdorda to‘xtadi ({fmt(rMult, 2)}R). SL bo‘lmaganda narx yanada pastroq ketishi mumkin edi. Bu normal holat — har qanday strategiyada zararli savdolar bo‘ladi.</Callout>}
      {scen === "chase" && !inZone && (
        <Callout tone="warn" title="Bu yerda xato bor">Narx kirish zonasidan ({fmt(zone[0], 0)}–{fmt(zone[1], 0)}) allaqachon chiqib ketgan paytda kirildi. Endi SL uzoqroq, tavakkal ${fmt(riskUsd)} ga oshdi, TP esa o‘sha joyda. Zonadan tashqarida kirmang.</Callout>
      )}
      {!closed && scen !== "chase" && <Callout>Savdo hali ochiq. Narx SL va TP orasida harakatlanyapti — hech narsa qilish shart emas, reja ishlayapti.</Callout>}
    </div>
  );
}
