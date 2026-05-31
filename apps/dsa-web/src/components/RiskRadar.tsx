import React, { useMemo, useRef, useEffect } from 'react';
import * as echarts from 'echarts';

interface RiskRadarProps {
  volatility: number;
  drawdown: number;
  correlation: number;
  spread: number;
  fx: number;
  valuation: number;
  details?: Record<string, number | null>;
}

const indicators = [
  { name: '波动率', key: 'volatility', rawKey: 'volatility_raw', unit: '%' },
  { name: '回撤', key: 'drawdown', rawKey: 'drawdown_raw', unit: '%' },
  { name: '股债相关', key: 'correlation' },
  { name: '信用利差', key: 'spread', unit: '%' },
  { name: '汇率压力', key: 'fx', rawKey: 'fx_raw', unit: '%' },
  { name: '估值分位', key: 'valuation', unit: '%' },
];

type RadarTooltipParam = {
  data?: {
    value?: number[];
  };
};

export const RiskRadar: React.FC<RiskRadarProps> = ({
  volatility, drawdown, correlation, spread, fx, valuation, details = {},
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  const option = useMemo(() => {
    const values = [volatility, drawdown, correlation, spread, fx, valuation];
    const safeValues = [25, 15, 35, 20, 15, 30];
    const color = values.some((v) => v > 60) ? '#ef4444' : 'rgba(34,197,94,0.8)';

    return {
      tooltip: {
        trigger: 'item' as const,
        appendTo: 'body' as const,
        formatter: (params: RadarTooltipParam) => {
          if (!params?.data?.value) return '';
          return params.data.value.map((v: number, i: number) => {
            let rawInfo = '';
            const rawKey = indicators[i].rawKey;
            const raw = rawKey ? details[rawKey] : null;
            if (raw != null) {
              rawInfo = ` (${raw}${indicators[i].unit || ''})`;
            }
            // 特殊处理 Spread 的原始值显示，因为是 Yield Level
            if (indicators[i].key === 'spread') {
               rawInfo = ` (60D回撤: ${details['spread_raw'] ?? '--'})`;
            }
            return `${indicators[i].name}: <strong>${v.toFixed(1)}</strong>${rawInfo}`;
          }).join('<br/>');
        },
      },
      legend: {
        orient: 'vertical',
        right: 5,
        bottom: 10,
        textStyle: { fontSize: 10, color: '#888' },
        data: ['当前风险', '安全基线'],
      },
      radar: {
        shape: 'circle' as const,
        splitNumber: 4,
        radius: '70%',
        center: ['45%', '48%'],
        axisName: { color: '#aab8c8', fontSize: 11, padding: [3, 5] },
        splitArea: { areaStyle: { color: ['rgba(37,99,235,0.08)', 'rgba(37,99,235,0.18)'] } },
        axisLine: { lineStyle: { color: 'rgba(37,99,235,0.35)' } },
        splitLine: { lineStyle: { color: 'rgba(37,99,235,0.25)' } },
        indicator: indicators.map((i) => ({ name: i.name, max: 100 })),
      },
      series: [
        {
          name: '当前风险',
          type: 'radar' as const,
          symbol: 'circle' as const,
          symbolSize: 5,
          lineStyle: { width: 2, color },
          areaStyle: { color: color === '#ef4444' ? 'rgba(239,68,68,0.15)' : 'rgba(34,197,94,0.12)' },
          label: { show: true, fontSize: 9 },
          data: [{ value: values, name: '当前风险' }],
        },
        {
          name: '安全基线',
          type: 'radar' as const,
          symbol: 'none' as const,
          lineStyle: { width: 1, color: '#eab308', type: 'dashed' },
          areaStyle: { color: 'rgba(234,179,8,0.05)' },
          data: [{ value: safeValues, name: '安全基线' }],
        },
      ],
    };
  }, [volatility, drawdown, correlation, spread, fx, valuation, details]);

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

  const riskItems = [
    { n: '波动率', v: volatility, r: details?.volatility_raw },
    { n: '回撤', v: drawdown, r: details?.drawdown_raw },
    { n: '股债相关', v: correlation },
    { n: '信用利差', v: spread },
    { n: '汇率压力', v: fx, r: details?.fx_raw },
    { n: '估值', v: valuation },
  ];
  const alerts = riskItems.filter((i) => i.v > 60).map((i) => i.n);
  const summary = alerts.length > 0 ? `风险聚焦：${alerts.join('、')}` : '整体处于安全区间';
  const tone = alerts.length > 0 ? 'text-amber-500' : 'text-green-500';

  return (
    <>
      <div ref={containerRef} style={{ width: '100%', height: 220, background: 'radial-gradient(circle, rgba(37,99,235,0.06) 0%, transparent 70%)' }} />
      <div className={`mt-1 flex flex-wrap items-baseline gap-2 border-t border-border/30 px-1 pt-1.5 text-[11px] leading-snug ${tone}`}>
        <span className="font-medium">{summary}</span>
        {details?.volatility_raw != null && (
          <span className="text-secondary-text">
            RV {details.volatility_raw}% · 回撤 {details.drawdown_raw}%
          </span>
        )}
      </div>
    </>
  );
};
