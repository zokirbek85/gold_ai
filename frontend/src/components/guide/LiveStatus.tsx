"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Activity, FlaskConical, ShieldCheck, Zap } from "lucide-react";
import { api } from "@/lib/api";
import { SignalBadge } from "@/components/ui";
import { fmt } from "./Basics";
import { findReason } from "./data";

/** Extract reason codes from the plain-text explanation stored with each signal. */
export function codesFromText(text?: string | null): string[] {
  const m = text?.match(/Kodlar:\s*([A-Z_,\s]+)/);
  return m ? m[1].split(",").map(s => s.trim()).filter(Boolean) : [];
}

export function useLatestSignal() {
  return useQuery({
    queryKey: ["guide-latest-signal"],
    queryFn: () => api.get("/signals", { params: { symbol: "XAUUSD", timeframe: "240", limit: 1 } }).then(r => r.data?.[0] ?? null),
    refetchInterval: 60_000,
  });
}

function Box({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-2 text-xs font-medium uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
        <span style={{ color: "var(--gold)" }}>{icon}</span>{title}
      </div>
      {children}
    </div>
  );
}

export function LiveStatus() {
  const sig = useLatestSignal();
  const paper = useQuery({ queryKey: ["guide-paper"], queryFn: () => api.get("/paper/stats").then(r => r.data), refetchInterval: 60_000 });
  const ready = useQuery({ queryKey: ["guide-ready"], queryFn: () => api.get("/execution/readiness").then(r => r.data) });

  const s = sig.data;
  const codes = codesFromText(s?.plain_explanation);
  const reason = codes.length ? findReason(codes[0]) : undefined;
  const failed = (ready.data?.checks ?? []).filter((c: { passed: boolean }) => !c.passed).length;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
      <Box icon={<Zap className="w-3.5 h-3.5" />} title="Oxirgi signal">
        {sig.isLoading ? <p className="text-sm" style={{ color: "var(--text-faint)" }}>Yuklanmoqda…</p> : !s ? (
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>Hali signal yo‘q. <Link href="/signals" className="underline" style={{ color: "var(--gold)" }}>Signals</Link> sahifasida «Generate» ni bosing.</p>
        ) : (
          <div className="space-y-1.5 text-sm">
            <div className="flex items-center gap-2">
              <SignalBadge type={s.signal_type} />
              <span className="text-xs" style={{ color: "var(--text-faint)" }}>{new Date(s.created_at + (s.created_at.endsWith("Z") ? "" : "Z")).toLocaleString()}</span>
            </div>
            {s.signal_type === "NO TRADE" ? (
              <p style={{ color: "var(--text-muted)" }}>
                {reason ? <><b style={{ color: "var(--text)" }}>{reason.title}.</b> {reason.action}</> : "Hozir savdo qilmang."}
              </p>
            ) : (
              <p className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                Kirish {fmt(s.entry)} · SL {fmt(s.stop_loss)} · TP {fmt(s.take_profit)}
              </p>
            )}
          </div>
        )}
      </Box>
      <Box icon={<FlaskConical className="w-3.5 h-3.5" />} title="Virtual (paper) hisob">
        {paper.data ? (
          <div className="text-sm space-y-1">
            <p className="font-mono text-lg font-bold" style={{ color: "var(--text)" }}>${fmt(paper.data.account?.balance, 0)}</p>
            <p style={{ color: "var(--text-muted)" }}>
              Yopilgan savdolar: <b>{paper.data.trades}</b> · Ochiq/kutilayotgan: <b>{paper.data.open_or_pending}</b>
            </p>
            <p className="text-xs" style={{ color: "var(--text-faint)" }}>Holat: {paper.data.health?.status === "INSUFFICIENT_DATA" ? "xulosa uchun savdo kam" : paper.data.health?.status}</p>
          </div>
        ) : <p className="text-sm" style={{ color: "var(--text-faint)" }}>{paper.isError ? "Ma'lumot olinmadi" : "Yuklanmoqda…"}</p>}
      </Box>
      <Box icon={<ShieldCheck className="w-3.5 h-3.5" />} title="Real savdo">
        {ready.data ? (
          <div className="text-sm space-y-1">
            <p className="font-semibold" style={{ color: ready.data.live_allowed ? "var(--green)" : "var(--red)" }}>
              {ready.data.live_allowed ? "Ruxsat berilgan" : "Bloklangan (xavfsizlik uchun)"}
            </p>
            <p style={{ color: "var(--text-muted)" }}>
              Dastur real hisobda o‘zi savdo ochmaydi. Real savdo uchun {failed} ta shart hali bajarilmagan.
            </p>
          </div>
        ) : <p className="text-sm" style={{ color: "var(--text-faint)" }}>{ready.isError ? "Ma'lumot olinmadi" : "Yuklanmoqda…"}</p>}
      </Box>
      <p className="md:col-span-3 text-xs flex items-center gap-1.5" style={{ color: "var(--text-faint)" }}>
        <Activity className="w-3 h-3" /> Bu bloklar har daqiqada avtomatik yangilanadi.
      </p>
    </div>
  );
}
