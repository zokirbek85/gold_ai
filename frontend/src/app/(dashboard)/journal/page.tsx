"use client";

import { useQuery } from "@tanstack/react-query";
import { signalApi } from "@/lib/api";
import { formatPrice } from "@/lib/utils";
import { Card, CardHeader, PageHeader, StatCard, SignalBadge, EmptyState } from "@/components/ui";
import { BookOpen, Zap, TrendingUp, Target, BarChart3 } from "lucide-react";

export default function JournalPage() {
  const { data: signals, isLoading } = useQuery({
    queryKey: ["journal-signals"],
    queryFn: () => signalApi.list(undefined, undefined, 200).then(r => r.data),
  });

  const buys = signals?.filter((s: any) => s.signal_type === "BUY").length ?? 0;
  const sells = signals?.filter((s: any) => s.signal_type === "SELL").length ?? 0;
  const avgConf = signals?.length
    ? (signals.reduce((a: number, s: any) => a + (s.confidence ?? 0), 0) / signals.length)
    : null;
  const avgRR = signals?.filter((s: any) => s.rr).length
    ? signals.filter((s: any) => s.rr).reduce((a: number, s: any) => a + s.rr, 0) / signals.filter((s: any) => s.rr).length
    : null;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-5">
      <PageHeader
        title="Trade Journal"
        subtitle="Full history of all generated signals and performance metrics"
      />

      {/* Summary stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="Total Signals" value={signals?.length ?? 0} icon={<Zap className="w-4 h-4" />} />
        <StatCard
          label="Buy / Sell"
          value={`${buys} / ${sells}`}
          color="text-white"
          icon={<TrendingUp className="w-4 h-4" />}
        />
        <StatCard
          label="Avg Confidence"
          value={avgConf != null ? `${avgConf.toFixed(1)}%` : "—"}
          color="text-[var(--gold)]"
          icon={<Target className="w-4 h-4" />}
        />
        <StatCard
          label="Avg R:R"
          value={avgRR != null ? `${avgRR.toFixed(2)} R` : "—"}
          color="text-green-400"
          icon={<BarChart3 className="w-4 h-4" />}
        />
      </div>

      <Card>
        <div className="p-4 pb-0">
          <CardHeader icon={<BookOpen className="w-4 h-4" />} title={`Signal Log (${signals?.length ?? 0})`} />
        </div>
        {isLoading ? (
          <div className="p-4 space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-10 rounded skeleton" />
            ))}
          </div>
        ) : signals?.length ? (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Signal</th>
                  <th>Pair / TF</th>
                  <th className="text-right">Entry</th>
                  <th className="text-right">SL</th>
                  <th className="text-right">TP</th>
                  <th className="text-right">R:R</th>
                  <th className="text-right">Conf</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((s: any) => (
                  <tr key={s.id}>
                    <td className="text-xs" style={{ color: "var(--text-faint)" }}>{s.id}</td>
                    <td><SignalBadge type={s.signal_type} /></td>
                    <td className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                      {s.symbol} · {s.timeframe}m
                    </td>
                    <td className="text-right font-mono text-xs" style={{ color: "var(--text)" }}>{formatPrice(s.entry)}</td>
                    <td className="text-right font-mono text-xs text-red-400">{formatPrice(s.stop_loss)}</td>
                    <td className="text-right font-mono text-xs text-green-400">{formatPrice(s.take_profit)}</td>
                    <td className="text-right font-mono text-xs" style={{ color: "var(--gold)" }}>
                      {s.rr?.toFixed(2) ?? "—"}
                    </td>
                    <td className="text-right text-xs" style={{ color: "var(--text-muted)" }}>
                      {s.confidence?.toFixed(1)}%
                    </td>
                    <td className="text-xs" style={{ color: "var(--text-faint)" }}>
                      {new Date(s.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            icon={<BookOpen className="w-8 h-8" />}
            title="No signals logged"
            description="Generate signals from the Signals page"
          />
        )}
      </Card>
    </div>
  );
}

