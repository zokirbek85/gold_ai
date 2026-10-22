"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowLeft, ArrowRight, ExternalLink, RotateCcw, Search } from "lucide-react";
import { Callout, Tabs } from "./Basics";
import { GLOSSARY, PAGES, QUIZ, type Term } from "./data";

// ── Step-by-step walkthrough ─────────────────────────────────────────────────

const STEPS: { title: string; body: React.ReactNode }[] = [
  {
    title: "Signal oling",
    body: (
      <>
        <p>Chap menyudan <Link href="/signals" className="underline" style={{ color: "var(--gold)" }}>Signals</Link> sahifasini oching va <b>Generate</b> tugmasini bosing. Yoki Telegram botga <code>/signal</code> yozing.</p>
        <p>Tizim oxirgi yopilgan 4 soatlik shamni tahlil qiladi. Bir necha soniyada javob keladi: <b>BUY</b>, <b>SELL</b> yoki <b>NO TRADE</b>.</p>
      </>
    ),
  },
  {
    title: "NO TRADE bo‘lsa — kuting",
    body: (
      <>
        <p>Bu eng ko‘p uchraydigan javob va bu yaxshi narsa: tizim sifatsiz savdolarni filtrlayapti.</p>
        <p>Sababini bilish uchun pastdagi <b>«NO TRADE dekoderi»</b>ga signal matnidagi kodni kiriting. Bir necha soatdan keyin qayta tekshiring — tizim har soat bozorni o‘zi ham tekshiradi.</p>
      </>
    ),
  },
  {
    title: "BUY yoki SELL bo‘lsa — tekshiring",
    body: (
      <>
        <p>Darhol savdo ochmang. Avval:</p>
        <ul className="list-disc pl-5 space-y-1">
          <li>brokeringizdagi joriy narx <b>kirish zonasi</b> ichidami?</li>
          <li><b>amal qilish muddati</b> o‘tmaganmi?</li>
          <li><Link href="/economic-calendar" className="underline" style={{ color: "var(--gold)" }}>Econ Calendar</Link>da 30 daqiqa ichida muhim yangilik yo‘qmi?</li>
        </ul>
        <p>Pastdagi <b>tekshiruv ro‘yxati</b>dan foydalaning.</p>
      </>
    ),
  },
  {
    title: "Lotni hisoblang",
    body: (
      <>
        <p>Pastdagi <b>risk kalkulyatori</b>ga balansingiz, risk foizi (0.5–1%), kirish va SL narxini kiriting. U nechta lot ochish kerakligini va SL ishlasa qancha yo‘qotishingizni ko‘rsatadi.</p>
        <p>Tizim taklif qilgan lot 10 000 $ lik hisob uchun hisoblangan — o‘z balansingiz uchun qayta hisoblang.</p>
      </>
    ),
  },
  {
    title: "Brokerda savdo oching",
    body: (
      <>
        <p>Brokeringiz terminalida (MT4/MT5 yoki mobil ilova):</p>
        <ol className="list-decimal pl-5 space-y-1">
          <li>XAUUSD (yoki GOLD) belgisini tanlang;</li>
          <li>«Yangi buyurtma» → hajm (lot) ni kiriting;</li>
          <li><b>S/L</b> maydoniga Stop Loss, <b>T/P</b> maydoniga Take Profit narxini yozing;</li>
          <li>signal BUY bo‘lsa <b>Buy</b>, SELL bo‘lsa <b>Sell</b> tugmasini bosing.</li>
        </ol>
        <p>Avval <b>demo hisobda</b> mashq qiling.</p>
      </>
    ),
  },
  {
    title: "Kuting va aralashmang",
    body: (
      <>
        <p>Savdo ochilgandan keyin SL va TP ni o‘zgartirmang va savdoni «qo‘rqib» erta yopmang. Natijalar aynan shu reja bo‘yicha hisoblangan.</p>
        <p>Savdo bir necha kun ochiq turishi mumkin. 8 savdo kuni (taxminan 1.5 hafta) ichida SL ham, TP ham ishlamasa, tizim modelida savdo yopiladi.</p>
      </>
    ),
  },
  {
    title: "Natijani yozib boring",
    body: (
      <>
        <p>Har bir real savdoni <Link href="/journal" className="underline" style={{ color: "var(--gold)" }}>Trade Journal</Link>ga yozing.</p>
        <p>Tizimning o‘z virtual natijalari shu sahifa tepasidagi «Virtual (paper) hisob» blokida ko‘rinadi. Ularni o‘zingiznikilar bilan solishtiring: farq katta bo‘lsa, sababini qidiring (spread, kech kirish, SL o‘zgartirish).</p>
      </>
    ),
  },
];

export function Stepper() {
  const [i, setI] = useState(0);
  return (
    <div className="card p-5">
      <div className="flex gap-1 mb-4" role="tablist">
        {STEPS.map((s, k) => (
          <button key={k} onClick={() => setI(k)} aria-label={s.title}
                  className="flex-1 h-1.5 rounded-full transition-colors"
                  style={{ background: k <= i ? "var(--gold)" : "var(--surface-3)" }} />
        ))}
      </div>
      <p className="text-xs mb-1" style={{ color: "var(--text-faint)" }}>{i + 1}-qadam / {STEPS.length}</p>
      <h3 className="text-base font-semibold mb-3" style={{ color: "var(--text)" }}>{STEPS[i].title}</h3>
      <div className="text-sm leading-relaxed space-y-2 min-h-[140px]" style={{ color: "var(--text-muted)" }}>{STEPS[i].body}</div>
      <div className="flex justify-between mt-4">
        <button className="btn-ghost text-xs inline-flex items-center gap-1" disabled={i === 0} onClick={() => setI(i - 1)}>
          <ArrowLeft className="w-3.5 h-3.5" /> Orqaga
        </button>
        <button className="btn-gold text-xs inline-flex items-center gap-1" disabled={i === STEPS.length - 1} onClick={() => setI(i + 1)}>
          Keyingi <ArrowRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

// ── Glossary ─────────────────────────────────────────────────────────────────

type Group = "all" | Term["group"];
const GROUPS: { value: Group; label: string }[] = [
  { value: "all", label: "Hammasi" }, { value: "asos", label: "Asoslar" },
  { value: "signal", label: "Signal" }, { value: "risk", label: "Risk" }, { value: "tizim", label: "Tizim" },
];

export function Glossary() {
  const [q, setQ] = useState("");
  const [g, setG] = useState<Group>("all");
  const [open, setOpen] = useState<string | null>(null);
  const list = GLOSSARY.filter(t => (g === "all" || t.group === g) &&
    (!q || (t.term + t.short + t.long).toLowerCase().includes(q.toLowerCase())));
  return (
    <div className="space-y-3">
      <div className="flex flex-col sm:flex-row gap-2 sm:items-center">
        <div className="relative flex-1">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5" style={{ color: "var(--text-faint)" }} />
          <input className="input w-full pl-8 text-sm" placeholder="Atamani qidiring: lot, spread, SL…" value={q} onChange={e => setQ(e.target.value)} />
        </div>
        <Tabs value={g} onChange={setG} options={GROUPS} />
      </div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
        {list.map(t => (
          <button key={t.term} onClick={() => setOpen(open === t.term ? null : t.term)}
                  className="card card-hover p-3 text-left self-start">
            <p className="text-sm font-semibold" style={{ color: "var(--gold)" }}>{t.term}</p>
            <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{t.short}</p>
            {open === t.term && (
              <div className="mt-2 pt-2 text-xs leading-relaxed space-y-1.5" style={{ borderTop: "1px solid var(--border)", color: "var(--text)" }}>
                <p>{t.long}</p>
                {t.example && <p className="font-mono text-[11px] rounded px-2 py-1" style={{ background: "var(--surface-2)", color: "var(--text-muted)" }}>Misol: {t.example}</p>}
              </div>
            )}
          </button>
        ))}
        {list.length === 0 && <p className="text-sm" style={{ color: "var(--text-faint)" }}>Hech narsa topilmadi.</p>}
      </div>
    </div>
  );
}

// ── Quiz ─────────────────────────────────────────────────────────────────────

export function Quiz() {
  const [i, setI] = useState(0);
  const [pick, setPick] = useState<number | null>(null);
  const [score, setScore] = useState(0);
  const done = i >= QUIZ.length;

  if (done) {
    const great = score === QUIZ.length;
    return (
      <div className="card p-5 text-center space-y-3">
        <p className="text-3xl font-bold font-mono" style={{ color: great ? "var(--green)" : "var(--gold)" }}>{score} / {QUIZ.length}</p>
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          {great ? "Ajoyib! Asosiy qoidalarni tushundingiz." : "Yaxshi boshlanish. Xato qilgan savollaringiz izohini qayta o‘qib chiqing."}
        </p>
        <button className="btn-ghost text-xs inline-flex items-center gap-1" onClick={() => { setI(0); setPick(null); setScore(0); }}>
          <RotateCcw className="w-3.5 h-3.5" /> Qaytadan
        </button>
      </div>
    );
  }
  const q = QUIZ[i];
  return (
    <div className="card p-5 space-y-3">
      <p className="text-xs" style={{ color: "var(--text-faint)" }}>Savol {i + 1} / {QUIZ.length} · To‘g‘ri: {score}</p>
      <p className="text-sm font-semibold" style={{ color: "var(--text)" }}>{q.q}</p>
      <div className="space-y-2">
        {q.options.map((o, k) => {
          const state = pick === null ? "idle" : k === q.answer ? "right" : k === pick ? "wrong" : "idle";
          return (
            <button key={k} disabled={pick !== null}
                    onClick={() => { setPick(k); if (k === q.answer) setScore(s => s + 1); }}
                    className="w-full text-left px-3 py-2 rounded-md text-sm transition-colors"
                    style={{
                      background: state === "right" ? "rgba(34,197,94,0.12)" : state === "wrong" ? "rgba(239,68,68,0.12)" : "var(--surface-2)",
                      border: `1px solid ${state === "right" ? "rgba(34,197,94,0.4)" : state === "wrong" ? "rgba(239,68,68,0.4)" : "transparent"}`,
                      color: "var(--text)",
                    }}>
              {o}
            </button>
          );
        })}
      </div>
      {pick !== null && (
        <>
          <Callout tone={pick === q.answer ? "ok" : "danger"} title={pick === q.answer ? "To‘g‘ri" : "Noto‘g‘ri"}>{q.why}</Callout>
          <button className="btn-gold text-xs" onClick={() => { setI(i + 1); setPick(null); }}>
            {i === QUIZ.length - 1 ? "Natijani ko‘rish" : "Keyingi savol"}
          </button>
        </>
      )}
    </div>
  );
}

// ── Page map ─────────────────────────────────────────────────────────────────

const TRUST: Record<string, [string, string]> = {
  ha: ["Foydalaning", "var(--green)"],
  malumot: ["Faqat ma'lumot", "var(--gold)"],
  yoq: ["Tayanmang", "var(--red)"],
};

export function PagesMap() {
  return (
    <div className="card overflow-x-auto">
      <table className="data-table w-full text-sm">
        <thead><tr><th className="text-left">Sahifa</th><th className="text-left">Nima uchun</th><th className="text-left">Baho</th></tr></thead>
        <tbody>
          {PAGES.map(p => (
            <tr key={p.href}>
              <td className="whitespace-nowrap">
                <Link href={p.href} className="inline-flex items-center gap-1 font-medium" style={{ color: "var(--gold)" }}>
                  {p.name} <ExternalLink className="w-3 h-3" />
                </Link>
              </td>
              <td style={{ color: "var(--text-muted)" }}>{p.use}</td>
              <td className="whitespace-nowrap text-xs font-semibold" style={{ color: TRUST[p.trust][1] }}>{TRUST[p.trust][0]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
