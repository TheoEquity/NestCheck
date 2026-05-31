import React, { useMemo, useRef, useEffect } from 'react';
import * as echarts from 'echarts';
import type { MonthlySeasonalityResponse } from '../api/market';

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
  const chartRef = useRef<echarts.ECharts | null>(null);

  const option = useMemo(() => {
    const colors = data.avgReturns.map((v) => v >= 0 ? '#ef4444' : '#22c55e');
    return {
      tooltip: {
        trigger: 'axis' as const,
        axisPointer: { type: 'shadow' as const },
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
      grid: { left: 40, right: 40, top: 10, bottom: 10, containLabel: true },
      xAxis: {
        type: 'value' as const,
        axisLabel: { color: '#888', formatter: '{value}%' },
        splitLine: { lineStyle: { color: 'rgba(128,128,128,0.15)' } },
        axisLine: { lineStyle: { color: 'rgba(128,128,128,0.3)' } },
      },
      yAxis: {
        type: 'category' as const,
        data: data.months,
        inverse: true,
        axisLabel: { color: '#aaa', fontSize: 12 },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [{
        name: '平均涨跌幅',
        type: 'bar' as const,
        barWidth: 14,
        data: data.avgReturns.map((v, i) => ({
          value: v,
          itemStyle: {
            color: colors[i],
            borderRadius: [0, 3, 3, 0],
          },
        })),
        label: {
          show: true,
          position: 'right' as const,
          color: '#aaa',
          fontSize: 10,
          formatter: (p: BarLabelParam) => `${p.value >= 0 ? '+' : ''}${p.value}%`,
        },
      }],
    };
  }, [data]);

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

  return <div ref={containerRef} style={{ width: '100%', height: 240 }} />;
};
