import React, { useMemo, useRef, useEffect } from 'react';
import * as echarts from 'echarts';

type HeatmapFormatterParam = {
  data: [number, number, number];
};

export interface CorrelationData {
  labels: string[];
  data: Array<[number, number, number]>;
  error: string | null;
}

export const CorrelationHeatmap: React.FC<{ data: CorrelationData }> = ({ data }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const labels = data.labels;
  const shortLabels = labels.map((l) => l.replace(/[（(].*?[）)]/g, '').trim());

  const summary = useMemo(() => {
    const findIdx = (part: string) => labels.findIndex((l: string) => l.includes(part));
    const iCsi = findIdx('沪深300');
    const iBond = findIdx('债券');
    const iSpx = findIdx('美股');

    const corr = (i: number, j: number) => {
      const found = data.data.find((item) => item[0] === i && item[1] === j);
      return found ? found[2] : null;
    };

    const parts: string[] = [];
    if (iCsi >= 0 && iBond >= 0) {
      const c = corr(iCsi, iBond);
      if (c !== null) {
        parts.push(c < 0 ? '股债跷跷板正常（负相关），对冲有效' : '股债相关性转正，对冲可能失效');
      }
    }
    if (iCsi >= 0 && iSpx >= 0) {
      const c = corr(iCsi, iSpx);
      if (c !== null) {
        parts.push(c > 0.7 ? '中美高度联动，波动易传导' : `中美联动性 ${c.toFixed(2)}，相对独立`);
      }
    }
    return parts.join('；');
  }, [labels, data]);

  const option = useMemo(() => ({
    tooltip: {
      formatter: (p: HeatmapFormatterParam) => `${labels[p.data[0]]} / ${labels[p.data[1]]}<br/>相关系数: <strong>${p.data[2]}</strong>`,
    },
    grid: { left: 30, right: 30, top: 5, bottom: 5 },
    xAxis: {
      type: 'category',
      data: shortLabels,
      position: 'top',
      axisLabel: { color: '#ccc', fontSize: 11 },
      axisLine: { lineStyle: { color: 'rgba(128,128,128,0.2)' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'category',
      data: shortLabels,
      axisLabel: { color: '#ccc', fontSize: 11 },
      axisLine: { lineStyle: { color: 'rgba(128,128,128,0.2)' } },
      axisTick: { show: false },
    },
    visualMap: {
      min: -1,
      max: 1,
      calculable: true,
      orient: 'vertical',
      right: 0,
      top: 'center',
      textStyle: { color: '#aaa', fontSize: 9 },
      inRange: {
        color: ['#22c55e', '#a3a3a3', '#ef4444'], // 绿 -> 灰 -> 红
      },
    },
    series: [{
      type: 'heatmap',
      data: data.data,
      label: { show: true, color: 'auto', fontSize: 10, fontWeight: 'bold', formatter: (p: HeatmapFormatterParam) => p.data[2] === 1 ? '' : p.data[2].toFixed(2) },
      itemStyle: { borderColor: '#0d1117', borderWidth: 2, borderRadius: 6 },
    }],
  }), [data, labels, shortLabels]);

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

  return (
    <>
      <div ref={containerRef} style={{ width: '100%', height: 220 }} />
      <div className="mt-1 border-t border-border/30 px-1 pt-1.5 text-[11px] leading-snug text-secondary-text">
        {summary || '暂无足够数据进行分析'}
      </div>
    </>
  );
};
