"use client";

import { BarChart3, Bot, ShieldCheck } from "lucide-react";
import { PageHeader } from "@/components/ui";
import { Accordion, Callout, Section } from "@/components/guide/Basics";
import { LiveStatus } from "@/components/guide/LiveStatus";
import { PriceSimulator } from "@/components/guide/PriceSimulator";
import { SignalAnatomy } from "@/components/guide/SignalAnatomy";
import { Checklist, ReasonDecoder, RiskCalculator } from "@/components/guide/Tools";
import { Glossary, PagesMap, Quiz, Stepper } from "@/components/guide/Learn";
import { FAQ } from "@/components/guide/data";

const TOC = [
  ["nima", "Dastur nima qiladi"],
  ["holat", "Hozirgi holat"],
  ["qadamlar", "Qadam-baqadam"],
  ["diagramma", "SL va TP qanday ishlaydi"],
  ["signal", "Signalni o‘qish"],
  ["notrade", "NO TRADE sabablari"],
  ["kalkulyator", "Lot kalkulyatori"],
  ["tekshiruv", "Savdodan oldin"],
  ["lugat", "Lug‘at"],
  ["test", "Bilimingizni sinang"],
  ["sahifalar", "Sahifalar xaritasi"],
  ["savollar", "Savol-javob"],
] as const;

function go(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export default function GuidePage() {
  return (
    <div className="p-6 max-w-6xl mx-auto">
      <PageHeader title="Qo‘llanma" subtitle="Gold AI dan qanday foydalanish — trading tajribasi bo‘lmaganlar uchun, qadam-baqadam" />

      <nav className="card p-3 mb-8 flex flex-wrap gap-1.5" aria-label="Mundarija">
        {TOC.map(([id, label], k) => (
          <button key={id} onClick={() => go(id)}
                  className="text-xs px-2.5 py-1 rounded-md hover:bg-[var(--surface-2)]"
                  style={{ color: "var(--text-muted)" }}>
            <span style={{ color: "var(--gold)" }}>{k + 1}.</span> {label}
          </button>
        ))}
      </nav>

      <div className="space-y-12">
        <Section id="nima" step="1" title="Dastur nima qiladi?" subtitle="30 soniyada">
          <div className="grid md:grid-cols-3 gap-3 mb-4">
            {[
              [<BarChart3 key="a" className="w-5 h-5" />, "Bozorni kuzatadi", "Har soat oltin (XAUUSD) narxini tahlil qiladi: narx qaysi yo‘nalishda harakatlanyapti, bozor tinchmi yoki keskinmi."],
              [<Bot key="b" className="w-5 h-5" />, "Signal beradi", "Shartlar yaxshi bo‘lsa — BUY (sotib ol) yoki SELL (sot) signali: qayerda kirish, qayerda zararni to‘xtatish va qayerda foydani olish."],
              [<ShieldCheck key="c" className="w-5 h-5" />, "Sizni himoya qiladi", "Shartlar yaxshi bo‘lmasa — NO TRADE. Yangilik, keskin bozor, yomon ma'lumot paytida signal bermaydi."],
            ].map(([icon, t, d]) => (
              <div key={t as string} className="card p-4">
                <span style={{ color: "var(--gold)" }}>{icon}</span>
                <p className="text-sm font-semibold mt-2" style={{ color: "var(--text)" }}>{t}</p>
                <p className="text-sm mt-1 leading-relaxed" style={{ color: "var(--text-muted)" }}>{d}</p>
              </div>
            ))}
          </div>
          <div className="grid md:grid-cols-2 gap-3">
            <Callout tone="info" title="Muhim: dastur siz uchun savdo ochmaydi">
              Real hisobda savdoni faqat siz o‘zingiz brokerda ochasiz. Dastur faqat maslahat beradi va o‘z natijasini virtual (paper) hisobda tekshiradi.
            </Callout>
            <Callout tone="warn" title="Foyda kafolatlanmaydi">
              Tarixiy testda strategiya xarajatlardan keyin musbat natija ko‘rsatgan, lekin savdolar soni kam. O‘rtacha oyiga atigi 1–1.5 ta signal chiqadi. Faqat yo‘qotishga tayyor bo‘lgan pul bilan, avval demo hisobda ishlang.
            </Callout>
          </div>
        </Section>

        <Section id="holat" step="2" title="Hozirgi holat" subtitle="Tizimdan jonli ma'lumot">
          <LiveStatus />
        </Section>

        <Section id="qadamlar" step="3" title="Qadam-baqadam foydalanish" subtitle="Signal olishdan savdoni yopishgacha">
          <Stepper />
        </Section>

        <Section id="diagramma" step="4" title="Stop Loss va Take Profit qanday ishlaydi" subtitle="Vaqt slayderini suring va natijani kuzating">
          <PriceSimulator />
        </Section>

        <Section id="signal" step="5" title="Signalni qanday o‘qish kerak" subtitle="Har bir maydonni bosing — tushuntirish o‘ng tomonda chiqadi">
          <SignalAnatomy />
        </Section>

        <Section id="notrade" step="6" title="NO TRADE sabablari dekoderi" subtitle="Signal matnidagi «Kodlar:» qatori nimani anglatadi">
          <ReasonDecoder />
        </Section>

        <Section id="kalkulyator" step="7" title="Lot (savdo hajmi) kalkulyatori" subtitle="Hisobingiz uchun nechta lot ochish kerakligini hisoblang">
          <RiskCalculator />
        </Section>

        <Section id="tekshiruv" step="8" title="Savdo ochishdan oldingi tekshiruv" subtitle="Har bir bandni belgilang — hammasi bajarilmaguncha savdo ochmang">
          <Checklist />
        </Section>

        <Section id="lugat" step="9" title="Lug‘at" subtitle="Atamani bosing — batafsil izoh va misol chiqadi">
          <Glossary />
        </Section>

        <Section id="test" step="10" title="Bilimingizni sinang" subtitle="6 ta qisqa savol">
          <Quiz />
        </Section>

        <Section id="sahifalar" step="11" title="Sahifalar xaritasi" subtitle="Qaysi sahifa nima uchun va qaysi biriga tayanish mumkin">
          <PagesMap />
        </Section>

        <Section id="savollar" step="12" title="Ko‘p beriladigan savollar">
          <Accordion items={FAQ} />
        </Section>

        <Callout tone="danger" title="Eng muhim 5 qoida">
          <ol className="list-decimal pl-5 space-y-1">
            <li>Har doim Stop Loss qo‘ying.</li>
            <li>Bir savdoda hisobning 1% idan ko‘pini tavakkal qilmang.</li>
            <li>NO TRADE bo‘lsa — savdo qilmang.</li>
            <li>Kirish zonasidan chiqib ketgan narxni quvlamang.</li>
            <li>Zarardan keyin lotni oshirib «qaytarib olishga» urinmang.</li>
          </ol>
        </Callout>
      </div>
    </div>
  );
}
