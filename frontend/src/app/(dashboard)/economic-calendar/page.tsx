"use client";

import { useQuery } from "@tanstack/react-query";
import { econApi } from "@/lib/api";
import { Card, CardHeader, PageHeader, StatCard, DirectionBadge, EmptyState, SkeletonCard } from "@/components/ui";
import { Calendar, TrendingUp, Activity, BarChart3, Globe } from "lucide-react";
import type { EconomicEvent } from "@/types";

const IMPACT_LABEL = ["", "Low", "Medium", "High"];
const IMPACT_DOT = [
  "",
  "bg-gray-500",
  "bg-yellow-500",
  "bg-red-500",
];

export default function EconomicCalendarPage() {
  const { data: events, isLoading: eventsLoading } = useQuery({
    queryKey: ["econ-events"],
    queryFn: () => econApi.list(100).then(r => r.data),
    refetchInterval: 300_000,
  });

  const { data: score, isLoading: scoreLoading } = useQuery({
    queryKey: ["econ-aggregate"],
    queryFn: () => econApi.aggregateScore(48).then(r => r.data),
  });

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-5">
      <PageHeader
        title="Economic Calendar"
        subtitle="High-impact events: CPI, NFP, FOMC, GDP and gold impact scoring"
      />

      {/* Score cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {scoreLoading ? (
          Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
        ) : score ? (
          <>
            <StatCard
              label="Gold Direction (48h)"
              value={score.direction?.toUpperCase() ?? "—"}
              color={
                score.direction === "bullish" ? "text-green-400" :
                score.direction === "bearish" ? "text-red-400" : "text-[var(--text-muted)]"
              }
              icon={<TrendingUp className="w-4 h-4" />}
            />
            <StatCard label="Score" value={`${score.score?.toFixed(1)}/100`} icon={<Activity className="w-4 h-4" />} />
            <StatCard label="Avg Impact" value={`${score.avg_impact?.toFixed(1)}/10`} color="text-[var(--gold)]" icon={<BarChart3 className="w-4 h-4" />} />
            <StatCard label="Events Tracked" value={score.event_count ?? 0} icon={<Globe className="w-4 h-4" />} />
          </>
        ) : null}
      </div>

      {/* Events table */}
      <Card>
        <div className="p-4 pb-0">
          <CardHeader icon={<Calendar className="w-4 h-4" />} title="Events" />
        </div>
        {eventsLoading ? (
          <div className="p-4 space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-10 rounded skeleton" />
            ))}
          </div>
        ) : events?.length ? (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Impact</th>
                  <th>Event</th>
                  <th>Country</th>
                  <th className="text-right">Actual</th>
                  <th className="text-right">Forecast</th>
                  <th className="text-right">Previous</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {events.map((e: EconomicEvent) => (
                  <tr key={e.id}>
                    <td>
                      <div className="flex items-center gap-1.5">
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${IMPACT_DOT[e.impact ?? 0] || "bg-gray-600"}`} />
                        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                          {IMPACT_LABEL[e.impact ?? 0] || "—"}
                        </span>
                      </div>
                    </td>
                    <td className="font-medium text-sm" style={{ color: "var(--text)" }}>{e.event_type}</td>
                    <td>
                      <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: "var(--surface-2)", color: "var(--text-muted)" }}>
                        {e.country}
                      </span>
                    </td>
                    <td className="text-right font-mono text-xs" style={{ color: "var(--gold)" }}>{e.actual ?? "—"}</td>
                    <td className="text-right font-mono text-xs" style={{ color: "var(--text-muted)" }}>{e.forecast ?? "—"}</td>
                    <td className="text-right font-mono text-xs" style={{ color: "var(--text-faint)" }}>{e.previous ?? "—"}</td>
                    <td className="text-xs" style={{ color: "var(--text-faint)" }}>
                      {new Date(e.scheduled_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            icon={<Calendar className="w-8 h-8" />}
            title="No events yet"
            description="Fetch calendar data from Admin Panel → Economic Calendar → Fetch"
          />
        )}
      </Card>
    </div>
  );
}
