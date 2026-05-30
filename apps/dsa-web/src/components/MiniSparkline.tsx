import React, { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

interface MiniSparklineProps {
  data: Array<{ date: string; close: number }>;
  color?: string;
  height?: number;
  prevClose?: number;
}

export const MiniSparkline: React.FC<MiniSparklineProps> = ({
  data,
  color = '#22c55e',
  height = 40,
  prevClose,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

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

    const seriesData = data
      .filter((item) => item.close != null && item.date)
      .map((item) => [new Date(item.date).getTime(), item.close]);

    if (seriesData.length === 0) return;

    chart.setOption({
      animation: false,
      grid: { left: 0, right: 0, top: 2, bottom: 2 },
      xAxis: {
        type: 'time',
        show: false,
        splitLine: { show: false },
        axisLabel: { show: false },
        axisTick: { show: false },
        axisLine: { show: false },
      },
      yAxis: {
        type: 'value',
        show: false,
        scale: true,
        splitLine: { show: false },
        axisLabel: { show: false },
        axisTick: { show: false },
        axisLine: { show: false },
      },
      series: [
        {
          type: 'line',
          data: seriesData,
          symbol: 'none',
          lineStyle: { width: 1, color },
          markLine: prevClose != null ? {
            silent: true,
            symbol: 'none',
            lineStyle: { type: 'dashed', color: '#888', width: 1 },
            data: [{ yAxis: prevClose }],
            label: { show: false },
          } : undefined,
        },
      ],
    });

    const resizeObserver = new ResizeObserver(() => {
      chart.resize({
        width: containerRef.current?.clientWidth,
        height,
      });
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, [data, color, height]);

  if (!data || data.length === 0) {
    return null;
  }

  return <div ref={containerRef} style={{ width: '100%', height }} />;
};
