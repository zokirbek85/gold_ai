"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { mlApi } from "@/lib/api";
import { Card, CardHeader, PageHeader, DirectionBadge, ScoreBar, Select, EmptyState } from "@/components/ui";
import { Brain, Play, RefreshCw } from "lucide-react";

const RANGES = [
  { value: "1d",  label: "1D",  desc: "Last day — M15 bars",    tf: "15"  },
  { value: "1w",  label: "1W",  desc: "Last week — H1 bars",    tf: "60"  },
  { value: "1m",  label: "1M",  desc: "Last month — H4 bars",   tf: "240" },
  { value: "3m",  label: "3M",  desc: "Last 3 months — D1 bars", tf: "1440" },
];

export default function MLPage() {
  const [symbol, setSymbol] = useState("XAUUSD");
  const [range, setRange] = useState("1m");

  const activeRange = RANGES.find(r => r.value === range) ?? RANGES[2];

  const predictMut = useMutation({
    mutationFn: () => mlApi.predict(symbol, activeRange.tf, range).then(r => r.data),
  });
  const trainMut = useMutation({
    mutationFn: () => mlApi.train(symbol, activeRange.tf, range).then(r => r.data),
  });
  const pred = predictMut.data;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-5">
      <PageHeader
        title="Machine Learning"
        subtitle="RandomForest model trained on real Twelvedata historical candles"
      />

      {/* Controls */}
      <Card>
        <div className="p-5">
          <CardHeader icon={<Brain className="w-4 h-4" />} title="Model Controls" />
          <div className="flex flex-wrap gap-4 items-end">
            <div>
              <label className="block text-xs mb-1" style={{ color: "var(--text-muted)" }}>Symbol</label>
              <Select
                options={[
                  { value: "XAUUSD", label: "XAUUSD" },
                  { value: "EURUSD", label: "EURUSD" },
                  { value: "BTCUSD", label: "BTCUSD" },
                ]}
                value={symbol}
                onChange={e => setSymbol(e.target.value)}
                className="w-28"
              />
            </div>

            {/* Shared range selector */}
            <div className="flex flex-col gap-1">
              <label className="text-xs" style={{ color: "var(--text-muted)" }}>
                Data range <span className="text-gray-600">— used for both train & predict</span>
              </label>
              <div className="flex gap-1">
                {RANGES.map(r => (
                  <button
                    key={r.value}
                    title={r.desc}
                    onClick={() => setRange(r.value)}
                    className={`px-2.5 py-1.5 text-xs rounded-lg font-medium transition-colors ${
                      range === r.value
                        ? "bg-yellow-500 text-black"
                        : "bg-[#1a1a24] text-gray-400 hover:text-gray-200"
                    }`}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
            </div>

            <button
              onClick={() => predictMut.mutate()}
              disabled={predictMut.isPending}
              className="btn btn-gold"
            >
              {predictMut.isPending
                ? <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                : <Play className="w-3.5 h-3.5" />}
              {predictMut.isPending ? "Predicting…" : "Run Prediction"}
            </button>

            <button
              onClick={() => trainMut.mutate()}
              disabled={trainMut.isPending}
              className="btn btn-ghost"
            >
              {trainMut.isPending
                ? <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                : <Brain className="w-3.5 h-3.5" />}
              {trainMut.isPending ? "Training…" : "Train Model"}
            </button>
          </div>

          {/* Active config badge */}
          <div className="mt-3 flex gap-3 text-[11px] text-gray-500">
            <span>
              Timeframe: <span className="text-yellow-400">{activeRange.tf}min — {activeRange.desc}</span>
            </span>
            <span className="text-[#2a2a3a]">|</span>
            <span className="text-green-400">Data: Twelvedata real candles</span>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Prediction result */}
        <Card className={pred ? "border-[var(--gold)]/20" : ""}>
          <div className="p-5">
            <CardHeader icon={<Brain className="w-4 h-4" />} title="Prediction" />
            {predictMut.isError && (
              <p className="text-sm text-red-400 mb-3">
                {(predictMut.error as any)?.response?.data?.detail || "Prediction failed"}
              </p>
            )}
            {pred ? (
              <>
                <div className="flex items-center gap-4 mb-5">
                  <DirectionBadge direction={pred.direction} />
                  <div>
                    <p className="text-2xl font-bold font-mono" style={{ color: "var(--text)" }}>
                      {pred.score?.toFixed(1)}
                      <span className="text-sm font-normal" style={{ color: "var(--text-muted)" }}>/100</span>
                    </p>
                  </div>
                  <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {pred.models_used} model{pred.models_used !== 1 ? "s" : ""}
                  </div>
                </div>
                <div className="space-y-3">
                  {[
                    { label: "BUY",     pct: pred.buy_pct,     dir: "bullish" },
                    { label: "SELL",    pct: pred.sell_pct,    dir: "bearish" },
                    { label: "NEUTRAL", pct: pred.neutral_pct, dir: "neutral" },
                  ].map(b => (
                    <div key={b.label}>
                      <div className="flex justify-between text-xs mb-1">
                        <span style={{ color: "var(--text-muted)" }}>{b.label}</span>
                        <span className="font-mono" style={{ color: "var(--text)" }}>
                          {b.pct?.toFixed(1)}%
                        </span>
                      </div>
                      <ScoreBar score={b.pct ?? 0} direction={b.dir} />
                    </div>
                  ))}
                </div>
                {pred.note && (
                  <p className="mt-3 text-xs" style={{ color: "var(--gold)" }}>{pred.note}</p>
                )}
              </>
            ) : (
              <EmptyState
                icon={<Brain className="w-8 h-8" />}
                title="No prediction yet"
                description="Select a range and click Run Prediction"
              />
            )}
          </div>
        </Card>

        {/* Train result */}
        <Card>
          <div className="p-5">
            <CardHeader icon={<RefreshCw className="w-4 h-4" />} title="Training Result" />
            {trainMut.isError && (
              <p className="text-sm text-red-400 mb-3">
                {(trainMut.error as any)?.response?.data?.detail || "Training failed"}
              </p>
            )}
            {trainMut.data ? (
              trainMut.data.error ? (
                <p className="text-sm" style={{ color: "var(--red)" }}>{trainMut.data.error}</p>
              ) : (
                <div className="space-y-3">
                  <div className="flex gap-6">
                    <div>
                      <p className="text-[11px] mb-0.5" style={{ color: "var(--text-muted)" }}>Version</p>
                      <p className="text-sm font-mono" style={{ color: "var(--gold)" }}>{trainMut.data.version}</p>
                    </div>
                    <div>
                      <p className="text-[11px] mb-0.5" style={{ color: "var(--text-muted)" }}>Samples</p>
                      <p className="text-sm font-mono" style={{ color: "var(--text)" }}>
                        {trainMut.data.sample_count?.toLocaleString()}
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] mb-0.5" style={{ color: "var(--text-muted)" }}>Range</p>
                      <p className="text-sm font-mono text-blue-400">
                        {activeRange.label}
                      </p>
                    </div>
                  </div>
                  <div>
                    <p className="text-[11px] mb-1" style={{ color: "var(--text-muted)" }}>Models trained</p>
                    <p className="text-sm" style={{ color: "var(--text)" }}>
                      {trainMut.data.trained_models?.join(", ") || "None"}
                    </p>
                  </div>
                  {trainMut.data.metrics &&
                    Object.entries(trainMut.data.metrics).map(([model, m]: any) => (
                      <div
                        key={model}
                        className="flex justify-between items-center py-1 border-t"
                        style={{ borderColor: "var(--surface-2)" }}
                      >
                        <span className="text-xs" style={{ color: "var(--text-muted)" }}>{model}</span>
                        <span className="text-xs font-mono text-green-400">
                          {(m.accuracy * 100).toFixed(1)}% accuracy
                        </span>
                      </div>
                    ))}
                </div>
              )
            ) : (
              <EmptyState
                icon={<RefreshCw className="w-8 h-8" />}
                title="Not trained yet"
                description={
                  <>
                    Select a training range and click Train Models
                    <br />
                    <code className="text-[var(--gold)]">scikit-learn RandomForest</code>
                  </>
                }
              />
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
