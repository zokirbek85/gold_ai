"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { smcApi, aiApi, indicatorApi } from "@/lib/api";
import { directionColor, formatPrice } from "@/lib/utils";

const SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD"];
const TIMEFRAMES = [
  { value: "15",   label: "M15" },
  { value: "60",   label: "H1" },
  { value: "240",  label: "H4" },
  { value: "1440", label: "D1" },
];
const RANGES = [
  { value: "1h",  label: "1H",  desc: "Last hour (M1 candles)" },
  { value: "4h",  label: "4H",  desc: "Last 4 hours (M5)" },
  { value: "1d",  label: "1D",  desc: "Last day (M15)" },
  { value: "1w",  label: "1W",  desc: "Last week (H1)" },
  { value: "1m",  label: "1M",  desc: "Last month (H4)" },
  { value: "3m",  label: "3M",  desc: "Last 3 months (D1)" },
];

export default function AnalysisPage() {
  const [symbol, setSymbol] = useState("XAUUSD");
  const [timeframe, setTimeframe] = useState("60");
  const [range, setRange] = useState("1w");

  const queryOpts = { symbol, timeframe, range };

  const { data: smcAnalysis, isLoading: smcLoading, isError: smcIsError, error: smcError } = useQuery({
    queryKey: ["smc-analyze", symbol, timeframe, range],
    queryFn: () => smcApi.analyze(symbol, timeframe, range).then(r => r.data),
    staleTime: 30_000,
  });

  const { data: snapshot, isLoading: indLoading, isError: indIsError, error: indError } = useQuery({
    queryKey: ["snapshot", symbol, timeframe, range],
    queryFn: () => indicatorApi.getSnapshot(symbol, timeframe, range).then(r => r.data),
    staleTime: 30_000,
  });

  const biasMut = useMutation({
    mutationFn: () =>
      aiApi.dailyBias("", "", "", snapshot ?? undefined).then(r => r.data),
  });

  const pd = smcAnalysis?.premium_discount;
  const isLoading = smcLoading || indLoading;

  return (
    <div className="p-6 space-y-6">
      {/* Header + Controls */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-yellow-400">Market Analysis</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            SMC Structure · Indicators · AI Bias
            <span className="ml-2 text-green-400 text-[11px]">● Twelvedata real data</span>
          </p>
        </div>
        <div className="flex gap-2 flex-wrap items-center">
          <select
            value={symbol}
            onChange={e => setSymbol(e.target.value)}
            className="bg-[#1a1a24] border border-[#2a2a3a] text-gray-200 text-sm rounded-lg px-3 py-2"
          >
            {SYMBOLS.map(s => <option key={s}>{s}</option>)}
          </select>
          <select
            value={timeframe}
            onChange={e => setTimeframe(e.target.value)}
            className="bg-[#1a1a24] border border-[#2a2a3a] text-gray-200 text-sm rounded-lg px-3 py-2"
          >
            {TIMEFRAMES.map(tf => <option key={tf.value} value={tf.value}>{tf.label}</option>)}
          </select>
        </div>
      </div>

      {/* Range selector */}
      <div className="bg-[#111118] border border-[#2a2a3a] rounded-xl p-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-gray-500 mr-1">Data range:</span>
          {RANGES.map(r => (
            <button
              key={r.value}
              onClick={() => setRange(r.value)}
              title={r.desc}
              className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors ${
                range === r.value
                  ? "bg-yellow-500 text-black"
                  : "bg-[#1a1a24] text-gray-400 hover:text-gray-200"
              }`}
            >
              {r.label}
            </button>
          ))}
          {isLoading && (
            <span className="text-xs text-yellow-500 animate-pulse ml-2">Fetching from Twelvedata…</span>
          )}
        </div>
        <p className="text-[11px] text-gray-600 mt-2">
          {RANGES.find(r => r.value === range)?.desc} — fresh candles fetched on each range change
        </p>
      </div>

      {(smcIsError || indIsError) && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-sm text-red-300">
          {(smcError as any)?.response?.data?.detail ||
            (indError as any)?.response?.data?.detail ||
            "Fresh historical data unavailable. Check TWELVEDATA_API_KEY or try a longer range."}
        </div>
      )}

      {/* Premium/Discount */}
      {pd && (
        <div className="bg-[#111118] border border-[#2a2a3a] rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-200 mb-4">Premium / Discount Zone</h2>
          <div className="flex gap-6 flex-wrap">
            <div>
              <p className="text-xs text-gray-500">Zone</p>
              <p className={`text-xl font-bold ${pd.zone === "discount" ? "text-green-400" : "text-red-400"}`}>
                {pd.zone?.toUpperCase()}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Position</p>
              <p className="text-xl font-bold font-mono text-white">{pd.pct_of_range?.toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Equilibrium</p>
              <p className="text-xl font-bold font-mono text-yellow-400">{formatPrice(pd.equilibrium)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Swing High</p>
              <p className="text-xl font-bold font-mono text-green-400">{formatPrice(pd.swing_high)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Swing Low</p>
              <p className="text-xl font-bold font-mono text-red-400">{formatPrice(pd.swing_low)}</p>
            </div>
          </div>
          <div className="mt-4 w-full bg-[#1a1a24] rounded-full h-3 relative">
            <div className="h-3 rounded-full bg-gradient-to-r from-red-700 via-gray-600 to-green-700 w-full" />
            <div
              className="absolute top-0 h-3 w-1 bg-yellow-400 rounded"
              style={{ left: `${Math.min(Math.max(pd.pct_of_range ?? 50, 0), 100)}%` }}
            />
          </div>
          <div className="flex justify-between text-[10px] text-gray-500 mt-1">
            <span>Bearish Premium</span><span>Equilibrium</span><span>Bullish Discount</span>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Market Structure */}
        <div className="bg-[#111118] border border-[#2a2a3a] rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-200 mb-4">Market Structure</h2>
          {smcAnalysis?.market_structure?.length ? (
            <div className="space-y-2">
              {smcAnalysis.market_structure.map((e: any, i: number) => (
                <div key={i} className="flex items-center justify-between py-2 border-b border-[#1a1a24] last:border-0">
                  <div>
                    <span className="text-xs font-bold px-2 py-0.5 rounded bg-yellow-900/20 text-yellow-400 border border-yellow-800/30">
                      {e.type}
                    </span>
                    <p className="text-xs text-gray-500 mt-1">{e.description}</p>
                  </div>
                  <span className={`text-sm font-bold ${directionColor(e.direction)}`}>
                    {e.direction?.toUpperCase()}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-600 text-center py-6">
              {smcLoading ? "Fetching real data…" : "No structure events detected"}
            </p>
          )}
        </div>

        {/* Order Blocks */}
        <div className="bg-[#111118] border border-[#2a2a3a] rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-200 mb-4">Order Blocks</h2>
          {smcAnalysis?.order_blocks?.length ? (
            <div className="space-y-2">
              {smcAnalysis.order_blocks.map((ob: any, i: number) => (
                <div key={i} className="flex items-center justify-between py-2 border-b border-[#1a1a24] last:border-0">
                  <div>
                    <p className="text-xs text-gray-300">{ob.type}</p>
                    <p className="text-xs text-gray-500 font-mono">
                      {formatPrice(ob.ob_low)} — {formatPrice(ob.ob_high)}
                    </p>
                  </div>
                  <span className={`text-sm font-bold ${directionColor(ob.direction)}`}>
                    {ob.direction?.toUpperCase()}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-600 text-center py-6">
              {smcLoading ? "Fetching real data…" : "No order blocks detected"}
            </p>
          )}
        </div>
      </div>

      {/* Indicators from real data */}
      {snapshot && Object.keys(snapshot).length > 0 && (
        <div className="bg-[#111118] border border-[#2a2a3a] rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-200 mb-4">Technical Indicators</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {Object.entries(snapshot).map(([k, v]) => {
              const val = typeof v === "number" ? v : null;
              let color = "text-gray-300";
              if (k === "rsi" && val != null)
                color = val > 70 ? "text-red-400" : val < 30 ? "text-green-400" : "text-gray-300";
              if (k === "macd" && val != null)
                color = val > 0 ? "text-green-400" : "text-red-400";
              return (
                <div key={k} className="bg-[#0d0d14] border border-[#2a2a3a] rounded-xl p-3 text-center">
                  <p className="text-[10px] text-gray-500 uppercase mb-1">{k.replace(/_/g, " ")}</p>
                  <p className={`text-sm font-mono font-bold ${color}`}>
                    {val != null ? val.toFixed(4) : "—"}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* AI Daily Bias */}
      <div className="bg-[#111118] border border-[#2a2a3a] rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-gray-200">AI Daily Bias</h2>
          <button
            onClick={() => biasMut.mutate()}
            disabled={biasMut.isPending}
            className="px-3 py-1.5 bg-yellow-500/20 hover:bg-yellow-500/30 text-yellow-400 border border-yellow-500/30 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
          >
            {biasMut.isPending ? "Analyzing…" : "Generate Bias"}
          </button>
        </div>
        {biasMut.data ? (
          <div className="space-y-4">
            {/* Bias summary */}
            <div className="flex items-center gap-4 flex-wrap">
              <span className={`text-2xl font-black px-4 py-1.5 rounded-lg ${
                biasMut.data.direction === "bullish"
                  ? "bg-green-500/15 text-green-400 border border-green-500/30"
                  : biasMut.data.direction === "bearish"
                  ? "bg-red-500/15 text-red-400 border border-red-500/30"
                  : "bg-gray-500/10 text-gray-400 border border-gray-500/20"
              }`}>
                {biasMut.data.bias}
              </span>
              <div>
                <p className="text-xs text-gray-500">Ishonch</p>
                <p className={`text-xl font-bold font-mono ${
                  biasMut.data.confidence >= 70 ? "text-green-400" :
                  biasMut.data.confidence >= 55 ? "text-yellow-400" : "text-gray-400"
                }`}>{biasMut.data.confidence}%</p>
              </div>
              {biasMut.data.bull_score !== undefined && (
                <>
                  <div>
                    <p className="text-xs text-gray-500">Bull omillar</p>
                    <p className="text-lg font-bold text-green-400">{biasMut.data.bull_score}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Bear omillar</p>
                    <p className="text-lg font-bold text-red-400">{biasMut.data.bear_score}</p>
                  </div>
                </>
              )}
            </div>
            {/* Reasoning */}
            <div className="bg-[#0d0d14] rounded-lg p-4 text-sm text-gray-300 leading-relaxed whitespace-pre-wrap font-mono">
              {biasMut.data.reasoning}
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-600 text-center py-8">
            "Generate Bias" tugmasini bosing — real {range} ma'lumotlari asosida bozor tahlili
          </p>
        )}
      </div>
    </div>
  );
}
