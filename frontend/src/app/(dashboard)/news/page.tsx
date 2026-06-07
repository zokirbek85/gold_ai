"use client";

import { useQuery } from "@tanstack/react-query";
import { newsApi } from "@/lib/api";
import { Card, CardHeader, PageHeader, StatCard, ImpactBadge, DirectionBadge, EmptyState, SkeletonCard, SkeletonRow } from "@/components/ui";
import { Newspaper, ExternalLink, TrendingUp, MessageSquare, Clock } from "lucide-react";
import type { NewsArticle } from "@/types";

export default function NewsPage() {
  const { data: articles, isLoading } = useQuery({
    queryKey: ["news"],
    queryFn: () => newsApi.list(100).then(r => r.data),
    refetchInterval: 60_000,
  });

  const { data: sentiment } = useQuery({
    queryKey: ["news-sentiment-24h"],
    queryFn: () => newsApi.sentiment(24).then(r => r.data),
  });

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-5">
      <PageHeader
        title="News Intelligence"
        subtitle="Gold-related news with AI impact scoring and sentiment analysis"
      />

      {/* Sentiment stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {!sentiment ? (
          Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
        ) : (
          <>
            <StatCard
              label="Sentiment (24h)"
              value={sentiment.direction?.toUpperCase() ?? "—"}
              color={
                sentiment.direction === "bullish" ? "text-green-400" :
                sentiment.direction === "bearish" ? "text-red-400" :
                "text-[var(--text-muted)]"
              }
              icon={<TrendingUp className="w-4 h-4" />}
            />
            <StatCard
              label="Score"
              value={`${sentiment.score?.toFixed(1)}/100`}
              sub="Confidence level"
              icon={<MessageSquare className="w-4 h-4" />}
            />
            <StatCard
              label="Articles (24h)"
              value={sentiment.article_count ?? 0}
              sub={`${sentiment.bullish_count ?? 0} bullish · ${sentiment.bearish_count ?? 0} bearish`}
              icon={<Newspaper className="w-4 h-4" />}
            />
            <StatCard
              label="Avg Impact"
              value={`${sentiment.avg_impact?.toFixed(1) ?? "—"}/10`}
              color="text-[var(--gold)]"
              icon={<Clock className="w-4 h-4" />}
            />
          </>
        )}
      </div>

      {/* Articles */}
      <Card>
        <div className="p-4 pb-0">
          <CardHeader icon={<Newspaper className="w-4 h-4" />} title="Latest Articles" />
        </div>
        {isLoading ? (
          <div className="p-4 space-y-3">
            {Array.from({ length: 6 }).map((_, i) => <SkeletonRow key={i} />)}
          </div>
        ) : articles?.length ? (
          <div className="divide-y px-4 pb-2" style={{ borderColor: "var(--surface-2)" }}>
            {articles.map((a: NewsArticle) => (
              <div
                key={a.id}
                className="py-3 flex items-start gap-3 group transition-colors rounded-lg -mx-2 px-2"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-start gap-2 mb-1">
                    <a
                      href={a.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[13px] leading-snug font-medium transition-colors flex-1"
                      style={{ color: "var(--text)" }}
                      onMouseEnter={e => (e.target as HTMLElement).style.color = "var(--gold)"}
                      onMouseLeave={e => (e.target as HTMLElement).style.color = "var(--text)"}
                    >
                      {a.title}
                    </a>
                    <ExternalLink
                      className="w-3 h-3 shrink-0 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                      style={{ color: "var(--text-faint)" }}
                    />
                  </div>
                  {a.summary && (
                    <p className="text-[12px] leading-relaxed line-clamp-2 mb-1.5" style={{ color: "var(--text-muted)" }}>
                      {a.summary}
                    </p>
                  )}
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[11px]" style={{ color: "var(--text-faint)" }}>{a.source}</span>
                    <span className="text-[11px]" style={{ color: "var(--text-faint)" }}>
                      {new Date(a.published_at).toLocaleString()}
                    </span>
                    {a.duration && (
                      <span className="text-[11px] px-1.5 py-0.5 rounded" style={{
                        background: "rgba(59,130,246,0.1)",
                        color: "var(--blue)",
                        border: "1px solid rgba(59,130,246,0.2)",
                      }}>
                        {a.duration}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1.5 shrink-0">
                  <ImpactBadge score={a.impact_score} />
                  {a.confidence != null && (
                    <span className="text-[11px]" style={{ color: "var(--text-faint)" }}>
                      {(a.confidence * 100).toFixed(0)}% conf
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            icon={<Newspaper className="w-8 h-8" />}
            title="No articles yet"
            description="Trigger news ingestion from the Admin Panel"
          />
        )}
      </Card>
    </div>
  );
}
