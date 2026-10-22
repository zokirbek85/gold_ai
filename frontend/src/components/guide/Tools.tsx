"use client";

import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Circle, Search } from "lucide-react";
import { Callout, fmt } from "./Basics";
import { CHECKLIST, REASONS, findReason } from "./data";
import { codesFromText, useLatestSignal } from "./LiveStatus";

// ── NO TRADE decoder ─────────────────────────────────────────────────────────

const KIND: Record<string, [string, string]> = {
  bozor: ["Bozor holati", "var(--blue)"],
  risk: ["Risk", "var(--gold)"],
  himoya: ["Himoya", "var(--red)"],
  malumot: ["Ma'lumot", "var(--text-muted)"],
};

export function ReasonDecoder() {
  const latest = useLatestSignal();
  const latestCodes = codesFromText(latest.data?.plain_explanation);
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<string | null>(null);
  useEffect(() => { if (!picked && latestCodes[0]) setPicked(latestCodes[0]); }, [latestCodes, picked]);

  const list = REASONS.filter(r => !q || (r.code + r.title + r.meaning).toLowerCase().includes(q.toLowerCase()));
  const r = picked ? findReason(picked) : undefined;

  return (
    <div className="grid md:grid-cols-5 gap-4">
      <div className="md:col-span-2 card p-3 space-y-2">
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5" style={{ color: "var(--text-faint)" }} />
          <input className="input w-full pl-8 text-sm" placeholder="Kod yoki so‘z bilan qidiring…" value={q} onChange={e => setQ(e.target.value)} />
        </div>
        {latestCodes.length > 0 && (
          <button onClick={() => setPicked(latestCodes[0])} className="w-full text-left text-xs px-2 py-1.5 rounded-md"
                  style={{ background: "rgba(245,166,35,0.08)", color: "var(--gold)" }}>
            ★ Oxirgi signalingiz sababi: <span className="font-mono">{latestCodes[0]}</span>
          </button>
        )}
        <div className="max-h-80 overflow-y-auto space-y-0.5">
          {list.map(x => (
            <button key={x.code} onClick={() => setPicked(x.code)}
                    className="w-full text-left px-2 py-1.5 rounded-md text-sm"
                    style={picked && findReason(picked)?.code === x.code ? { background: "var(--surface-3)" } : {}}>
              <span className="block font-mono text-[11px]" style={{ color: KIND[x.kind][1] }}>{x.code.endsWith("_") ? x.code + "…" : x.code}</span>
              <span style={{ color: "var(--text)" }}>{x.title}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="md:col-span-3 card p-5 self-start">
        {r ? (
          <>
            <span className="text-[11px] px-2 py-0.5 rounded-full" style={{ background: "var(--surface-2)", color: KIND[r.kind][1] }}>{KIND[r.kind][0]}</span>
            <p className="font-mono text-xs mt-3" style={{ color: "var(--text-faint)" }}>{picked}</p>
            <h3 className="text-base font-semibold mt-1 mb-3" style={{ color: "var(--text)" }}>{r.title}</h3>
            <p className="text-sm leading-relaxed mb-3" style={{ color: "var(--text-muted)" }}><b style={{ color: "var(--text)" }}>Bu nima degani: </b>{r.meaning}</p>
            <Callout tone="ok" title="Nima qilish kerak">{r.action}</Callout>
          </>
        ) : (
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>Chap tomondan kodni tanlang. Signal sahifasida yoki Telegram xabarida «Kodlar:» qatoridagi so‘zni shu yerda qidiring.</p>
        )}
      </div>
    </div>
  );
}

// ── Risk / lot calculator ────────────────────────────────────────────────────

function Num({ label, value, onChange, step = 1, hint }: {
  label: string; value: number; onChange: (v: number) => void; step?: number; hint?: string;
}) {
  return (
    <label className="block">
      <span className="text-xs" style={{ color: "var(--text-muted)" }}>{label}</span>
      <input type="number" step={step} className="input w-full mt-1 font-mono text-sm" value={Number.isFinite(value) ? value : ""}
             onChange={e => onChange(parseFloat(e.target.value))} />
      {hint && <span className="text-[11px]" style={{ color: "var(--text-faint)" }}>{hint}</span>}
    </label>
  );
}

export function RiskCalculator() {
  const latest = useLatestSignal();
  const [balance, setBalance] = useState(10000);
  const [riskPct, setRiskPct] = useState(0.5);
  const [entry, setEntry] = useState(4000);
  const [sl, setSl] = useState(3980);
  const [tp, setTp] = useState(4050);
  const [contract, setContract] = useState(100);
  const minLot = 0.01, step = 0.01;

  const s = latest.data;
  const canFill = s && s.signal_type !== "NO TRADE" && s.entry && s.stop_loss;

  const r = useMemo(() => {
    const dist = Math.abs(entry - sl);
    const riskUsd = balance * riskPct / 100;
    const raw = dist > 0 ? riskUsd / (dist * contract) : 0;
    const lots = Math.floor(raw / step + 1e-9) * step;
    const side = sl < entry ? "BUY" : sl > entry ? "SELL" : "—";
    const tpOk = side === "BUY" ? tp > entry : side === "SELL" ? tp < entry : false;
    return {
      dist, riskUsd, raw, lots, side, tpOk,
      lossAtSl: lots * dist * contract,
      profitAtTp: tpOk ? lots * Math.abs(tp - entry) * contract : 0,
      rr: dist > 0 && tpOk ? Math.abs(tp - entry) / dist : 0,
      perDollar: lots * contract,
    };
  }, [balance, riskPct, entry, sl, tp, contract]);

  return (
    <div className="grid md:grid-cols-2 gap-4">
      <div className="card p-4 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Num label="Hisob balansi ($)" value={balance} onChange={setBalance} step={100} />
          <Num label="Risk (% bir savdoga)" value={riskPct} onChange={setRiskPct} step={0.1} hint="Tavsiya: 0.5–1%" />
          <Num label="Kirish narxi" value={entry} onChange={setEntry} step={0.1} />
          <Num label="Stop Loss" value={sl} onChange={setSl} step={0.1} />
          <Num label="Take Profit" value={tp} onChange={setTp} step={0.1} />
          <Num label="1 lot = necha oz" value={contract} onChange={setContract} hint="Brokerdan tekshiring" />
        </div>
        {canFill && (
          <button className="btn-ghost text-xs w-full" onClick={() => { setEntry(s.entry); setSl(s.stop_loss); if (s.take_profit) setTp(s.take_profit); }}>
            Oxirgi signal qiymatlarini qo‘yish ({s.signal_type} {fmt(s.entry)})
          </button>
        )}
      </div>
      <div className="card p-4 space-y-3">
        <div className="rounded-lg p-4 text-center" style={{ background: "var(--surface-2)" }}>
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>Ochish kerak bo‘lgan hajm</p>
          <p className="font-mono text-3xl font-bold" style={{ color: r.lots >= minLot ? "var(--gold)" : "var(--red)" }}>
            {r.lots >= minLot ? `${fmt(r.lots)} lot` : "—"}
          </p>
          <p className="text-xs mt-1" style={{ color: "var(--text-faint)" }}>{r.side} · SL masofasi {fmt(r.dist)} $</p>
        </div>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="rounded-md p-2" style={{ background: "var(--surface-2)" }}>
            <p className="text-[11px]" style={{ color: "var(--text-faint)" }}>SL ishlasa</p>
            <p className="font-mono font-semibold" style={{ color: "var(--red)" }}>−${fmt(r.lossAtSl)}</p>
          </div>
          <div className="rounded-md p-2" style={{ background: "var(--surface-2)" }}>
            <p className="text-[11px]" style={{ color: "var(--text-faint)" }}>TP ishlasa</p>
            <p className="font-mono font-semibold" style={{ color: "var(--green)" }}>+${fmt(r.profitAtTp)}</p>
          </div>
          <div className="rounded-md p-2" style={{ background: "var(--surface-2)" }}>
            <p className="text-[11px]" style={{ color: "var(--text-faint)" }}>R/R</p>
            <p className="font-mono font-semibold" style={{ color: "var(--text)" }}>{r.rr ? fmt(r.rr, 2) : "—"}</p>
          </div>
          <div className="rounded-md p-2" style={{ background: "var(--surface-2)" }}>
            <p className="text-[11px]" style={{ color: "var(--text-faint)" }}>Narx 1 $ o‘zgarsa</p>
            <p className="font-mono font-semibold" style={{ color: "var(--text)" }}>±${fmt(r.perDollar)}</p>
          </div>
        </div>
        {r.lots < minLot && r.dist > 0 && (
          <Callout tone="danger" title="Hisob bu savdo uchun juda kichik">
            Hisoblangan hajm {fmt(r.raw, 4)} lot — minimal 0.01 lotdan kam. 0.01 lot ochsangiz, zarar ${fmt(minLot * r.dist * contract)} bo‘ladi, bu sizning risk limitingizdan ({fmt(r.riskUsd)} $) ko‘p. Savdoni o‘tkazib yuborish tavsiya etiladi.
          </Callout>
        )}
        {riskPct > 1 && <Callout tone="warn" title="Risk yuqori">Har savdoda {riskPct}% risk — ketma-ket 6 ta zarar (tarixda bo‘lgan) hisobning ~{fmt(100 - 100 * Math.pow(1 - riskPct / 100, 6), 0)}% ini oladi.</Callout>}
        {r.side !== "—" && !r.tpOk && <Callout tone="warn">Take Profit kirish narxining noto‘g‘ri tomonida.</Callout>}
        {r.side === "—" && <Callout tone="warn">Kirish va Stop Loss bir xil bo‘lmasligi kerak.</Callout>}
      </div>
    </div>
  );
}

// ── Pre-trade checklist ──────────────────────────────────────────────────────

export function Checklist() {
  const [done, setDone] = useState<Record<string, boolean>>({});
  const n = CHECKLIST.filter(c => done[c.id]).length;
  const all = n === CHECKLIST.length;
  return (
    <div className="card p-4 space-y-3">
      <div className="flex items-center justify-between text-xs" style={{ color: "var(--text-muted)" }}>
        <span>{n} / {CHECKLIST.length} bajarildi</span>
        <button className="underline" onClick={() => setDone({})}>Tozalash</button>
      </div>
      <div className="score-bar-track"><div className="score-bar-fill" style={{ width: `${n / CHECKLIST.length * 100}%`, background: all ? "var(--green)" : "var(--gold)" }} /></div>
      <div className="space-y-1">
        {CHECKLIST.map(c => (
          <button key={c.id} onClick={() => setDone(d => ({ ...d, [c.id]: !d[c.id] }))}
                  className="w-full flex items-start gap-3 px-2 py-2 rounded-md text-left hover:bg-[var(--surface-2)]">
            {done[c.id] ? <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" style={{ color: "var(--green)" }} />
                        : <Circle className="w-4 h-4 mt-0.5 shrink-0" style={{ color: "var(--text-faint)" }} />}
            <span>
              <span className="block text-sm" style={{ color: done[c.id] ? "var(--text)" : "var(--text-muted)" }}>{c.text}</span>
              <span className="block text-[11px]" style={{ color: "var(--text-faint)" }}>{c.why}</span>
            </span>
          </button>
        ))}
      </div>
      {all ? <Callout tone="ok" title="Tayyor">Barcha shartlar bajarildi. Savdoni brokerda ochishingiz mumkin — va SL/TP ni o‘zgartirmang.</Callout>
           : <Callout tone="warn">Bitta band ham bajarilmagan bo‘lsa — savdo ochmang.</Callout>}
    </div>
  );
}
