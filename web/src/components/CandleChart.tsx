import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  createChart,
  type IChartApi,
} from "lightweight-charts";
import type { CandleSnapshot } from "../lib/types";

interface CandleChartProps {
  candles: CandleSnapshot[];
}

export function CandleChart({ candles }: CandleChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }
    containerRef.current.innerHTML = "";
    const chart = createChart(containerRef.current, {
      height: 330,
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#4a545b",
      },
      grid: {
        vertLines: { color: "#edf2f3" },
        horzLines: { color: "#edf2f3" },
      },
      rightPriceScale: { borderColor: "#dfe7ea" },
      timeScale: { borderColor: "#dfe7ea" },
    });
    chartRef.current = chart;
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#d64b3f",
      downColor: "#14845f",
      borderUpColor: "#d64b3f",
      borderDownColor: "#14845f",
      wickUpColor: "#d64b3f",
      wickDownColor: "#14845f",
    });
    candleSeries.setData(
      candles.map((item) => ({
        time: item.date,
        open: item.open,
        high: item.high,
        low: item.low,
        close: item.close,
      })),
    );
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
      color: "#8da2a8",
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.82,
        bottom: 0,
      },
    });
    volumeSeries.setData(
      candles.map((item) => ({
        time: item.date,
        value: item.volume,
        color: item.close >= item.open ? "#d64b3f66" : "#14845f66",
      })),
    );
    chart.timeScale().fitContent();
    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [candles]);

  return <div className="chart-host" ref={containerRef} />;
}
