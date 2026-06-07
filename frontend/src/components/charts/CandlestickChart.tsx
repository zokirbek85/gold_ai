"use client";

import { useEffect, useRef } from "react";

interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface Props {
  candles: Candle[];
  height?: number;
  livePrice?: number;
}

export function CandlestickChart({ candles, height = 420, livePrice }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);
  const candleSeriesRef = useRef<any>(null);
  const volumeSeriesRef = useRef<any>(null);

  // Initialize chart once
  useEffect(() => {
    if (!containerRef.current || typeof window === "undefined") return;

    let chart: any;
    let cancelled = false;

    import("lightweight-charts").then(({ createChart, ColorType, CrosshairMode }) => {
      if (cancelled || !containerRef.current) return;

      chart = createChart(containerRef.current, {
        layout: {
          background: { type: ColorType.Solid, color: "#0d0d14" },
          textColor: "#6b7280",
          fontSize: 11,
        },
        grid: {
          vertLines: { color: "#1a1a2e" },
          horzLines: { color: "#1a1a2e" },
        },
        crosshair: { mode: CrosshairMode.Normal },
        rightPriceScale: { borderColor: "#2a2a3a", scaleMargins: { top: 0.1, bottom: 0.25 } },
        timeScale: { borderColor: "#2a2a3a", timeVisible: true, secondsVisible: false },
        width: containerRef.current.clientWidth,
        height,
      });

      const candleSeries = chart.addCandlestickSeries({
        upColor: "#22c55e",
        downColor: "#ef4444",
        borderUpColor: "#22c55e",
        borderDownColor: "#ef4444",
        wickUpColor: "#22c55e",
        wickDownColor: "#ef4444",
      });

      const volumeSeries = chart.addHistogramSeries({
        priceFormat: { type: "volume" },
        priceScaleId: "vol",
      });
      chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

      chartRef.current = chart;
      candleSeriesRef.current = candleSeries;
      volumeSeriesRef.current = volumeSeries;
    });

    const onResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", onResize);

    return () => {
      cancelled = true;
      window.removeEventListener("resize", onResize);
      chartRef.current?.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, [height]);

  // Update candle data when candles prop changes
  useEffect(() => {
    if (!candleSeriesRef.current || !candles?.length) return;

    const sorted = [...candles]
      .map(c => ({
        time: Math.floor(new Date(c.timestamp).getTime() / 1000) as any,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
      .sort((a, b) => a.time - b.time);

    const volumes = [...candles]
      .map(c => ({
        time: Math.floor(new Date(c.timestamp).getTime() / 1000) as any,
        value: c.volume || 0,
        color: c.close >= c.open ? "#22c55e33" : "#ef444433",
      }))
      .sort((a, b) => a.time - b.time);

    candleSeriesRef.current.setData(sorted);
    volumeSeriesRef.current?.setData(volumes);
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  // Update last candle close with live price (tick update)
  useEffect(() => {
    if (!candleSeriesRef.current || !livePrice || !candles?.length) return;
    const last = [...candles].sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    )[0];
    candleSeriesRef.current.update({
      time: Math.floor(new Date(last.timestamp).getTime() / 1000) as any,
      open: last.open,
      high: Math.max(last.high, livePrice),
      low: Math.min(last.low, livePrice),
      close: livePrice,
    });
  }, [livePrice, candles]);

  return <div ref={containerRef} style={{ height }} className="w-full rounded-lg overflow-hidden" />;
}
