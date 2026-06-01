import React, { useMemo, useRef, useEffect } from 'react';
import type { MonthlySeasonalityResponse } from '../api/market';
import { echarts, type ECharts } from './echarts';

interface SeasonalityChartProps {
  data: MonthlySeasonalityResponse;
}

type AxisTooltipParam = {
  dataIndex: number;
  name: string;
};

type BarLabelParam = {
  value: number;
};

export const SeasonalityChart: React.FC<SeasonalityChartProps> = ({ data }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ECharts | null>(null);

  const option = useMemo(() => ({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: AxisTooltipParam[]) => {
        if (!params || params.length === 0) return '';
        const idx = params[0].dataIndex;
        const ret = data.avgReturns[idx];
        const wr = data.winRates[idx];
        const color = ret >= 0 ? '#ef4444' : '#22c55e';
        return `${params[0].name}<br/>
平均涨跌幅: <strong style="color:${color}">${ret >= 0 ? '+' : ''}${ret}%</strong><br/>
上涨概率: ${wr}%`;
      },
    },
    grid: { left: 30, right: 30, top: 20, bottom: 40 },
    xAxis: {
      type: 'category',
      data: data.months,
      axisLabel: { color: '#aaa', fontSize: 11, rotate: 0 },
      axisLine: { lineStyle: { color: 'rgba(128,128,128,0.3)' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#888', formatter: '{value}%' },
      splitLine: { lineStyle: { color: 'rgba(128,128,128,0.15)' } },
      axisLine: { lineStyle: { color: 'rgba(128,128,128,0.3)' } },
    },
    series: [{
      name: '平均涨跌幅',
      type: 'bar',
      barWidth: 20,
      data: data.avgReturns.map((v) => ({
        value: v,
        itemStyle: {
          color: v >= 0 ? '#ef4444' : '#22c55e',
          borderRadius: v >= 0 ? [3, 3, 0, 0] : [0, 0, 3, 3],
        },
      })),
      label: {
        show: true,
        position: 'top',
        color: '#aaa',
        fontSize: 9,
        formatter: (p: BarLabelParam) => `${p.value >= 0 ? '+' : ''}${p.value}%`,
      },
    }],
  }), [data]);

  useEffect(() => {
    if (!containerRef.current) return;
    if (!chartRef.current) {
      chartRef.current = echarts.init(containerRef.current);
    }
    const chart = chartRef.current;
    chart.setOption(option);

    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(containerRef.current);
    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, [option]);

  return <div ref={containerRef} style={{ width: '100%', height: 220 }} />;
};
