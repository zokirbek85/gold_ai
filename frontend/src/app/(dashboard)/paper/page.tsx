"use client";

import Link from "next/link";
import { Fragment, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
  Activity, AlertTriangle, CheckCircle2, ChevronDown, FlaskConical, HeartPulse, Lightbulb,
  ShieldCheck, XCircle,
} from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardHeader, EmptyState, PageHeader, SignalBadge, StatCard } from "@/components/ui";
import { Callout, Tabs, fmt } from "@/components/guide/Basics";

// ── types (subset of backend/models/paper.py + paper.service.stats) ─────────
interface PaperTrade {
  id: number; status: "PENDING" | "OPEN" | "CLOSED" | "CANCELLED"; direction: "BUY" | "SELL";
  regime: string | null; signal_time: string; expires_at: string; entry_ref: number;
  zone_low: number; zone_high: number; stop_loss: number; take_profit: number; risk_per_oz: number;
  lots: number; spread: number; slippage: number; fill_price: number | null; fill_time: string | null;
  exit_price: number | null; exit_time: string | null; exit_reason: string | null;
  r_multiple: number | null; pnl_usd: number | null; costs_usd: number | null;
  mfe_r: number | null; mae_r: number | null; data_gap: boolean | null; reasons: string | null;
  strategy_version: string; config_hash: string; created_at: string;
}

const STATUS: Record<PaperTrade["status"], [string, string]> = {
  PENDING: ["Kirish kutilmoqda", "var(--blue)"],
  OPEN: ["Ochiq", "var(--gold)"],
  CLOSED: ["Yopilgan", "var(--text-muted)"],
  CANCELLED: ["Bekor qilingan", "var(--text-faint)"],
};

const EXIT: Record<string, string> = {
  TP: "Take Profit ishladi — foyda bilan yopildi",
  SL: "Stop Loss ishladi — rejalashtirilgan zarar",
  SL_AMBIGUOUS: "Bir shamda SL ham, TP ham tegdi — ehtiyotkorlik uchun SL deb hisoblandi",
  SL_GAP: "Narx SL dan sakrab o‘tdi — ochilish narxida yopildi",
  TIME: "8 savdo kuni ichida SL ham, TP ham ishlamadi — vaqt bo‘yicha yopildi",
  EXPIRED: "Muddat ichida kirish imkoni bo‘lmadi",
  ENTRY_ZONE_MISSED: "Narx kirish zonasidan tashqarida ochildi — kirilmadi",
  OPENED_BEYOND_LEVELS: "Narx SL yoki TP dan o‘tib ochildi — kirilmadi",
};

const HEALTH: Record<string, [string, string, string]> = {
  OK: ["Normal", "var(--green)", "Natijalar backtest kutganiga mos."],
  INSUFFICIENT_DATA: ["Ma'lumot kam", "var(--text-muted)", "Xulosa chiqarish uchun kamida 10 ta yopilgan savdo kerak. Savdo davom etadi."],
  DEGRADED: ["Yomonlashgan", "var(--gold)", "Natijalar kutilganidan past — risk avtomatik 50% ga kamaytirildi."],
  SUSPENDED: ["To‘xtatilgan", "var(--red)", "Natijalar kutilganidan ancha yomon — tizim yangi signal bermaydi. Qayta yoqish administrator qarori bilan."],
};

const CHECK_LABEL: Record<string, string> = {
  broker_adapter_implemented: "Broker bilan xavfsiz ulanish yozilgan",
  paper_trades: "Kamida 100 ta yopilgan paper savdo",
  paper_days: "Kamida 180 kunlik paper tarix",
  paper_expectancy_ci: "Natija statistik jihatdan ishonchli musbat",
  strategy_health: "Strategiya holati normal",
  explicit_consent: "Egasining yozma roziligi",
  risk_limits: "Risk limitlari sozlangan",
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

type Filter = "all" | "active" | "CLOSED" | "CANCELLED";

export default function PaperPage() {
  const stats = useQuery({ queryKey: ["paper-stats"], queryFn: () => api.get("/paper/stats").then(r => r.data), refetchInterval: 30_000 });
  const trades = useQuery<PaperTrade[]>({ queryKey: ["paper-trades"], queryFn: () => api.get("/paper/trades", { params: { limit: 500 } }).then(r => r.data), refetchInterval: 30_000 });
  const ready = useQuery({ queryKey: ["paper-ready"], queryFn: () => api.get("/execution/readiness").then(r => r.data), refetchInterval: 120_000 });
  const analysis = useQuery({ queryKey: ["paper-analysis"], queryFn: () => api.get("/paper/analysis").then(r => r.data), refetchInterval: 120_000 });
  const price = useQuery({ queryKey: ["paper-price"], queryFn: () => api.get("/market-data/price", { params: { symbol: "XAUUSD" } }).then(r => r.data), refetchInterval: 15_000 });

  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<number | null>(null);

  const all = trades.data ?? [];
  const active = all.filter(t => t.status === "OPEN" || t.status === "PENDING");
  const shown = all.filter(t => filter === "all" || (filter === "active" ? active.includes(t) : t.status === filter));

  const s = stats.data;
  const start = s?.account?.start_balance ?? 10000;
  const pnl = s ? s.account.balance - start : null;

  // equity curve from closed trades in exit order
  const curve = useMemo(() => {
    const closed = all.filter(t => t.status === "CLOSED" && t.exit_time && t.pnl_usd !== null)
      .sort((a, b) => (utc(a.exit_time)!.getTime() - utc(b.exit_time)!.getTime()));
    let bal = start;
    const pts = [{ i: 0, label: "Boshlanish", balance: start, r: null as number | null }];
    closed.forEach((t, k) => { bal += t.pnl_usd!; pts.push({ i: k + 1, label: when(t.exit_time), balance: +bal.toFixed(2), r: t.r_multiple }); });
    return pts;
  }, [all, start]);

  const livePx: number | null = price.data?.price ?? null;
  const health = s?.health;
  const h = HEALTH[health?.status ?? "INSUFFICIENT_DATA"] ?? HEALTH.INSUFFICIENT_DATA;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-5">
      <PageHeader title="Paper Trading"
                  subtitle="Tizimning virtual hisobdagi savdolari — real narxlar, virtual pul. Hech qanday real buyurtma yuborilmaydi." />

      <Callout tone="info" title="Bu sahifa nima?">
        Tizim har soat bozorni tahlil qiladi. BUY yoki SELL signal chiqsa, shu yerdagi virtual hisobda savdo ochadi va spread hamda slippage bilan real narxlar bo‘yicha yuritadi. Maqsad — strategiya haqiqiy bozorda backtestdagidek ishlashini pul tavakkal qilmasdan tekshirish. Atamalar uchun <Link href="/guide" className="underline" style={{ color: "var(--gold)" }}>Qo‘llanma</Link>ga qarang.
      </Callout>

      {/* ── Account summary ─────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard label="Balans" value={s ? `$${fmt(s.account.balance)}` : null} sub={`Boshlang‘ich $${fmt(start, 0)}`} />
        <StatCard label="Foyda / zarar" value={pnl !== null ? `${pnl >= 0 ? "+" : "−"}$${fmt(Math.abs(pnl))}` : null}
                  sub={pnl !== null ? `${signed(pnl / start * 100, 2, "%")} hisobga nisbatan` : undefined}
                  color={pnl === null || pnl === 0 ? undefined : pnl > 0 ? "text-[var(--green)]" : "text-[var(--red)]"} />
        <StatCard label="Yopilgan savdolar" value={s?.trades ?? null} sub={s ? `${s.open_or_pending} ochiq · ${s.cancelled} bekor` : undefined} />
        <StatCard label="Yutgan savdolar" value={s?.win_rate !== undefined ? `${fmt(s.win_rate, 1)}%` : "—"} sub="Win rate" />
        <StatCard label="O‘rtacha natija" value={s?.expectancy_r !== undefined ? signed(s.expectancy_r, 2, "R") : "—"}
                  sub={s?.expectancy_r_ci95 ? `95% oraliq: ${fmt(s.expectancy_r_ci95[0], 2)} … ${fmt(s.expectancy_r_ci95[1], 2)}R` : "1 savdoga, risk birligida"} />
        <StatCard label="Xarajatlar" value={s?.total_costs_usd !== undefined ? `$${fmt(s.total_costs_usd)}` : "—"} sub="Spread + slippage + swap" />
      </div>

      {s?.account?.halted && (
        <Callout tone="danger" title="Virtual hisob to‘xtatilgan">{s.account.halt_reason} — yangi savdolar ochilmaydi.</Callout>
      )}

      {/* ── Open / pending positions ────────────────────────────────── */}
      <Card>
        <div className="p-4">
          <CardHeader icon={<Activity className="w-4 h-4" />} title="Hozir ochiq yoki kutilayotgan savdolar"
                      action={livePx ? <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>XAUUSD {fmt(livePx)}</span> : undefined} />
          {active.length === 0 ? (
            <EmptyState icon={<FlaskConical className="w-8 h-8" />} title="Hozir ochiq savdo yo‘q"
                        description="Tizim har soat :03 da bozorni tekshiradi. Shartlar mos kelganda (o‘rtacha oyiga 1–1.5 marta) savdo shu yerda paydo bo‘ladi." />
          ) : (
            <div className="grid md:grid-cols-2 gap-3">
              {active.map(t => {
                const side = t.direction === "BUY" ? 1 : -1;
                const unreal = t.status === "OPEN" && t.fill_price && livePx ? side * (livePx - t.fill_price) * 100 * t.lots : null;
                const unrealR = t.status === "OPEN" && t.fill_price && livePx ? side * (livePx - t.fill_price) / t.risk_per_oz : null;
                // progress: 0 = SL, 1 = TP
                const prog = livePx ? Math.min(1, Math.max(0, (side * (livePx - t.stop_loss)) / (side * (t.take_profit - t.stop_loss)))) : null;
                return (
                  <div key={t.id} className="rounded-lg p-4 space-y-3" style={{ background: "var(--surface-2)" }}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <SignalBadge type={t.direction} />
                        <span className="text-xs font-semibold" style={{ color: STATUS[t.status][1] }}>{STATUS[t.status][0]}</span>
                      </div>
                      <span className="text-xs font-mono" style={{ color: "var(--text-faint)" }}>{fmt(t.lots)} lot</span>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-xs font-mono">
                      <div><p style={{ color: "var(--text-faint)" }}>SL</p><p style={{ color: "var(--red)" }}>{fmt(t.stop_loss)}</p></div>
                      <div><p style={{ color: "var(--text-faint)" }}>{t.status === "OPEN" ? "Kirildi" : "Zona"}</p>
                        <p style={{ color: "var(--text)" }}>{t.status === "OPEN" ? fmt(t.fill_price) : `${fmt(t.zone_low)}–${fmt(t.zone_high)}`}</p></div>
                      <div><p style={{ color: "var(--text-faint)" }}>TP</p><p style={{ color: "var(--green)" }}>{fmt(t.take_profit)}</p></div>
                    </div>
                    {prog !== null && (
                      <div>
                        <div className="relative h-2 rounded-full" style={{ background: "linear-gradient(90deg, rgba(239,68,68,0.35), rgba(255,255,255,0.06) 30%, rgba(255,255,255,0.06) 70%, rgba(34,197,94,0.35))" }}>
                          <span className="absolute -top-1 w-1 h-4 rounded" style={{ left: `calc(${prog * 100}% - 2px)`, background: "var(--text)" }} />
                        </div>
                        <div className="flex justify-between text-[10px] mt-1" style={{ color: "var(--text-faint)" }}><span>SL</span><span>joriy narx</span><span>TP</span></div>
                      </div>
                    )}
                    {t.status === "OPEN" ? (
                      <p className="text-sm">Joriy natija (taxminiy): <b className="font-mono" style={{ color: tone(unreal) }}>{unreal !== null ? `${signed(unreal)} $ · ${signed(unrealR, 2, "R")}` : "—"}</b></p>
                    ) : (
                      <p className="text-xs" style={{ color: "var(--text-muted)" }}>Narx zonaga kirishi kutilmoqda. Muddat: {when(t.expires_at)}.</p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </Card>

      {/* ── Equity curve ────────────────────────────────────────────── */}
      <Card>
        <div className="p-4">
          <CardHeader icon={<Activity className="w-4 h-4" />} title="Virtual balans o‘zgarishi" />
          {curve.length < 3 ? (
            <EmptyState title="Grafik uchun kamida 2 ta yopilgan savdo kerak"
                        description={`Hozir yopilgan savdolar: ${curve.length - 1}. Har bir savdo yopilganda balans shu yerda chiziq bo‘lib ko‘rinadi.`} />
          ) : (
            <div className="h-64" role="img" aria-label="Virtual balans grafigi">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={curve} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
                  <defs>
                    <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--gold)" stopOpacity={0.25} />
                      <stop offset="100%" stopColor="var(--gold)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
                  <XAxis dataKey="i" tick={{ fill: "var(--text-faint)", fontSize: 11 }} axisLine={false} tickLine={false}
                         label={{ value: "savdo №", position: "insideBottomRight", fill: "var(--text-faint)", fontSize: 10 }} />
                  <YAxis domain={["auto", "auto"]} tick={{ fill: "var(--text-faint)", fontSize: 11 }} axisLine={false} tickLine={false}
                         tickFormatter={(v: number) => `$${Math.round(v).toLocaleString()}`} width={64} />
                  <ReferenceLine y={start} stroke="var(--text-faint)" strokeDasharray="4 4" />
                  <Tooltip cursor={{ stroke: "var(--border-2)" }}
                           contentStyle={{ background: "var(--surface-2)", border: "1px solid var(--border-2)", borderRadius: 8, fontSize: 12 }}
                           labelStyle={{ color: "var(--text-muted)" }} itemStyle={{ color: "var(--text)" }}
                           labelFormatter={(i: number) => curve[i]?.label ?? ""}
                           formatter={(v: number, _n: string, p: { payload?: { r: number | null } }) =>
                             [`$${fmt(v)}${p?.payload?.r !== null && p?.payload?.r !== undefined ? ` (${signed(p.payload.r, 2, "R")})` : ""}`, "Balans"]} />
                  <Area type="monotone" dataKey="balance" stroke="var(--gold)" strokeWidth={2} fill="url(#eq)"
                        dot={{ r: 4, fill: "var(--gold)", stroke: "var(--surface)", strokeWidth: 2 }} activeDot={{ r: 6 }} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </Card>

      {/* ── Trades table ────────────────────────────────────────────── */}
      <Card>
        <div className="p-4">
          <CardHeader icon={<FlaskConical className="w-4 h-4" />} title="Barcha paper savdolar"
                      action={<Tabs value={filter} onChange={setFilter} options={[
                        { value: "all", label: `Hammasi (${all.length})` },
                        { value: "active", label: `Faol (${active.length})` },
                        { value: "CLOSED", label: "Yopilgan" },
                        { value: "CANCELLED", label: "Bekor" },
                      ]} />} />
          {trades.isLoading ? <p className="text-sm" style={{ color: "var(--text-faint)" }}>Yuklanmoqda…</p> : shown.length === 0 ? (
            <EmptyState icon={<FlaskConical className="w-8 h-8" />} title="Hali savdo yo‘q"
                        description="Birinchi signal chiqqanda savdo shu jadvalda ko‘rinadi. Qatorni bosganingizda to‘liq tafsilot ochiladi." />
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table w-full text-sm">
                <thead>
                  <tr>
                    <th className="text-left">Signal vaqti</th><th className="text-left">Yo‘nalish</th><th className="text-left">Holat</th>
                    <th className="text-right">Kirish</th><th className="text-right">SL</th><th className="text-right">TP</th>
                    <th className="text-right">Chiqish</th><th className="text-right">R</th><th className="text-right">$</th><th />
                  </tr>
                </thead>
                <tbody>
                  {shown.map(t => {
                    let extra: { reasons?: string[]; score?: number } = {};
                    try { extra = t.reasons ? JSON.parse(t.reasons) : {}; } catch { /* ignore malformed */ }
                    return (
                      <Fragment key={t.id}>
                        <tr className="cursor-pointer" onClick={() => setOpen(open === t.id ? null : t.id)}>
                          <td className="whitespace-nowrap text-xs">{when(t.signal_time)}</td>
                          <td><SignalBadge type={t.direction} /></td>
                          <td className="text-xs font-medium whitespace-nowrap" style={{ color: STATUS[t.status][1] }}>{STATUS[t.status][0]}</td>
                          <td className="text-right font-mono text-xs">{fmt(t.fill_price ?? t.entry_ref)}</td>
                          <td className="text-right font-mono text-xs" style={{ color: "var(--red)" }}>{fmt(t.stop_loss)}</td>
                          <td className="text-right font-mono text-xs" style={{ color: "var(--green)" }}>{fmt(t.take_profit)}</td>
                          <td className="text-right font-mono text-xs">{fmt(t.exit_price)}</td>
                          <td className="text-right font-mono text-xs font-semibold" style={{ color: tone(t.r_multiple) }}>{signed(t.r_multiple, 2)}</td>
                          <td className="text-right font-mono text-xs font-semibold" style={{ color: tone(t.pnl_usd) }}>{signed(t.pnl_usd)}</td>
                          <td><ChevronDown className="w-3.5 h-3.5 transition-transform" style={{ color: "var(--text-faint)", transform: open === t.id ? "rotate(180deg)" : undefined }} /></td>
                        </tr>
                        {open === t.id && (
                          <tr>
                            <td colSpan={10} style={{ background: "var(--surface-2)" }}>
                              <div className="grid md:grid-cols-3 gap-4 py-2 text-xs leading-relaxed">
                                <div className="space-y-1">
                                  <p className="font-semibold" style={{ color: "var(--text)" }}>Nima bo‘ldi</p>
                                  <p style={{ color: "var(--text-muted)" }}>{t.exit_reason ? (EXIT[t.exit_reason] ?? t.exit_reason) : t.status === "OPEN" ? "Savdo hali ochiq." : "Kirish kutilmoqda."}</p>
                                  {t.data_gap && <p className="flex items-center gap-1" style={{ color: "var(--gold)" }}><AlertTriangle className="w-3 h-3" /> Narx ma'lumotida uzilish bo‘lgan — natija taxminiy.</p>}
                                  <p style={{ color: "var(--text-faint)" }}>Kirildi: {when(t.fill_time)} · Yopildi: {when(t.exit_time)}</p>
                                </div>
                                <div className="space-y-1 font-mono" style={{ color: "var(--text-muted)" }}>
                                  <p className="font-sans font-semibold" style={{ color: "var(--text)" }}>Raqamlar</p>
                                  <p>Hajm: {fmt(t.lots)} lot · Risk: ${fmt(t.risk_per_oz * 100 * t.lots)}</p>
                                  <p>Kirish zonasi: {fmt(t.zone_low)}–{fmt(t.zone_high)}</p>
                                  <p>Xarajatlar: ${fmt(t.costs_usd)} (spread {fmt(t.spread)}, slippage {fmt(t.slippage)})</p>
                                  <p title="Savdo davomida eng ko‘p foydada va zararda bo‘lgan nuqta">Eng yuqori foyda: {signed(t.mfe_r, 2, "R")} · Eng chuqur zarar: −{fmt(t.mae_r, 2)}R</p>
                                  <p>Rejim: {t.regime ?? "—"} · Score: {extra.score ?? "—"}</p>
                                </div>
                                <div className="space-y-1">
                                  <p className="font-semibold" style={{ color: "var(--text)" }}>Signal sabablari</p>
                                  {(extra.reasons ?? []).length ? (
                                    <ul className="list-disc pl-4 space-y-0.5" style={{ color: "var(--text-muted)" }}>
                                      {extra.reasons!.map((r, k) => <li key={k}>{r}</li>)}
                                    </ul>
                                  ) : <p style={{ color: "var(--text-faint)" }}>—</p>}
                                  <p className="font-mono text-[10px]" style={{ color: "var(--text-faint)" }}>{t.strategy_version} · {t.config_hash}</p>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>

      {/* ── Health / readiness / learning ───────────────────────────── */}
      <div className="grid lg:grid-cols-3 gap-4">
        <Card>
          <div className="p-4 space-y-3">
            <CardHeader icon={<HeartPulse className="w-4 h-4" />} title="Strategiya holati" />
            <p className="text-lg font-semibold" style={{ color: h[1] }}>{h[0]}</p>
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>{h[2]}</p>
            {health && (
              <div className="text-xs font-mono space-y-0.5" style={{ color: "var(--text-faint)" }}>
                <p>Savdolar: {health.trades} · Ketma-ket zarar: {health.consecutive_losses}</p>
                <p>Joriy pasayish: {fmt(health.current_drawdown_r, 2)}R · Risk koeffitsiyenti: ×{health.risk_multiplier}</p>
                {health.reference && <p>Backtest kutgani: {signed(health.reference.expectancy_r, 2, "R")} / savdo</p>}
              </div>
            )}
            {(health?.reasons ?? []).map((r: string, k: number) => <Callout key={k} tone="warn">{r}</Callout>)}
          </div>
        </Card>

        <Card>
          <div className="p-4 space-y-3">
            <CardHeader icon={<ShieldCheck className="w-4 h-4" />} title="Real savdoga tayyorlik" />
            <p className="text-sm font-semibold" style={{ color: ready.data?.live_allowed ? "var(--green)" : "var(--red)" }}>
              {ready.data ? (ready.data.live_allowed ? "Barcha shartlar bajarilgan" : "Tayyor emas — real savdo bloklangan") : "…"}
            </p>
            <ul className="space-y-1.5">
              {(ready.data?.checks ?? []).map((c: { check: string; passed: boolean; detail: string }) => (
                <li key={c.check} className="flex items-start gap-2 text-xs" title={c.detail}>
                  {c.passed ? <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color: "var(--green)" }} />
                            : <XCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color: "var(--red)" }} />}
                  <span style={{ color: c.passed ? "var(--text)" : "var(--text-muted)" }}>{CHECK_LABEL[c.check] ?? c.check}</span>
                </li>
              ))}
            </ul>
          </div>
        </Card>

        <Card>
          <div className="p-4 space-y-3">
            <CardHeader icon={<Lightbulb className="w-4 h-4" />} title="Natijalardan xulosalar" />
            {analysis.data?.hypotheses?.length ? (
              <ul className="space-y-2">
                {analysis.data.hypotheses.map((x: { finding: string; hypothesis: string; required_test: string }, k: number) => (
                  <li key={k} className="text-xs rounded-md p-2 space-y-1" style={{ background: "var(--surface-2)" }}>
                    <p style={{ color: "var(--text)" }}>{x.finding}</p>
                    <p style={{ color: "var(--gold)" }}>Gipoteza: {x.hypothesis}</p>
                    <p style={{ color: "var(--text-faint)" }}>Tekshirish: {x.required_test}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                {analysis.data?.note ?? "Yuklanmoqda…"} Tizim xulosalarni faqat taklif qiladi — strategiyani o‘zi o‘zgartirmaydi.
              </p>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
