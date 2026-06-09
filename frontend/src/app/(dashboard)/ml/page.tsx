"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { mlApi, api } from "@/lib/api";
import { Card, CardHeader, PageHeader, DirectionBadge, ScoreBar, EmptyState } from "@/components/ui";
import { Brain, Play, RefreshCw, Clock, Database, CheckCircle, AlertCircle } from "lucide-react";

// Timeframe → backend range mapping (matches backend RANGE_CONFIG exactly)
const TIMEFRAMES = [
  { tf: "1",    label: "M1",  range: "4h",  candles: 240,  desc: "Oxirgi 4 soat · 1-daqiqalik" },
  { tf: "5",    label: "M5",  range: "1d",  candles: 288,  desc: "Oxirgi kun · 5-daqiqalik"    },
  { tf: "15",   label: "M15", range: "1w",  candles: 672,  desc: "Oxirgi hafta · 15-daqiqalik" },
  { tf: "60",   label: "H1",  range: "1m",  candles: 720,  desc: "Oxirgi oy · Soatlik"         },
  { tf: "240",  label: "H4",  range: "3m",  candles: 540,  desc: "Oxirgi 3 oy · 4-soatlik"     },
  { tf: "1440", label: "D1",  range: null,  candles: 365,  desc: "1 yil · Kunlik"               },
] as const;

const SYMBOLS = [
  { value: "XAUUSD", label: "XAUUSD" },
  { value: "EURUSD", label: "EURUSD" },
  { value: "BTCUSD", label: "BTCUSD" },
];

type TfLabel = typeof TIMEFRAMES[number]["label"];

function TfBadge({ label, active, onClick }: { label: TfLabel; active: boolean; onClick: () => void }) {
  const isShort = ["M1", "M5", "M15"].includes(label);
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
        active
          ? isShort
            ? "bg-blue-500 text-white shadow-md shadow-blue-500/25"
            : "bg-yellow-500 text-black shadow-md shadow-yellow-500/25"
          : "bg-[#1a1a24] text-gray-400 hover:text-gray-200 hover:bg-[#22223a]"
      }`}
    >
      {label}
    </button>
  );
}

function StatChip({ label, value, color = "var(--text)" }: { label: string; value: string; color?: string }) {
  return (
    <div className="text-center">
      <p className="text-[10px] mb-0.5" style={{ color: "var(--text-faint)" }}>{label}</p>
      <p className="text-xs font-mono font-semibold" style={{ color }}>{value}</p>
    </div>
  );
}

export default function MLPage() {
  const [symbol, setSymbol]   = useState("XAUUSD");
  const [tfLabel, setTfLabel] = useState<TfLabel>("H1");

  const active = TIMEFRAMES.find(t => t.label === tfLabel) ?? TIMEFRAMES[3];
  const isShortTf = ["M1", "M5", "M15"].includes(active.label);

  // Available trained models (to show whether a model exists for this TF)
  const { data: models } = useQuery({
    queryKey: ["ml-models"],
    queryFn: () => api.get("/ml/models").then(r => r.data as Array<{ symbol: string; timeframe: string | null; accuracy: number | null; samples: number | null; trained_at: string | null; file_exists: boolean }>),
    refetchOnWindowFocus: false,
  });

  const existingModel = models?.find(
    m => m.symbol === symbol && m.timeframe === active.tf && m.file_exists,
  );

  const predictMut = useMutation({
    mutationFn: () =>
      mlApi.predict(symbol, active.tf, active.range ?? undefined).then(r => r.data),
  });

  const trainMut = useMutation({
    mutationFn: () =>
      mlApi.train(symbol, active.tf, active.range ?? undefined).then(r => r.data),
  });

  const pred = predictMut.data;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-5">
      <PageHeader
        title="Machine Learning"
        subtitle="RandomForest ensemble — real Twelvedata historical candles"
      />

      {/* ── Controls ── */}
      <Card>
        <div className="p-5 space-y-4">
          <CardHeader icon={<Brain className="w-4 h-4" />} title="Model Controls" />

          <div className="flex flex-wrap gap-5 items-end">
            {/* Symbol */}
            <div>
              <label className="block text-xs mb-1.5" style={{ color: "var(--text-muted)" }}>Symbol</label>
              <div className="flex gap-1">
                {SYMBOLS.map(s => (
                  <button
                    key={s.value}
                    onClick={() => setSymbol(s.value)}
                    className={`px-2.5 py-1.5 text-xs rounded-lg font-medium transition-colors ${
                      symbol === s.value
                        ? "bg-yellow-500 text-black"
                        : "bg-[#1a1a24] text-gray-400 hover:text-gray-200"
                    }`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Timeframe groups */}
            <div>
              <label className="block text-xs mb-1.5" style={{ color: "var(--text-muted)" }}>
                Timeframe
              </label>
              <div className="flex gap-1 flex-wrap">
                {/* Short-term group */}
                <div className="flex gap-1 pr-2 border-r" style={{ borderColor: "var(--surface-2)" }}>
                  <span className="self-center text-[9px] text-blue-400 font-semibold mr-1 uppercase tracking-wider">Qisqa</span>
                  {TIMEFRAMES.filter(t => ["M1","M5","M15"].includes(t.label)).map(t => (
                    <TfBadge key={t.tf} label={t.label} active={tfLabel === t.label} onClick={() => setTfLabel(t.label)} />
                  ))}
                </div>
                {/* Long-term group */}
                <div className="flex gap-1 pl-1">
                  <span className="self-center text-[9px] text-yellow-400 font-semibold mr-1 uppercase tracking-wider">Uzun</span>
                  {TIMEFRAMES.filter(t => ["H1","H4","D1"].includes(t.label)).map(t => (
                    <TfBadge key={t.tf} label={t.label} active={tfLabel === t.label} onClick={() => setTfLabel(t.label)} />
                  ))}
                </div>
              </div>
            </div>

            {/* Action buttons */}
            <div className="flex gap-2 ml-auto">
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
          </div>

          {/* Active config info bar */}
          <div
            className="flex flex-wrap items-center gap-4 rounded-lg px-4 py-2.5"
            style={{ background: "var(--surface-2)" }}
          >
            <div className="flex items-center gap-1.5">
              <Clock className="w-3 h-3" style={{ color: isShortTf ? "#60a5fa" : "var(--gold)" }} />
              <span className="text-xs font-semibold" style={{ color: isShortTf ? "#60a5fa" : "var(--gold)" }}>
                {active.label}
              </span>
            </div>
            <StatChip label="Vaqt oralig'i" value={active.tf + " daqiqa"} />
            <StatChip label="Candle soni" value={active.candles.toString()} />
            <StatChip label="Masofa" value={active.desc.split(" · ")[0]} />
            <StatChip
              label="Model holati"
              value={existingModel ? `${((existingModel.accuracy ?? 0) * 100).toFixed(1)}% acc ✓` : "Mavjud emas"}
              color={existingModel ? "#22c55e" : "#6b7280"}
            />
            {isShortTf && (
              <span className="ml-auto text-[10px] rounded-full px-2 py-0.5 font-medium bg-blue-500/15 text-blue-400">
                Skalping / qisqa muddatli
              </span>
            )}
          </div>

          {/* Short-TF notice */}
          {isShortTf && (
            <div
              className="flex items-start gap-2 rounded-lg px-3 py-2 text-xs"
              style={{ background: "rgba(59,130,246,0.08)", border: "1px solid rgba(59,130,246,0.2)", color: "#93c5fd" }}
            >
              <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              <span>
                <strong>{active.label}</strong> — Twelvedata free planida {active.label === "M1" ? "1-daqiqalik" : active.label === "M5" ? "5-daqiqalik" : "15-daqiqalik"} ma&apos;lumotlar cheklangan bo&apos;lishi mumkin.
                Yetarli candle bo&apos;lmasa training xato berishi mumkin.
              </span>
            </div>
          )}
        </div>
      </Card>

      {/* ── Results ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* Prediction result */}
        <Card className={pred ? "border-[var(--gold)]/20" : ""}>
          <div className="p-5">
            <div className="flex items-center justify-between mb-4">
              <CardHeader icon={<Play className="w-4 h-4" />} title="Prediction" />
              <span
                className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
                style={{
                  background: isShortTf ? "rgba(59,130,246,0.15)" : "rgba(212,175,55,0.12)",
                  color: isShortTf ? "#60a5fa" : "var(--gold)",
                }}
              >
                {active.label} · {symbol}
              </span>
            </div>

            {predictMut.isError && (
              <div className="flex items-start gap-2 rounded-lg px-3 py-2 mb-3 text-xs bg-red-500/10 text-red-400">
                <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                {(predictMut.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Prediction xatosi"}
              </div>
            )}

            {pred ? (
              <>
                <div className="flex items-center gap-4 mb-5">
                  <DirectionBadge direction={pred.direction} />
                  <div>
                    <p className="text-2xl font-bold font-mono" style={{ color: "var(--text)" }}>
                      {pred.score?.toFixed(1)}
                      <span className="text-sm font-normal ml-1" style={{ color: "var(--text-muted)" }}>/100</span>
                    </p>
                  </div>
                  <div className="flex items-center gap-1 text-xs" style={{ color: "var(--text-muted)" }}>
                    <Database className="w-3 h-3" />
                    {pred.models_used} model
                  </div>
                </div>

                <div className="space-y-3">
                  {[
                    { label: "BUY",     pct: pred.buy_pct,     dir: "bullish" as const, color: "#22c55e" },
                    { label: "SELL",    pct: pred.sell_pct,    dir: "bearish" as const, color: "#ef4444" },
                    { label: "NEUTRAL", pct: pred.neutral_pct, dir: "neutral" as const, color: "#6b7280" },
                  ].map(b => (
                    <div key={b.label}>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="font-medium" style={{ color: b.color }}>{b.label}</span>
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

                <p className="mt-3 text-[10px]" style={{ color: "var(--text-faint)" }}>
                  Timeframe: {active.label} · {active.desc}
                </p>
              </>
            ) : (
              <EmptyState
                icon={<Play className="w-8 h-8" />}
                title="Prediction yo'q"
                description={`${active.label} timeframe tanlang va Run Prediction bosing`}
              />
            )}
          </div>
        </Card>

        {/* Training result */}
        <Card>
          <div className="p-5">
            <div className="flex items-center justify-between mb-4">
              <CardHeader icon={<Brain className="w-4 h-4" />} title="Training Natijasi" />
              {existingModel && (
                <div className="flex items-center gap-1 text-xs text-green-400">
                  <CheckCircle className="w-3 h-3" />
                  Model mavjud
                </div>
              )}
            </div>

            {trainMut.isError && (
              <div className="flex items-start gap-2 rounded-lg px-3 py-2 mb-3 text-xs bg-red-500/10 text-red-400">
                <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                {(trainMut.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Training xatosi"}
              </div>
            )}

            {trainMut.data ? (
              trainMut.data.error ? (
                <p className="text-sm text-red-400">{trainMut.data.error}</p>
              ) : (
                <div className="space-y-3">
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      { label: "Versiya",   value: trainMut.data.version,                    color: "var(--gold)"  },
                      { label: "Namunalar", value: trainMut.data.sample_count?.toLocaleString(), color: "var(--text)"  },
                      { label: "Timeframe", value: active.label,                              color: isShortTf ? "#60a5fa" : "#facc15" },
                    ].map(({ label, value, color }) => (
                      <div key={label} className="rounded-lg p-2.5 text-center" style={{ background: "var(--surface-2)" }}>
                        <p className="text-[10px] mb-0.5" style={{ color: "var(--text-faint)" }}>{label}</p>
                        <p className="text-xs font-mono font-semibold" style={{ color }}>{value ?? "—"}</p>
                      </div>
                    ))}
                  </div>

                  <div>
                    <p className="text-[11px] mb-1" style={{ color: "var(--text-muted)" }}>O'qitilgan modellar</p>
                    <p className="text-sm" style={{ color: "var(--text)" }}>
                      {trainMut.data.trained_models?.join(", ") || "Yo'q"}
                    </p>
                  </div>

                  {trainMut.data.metrics &&
                    Object.entries(trainMut.data.metrics).map(([model, m]) => (
                      <div
                        key={model}
                        className="flex justify-between items-center py-1.5 border-t"
                        style={{ borderColor: "var(--surface-2)" }}
                      >
                        <span className="text-xs font-medium capitalize" style={{ color: "var(--text-muted)" }}>
                          {model}
                        </span>
                        <span className="text-xs font-mono text-green-400">
                          {((m as { accuracy: number }).accuracy * 100).toFixed(1)}% accuracy
                        </span>
                      </div>
                    ))}
                </div>
              )
            ) : (
              <EmptyState
                icon={<Brain className="w-8 h-8" />}
                title="Hali o'qitilmagan"
                description={
                  <>
                    <strong style={{ color: isShortTf ? "#60a5fa" : "var(--gold)" }}>{active.label}</strong> ni tanlang va Train bosing
                    <br />
                    <span className="text-[11px]">{active.desc}</span>
                  </>
                }
              />
            )}
          </div>
        </Card>
      </div>

      {/* ── All models table ── */}
      {models && models.length > 0 && (
        <Card>
          <div className="p-4 pb-0">
            <CardHeader icon={<Database className="w-4 h-4" />} title="Barcha Modellar" />
          </div>
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Timeframe</th>
                  <th className="text-right">Accuracy</th>
                  <th className="text-right">Namunalar</th>
                  <th>O'qitilgan</th>
                  <th>Holat</th>
                </tr>
              </thead>
              <tbody>
                {models.map((m, i) => {
                  const tfEntry = TIMEFRAMES.find(t => t.tf === m.timeframe);
                  const isShort = ["1","5","15"].includes(m.timeframe ?? "");
                  return (
                    <tr key={i} className="hover:bg-[var(--surface-2)]">
                      <td className="font-mono text-xs font-semibold" style={{ color: "var(--gold)" }}>
                        {m.symbol}
                      </td>
                      <td>
                        {tfEntry ? (
                          <span
                            className="inline-block px-2 py-0.5 rounded text-[11px] font-bold"
                            style={{
                              background: isShort ? "rgba(59,130,246,0.15)" : "rgba(212,175,55,0.12)",
                              color: isShort ? "#60a5fa" : "var(--gold)",
                            }}
                          >
                            {tfEntry.label}
                          </span>
                        ) : (
                          <span className="text-xs text-gray-500">{m.timeframe ?? "?"}</span>
                        )}
                      </td>
                      <td className="text-right font-mono text-xs">
                        {m.accuracy != null ? (
                          <span className={m.accuracy >= 0.55 ? "text-green-400" : "text-yellow-400"}>
                            {(m.accuracy * 100).toFixed(1)}%
                          </span>
                        ) : "—"}
                      </td>
                      <td className="text-right text-xs" style={{ color: "var(--text-muted)" }}>
                        {m.samples?.toLocaleString() ?? "—"}
                      </td>
                      <td className="text-xs" style={{ color: "var(--text-faint)" }}>
                        {m.trained_at ? new Date(m.trained_at).toLocaleString() : "—"}
                      </td>
                      <td>
                        {m.file_exists ? (
                          <span className="flex items-center gap-1 text-[11px] text-green-400">
                            <CheckCircle className="w-3 h-3" /> Faol
                          </span>
                        ) : (
                          <span className="text-[11px] text-gray-500">Fayl yo'q</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
