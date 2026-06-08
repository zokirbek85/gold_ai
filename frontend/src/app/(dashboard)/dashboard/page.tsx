"use client";

import { useQuery } from "@tanstack/react-query";
import { adminApi, signalApi, newsApi, econApi } from "@/lib/api";
import { formatPrice, signalColor, directionColor } from "@/lib/utils";
import { Activity, Zap, Newspaper, BarChart3, Database, TrendingUp, TrendingDown, Minus } from "lucide-react";
import {
  Card, CardHeader, PageHeader, StatCard, SignalBadge,
  DirectionBadge, ImpactBadge, ScoreBar, SkeletonCard, SkeletonRow, EmptyState,
} from "@/components/ui";

export default function DashboardPage() {
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["admin-stats"],
    queryFn: () => adminApi.stats().then(r => r.data),
  });
  const { data: signals, isLoading: sigsLoading } = useQuery({
    queryKey: ["signals-recent"],
    queryFn: () => signalApi.list("XAUUSD", undefined, 5).then(r => r.data),
  });
  const { data: news, isLoading: newsLoading } = useQuery({
    queryKey: ["news-recent"],
    queryFn: () => newsApi.list(5).then(r => r.data),
  });
  const { data: sentiment } = useQuery({
    queryKey: ["news-sentiment"],
    queryFn: () => newsApi.sentiment(24).then(r => r.data),
  });
  const { data: econScore } = useQuery({
    queryKey: ["econ-score"],
    queryFn: () => econApi.aggregateScore(48).then(r => r.data),
  });

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <PageHeader
        title="Dashboard"
        subtitle="XAUUSD Intelligence Overview"
      />

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {statsLoading ? (
          Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
        ) : (
          <>
            <StatCard
              label="Total Signals"
              value={stats?.signals ?? 0}
              sub="All time"
              icon={<Zap className="w-4 h-4" />}
            />
            <StatCard
              label="Candles Stored"
              value={stats?.candles?.toLocaleString() ?? 0}
              sub="Market data"
              icon={<TrendingUp className="w-4 h-4" />}
            />
            <StatCard
              label="News Articles"
              value={stats?.news_articles?.toLocaleString() ?? 0}
              sub="Analyzed"
              icon={<Newspaper className="w-4 h-4" />}
            />
            <StatCard
              label="Sentiment (24h)"
              value={sentiment?.direction?.toUpperCase() ?? "—"}
              sub={sentiment ? `Score: ${sentiment.score?.toFixed(1)}/100` : ""}
              color={
                sentiment?.direction === "bullish" ? "text-green-400" :
                sentiment?.direction === "bearish" ? "text-red-400" :
                "text-[var(--text-muted)]"
              }
              icon={<Activity className="w-4 h-4" />}
            />
          </>
        )}
      </div>

      {/* Two-column: Signals + News */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Recent Signals */}
        <Card>
          <div className="p-4">
            <CardHeader icon={<Zap className="w-4 h-4" />} title="Recent Signals" />
            {sigsLoading ? (
              <div className="space-y-1">{Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} />)}</div>
            ) : signals?.length ? (
              <div className="space-y-1">
                {signals.map((s: any) => (
                  <div
                    key={s.id}
                    className={`flex items-center justify-between px-3 py-2.5 rounded-lg transition-colors ${
                      s.signal_type === "BUY"  ? "bg-green-500/8 hover:bg-green-500/15" :
                      s.signal_type === "SELL" ? "bg-red-500/8 hover:bg-red-500/15"     :
                      "hover:bg-[var(--surface-2)]"
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                      <span className={`inline-flex items-center gap-1.5 text-sm font-black px-2.5 py-1 rounded-lg ${
                        s.signal_type === "BUY"
                          ? "text-green-400 bg-green-500/15 border border-green-500/25"
                          : s.signal_type === "SELL"
                          ? "text-red-400 bg-red-500/15 border border-red-500/25"
                          : "text-gray-400 bg-gray-500/10 border border-gray-500/20"
                      }`}>
                        {s.signal_type === "BUY"      && <TrendingUp   className="w-3.5 h-3.5" />}
                        {s.signal_type === "SELL"     && <TrendingDown  className="w-3.5 h-3.5" />}
                        {s.signal_type === "NO TRADE" && <Minus         className="w-3.5 h-3.5" />}
                        {s.signal_type}
                      </span>
                      <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                        {s.symbol} · {s.timeframe}m
                      </span>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-mono font-semibold" style={{ color: "var(--text)" }}>
                        {formatPrice(s.entry, 2)}
                      </p>
                      <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                        {s.confidence?.toFixed(1)}% conf
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                icon={<Zap className="w-8 h-8" />}
                title="No signals yet"
                description="Go to Signals page and click Generate Signal"
              />
            )}
          </div>
        </Card>

        {/* Recent News */}
        <Card>
          <div className="p-4">
            <CardHeader icon={<Newspaper className="w-4 h-4" />} title="Latest News" />
            {newsLoading ? (
              <div className="space-y-1">{Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} />)}</div>
            ) : news?.length ? (
              <div className="divide-y" style={{ borderColor: "var(--surface-2)" }}>
                {news.map((n: any) => (
                  <div key={n.id} className="py-2.5 first:pt-0 last:pb-0">
                    <div className="flex items-start gap-2">
                      <p className="text-[13px] leading-snug flex-1" style={{ color: "var(--text)" }}>
                        {n.title}
                      </p>
                      <ImpactBadge score={n.impact_score} />
                    </div>
                    <div className="flex gap-2 mt-1">
                      <span className="text-[11px]" style={{ color: "var(--text-faint)" }}>{n.source}</span>
                      {n.duration && (
                        <span className="text-[11px]" style={{ color: "var(--blue)" }}>{n.duration}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                icon={<Newspaper className="w-8 h-8" />}
                title="No news yet"
                description="Trigger ingestion from Admin Panel"
              />
            )}
          </div>
        </Card>
      </div>

      {/* Economic Score */}
      {econScore && (
        <Card>
          <div className="p-4">
            <CardHeader icon={<BarChart3 className="w-4 h-4" />} title="Economic Score (48h)" />
            <div className="flex flex-wrap gap-8 mb-4">
              {[
                { label: "Direction", value: <DirectionBadge direction={econScore.direction} /> },
                { label: "Score", value: <span className="text-lg font-bold font-mono text-white">{econScore.score?.toFixed(1)}/100</span> },
                { label: "Avg Impact", value: <span className="text-lg font-bold font-mono" style={{ color: "var(--gold)" }}>{econScore.avg_impact?.toFixed(1)}/10</span> },
                { label: "Events", value: <span className="text-lg font-bold font-mono text-white">{econScore.event_count}</span> },
              ].map(item => (
                <div key={item.label}>
                  <p className="text-[11px] mb-1" style={{ color: "var(--text-muted)" }}>{item.label}</p>
                  {item.value}
                </div>
              ))}
            </div>
            <ScoreBar score={econScore.score} direction={econScore.direction} />
          </div>
        </Card>
      )}
    </div>
  );
}
