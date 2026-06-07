"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { backtestApi } from "@/lib/api";
import { Card, CardHeader, PageHeader, EmptyState, Select, ScoreBar } from "@/components/ui";
import { FlaskConical, Play } from "lucide-react";
import type { BacktestResult } from "@/types";

export default function BacktestingPage() {
  const [symbol, setSymbol] = useState("XAUUSD");
  const [timeframe, setTimeframe] = useState("60");
  const [window, setWindow] = useState(100);

  const { data: backtests } = useQuery({
    queryKey: ["backtests"],
    queryFn: () => backtestApi.list().then(r => r.data),
  });

  const runMut = useMutation({
    mutationFn: () => backtestApi.run(symbol, timeframe, window).then(r => r.data),
  });

  const result = runMut.data;

  const MetricBox = ({ label, value, color = "text-white" }: { label: string; value: string; color?: string }) => (
    <div className="rounded-xl p-3 text-center" style={{ background: "var(--surface-2)" }}>
      <p className="text-[10px] mb-1" style={{ color: "var(--text-muted)" }}>{label}</p>
      <p className={`text-sm font-bold font-mono ${color}`}>{value}</p>
    </div>
  );

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-5">
      <PageHeader
        title="Backtesting"
        subtitle="Historical signal simulation with full performance metrics"
      />

      {/* Config */}
      <Card>
        <div className="p-5">
          <CardHeader icon={<FlaskConical className="w-4 h-4" />} title="Run Configuration" />
          <div className="flex flex-wrap gap-3 items-end">
            <div>
              <label className="block text-xs mb-1" style={{ color: "var(--text-muted)" }}>Symbol</label>
              <Select
                options={[{ value: "XAUUSD", label: "XAUUSD" }, { value: "EURUSD", label: "EURUSD" }]}
                value={symbol}
                onChange={e => setSymbol(e.target.value)}
                className="w-28"
              />
            </div>
            <div>
              <label className="block text-xs mb-1" style={{ color: "var(--text-muted)" }}>Timeframe</label>
              <Select
                options={[
                  { value: "5", label: "M5" }, { value: "15", label: "M15" },
                  { value: "60", label: "H1" }, { value: "240", label: "H4" },
                ]}
                value={timeframe}
                onChange={e => setTimeframe(e.target.value)}
                className="w-20"
              />
            </div>
            <div>
              <label className="block text-xs mb-1" style={{ color: "var(--text-muted)" }}>Window (bars)</label>
              <input
                type="number"
                value={window}
                onChange={e => setWindow(Number(e.target.value))}
                min={50} max={500}
                className="input w-24"
              />
            </div>
            <button
              onClick={() => runMut.mutate()}
              disabled={runMut.isPending}
              className="btn btn-gold"
            >
              {runMut.isPending ? <><FlaskConical className="w-3.5 h-3.5 animate-pulse" /> Running…</> : <><Play className="w-3.5 h-3.5" /> Run Backtest</>}
            </button>
          </div>
        </div>
      </Card>

      {/* Result */}
      {result && !result.error && (
        <Card className="border-[var(--gold)]/20">
          <div className="p-5">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-semibold" style={{ color: "var(--gold)" }}>
                Results — {result.name}
              </span>
              <span className="text-xs" style={{ color: "var(--text-faint)" }}>
                {result.trade_count} trades · {result.candle_count?.toLocaleString()} candles
              </span>
            </div>
            <div className="grid grid-cols-3 md:grid-cols-6 gap-2 mb-5">
              <MetricBox label="Win Rate" value={`${result.metrics?.win_rate?.toFixed(1)}%`} color="text-green-400" />
              <MetricBox label="Profit Factor" value={result.metrics?.profit_factor?.toFixed(2)} color="text-[var(--gold)]" />
              <MetricBox label="Sharpe" value={result.metrics?.sharpe_ratio?.toFixed(2)} color="text-blue-400" />
              <MetricBox label="Sortino" value={result.metrics?.sortino_ratio?.toFixed(2)} color="text-blue-400" />
              <MetricBox label="Max DD" value={`${result.metrics?.max_drawdown_pct?.toFixed(1)}%`} color="text-red-400" />
              <MetricBox
                label="Total PnL"
                value={`$${result.metrics?.total_pnl?.toFixed(0)}`}
                color={result.metrics?.total_pnl > 0 ? "text-green-400" : "text-red-400"}
              />
            </div>
            <div className="flex flex-wrap gap-5 text-xs" style={{ color: "var(--text-muted)" }}>
              <span>Trades: <strong style={{ color: "var(--text)" }}>{result.metrics?.total_trades}</strong></span>
              <span className="text-green-400">W: {result.metrics?.winning_trades}</span>
              <span className="text-red-400">L: {result.metrics?.losing_trades}</span>
              <span>Avg R:R: <strong style={{ color: "var(--gold)" }}>{result.metrics?.avg_rr?.toFixed(2)}</strong></span>
            </div>
          </div>
        </Card>
      )}

      {/* History */}
      {backtests?.length ? (
        <Card>
          <div className="p-4 pb-0">
            <CardHeader icon={<FlaskConical className="w-4 h-4" />} title="Backtest History" />
          </div>
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th className="text-right">Win Rate</th>
                  <th className="text-right">PF</th>
                  <th className="text-right">Sharpe</th>
                  <th className="text-right">Max DD</th>
                  <th className="text-right">PnL</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {backtests.map((bt: BacktestResult & { created_at: string }) => (
                  <tr key={bt.id}>
                    <td className="text-sm" style={{ color: "var(--text)" }}>{bt.name}</td>
                    <td className="text-right font-mono text-xs text-green-400">{bt.metrics?.win_rate?.toFixed(1)}%</td>
                    <td className="text-right font-mono text-xs" style={{ color: "var(--gold)" }}>{bt.metrics?.profit_factor?.toFixed(2)}</td>
                    <td className="text-right font-mono text-xs text-blue-400">{bt.metrics?.sharpe_ratio?.toFixed(2)}</td>
                    <td className="text-right font-mono text-xs text-red-400">{bt.metrics?.max_drawdown_pct?.toFixed(1)}%</td>
                    <td className={`text-right font-mono text-xs ${bt.metrics?.total_pnl > 0 ? "text-green-400" : "text-red-400"}`}>
                      ${bt.metrics?.total_pnl?.toFixed(0)}
                    </td>
                    <td className="text-xs" style={{ color: "var(--text-faint)" }}>
                      {new Date(bt.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : (
        !result && (
          <Card>
            <EmptyState
              icon={<FlaskConical className="w-8 h-8" />}
              title="No backtests yet"
              description="Configure a symbol and timeframe, then run your first backtest"
            />
          </Card>
        )
      )}
    </div>
  );
}
