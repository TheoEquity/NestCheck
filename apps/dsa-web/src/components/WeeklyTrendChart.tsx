import React, { useEffect, useRef } from 'react';
import type { WeeklyDataPoint } from '../api/market';
import { echarts, type ECharts } from './echarts';

interface WeeklyTrendChartProps {
  data: WeeklyDataPoint[];
  color?: string;
  height?: number;
  maValues?: { ma10: number | null; ma20: number | null; ma50: number | null };
}

type AxisTooltipParam = {
  dataIndex: number;
};

export const WeeklyTrendChart: React.FC<WeeklyTrendChartProps> = ({
  data,
  color = '#26a69a',
  height = 120,
  maValues,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ECharts | null>(null);

  useEffect(() => {
    if (!containerRef.current || !data || data.length === 0) return;

    if (!chartRef.current) {
      chartRef.current = echarts.init(containerRef.current, undefined, {
        renderer: 'canvas',
      });
    }

    const chart = chartRef.current;
    const containerWidth = containerRef.current.clientWidth;
    chart.resize({ width: containerWidth, height });

    const dates = data.map((item) => item.date);
    const closes = data.map((item) => item.close);
    const ma10 = data.map((item) => item.ma10 ?? null);
    const ma20 = data.map((item) => item.ma20 ?? null);
    const ma50 = data.map((item) => item.ma50 ?? null);

    const lineColor = closes.length > 1 && closes[closes.length - 1] >= closes[closes.length - 2] ? '#ef4444' : '#22c55e';

    const hasValidMA = (values: (number | null)[]) => values.some((v) => v !== null);

    chart.setOption({
      animation: false,
      grid: { left: 0, right: 10, top: 4, bottom: 4 },
      xAxis: {
        type: 'category',
        data: dates,
        show: false,
      },
      yAxis: {
        type: 'value',
        show: false,
        scale: true,
        splitLine: { show: false },
      },
      tooltip: {
        trigger: 'axis',
        formatter: (params: AxisTooltipParam[]) => {
          if (!params || params.length === 0) return '';
          const idx = params[0].dataIndex;
          const d = data[idx];
          return `${d.date}<br/>
            收盘: ${d.close}<br/>
            MA10: ${d.ma10 ?? '--'}<br/>
            MA20: ${d.ma20 ?? '--'}<br/>
            MA50: ${d.ma50 ?? '--'}`;
        },
      },
      legend: {
        show: hasValidMA(ma10) || hasValidMA(ma20) || hasValidMA(ma50),
        bottom: 4,
        right: 10,
        orient: 'horizontal',
        itemWidth: 16,
        itemHeight: 2,
        itemGap: 10,
        textStyle: { fontSize: 9, color: '#888' },
        data: [
          { name: 'MA10', icon: 'rect', itemStyle: { color: '#fbbf24' } },
          { name: 'MA20', icon: 'rect', itemStyle: { color: '#3b82f6' } },
          { name: 'MA50', icon: 'rect', itemStyle: { color: '#8b5cf6' } },
        ],
      },
      series: [
        {
          name: 'Close',
          type: 'line',
          data: closes,
          smooth: false,
          symbol: 'none',
          lineStyle: { width: 1.5, color: lineColor },
          z: 3,
        },
        {
          name: 'MA10',
          type: 'line',
          data: ma10,
          symbol: 'none',
          lineStyle: { width: 1, type: 'solid', color: '#fbbf24' },
          connectNulls: true,
          z: 2,
        },
        {
          name: 'MA20',
          type: 'line',
          data: ma20,
          symbol: 'none',
          lineStyle: { width: 1, type: 'dashed', color: '#3b82f6' },
          connectNulls: true,
          z: 2,
        },
        {
          name: 'MA50',
          type: 'line',
          data: ma50,
          symbol: 'none',
          lineStyle: { width: 1, type: 'dotted', color: '#8b5cf6' },
          connectNulls: true,
          z: 1,
        },
      ],
    });

    const observer = new ResizeObserver(() => {
      chart.resize({ width: containerRef.current?.clientWidth, height });
    });
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, [data, color, height, maValues]);

  if (!data || data.length === 0) {
    return <div style={{ width: '100%', height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999', fontSize: 10 }}>无数据</div>;
  }

  return <div ref={containerRef} style={{ width: '100%', height }} />;
};
