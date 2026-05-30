import { useCallback, useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { EChartsOption } from "echarts";
import { cn } from "../utils/cn";

type GaugeSegment = {
  label: string;
  min: number;
  max: number;
  color: string;
};

type GaugeProps = {
  value: number;
  unit?: string;
  minValue: number;
  maxValue: number;
  segments: GaugeSegment[];
  title: string;
  description?: string;
  className?: string;
};

export function Gauge({
  value,
  unit: _unit = "",
  minValue,
  maxValue,
  segments,
  title,
  description,
  className,
}: GaugeProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<echarts.EChartsType | null>(null);
  const valueRef = useRef(value);

  const getChartOption = useCallback((): EChartsOption => {
    const normalized = Math.min(maxValue, Math.max(minValue, value));

    return {
      series: [
        {
          type: "gauge",
          startAngle: 200,
          endAngle: -20,
          min: 0,
          max: 100,
          splitNumber: 5,
          itemStyle: {
            color: (() => {
              const ratio = (normalized - minValue) / (maxValue - minValue);
              return segments[ratio < 0.33 ? 0 : ratio < 0.66 ? 1 : 2]?.color;
            })(),
          },
          progress: {
            show: true,
            roundCap: true,
            width: 16,
          },
          axisLine: {
            lineStyle: {
              width: 16,
              color: [
                [1, "#2563eb"],
              ],
            },
          },
          axisTick: {
            show: false,
          },
          splitLine: {
            distance: -20,
            length: 5,
            lineStyle: {
              width: 2,
              color: "#64748b",
              opacity: 0.3,
            },
          },
          axisLabel: {
            show: false,
          },
          pointer: {
            show: true,
            icon: "path://M-10,0 L10,0 L0,90 Z",
            length: "65%",
            width: 4,
            offsetCenter: [0, "-5%"],
            itemStyle: {
              color: "auto",
              shadowColor: "rgba(0, 138, 255, 0.3)",
              shadowBlur: 6,
            },
          },
          anchor: {
            show: true,
            size: 10,
            showAbove: true,
            itemStyle: {
              color: "#fff",
              borderColor: "auto",
              borderWidth: 2.5,
            },
          },
          title: {
            show: false,
          },
          detail: {
            show: true,
            offsetCenter: [0, "20%"],
            fontSize: 18,
            fontWeight: "bold",
            formatter: `{value}`,
            color: "auto",
          },
          data: [
            {
              value: Number(normalized.toFixed(1)),
            },
          ],
        },
      ],
    };
  }, [value, minValue, maxValue, segments]);

  useEffect(() => {
    if (!chartRef.current) return;

    if (!instanceRef.current) {
      instanceRef.current = echarts.init(chartRef.current);
    }

    const chart = instanceRef.current;
    chart.setOption(getChartOption());

    return () => {
      if (instanceRef.current) {
        instanceRef.current.dispose();
        instanceRef.current = null;
      }
    };
  }, [getChartOption]);

  useEffect(() => {
    valueRef.current = value;
    if (instanceRef.current) {
      instanceRef.current.setOption(getChartOption());
    }
  }, [value, getChartOption]);

  return (
    <div className={cn("flex flex-col items-center gap-0.5", className)}>
      <div ref={chartRef} className="w-full" style={{ height: 120 }} />
      <div className="text-sm font-semibold text-foreground -mt-10">{title}</div>
      {description && (
        <div className="text-xs font-medium text-foreground/90 text-center leading-tight max-w-[140px]">
          {description}
        </div>
      )}
    </div>
  );
}
