"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { marketApi, patternApi, smcApi, indicatorApi } from "@/lib/api";
import { TradingViewChart } from "@/components/charts/TradingViewChart";
import { directionColor } from "@/lib/utils";

const SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD"];
const TIMEFRAMES = [
  { value: "1", label: "M1" },
  { value: "5", label: "M5" },
  { value: "15", label: "M15" },
  { value: "60", label: "H1" },
  { value: "240", label: "H4" },
  { value: "1440", label: "D1" },
];

function fmtPrice(v?: number) {
  if (v == null) return "—";
  return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

export default function ChartsPage() {
  const [symbol, setSymbol] = useState("XAUUSD");
  const [timeframe, setTimeframe] = useState("60");

  const { data: candles } = useQuery({
    queryKey: ["candles", symbol, timeframe],
    queryFn: () => marketApi.getCandles(symbol, timeframe, 300).then(r => r.data),
    refetchInterval: 60_000,
  });

  const { data: snapshot } = useQuery({
    queryKey: ["snapshot", symbol, timeframe],
    queryFn: () => indicatorApi.getSnapshot(symbol, timeframe).then(r => r.data),
    refetchInterval: 60_000,
  });

  const { data: smcScore } = useQuery({
    queryKey: ["smc-score", symbol, timeframe],
    queryFn: () => smcApi.score(symbol, timeframe).then(r => r.data),
    refetchInterval: 120_000,
  });

  const { data: patterns } = useQuery({
    queryKey: ["patterns", symbol, timeframe],
    queryFn: () => patternApi.getAll(symbol, timeframe).then(r => r.data),
    refetchInterval: 120_000,
  });

  const latest = candles?.length ? candles[candles.length - 1] : null;
  const prev = candles?.length > 1 ? candles[candles.length - 2] : null;
  const change = latest && prev ? latest.close - prev.close : 0;
  const changePct = prev ? (change / prev.close) * 100 : 0;

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-yellow-400">Live Charts</h1>
          <p className="text-xs text-gray-500 mt-0.5">TradingView · Real-time · RSI · MACD · Bollinger Bands</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <select
            value={symbol}
            onChange={e => setSymbol(e.target.value)}
            className="bg-[#1a1a24] border border-[#2a2a3a] text-gray-200 text-sm rounded-lg px-3 py-2"
          >
            {SYMBOLS.map(s => <option key={s}>{s}</option>)}
          </select>
          <div className="flex gap-1">
            {TIMEFRAMES.map(tf => (
              <button
                key={tf.value}
                onClick={() => setTimeframe(tf.value)}
                className={`px-3 py-2 text-xs rounded-lg font-medium transition-colors ${
                  timeframe === tf.value
                    ? "bg-yellow-500 text-black"
                    : "bg-[#1a1a24] text-gray-400 hover:text-gray-200"
                }`}
              >
                {tf.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* OHLCV Bar from DB */}
      {latest && (
        <div className="grid grid-cols-6 gap-2">
          {[
            { label: "Open", value: fmtPrice(latest.open), color: "text-gray-200" },
            { label: "High", value: fmtPrice(latest.high), color: "text-green-400" },
            { label: "Low", value: fmtPrice(latest.low), color: "text-red-400" },
            { label: "Close", value: fmtPrice(latest.close), color: "text-yellow-400" },
            { label: "Volume", value: latest.volume?.toFixed(0) ?? "—", color: "text-blue-400" },
            {
              label: "Change",
              value: `${change >= 0 ? "+" : ""}${change.toFixed(2)} (${changePct >= 0 ? "+" : ""}${changePct.toFixed(2)}%)`,
              color: change >= 0 ? "text-green-400" : "text-red-400",
            },
          ].map(f => (
            <div key={f.label} className="bg-[#111118] border border-[#2a2a3a] rounded-xl p-3 text-center">
              <p className="text-xs text-gray-500 mb-1">{f.label}</p>
              <p className={`text-sm font-bold font-mono ${f.color}`}>{f.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* TradingView Chart — primary, realtime */}
      <div className="bg-[#111118] border border-[#2a2a3a] rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-[#2a2a3a] flex items-center justify-between">
          <p className="text-sm font-semibold text-gray-200">
            {symbol} / {TIMEFRAMES.find(t => t.value === timeframe)?.label}
          </p>
          <span className="text-xs px-2 py-0.5 rounded bg-green-500/10 text-green-400 font-medium">
            ● Real-time via TradingView
          </span>
        </div>
        <TradingViewChart
          symbol={symbol}
          timeframe={timeframe}
          height={560}
          showIndicators={true}
        />
      </div>

      {/* Analysis panels */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Indicators from DB */}
        {snapshot && Object.keys(snapshot).length > 0 && (
          <div className="bg-[#111118] border border-[#2a2a3a] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-gray-200 mb-4">DB Indicators</h2>
            <div className="space-y-2">
              {Object.entries(snapshot).map(([k, v]) => {
                const val = typeof v === "number" ? v : null;
                let color = "text-gray-300";
                if (k === "rsi" && val != null)
                  color = val > 70 ? "text-red-400" : val < 30 ? "text-green-400" : "text-gray-300";
                if (k === "macd" && val != null)
                  color = val > 0 ? "text-green-400" : "text-red-400";
                return (
                  <div key={k} className="flex items-center justify-between py-1 border-b border-[#1a1a24] last:border-0">
                    <span className="text-xs text-gray-500 uppercase">{k.replace(/_/g, " ")}</span>
                    <span className={`text-xs font-mono font-bold ${color}`}>
                      {val != null ? val.toFixed(4) : "—"}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* SMC Score */}
        {smcScore && (
          <div className="bg-[#111118] border border-[#2a2a3a] rounded-xl p-5">
            <h2 className="text-sm font-semibold text-gray-200 mb-4">SMC Analysis</h2>
            <div className="flex items-center gap-4 mb-4">
              <div>
                <p className="text-xs text-gray-500">Bias</p>
                <p className={`text-3xl font-bold ${directionColor(smcScore.direction)}`}>
                  {smcScore.direction?.toUpperCase() ?? "—"}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Score</p>
                <p className="text-3xl font-bold font-mono text-white">{smcScore.score?.toFixed(0)}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Events</p>
                <p className="text-3xl font-bold font-mono text-yellow-400">{smcScore.events}</p>
              </div>
            </div>
            <div className="w-full bg-[#1a1a24] rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all duration-500 ${
                  smcScore.direction === "bullish"
                    ? "bg-green-500"
                    : smcScore.direction === "bearish"
                    ? "bg-red-500"
                    : "bg-gray-500"
                }`}
                style={{ width: `${smcScore.score}%` }}
              />
            </div>
          </div>
        )}

        {/* Patterns */}
        <div className="bg-[#111118] border border-[#2a2a3a] rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-200 mb-4">Patterns</h2>
          {patterns?.length ? (
            <div className="space-y-2">
              {patterns.slice(0, 6).map((p: any, i: number) => (
                <div
                  key={i}
                  className="flex items-center justify-between py-1.5 border-b border-[#1a1a24] last:border-0"
                >
                  <div>
                    <p className="text-xs text-gray-200">{p.name}</p>
                    <p className="text-[10px] text-gray-600 mt-0.5">{p.description}</p>
                  </div>
                  <div className="text-right">
                    <p className={`text-xs font-bold ${directionColor(p.direction)}`}>
                      {p.direction?.toUpperCase()}
                    </p>
                    <p className="text-[10px] text-gray-500">{(p.confidence * 100).toFixed(0)}%</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-gray-600 text-center py-8">No patterns detected</p>
          )}
        </div>
      </div>
    </div>
  );
}
