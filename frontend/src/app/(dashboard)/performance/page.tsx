"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Gauge, LineChart as LineIcon, ListChecks, Target } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardHeader, EmptyState, PageHeader, SignalBadge, StatCard } from "@/components/ui";
import { Callout, Tabs, fmt } from "@/components/guide/Basics";

// ── types (backend/services/signal_outcomes.py) ─────────────────────────────
interface Summary {
  trades: number; win_rate?: number; expectancy_r?: number; ci95_r?: [number, number] | null;
  total_r?: number; profit_factor?: number | null; avg_win_r?: number | null; avg_loss_r?: number | null;
  max_drawdown_r?: number; max_consecutive_losses?: number; avg_mfe_r?: number | null;
  tp1_hit_rate?: number | null; reliable?: boolean;
}
interface Perf {
  signals: number; outcomes: Record<string, number>; fill_rate: number; overall: Summary;
  by_timeframe: Record<string, Summary>; by_side: Record<string, Summary>; by_session: Record<string, Summary>;
  by_month: Record<string, Summary>; by_resolution: Record<string, Summary>;
  confidence_calibration: { bucket: string; trades: number; win_rate?: number; expectancy_r?: number }[];
  equity_curve: { time: string; cum_r: number; r: number; id: number; timeframe: string; side: string }[];
  notes: string[];
}
interface Sig {
  id: number; timeframe: string; signal_type: string; entry: number | null; stop_loss: number | null;
  take_profit: number | null; confidence: number | null; created_at: string; status: string | null;
  outcome: string | null; outcome_r: number | null; mfe_r: number | null; exit_price: number | null;
  exit_time: string | null; resolution_tf: string | null;
}

const TF: Record<string, string> = { "1": "M1", "5": "M5", "15": "M15", "30": "M30", "60": "H1", "240": "H4", "1440": "D1" };
const SESSION: Record<string, string> = {
  asia: "Osiyo (00–07 UTC)", london: "London (07–12)", london_ny_overlap: "London+NY (12–16)",
  new_york: "Nyu-York (16–21)", rollover: "Rollover (21–24)",
};
const OUTCOME: Record<string, [string, string]> = {
  TP: ["TP ishladi", "var(--green)"], SL: ["SL ishladi", "var(--red)"], SL_GAP: ["SL (gap)", "var(--red)"],
  SL_AMBIGUOUS: ["SL (bir shamda ikkalasi)", "var(--red)"], TIME: ["Vaqt bo‘yicha", "var(--text-muted)"],
  EXPIRED: ["Kirilmadi — muddat", "var(--text-faint)"], ENTRY_ZONE_MISSED: ["Kirilmadi — zona", "var(--text-faint)"],
  OPENED_BEYOND_LEVELS: ["Kirilmadi — SL/TP dan o‘tdi", "var(--text-faint)"], NO_DATA: ["Ma’lumot yo‘q", "var(--text-faint)"],
  INVALID: ["Noto‘g‘ri darajalar", "var(--text-faint)"], PENDING: ["Kutilmoqda", "var(--blue)"],
};

const utc = (s?: string | null) => (s ? new Date(s.endsWith("Z") || s.includes("+") ? s : s + "Z") : null);
const when = (s?: string | null) => {
  const d = utc(s);
  return d ? d.toLocaleString("uz-UZ", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
};
const signed = (v: number | null | undefined, d = 2, suffix = "") =>
  v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${fmt(v, d)}${suffix}`;
const tone = (v: number | null | undefined) =>
  v === null || v === undefined || v === 0 ? "var(--text)" : v > 0 ? "var(--green)" : "var(--red)";

type Range = "all" | "90" | "30";

function GroupTable({ title, data, label }: { title: string; data: Record<string, Summary>; label: (k: string) => string }) {
  const rows = Object.entries(data ?? {});
  return (
    <Card>
      <div className="p-4">
        <CardHeader icon={<ListChecks className="w-4 h-4" />} title={title} />
        {rows.length === 0 ? <p className="text-sm" style={{ color: "var(--text-faint)" }}>Ma’lumot yo‘q</p> : (
          <div className="overflow-x-auto">
            <table className="data-table w-full text-sm">
              <thead><tr>
                <th className="text-left">Guruh</th><th className="text-right">Savdo</th><th className="text-right">Win</th>
                <th className="text-right">O‘rtacha R</th><th className="text-right">Jami R</th><th className="text-right">PF</th>
              </tr></thead>
              <tbody>
                {rows.map(([k, s]) => (
                  <tr key={k}>
                    <td className="text-xs">{label(k)}</td>
                    <td className="text-right font-mono text-xs">{s.trades}</td>
                    <td className="text-right font-mono text-xs">{s.win_rate !== undefined ? `${fmt(s.win_rate, 0)}%` : "—"}</td>
                    <td className="text-right font-mono text-xs" style={{ color: tone(s.expectancy_r) }}>{signed(s.expectancy_r, 2, "R")}</td>
                    <td className="text-right font-mono text-xs" style={{ color: tone(s.total_r) }}>{signed(s.total_r, 1, "R")}</td>
                    <td className="text-right font-mono text-xs">{s.profit_factor ? fmt(s.profit_factor, 2) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Card>
  );
}

export default function PerformancePage() {
  const [range, setRange] = useState<Range>("all");
  const days = range === "all" ? undefined : Number(range);
  const perf = useQuery<Perf>({
    queryKey: ["signal-perf", range],
    queryFn: () => api.get("/signals/performance", { params: { symbol: "XAUUSD", ...(days && { days }) } }).then(r => r.data),
    refetchInterval: 120_000,
  });
  const sigs = useQuery<Sig[]>({
    queryKey: ["signal-list-outcomes"],
    queryFn: () => api.get("/signals", { params: { symbol: "XAUUSD", limit: 200 } }).then(r => r.data),
    refetchInterval: 120_000,
  });

  const p = perf.data;
  const o = p?.overall;
  const trades = (sigs.data ?? []).filter(s => s.signal_type === "BUY" || s.signal_type === "SELL");
  const curve = [{ i: 0, cum_r: 0, label: "Boshlanish", r: null as number | null },
    ...(p?.equity_curve ?? []).map((c, k) => ({ i: k + 1, cum_r: c.cum_r, label: `${when(c.time)} · ${TF[c.timeframe] ?? c.timeframe} ${c.side}`, r: c.r }))];

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-5">
      <PageHeader title="Signal natijalari"
                  subtitle="Har bir BUY/SELL signal keyin nima bo‘lgani: TP, SL yoki kirilmadi — spread va slippage hisobga olingan holda."
                  action={<Tabs value={range} onChange={setRange} options={[
                    { value: "all", label: "Hammasi" }, { value: "90", label: "90 kun" }, { value: "30", label: "30 kun" },
                  ]} />} />

      <Callout tone="info" title="Qanday hisoblanadi?">
        Signal saqlangandan keyingi birinchi shamdan boshlab narx yo‘li M5 (yo‘q bo‘lsa H1) shamlarda yuriladi — paper trading va backtest bilan bir xil qoidalar.
        Bir shamda SL ham, TP ham tegsa — SL deb olinadi (ehtiyotkor baho). <b>R</b> — riskka nisbatan natija: −1R = to‘liq SL, +2R = riskning ikki baravari foyda.
      </Callout>

      {p?.notes?.map(n => <Callout key={n} tone="warn">{n}</Callout>)}

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard label="Bajarilgan signallar" value={o?.trades ?? null}
                  sub={p ? `${p.signals} signaldan · kirish ${fmt(p.fill_rate, 0)}%` : undefined} />
        <StatCard label="Yutgan" value={o?.win_rate !== undefined ? `${fmt(o.win_rate, 1)}%` : "—"}
                  sub={o?.tp1_hit_rate != null ? `TP1 ga yetgan: ${fmt(o.tp1_hit_rate, 0)}%` : "Win rate"} />
        <StatCard label="O‘rtacha natija" value={o?.expectancy_r !== undefined ? signed(o.expectancy_r, 2, "R") : "—"}
                  color={o?.expectancy_r === undefined ? undefined : o.expectancy_r > 0 ? "text-[var(--green)]" : "text-[var(--red)]"}
                  sub={o?.ci95_r ? `95% oraliq: ${fmt(o.ci95_r[0], 2)} … ${fmt(o.ci95_r[1], 2)}R` : "1 savdoga"} />
        <StatCard label="Jami" value={o?.total_r !== undefined ? signed(o.total_r, 1, "R") : "—"}
                  sub={o?.profit_factor ? `Profit factor ${fmt(o.profit_factor, 2)}` : undefined} />
        <StatCard label="Maks. pasayish" value={o?.max_drawdown_r !== undefined ? `${fmt(o.max_drawdown_r, 1)}R` : "—"}
                  sub={o?.max_consecutive_losses !== undefined ? `Ketma-ket zarar: ${o.max_consecutive_losses}` : undefined} />
        <StatCard label="O‘rtacha MFE" value={o?.avg_mfe_r != null ? `${fmt(o.avg_mfe_r, 2)}R` : "—"}
                  sub="Savdo davomida eng yaxshi nuqta" />
      </div>

      <Card>
        <div className="p-4">
          <CardHeader icon={<LineIcon className="w-4 h-4" />} title="Jamlangan natija (R)" />
          {curve.length < 3 ? (
            <EmptyState title="Grafik uchun kamida 2 ta bajarilgan signal kerak" description="Signallar natijasi har 30 daqiqada avtomatik aniqlanadi." />
          ) : (
            <div className="h-64" role="img" aria-label="Jamlangan R grafigi">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={curve} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
                  <defs>
                    <linearGradient id="cumr" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--gold)" stopOpacity={0.25} />
                      <stop offset="100%" stopColor="var(--gold)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
                  <XAxis dataKey="i" tick={{ fill: "var(--text-faint)", fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: "var(--text-faint)", fontSize: 11 }} axisLine={false} tickLine={false}
                         tickFormatter={(v: number) => `${v}R`} width={48} />
                  <ReferenceLine y={0} stroke="var(--text-faint)" strokeDasharray="4 4" />
                  <Tooltip cursor={{ stroke: "var(--border-2)" }}
                           contentStyle={{ background: "var(--surface-2)", border: "1px solid var(--border-2)", borderRadius: 8, fontSize: 12 }}
                           labelStyle={{ color: "var(--text-muted)" }} itemStyle={{ color: "var(--text)" }}
                           labelFormatter={(i: number) => curve[i]?.label ?? ""}
                           formatter={(v: number, _n: string, pl: { payload?: { r: number | null } }) =>
                             [`${signed(v, 2, "R")}${pl?.payload?.r != null ? ` (bu savdo ${signed(pl.payload.r, 2, "R")})` : ""}`, "Jami"]} />
                  <Area type="monotone" dataKey="cum_r" stroke="var(--gold)" strokeWidth={2} fill="url(#cumr)"
                        dot={{ r: 3, fill: "var(--gold)", stroke: "var(--surface)", strokeWidth: 2 }} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </Card>

      <Card>
        <div className="p-4">
          <CardHeader icon={<Gauge className="w-4 h-4" />} title="Confidence (ishonch) haqiqatga mosmi?" />
          <p className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>
            To‘g‘ri kalibrlangan tizimda ishonch oshgani sari win rate ham oshishi kerak. Agar yuqori ishonchli signallar yomonroq bo‘lsa — confidence raqamiga tayanmang.
          </p>
          {!p?.confidence_calibration?.length ? <p className="text-sm" style={{ color: "var(--text-faint)" }}>Ma’lumot yo‘q</p> : (
            <div className="space-y-2">
              {p.confidence_calibration.map(c => (
                <div key={c.bucket} className="grid grid-cols-[90px_1fr_120px] items-center gap-3 text-xs">
                  <span className="font-mono" style={{ color: "var(--text-muted)" }}>{c.bucket}%</span>
                  <div className="h-2 rounded-full" style={{ background: "var(--surface-2)" }}>
                    <div className="h-2 rounded-full" style={{ width: `${c.win_rate ?? 0}%`, background: (c.expectancy_r ?? 0) > 0 ? "var(--green)" : "var(--red)" }} />
                  </div>
                  <span className="font-mono text-right">{fmt(c.win_rate ?? 0, 0)}% · {signed(c.expectancy_r, 2, "R")} · n={c.trades}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>

      <div className="grid lg:grid-cols-2 gap-5">
        <GroupTable title="Timeframe bo‘yicha" data={p?.by_timeframe ?? {}} label={k => TF[k] ?? k} />
        <GroupTable title="Yo‘nalish bo‘yicha" data={p?.by_side ?? {}} label={k => k} />
        <GroupTable title="Sessiya bo‘yicha (signal vaqti, UTC)" data={p?.by_session ?? {}} label={k => SESSION[k] ?? k} />
        <GroupTable title="Oy bo‘yicha" data={p?.by_month ?? {}} label={k => k} />
      </div>

      <Card>
        <div className="p-4">
          <CardHeader icon={<Target className="w-4 h-4" />} title="Signallar va natijalari"
                      action={p ? <span className="text-xs" style={{ color: "var(--text-faint)" }}>
                        {Object.entries(p.outcomes).map(([k, v]) => `${OUTCOME[k]?.[0] ?? k}: ${v}`).join(" · ")}
                      </span> : undefined} />
          {sigs.isLoading ? <p className="text-sm" style={{ color: "var(--text-faint)" }}>Yuklanmoqda…</p> : trades.length === 0 ? (
            <EmptyState title="BUY/SELL signal yo‘q" description="Signal chiqqanda va natijasi aniqlanganda shu yerda ko‘rinadi." />
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table w-full text-sm">
                <thead><tr>
                  <th className="text-left">Vaqt</th><th className="text-left">TF</th><th className="text-left">Yo‘nalish</th>
                  <th className="text-right">Ishonch</th><th className="text-right">Kirish</th><th className="text-right">SL</th>
                  <th className="text-right">TP</th><th className="text-left">Natija</th><th className="text-right">R</th><th className="text-right">MFE</th>
                </tr></thead>
                <tbody>
                  {trades.map(s => {
                    const oc = OUTCOME[s.outcome ?? "PENDING"] ?? [s.outcome ?? "—", "var(--text-muted)"];
                    return (
                      <tr key={s.id}>
                        <td className="whitespace-nowrap text-xs">{when(s.created_at)}</td>
                        <td className="text-xs font-mono">{TF[s.timeframe] ?? s.timeframe}</td>
                        <td><SignalBadge type={s.signal_type} /></td>
                        <td className="text-right font-mono text-xs">{s.confidence != null ? `${fmt(s.confidence, 0)}%` : "—"}</td>
                        <td className="text-right font-mono text-xs">{fmt(s.entry)}</td>
                        <td className="text-right font-mono text-xs" style={{ color: "var(--red)" }}>{fmt(s.stop_loss)}</td>
                        <td className="text-right font-mono text-xs" style={{ color: "var(--green)" }}>{fmt(s.take_profit)}</td>
                        <td className="text-xs whitespace-nowrap" style={{ color: oc[1] }}>
                          {oc[0]}{s.resolution_tf === "60" && Number(s.timeframe) < 60 ? " ·H1" : ""}
                        </td>
                        <td className="text-right font-mono text-xs" style={{ color: tone(s.outcome_r) }}>{signed(s.outcome_r, 2, "R")}</td>
                        <td className="text-right font-mono text-xs">{s.mfe_r != null ? `${fmt(s.mfe_r, 2)}R` : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
