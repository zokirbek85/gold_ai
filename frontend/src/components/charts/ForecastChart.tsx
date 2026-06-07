"use client";

import { useEffect, useRef, memo } from "react";
import {
  createChart,
  ColorType,
  LineStyle,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
  type PriceLineOptions,
} from "lightweight-charts";

export interface ForecastData {
  candles: { time: number; open: number; high: number; low: number; close: number }[];
  volume: { time: number; value: number; color: string }[];
  indicators: {
    ema_20: { time: number; value: number }[];
    ema_50: { time: number; value: number }[];
    ema_200: { time: number; value: number }[];
    bb_upper: { time: number; value: number }[];
    bb_middle: { time: number; value: number }[];
    bb_lower: { time: number; value: number }[];
    rsi: { time: number; value: number }[];
  };
  overlays: {
    order_blocks: { type: string; high: number; low: number; start_time: number; end_time: number }[];
    fvg: { type: string; high: number; low: number; start_time: number; end_time: number }[];
    support_resistance: { level: number; type: string }[];
    fibonacci: { swing_high: number; swing_low: number; trend: string; levels: Record<string, number> };
    signals: { time: number; type: string; price: number; sl?: number; tp?: number; confidence?: number }[];
  };
  latest_signal?: {
    type: string; entry?: number; sl?: number; tp?: number; confidence?: number; rr?: number;
  } | null;
  ml_forecast: {
    direction: string; confidence: number; buy_pct: number; sell_pct: number;
    projection: { time: number; value: number }[];
  };
}

export interface OverlayToggles {
  ema: boolean;
  bb: boolean;
  signals: boolean;
  orderBlocks: boolean;
  fvg: boolean;
  sltp: boolean;
  sr: boolean;
  fibonacci: boolean;
  mlForecast: boolean;
  volume: boolean;
  rsi: boolean;
}

interface Props {
  data: ForecastData;
  overlays: OverlayToggles;
  height?: number;
}

const COLORS = {
  bg:        "#0d0d14",
  grid:      "#1a1a2a",
  text:      "#9ca3af",
  gold:      "#f59e0b",
  ema20:     "#3b82f6",
  ema50:     "#f97316",
  ema200:    "#ef4444",
  bbUpper:   "#60a5fa",
  bbMid:     "#6b7280",
  bbLower:   "#60a5fa",
  bullish:   "#22c55e",
  bearish:   "#ef4444",
  neutral:   "#9ca3af",
  srSupport: "#22c55e",
  srResist:  "#ef4444",
  fib:       "#a78bfa",
  fvgBull:   "#16a34a",
  fvgBear:   "#dc2626",
  sl:        "#ef4444",
  tp:        "#22c55e",
  forecast:  "#f59e0b",
};

function addPriceLine(
  series: ISeriesApi<"Candlestick">,
  price: number,
  color: string,
  title: string,
  style: LineStyle = LineStyle.Dashed,
  width: number = 1,
): void {
  series.createPriceLine({ price, color, lineWidth: width, lineStyle: style, axisLabelVisible: true, title } as PriceLineOptions);
}

export const ForecastChart = memo(function ForecastChart({ data, overlays, height = 520 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rsiRef       = useRef<HTMLDivElement>(null);
  const chartRef     = useRef<IChartApi | null>(null);
  const rsiChartRef  = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || !data?.candles?.length) return;

    // ── Main chart ──
    const chart = createChart(containerRef.current, {
      width:  containerRef.current.clientWidth,
      height,
      layout: { background: { type: ColorType.Solid, color: COLORS.bg }, textColor: COLORS.text },
      grid:   { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: COLORS.grid },
      timeScale: { borderColor: COLORS.grid, timeVisible: true, secondsVisible: false },
    });
    chartRef.current = chart;

    // Candlestick series
    const candleSeries = chart.addCandlestickSeries({
      upColor:          COLORS.bullish,
      downColor:        COLORS.bearish,
      borderUpColor:    COLORS.bullish,
      borderDownColor:  COLORS.bearish,
      wickUpColor:      COLORS.bullish,
      wickDownColor:    COLORS.bearish,
    });
    candleSeries.setData(data.candles as any);

    // Volume
    if (overlays.volume) {
      const volSeries = chart.addHistogramSeries({
        priceFormat:    { type: "volume" },
        priceScaleId:   "vol",
        color:          "rgba(100,100,100,0.3)",
      });
      chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
      volSeries.setData(data.volume as any);
    }

    // EMA lines
    if (overlays.ema) {
      const ema20s = chart.addLineSeries({ color: COLORS.ema20,  lineWidth: 1, title: "EMA20",  priceLineVisible: false, lastValueVisible: false });
      const ema50s = chart.addLineSeries({ color: COLORS.ema50,  lineWidth: 1, title: "EMA50",  priceLineVisible: false, lastValueVisible: false });
      const ema200 = chart.addLineSeries({ color: COLORS.ema200, lineWidth: 1, title: "EMA200", priceLineVisible: false, lastValueVisible: false });
      ema20s.setData(data.indicators.ema_20 as any);
      ema50s.setData(data.indicators.ema_50 as any);
      ema200.setData(data.indicators.ema_200 as any);
    }

    // Bollinger Bands
    if (overlays.bb) {
      const bbUpper = chart.addLineSeries({ color: COLORS.bbUpper, lineWidth: 1, lineStyle: LineStyle.Dashed, title: "BB Upper", priceLineVisible: false, lastValueVisible: false });
      const bbMid   = chart.addLineSeries({ color: COLORS.bbMid,   lineWidth: 1, lineStyle: LineStyle.Dotted, title: "BB Mid",   priceLineVisible: false, lastValueVisible: false });
      const bbLower = chart.addLineSeries({ color: COLORS.bbLower, lineWidth: 1, lineStyle: LineStyle.Dashed, title: "BB Lower", priceLineVisible: false, lastValueVisible: false });
      bbUpper.setData(data.indicators.bb_upper as any);
      bbMid.setData(data.indicators.bb_middle as any);
      bbLower.setData(data.indicators.bb_lower as any);
    }

    // BUY/SELL signal markers
    if (overlays.signals && data.overlays.signals.length > 0) {
      const markers: SeriesMarker<Time>[] = data.overlays.signals
        .filter(s => s.time && s.price)
        .map(s => ({
          time:      s.time as Time,
          position:  s.type === "BUY" ? "belowBar" : "aboveBar",
          color:     s.type === "BUY" ? COLORS.bullish : COLORS.bearish,
          shape:     s.type === "BUY" ? "arrowUp" : "arrowDown",
          text:      `${s.type} ${s.confidence?.toFixed(0) ?? ""}%`,
          size:      2,
        }));
      candleSeries.setMarkers(markers);
    }

    // Order Block zones (top + bottom lines per block)
    if (overlays.orderBlocks) {
      data.overlays.order_blocks.forEach(ob => {
        const color = ob.type === "bullish" ? "rgba(34,197,94,0.7)" : "rgba(239,83,80,0.7)";
        const label = ob.type === "bullish" ? "Bull OB" : "Bear OB";
        const topSeries = chart.addLineSeries({
          color, lineWidth: 1, lineStyle: LineStyle.Solid,
          priceLineVisible: false, lastValueVisible: false, title: label,
        });
        const botSeries = chart.addLineSeries({
          color, lineWidth: 1, lineStyle: LineStyle.Solid,
          priceLineVisible: false, lastValueVisible: false,
        });
        topSeries.setData([
          { time: ob.start_time as Time, value: ob.high },
          { time: ob.end_time   as Time, value: ob.high },
        ]);
        botSeries.setData([
          { time: ob.start_time as Time, value: ob.low },
          { time: ob.end_time   as Time, value: ob.low },
        ]);
      });
    }

    // FVG zones
    if (overlays.fvg) {
      data.overlays.fvg.forEach(fvg => {
        const color = fvg.type === "bullish" ? "rgba(34,197,94,0.5)" : "rgba(239,83,80,0.5)";
        const topS = chart.addLineSeries({ color, lineWidth: 1, lineStyle: LineStyle.Dotted, priceLineVisible: false, lastValueVisible: false });
        const botS = chart.addLineSeries({ color, lineWidth: 1, lineStyle: LineStyle.Dotted, priceLineVisible: false, lastValueVisible: false });
        topS.setData([{ time: fvg.start_time as Time, value: fvg.high }, { time: fvg.end_time as Time, value: fvg.high }]);
        botS.setData([{ time: fvg.start_time as Time, value: fvg.low  }, { time: fvg.end_time as Time, value: fvg.low  }]);
      });
    }

    // Support / Resistance horizontal levels
    if (overlays.sr) {
      data.overlays.support_resistance.forEach(lv => {
        addPriceLine(candleSeries, lv.level,
          lv.type === "support" ? COLORS.srSupport : COLORS.srResist,
          lv.type === "support" ? "S" : "R",
          LineStyle.Dashed, 1);
      });
    }

    // Fibonacci levels
    if (overlays.fibonacci && data.overlays.fibonacci?.levels) {
      const fibColors: Record<string, string> = {
        "0": "#ffffff", "0.236": "#c4b5fd", "0.382": "#a78bfa",
        "0.5": "#8b5cf6", "0.618": "#7c3aed", "0.786": "#6d28d9", "1": "#ffffff",
      };
      Object.entries(data.overlays.fibonacci.levels).forEach(([ratio, level]) => {
        addPriceLine(candleSeries, level, fibColors[ratio] ?? COLORS.fib,
          `Fib ${ratio}`, LineStyle.Dotted, 1);
      });
    }

    // SL/TP from latest signal
    if (overlays.sltp && data.latest_signal) {
      const sig = data.latest_signal;
      if (sig.sl)    addPriceLine(candleSeries, sig.sl,    COLORS.sl, "SL",    LineStyle.Dashed, 1);
      if (sig.tp)    addPriceLine(candleSeries, sig.tp,    COLORS.tp, "TP",    LineStyle.Dashed, 1);
      if (sig.entry) addPriceLine(candleSeries, sig.entry, COLORS.gold, "Entry", LineStyle.Solid, 1);
    }

    // ML Forecast projection line
    if (overlays.mlForecast && data.ml_forecast?.projection?.length > 1) {
      const color = data.ml_forecast.direction === "bullish" ? COLORS.bullish
                  : data.ml_forecast.direction === "bearish" ? COLORS.bearish
                  : COLORS.neutral;
      const forecastSeries = chart.addLineSeries({
        color,
        lineWidth: 2,
        lineStyle: LineStyle.Dashed,
        priceLineVisible: false,
        lastValueVisible: true,
        title: `ML ${data.ml_forecast.confidence.toFixed(0)}%`,
      });
      forecastSeries.setData(data.ml_forecast.projection as any);
    }

    // Fit all data to view
    chart.timeScale().fitContent();

    // ── RSI sub-chart ──
    if (overlays.rsi && rsiRef.current && data.indicators.rsi?.length) {
      const rsiChart = createChart(rsiRef.current, {
        width:  rsiRef.current.clientWidth,
        height: 120,
        layout: { background: { type: ColorType.Solid, color: COLORS.bg }, textColor: COLORS.text },
        grid:   { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
        rightPriceScale: { borderColor: COLORS.grid, scaleMargins: { top: 0.1, bottom: 0.1 } },
        timeScale: { borderColor: COLORS.grid, timeVisible: true },
        crosshair: { mode: CrosshairMode.Normal },
      });
      rsiChartRef.current = rsiChart;

      const rsiSeries = rsiChart.addLineSeries({ color: "#a78bfa", lineWidth: 1, priceLineVisible: false });
      rsiSeries.setData(data.indicators.rsi as any);

      // Overbought / Oversold lines
      rsiSeries.createPriceLine({ price: 70, color: COLORS.bearish, lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "OB" } as PriceLineOptions);
      rsiSeries.createPriceLine({ price: 30, color: COLORS.bullish, lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "OS" } as PriceLineOptions);

      rsiChart.timeScale().fitContent();

      // Sync time ranges
      chart.timeScale().subscribeVisibleTimeRangeChange(range => {
        if (range) rsiChart.timeScale().setVisibleRange(range);
      });
    }

    // Responsive resize
    const ro = new ResizeObserver(() => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
      if (rsiRef.current && rsiChartRef.current) rsiChartRef.current.applyOptions({ width: rsiRef.current.clientWidth });
    });
    if (containerRef.current) ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      rsiChartRef.current?.remove();
      rsiChartRef.current = null;
      chartRef.current    = null;
    };
  }, [data, overlays, height]);

  return (
    <div className="w-full">
      <div ref={containerRef} className="w-full" style={{ height }} />
      {overlays.rsi && <div ref={rsiRef} className="w-full mt-1" style={{ height: 120 }} />}
    </div>
  );
});
