"use client";

import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export function Section({ id, step, title, subtitle, children }: {
  id: string; step?: string; title: string; subtitle?: string; children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-6">
      <div className="flex items-start gap-3 mb-4">
        {step && (
          <span className="w-7 h-7 shrink-0 rounded-full flex items-center justify-center text-xs font-bold"
                style={{ background: "rgba(245,166,35,0.12)", color: "var(--gold)" }}>{step}</span>
        )}
        <div>
          <h2 className="text-lg font-semibold" style={{ color: "var(--text)" }}>{title}</h2>
          {subtitle && <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>{subtitle}</p>}
        </div>
      </div>
      {children}
    </section>
  );
}

export function Callout({ tone = "info", title, children }: {
  tone?: "info" | "warn" | "danger" | "ok"; title?: string; children: ReactNode;
}) {
  const c = {
    info: ["rgba(59,130,246,0.08)", "rgba(59,130,246,0.3)", "var(--blue)"],
    warn: ["rgba(245,166,35,0.08)", "rgba(245,166,35,0.3)", "var(--gold)"],
    danger: ["rgba(239,68,68,0.08)", "rgba(239,68,68,0.3)", "var(--red)"],
    ok: ["rgba(34,197,94,0.08)", "rgba(34,197,94,0.3)", "var(--green)"],
  }[tone];
  return (
    <div className="rounded-lg px-4 py-3 text-sm leading-relaxed"
         style={{ background: c[0], border: `1px solid ${c[1]}`, color: "var(--text)" }}>
      {title && <p className="font-semibold mb-1" style={{ color: c[2] }}>{title}</p>}
      {children}
    </div>
  );
}

export function Accordion({ items }: { items: { q: string; a: ReactNode }[] }) {
  const [open, setOpen] = useState<number | null>(0);
  return (
    <div className="space-y-2">
      {items.map((it, i) => (
        <div key={i} className="card overflow-hidden">
          <button onClick={() => setOpen(open === i ? null : i)}
                  className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left text-sm font-medium"
                  style={{ color: "var(--text)" }} aria-expanded={open === i}>
            {it.q}
            <ChevronDown className={cn("w-4 h-4 shrink-0 transition-transform", open === i && "rotate-180")}
                         style={{ color: "var(--text-muted)" }} />
          </button>
          {open === i && (
            <div className="px-4 pb-4 text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>{it.a}</div>
          )}
        </div>
      ))}
    </div>
  );
}

export function Tabs<T extends string>({ value, onChange, options }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: string }[];
}) {
  return (
    <div className="inline-flex flex-wrap gap-1 p-1 rounded-lg" style={{ background: "var(--surface-2)" }}>
      {options.map(o => (
        <button key={o.value} onClick={() => onChange(o.value)}
                className="px-3 py-1 rounded-md text-xs font-medium transition-colors"
                style={value === o.value
                  ? { background: "var(--surface-3)", color: "var(--gold)" }
                  : { color: "var(--text-muted)" }}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export const fmt = (v: number | null | undefined, d = 2) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
