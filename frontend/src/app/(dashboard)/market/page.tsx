"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { marketApi } from "@/lib/api";
import { TradingViewChart } from "@/components/charts/TradingViewChart";

const SYMBOL = "XAUUSD";
const TIMEFRAMES = [
  { value: "5", label: "M5" },
  { value: "15", label: "M15" },
  { value: "60", label: "H1" },
  { value: "240", label: "H4" },
  { value: "1440", label: "D1" },
];

function fmtPrice(v: number) {
  return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function MarketPage() {
  const [timeframe, setTimeframe] = useState("60");
  const [livePrice, setLivePrice] = useState<number | null>(null);
  const [prevPrice, setPrevPrice] = useState<number | null>(null);
  const [sseOk, setSseOk] = useState(false);
  const [priceSource, setPriceSource] = useState<"sse" | "poll" | "td">("poll");
  const esRef = useRef<EventSource | null>(null);

  // SSE live price from backend
  useEffect(() => {
    const connect = () => {
      const es = new EventSource(`/api/v1/market-data/stream?symbol=${SYMBOL}`);
      esRef.current = es;
      es.onopen = () => { setSseOk(true); setPriceSource("sse"); };
      es.onmessage = (e) => {
        try {
          const tick = JSON.parse(e.data);
          if (tick?.price) {
            const src = tick.source === "twelvedata" ? "td" : "sse";
            setPriceSource(src);
            setLivePrice(prev => { setPrevPrice(prev); return tick.price; });
          }
        } catch {}
      };
      es.onerror = () => {
        setSseOk(false);
        es.close();
        setTimeout(connect, 8_000);
      };
    };
    connect();
    return () => { esRef.current?.close(); };
  }, []);

  // Fallback polling when SSE is down
  const { data: pollTick } = useQuery({
    queryKey: ["price", SYMBOL],
    queryFn: () => marketApi.getPrice(SYMBOL).then(r => r.data),
    refetchInterval: sseOk ? false : 8_000,
    enabled: !sseOk,
  });

  useEffect(() => {
    if (!sseOk && pollTick?.price) {
      setPriceSource(pollTick.source === "twelvedata" ? "td" : "poll");
      setLivePrice(prev => { setPrevPrice(prev); return pollTick.price; });
    }
  }, [pollTick, sseOk]);

  // Tick history table
  const { data: ticks } = useQuery({
    queryKey: ["ticks", SYMBOL],
    queryFn: () => marketApi.getTicks(SYMBOL, 20).then(r => r.data),
    refetchInterval: 60_000,
  });

  const priceColor =
    livePrice && prevPrice
      ? livePrice > prevPrice
        ? "text-green-400"
        : livePrice < prevPrice
        ? "text-red-400"
        : "text-yellow-400"
      : "text-yellow-400";

  const sourceLabel =
    priceSource === "td"
      ? { text: "● Twelvedata live", cls: "text-green-400" }
      : priceSource === "sse"
      ? { text: "● SSE stream", cls: "text-blue-400" }
      : { text: "● Polling (8s)", cls: "text-yellow-600" };

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-yellow-400">Live Market</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            <span className={sourceLabel.cls}>{sourceLabel.text}</span>
            {" "}&mdash; XAUUSD
          </p>
        </div>
        <div className="flex gap-2">
          {TIMEFRAMES.map(tf => (
            <button
              key={tf.value}
              onClick={() => setTimeframe(tf.value)}
              className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors ${
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

      {/* Live Price Hero */}
      <div className="bg-[#111118] border border-[#2a2a3a] rounded-xl p-6 flex items-end gap-6">
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-widest mb-1">XAUUSD</p>
          <p className={`text-6xl font-bold font-mono transition-colors duration-300 ${priceColor}`}>
            {livePrice ? fmtPrice(livePrice) : "—"}
          </p>
          {livePrice && prevPrice && livePrice !== prevPrice && (
            <p className={`text-sm font-mono mt-1 ${priceColor}`}>
              {livePrice > prevPrice ? "▲" : "▼"}{" "}
              {Math.abs(livePrice - prevPrice).toFixed(2)}
            </p>
          )}
        </div>
        {ticks?.[0] && (
          <div className="ml-auto text-right text-sm space-y-1">
            <div className="flex gap-6 text-xs text-gray-500">
              <span>
                Bid <span className="text-red-400 font-mono font-bold">{fmtPrice(ticks[0].bid)}</span>
              </span>
              <span>
                Ask <span className="text-green-400 font-mono font-bold">{fmtPrice(ticks[0].ask)}</span>
              </span>
            </div>
            <p className="text-xs text-gray-600">
              Spread {((ticks[0].ask - ticks[0].bid) * 10).toFixed(1)} pips
            </p>
          </div>
        )}
      </div>

      {/* TradingView Chart — realtime */}
      <div className="bg-[#111118] border border-[#2a2a3a] rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-[#2a2a3a] flex items-center justify-between">
          <p className="text-sm font-semibold text-gray-200">
            XAUUSD — {TIMEFRAMES.find(t => t.value === timeframe)?.label}
          </p>
          <span className="text-xs px-2 py-0.5 rounded bg-green-500/10 text-green-400 font-medium">
            ● Real-time via TradingView
          </span>
        </div>
        <TradingViewChart symbol={SYMBOL} timeframe={timeframe} height={480} showIndicators={false} />
      </div>

      {/* Price History */}
      <div className="bg-[#111118] border border-[#2a2a3a] rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-[#2a2a3a]">
          <p className="text-sm font-semibold text-gray-200">Recent H1 Closes</p>
        </div>
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="border-b border-[#1a1a24] text-gray-500">
              <th className="text-left p-3">Time (UTC)</th>
              <th className="text-right p-3">Price</th>
              <th className="text-right p-3">Bid</th>
              <th className="text-right p-3">Ask</th>
              <th className="text-right p-3">Volume</th>
            </tr>
          </thead>
          <tbody>
            {ticks?.map((t: any, i: number) => {
              const prevT = ticks[i + 1];
              const up = !prevT || t.price >= prevT.price;
              return (
                <tr key={t.time} className="border-b border-[#1a1a24] hover:bg-[#1a1a24]">
                  <td className="p-3 text-gray-500">{new Date(t.time).toLocaleString()}</td>
                  <td className={`p-3 text-right font-bold ${up ? "text-green-400" : "text-red-400"}`}>
                    {fmtPrice(t.price)}
                  </td>
                  <td className="p-3 text-right text-gray-400">{fmtPrice(t.bid)}</td>
                  <td className="p-3 text-right text-gray-400">{fmtPrice(t.ask)}</td>
                  <td className="p-3 text-right text-gray-600">{t.volume?.toFixed(0) ?? "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!ticks?.length && (
          <p className="text-center text-gray-600 text-sm py-8">No data</p>
        )}
      </div>
    </div>
  );
}
