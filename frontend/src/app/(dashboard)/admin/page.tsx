"use client";

import { useQuery } from "@tanstack/react-query";
import { adminApi } from "@/lib/api";
import { Card, CardHeader, PageHeader, StatCard, SkeletonCard, EmptyState } from "@/components/ui";
import { Shield, Users, BarChart3, ScrollText } from "lucide-react";

export default function AdminPage() {
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["admin-stats"],
    queryFn: () => adminApi.stats().then(r => r.data),
  });
  const { data: users } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => adminApi.users().then(r => r.data),
  });
  const { data: logs } = useQuery({
    queryKey: ["admin-logs"],
    queryFn: () => adminApi.logs().then(r => r.data),
  });

  const statItems = stats ? [
    { label: "Users", value: stats.users },
    { label: "Signals", value: stats.signals },
    { label: "Candles", value: stats.candles?.toLocaleString() },
    { label: "News", value: stats.news_articles },
    { label: "Econ Events", value: stats.economic_events },
    { label: "Backtests", value: stats.backtests },
  ] : [];

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-5">
      <PageHeader
        title="Admin Panel"
        subtitle="System management, users, logs and statistics"
      />

      {/* Stats */}
      <div className="grid grid-cols-3 lg:grid-cols-6 gap-3">
        {statsLoading
          ? Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)
          : statItems.map(s => (
              <StatCard key={s.label} label={s.label} value={s.value ?? 0} />
            ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Users */}
        <Card>
          <div className="p-4 pb-0">
            <CardHeader icon={<Users className="w-4 h-4" />} title="Users" />
          </div>
          {users?.length ? (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Joined</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u: any) => (
                    <tr key={u.id}>
                      <td className="text-xs" style={{ color: "var(--text)" }}>{u.email}</td>
                      <td>
                        <span
                          className="text-[11px] px-2 py-0.5 rounded font-medium"
                          style={{
                            background: "rgba(245,166,35,0.1)",
                            color: "var(--gold)",
                            border: "1px solid rgba(245,166,35,0.2)",
                          }}
                        >
                          {u.role ?? "—"}
                        </span>
                      </td>
                      <td>
                        <span
                          className="text-[11px] font-medium"
                          style={{ color: u.is_active ? "var(--green)" : "var(--red)" }}
                        >
                          {u.is_active ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td className="text-xs" style={{ color: "var(--text-faint)" }}>
                        {new Date(u.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState icon={<Users className="w-8 h-8" />} title="No users found" />
          )}
        </Card>

        {/* Logs */}
        <Card>
          <div className="p-4 pb-2">
            <CardHeader icon={<ScrollText className="w-4 h-4" />} title="System Logs" />
          </div>
          <div
            className="max-h-72 overflow-y-auto font-mono text-[11px] px-4 pb-3 space-y-1"
          >
            {logs?.length ? logs.map((l: any) => (
              <div key={l.id} className="flex gap-2.5 leading-relaxed">
                <span
                  className="shrink-0 font-semibold w-14"
                  style={{
                    color: l.level === "ERROR" ? "var(--red)" :
                           l.level === "WARNING" ? "var(--gold)" :
                           "var(--text-faint)",
                  }}
                >
                  [{l.level?.slice(0, 4)}]
                </span>
                <span className="flex-1 truncate" style={{ color: "var(--text-muted)" }}>
                  {l.message}
                </span>
                <span className="shrink-0" style={{ color: "var(--text-faint)" }}>
                  {new Date(l.created_at).toLocaleTimeString()}
                </span>
              </div>
            )) : (
              <p className="py-8 text-center" style={{ color: "var(--text-faint)" }}>No logs yet</p>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
