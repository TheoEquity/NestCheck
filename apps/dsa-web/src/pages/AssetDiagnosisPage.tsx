import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { WalletCards } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ApiErrorAlert, Card, EmptyState, PageHeader } from '../components/common';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { marketApi, type MarketIndexHistoryItem } from '../api/market';
import { portfolioApi } from '../api/portfolio';
import type { AssetAllocationPlanItem, PortfolioFundHistoryItem } from '../types/portfolio';
import { usePortfolioOverview, formatMoney, formatSignedPct, formatPct, formatNav } from './assetsShared';

const PERIODS = [
  { label: '近1周', days: 7 },
  { label: '近1月', days: 30 },
  { label: '近3月', days: 90 },
  { label: '近1年', days: 365 },
  { label: '近3年', days: 1095 },
];

const CORE_METRIC_PERIODS = [
  { key: '1y', label: '近1年', days: 365 },
  { key: '2y', label: '近2年', days: 730 },
  { key: '3y', label: '近3年', days: 1095 },
];

const EQUITY_BENCHMARK_CODE = 'sh000300';
const BOND_BENCHMARK_CODE = '511260.SH';
const PERFORMANCE_BENCHMARK_LABEL = '沪深300指数 50% + 十年国债ETF 50%';

const AssetDiagnosisPage: React.FC = () => {
  const { positions, isLoading, error } = usePortfolioOverview();
  const [fundHistory, setFundHistory] = useState<PortfolioFundHistoryItem[]>([]);
  const [hs300History, setHs300History] = useState<MarketIndexHistoryItem[]>([]);
  const [bondBenchmarkHistory, setBondBenchmarkHistory] = useState<MarketIndexHistoryItem[]>([]);
  const [activeAllocationPlan, setActiveAllocationPlan] = useState<AssetAllocationPlanItem | null>(null);
  const [fundHistoryError, setFundHistoryError] = useState<ParsedApiError | null>(null);
  const [fundHistoryLoading, setFundHistoryLoading] = useState(true);

  useEffect(() => {
    document.title = '稳巢基金 - NestCheck';
  }, []);

  useEffect(() => {
    let active = true;
    portfolioApi.getFundHistory(1200).then((resp) => {
      if (!active) return;
      setFundHistory(resp.items || []);
    }).catch((err) => {
      if (!active) return;
      setFundHistoryError(getParsedApiError(err));
    }).finally(() => {
      if (active) setFundHistoryLoading(false);
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    marketApi.getIndexHistory(EQUITY_BENCHMARK_CODE, 1200).then((resp) => {
      if (!active) return;
      setHs300History(resp.items || []);
    }).catch(() => {
      if (!active) return;
      setHs300History([]);
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    marketApi.getIndexHistory(BOND_BENCHMARK_CODE, 1200).then((resp) => {
      if (!active) return;
      setBondBenchmarkHistory(resp.items || []);
    }).catch(() => {
      if (!active) return;
      setBondBenchmarkHistory([]);
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    portfolioApi.listAllocationPlans().then((resp) => {
      if (!active) return;
      setActiveAllocationPlan((resp.plans || []).find((plan) => plan.isActive) || null);
    }).catch(() => {
      if (!active) return;
      setActiveAllocationPlan(null);
    });
    return () => {
      active = false;
    };
  }, []);

  const totalMarketValue = positions.reduce((sum, item) => sum + Number(item.marketValueBase || 0), 0);
  const totalHoldingPnl = positions.reduce((sum, item) => sum + Number(item.unrealizedPnlBase || 0), 0);
  const totalRealizedPnl = positions.reduce((sum, item) => sum + Number(item.realizedPnlBase || 0), 0);

  const latestFundPoint = fundHistory.length > 0 ? fundHistory[fundHistory.length - 1] : null;

  const periodReturns = useMemo(() => {
    return PERIODS.map((period) => ({ ...period, value: computePeriodReturn(fundHistory, period.days) }));
  }, [fundHistory]);

  const monthlyAssetRows = useMemo(() => computeMonthlyAssets(fundHistory), [fundHistory]);
  const navChartRows = useMemo(
    () => buildNavBenchmarkRows(fundHistory, hs300History, bondBenchmarkHistory, activeAllocationPlan?.expectedReturn ?? null),
    [fundHistory, hs300History, bondBenchmarkHistory, activeAllocationPlan],
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="稳巢基金"
        description="以内部基金方式对资产进行更科学的管理和收益风险评价。"
      />

      {error ? <ApiErrorAlert error={error} /> : null}
      {fundHistoryError ? <ApiErrorAlert error={fundHistoryError} /> : null}

      <FundOverview
        fundHistory={fundHistory}
        fundHistoryLoading={fundHistoryLoading}
        latestFundPoint={latestFundPoint}
        monthlyAssetRows={monthlyAssetRows}
        navChartRows={navChartRows}
        periodReturns={periodReturns}
        positions={positions}
        totalMarketValue={totalMarketValue}
        totalHoldingPnl={totalHoldingPnl}
        totalRealizedPnl={totalRealizedPnl}
        isLoading={isLoading}
        activeAllocationPlan={activeAllocationPlan}
      />
    </div>
  );
};

function FundOverview({
  fundHistory,
  fundHistoryLoading,
  latestFundPoint,
  monthlyAssetRows,
  navChartRows,
  periodReturns,
  positions,
  totalMarketValue,
  totalHoldingPnl,
  totalRealizedPnl,
  isLoading,
  activeAllocationPlan,
}: {
  fundHistory: PortfolioFundHistoryItem[];
  fundHistoryLoading: boolean;
  latestFundPoint: PortfolioFundHistoryItem | null;
  monthlyAssetRows: Array<{ month: string; totalEquity: number | null }>;
  navChartRows: Array<{ recordDate: string; fundNav: number; benchmarkNav?: number | null; planNav?: number | null }>;
  periodReturns: Array<{ label: string; value: number | null }>;
  positions: PortfolioFundHistoryItem[] | unknown[];
  totalMarketValue: number;
  totalHoldingPnl: number;
  totalRealizedPnl: number;
  isLoading: boolean;
  activeAllocationPlan: AssetAllocationPlanItem | null;
}) {
  const [activeMetricPeriod, setActiveMetricPeriod] = useState(CORE_METRIC_PERIODS[0].key);
  const inceptionDate = fundHistory[0]?.recordDate || '--';
  const fundTotalEquity = latestFundPoint ? Number(latestFundPoint.totalEquity || 0) : totalMarketValue;
  const dailyNavChange = computeDailyNavChange(fundHistory);
  const activeMetricConfig = CORE_METRIC_PERIODS.find((period) => period.key === activeMetricPeriod) || CORE_METRIC_PERIODS[0];
  const coreMetrics = computeNavMetrics(fundHistory, activeMetricConfig.days);
  const coreMetricCards = [
    { label: '年化收益', value: coreMetrics.annualizedReturnPct == null ? '--' : formatSignedPct(coreMetrics.annualizedReturnPct), hint: '把区间收益折算成年化表现。' },
    { label: '年化波动', value: coreMetrics.volatilityPct == null ? '--' : formatPct(coreMetrics.volatilityPct), hint: '衡量净值上下波动幅度。' },
    { label: '最大回撤', value: coreMetrics.maxDrawdownPct == null ? '--' : formatPct(coreMetrics.maxDrawdownPct), hint: '区间内从高点到低点的最大跌幅。' },
    { label: '夏普比率', value: coreMetrics.sharpe == null ? '--' : coreMetrics.sharpe.toFixed(2), hint: '每承担一份波动获得的超额收益。' },
    { label: '卡玛比率', value: coreMetrics.calmar == null ? '--' : coreMetrics.calmar.toFixed(2), hint: '年化收益相对最大回撤的效率。' },
  ];

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <Card className="p-5">
          <div className="mb-4 flex items-start gap-2">
            <div className="flex items-center gap-2">
              <WalletCards className="h-5 w-5 text-primary" />
              <div>
                <h2 className="text-base font-semibold text-foreground">稳巢基金</h2>
                <p className="mt-1 text-xs text-muted-text">成立日期：{inceptionDate}</p>
              </div>
            </div>
          </div>
          {isLoading ? (
            <div className="h-40 animate-pulse rounded-xl bg-border/20" />
          ) : positions.length === 0 && !latestFundPoint ? (
            <EmptyState title="暂无资产数据" description="先在资产初始化或资产管理中录入持仓。" />
          ) : (
            <>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <Metric label="总资产" value={formatMoney(fundTotalEquity)} />
                <Metric label="资产份额" value={latestFundPoint ? latestFundPoint.fundShares.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) : '--'} />
                <Metric label="单位净值" value={latestFundPoint ? formatNav(latestFundPoint.fundNav) : '--'} />
                <Metric label="日涨幅" value={dailyNavChange == null ? '--' : formatSignedPct(dailyNavChange)} />
                <Metric label="已实现收益" value={formatMoney(totalRealizedPnl)} />
                <Metric label="持仓收益" value={formatMoney(totalHoldingPnl)} />
                <Metric label="业绩基准" value={PERFORMANCE_BENCHMARK_LABEL} multiline />
                <Metric label="配置计划" value={activeAllocationPlan?.expectedReturn == null ? '--' : formatPlanRate(activeAllocationPlan.expectedReturn)} />
              </div>
            </>
          )}
        </Card>

        <Card className="p-5">
          <h2 className="mb-4 text-base font-semibold text-foreground">月度资产总额</h2>
          <div className="h-40">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monthlyAssetRows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.16)" vertical={false} />
                <XAxis dataKey="month" tick={{ fontSize: 10, fill: '#94a3b8' }} tickMargin={8} interval={0} tickFormatter={(value) => String(value).slice(5)} />
                <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} width={54} tickFormatter={(value) => `${Math.round(Number(value) / 10000)}万`} />
                <Tooltip
                  formatter={(value) => [value == null ? '--' : formatMoney(Number(value)), '资产总额']}
                  labelFormatter={(label) => `${label}`}
                  contentStyle={{ background: '#0f172a', border: '1px solid rgba(148, 163, 184, 0.28)', borderRadius: 8, color: '#e2e8f0' }}
                  labelStyle={{ color: '#cbd5e1' }}
                />
                <Bar dataKey="totalEquity" fill="#38bdf8" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-xs text-muted-text">固定展示最近 12 个月，未成立或无估值月份留空。</p>
        </Card>
      </div>

      <Card className="p-5">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-base font-semibold text-foreground">净值走势</h2>
            <p className="mt-1 text-xs text-muted-text">内部净值按日展示，业绩基准按首个重合日期归一化叠加。</p>
          </div>
        </div>

        {fundHistoryLoading ? (
          <div className="h-72 animate-pulse rounded-xl bg-border/20" />
        ) : fundHistory.length < 2 ? (
          <EmptyState title="暂无净值曲线" description="建立内部基金并完成至少两天估值后展示收益风险曲线。" />
        ) : (
          <div className="grid gap-4 xl:grid-cols-[1.5fr_0.8fr]">
            <div className="h-72 min-w-0">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={navChartRows} margin={{ top: 10, right: 12, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.18)" />
                  <XAxis dataKey="recordDate" tick={{ fontSize: 11, fill: '#94a3b8' }} tickMargin={8} minTickGap={28} />
                  <YAxis domain={["dataMin", "dataMax"]} tick={{ fontSize: 11, fill: '#94a3b8' }} width={52} tickFormatter={(value) => Number(value).toFixed(4)} />
                  <Legend formatter={(value) => <span className="text-xs text-secondary-text">{getNavSeriesLabel(String(value))}</span>} />
                  <Tooltip
                    formatter={(value, name) => [formatNav(Number(value)), getNavSeriesLabel(String(name))]}
                    labelFormatter={(label) => `日期 ${label}`}
                    contentStyle={{ background: '#0f172a', border: '1px solid rgba(148, 163, 184, 0.28)', borderRadius: 8, color: '#e2e8f0' }}
                    labelStyle={{ color: '#cbd5e1' }}
                  />
                  <Line type="monotone" dataKey="fundNav" stroke="#38bdf8" strokeWidth={2.2} dot={false} activeDot={{ r: 4 }} />
                  <Line type="monotone" dataKey="benchmarkNav" stroke="#f59e0b" strokeWidth={1.8} dot={false} strokeDasharray="4 3" connectNulls />
                  <Line type="monotone" dataKey="planNav" stroke="#a78bfa" strokeWidth={1.6} dot={false} strokeDasharray="2 5" connectNulls />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
              {periodReturns.map((row) => (
                <div key={row.label} className="flex items-center justify-between rounded-xl border border-subtle bg-background/50 px-3 py-2 text-sm">
                  <span className="text-secondary-text">{row.label}</span>
                  <span className="font-medium text-foreground">{row.value == null ? '--' : formatSignedPct(row.value)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      <div className="grid gap-4">
        <Card className="p-5">
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="text-base font-semibold text-foreground">核心指标</h2>
            <div className="flex rounded-xl border border-border/50 bg-background/40 p-1">
              {CORE_METRIC_PERIODS.map((period) => (
                <button
                  key={period.key}
                  type="button"
                  onClick={() => setActiveMetricPeriod(period.key)}
                  className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${activeMetricPeriod === period.key ? 'bg-primary text-primary-foreground shadow-sm' : 'text-secondary-text hover:bg-background/70 hover:text-foreground'}`}
                >
                  {period.label}
                </button>
              ))}
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {coreMetricCards.map((item) => <Metric key={item.label} label={item.label} value={item.value} hint={item.hint} />)}
          </div>
        </Card>
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  compact = false,
  hint,
  alignHintRight = false,
  multiline = false,
}: {
  label: string;
  value: string;
  compact?: boolean;
  hint?: string;
  alignHintRight?: boolean;
  multiline?: boolean;
}) {
  return (
    <div className="rounded-xl border border-subtle bg-background/50 p-3">
      <div className="text-xs text-muted-text">{label}</div>
      <div className={`mt-1 font-semibold text-foreground ${multiline ? 'whitespace-normal break-words text-sm leading-5' : `truncate ${compact ? 'text-sm' : 'text-lg'}`}`}>{value}</div>
      {hint ? <div className={`mt-1 text-xs text-secondary-text ${alignHintRight ? 'text-right' : ''}`}>{hint}</div> : null}
    </div>
  );
}

function computeDailyNavChange(items: PortfolioFundHistoryItem[]): number | null {
  if (items.length < 2) return null;
  const latest = items[items.length - 1];
  const previous = items[items.length - 2];
  if (!latest || !previous || previous.fundNav <= 0 || latest.recordDate === previous.recordDate) return null;
  return ((latest.fundNav / previous.fundNav) - 1) * 100;
}

function formatPlanRate(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return '--';
  return `${(value * 100).toFixed(1)}%`;
}

function getNavSeriesLabel(key: string): string {
  if (key === 'fundNav') return '内部净值';
  if (key === 'benchmarkNav') return '业绩基准';
  if (key === 'planNav') return '配置计划';
  return key;
}

function computePeriodReturn(items: PortfolioFundHistoryItem[], days: number): number | null {
  if (items.length < 2) return null;
  const latest = items[items.length - 1];
  const latestDate = new Date(latest.recordDate).getTime();
  const cutoff = latestDate - days * 24 * 60 * 60 * 1000;
  const base = [...items].reverse().find((item) => new Date(item.recordDate).getTime() <= cutoff) || items[0];
  if (!base || base.fundNav <= 0 || latest.fundNav <= 0 || base.recordDate === latest.recordDate) return null;
  return ((latest.fundNav / base.fundNav) - 1) * 100;
}

function computeMonthlyAssets(items: PortfolioFundHistoryItem[]): Array<{ month: string; totalEquity: number | null }> {
  const latestByMonth = new Map<string, PortfolioFundHistoryItem>();
  for (const item of items) {
    const month = item.recordDate.slice(0, 7);
    latestByMonth.set(month, item);
  }

  const latestDate = items.length > 0 ? new Date(`${items[items.length - 1].recordDate}T00:00:00`) : new Date();
  const endMonth = new Date(latestDate.getFullYear(), latestDate.getMonth(), 1);
  return Array.from({ length: 12 }, (_, index) => {
    const date = new Date(endMonth.getFullYear(), endMonth.getMonth() - (11 - index), 1);
    const month = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
    const item = latestByMonth.get(month);
    return {
      month,
      totalEquity: item ? Number(item.totalEquity || 0) : null,
    };
  });
}

function buildNavBenchmarkRows(
  fundItems: PortfolioFundHistoryItem[],
  equityItems: MarketIndexHistoryItem[],
  bondItems: MarketIndexHistoryItem[],
  expectedReturn: number | null,
): Array<{ recordDate: string; fundNav: number; benchmarkNav?: number | null; planNav?: number | null }> {
  if (fundItems.length === 0) return [];
  const equityByDate = new Map(equityItems.map((item) => [item.date, item.close]));
  const bondByDate = new Map(bondItems.map((item) => [item.date, item.close]));
  const firstFundWithBenchmark = fundItems.find((item) => {
    const equityClose = equityByDate.get(item.recordDate);
    const bondClose = bondByDate.get(item.recordDate);
    return equityClose != null && equityClose > 0 && bondClose != null && bondClose > 0 && item.fundNav > 0;
  });
  const baseEquity = firstFundWithBenchmark ? equityByDate.get(firstFundWithBenchmark.recordDate) : null;
  const baseBond = firstFundWithBenchmark ? bondByDate.get(firstFundWithBenchmark.recordDate) : null;
  const baseFundNav = firstFundWithBenchmark?.fundNav ?? null;
  const planBase = fundItems.find((item) => item.fundNav > 0);
  const planBaseDate = planBase ? new Date(`${planBase.recordDate}T00:00:00`).getTime() : null;

  return fundItems.map((item) => {
    const equityClose = equityByDate.get(item.recordDate);
    const bondClose = bondByDate.get(item.recordDate);
    const benchmarkNav = baseEquity && baseBond && baseFundNav && equityClose != null && equityClose > 0 && bondClose != null && bondClose > 0
      ? (((equityClose / baseEquity) * 0.5) + ((bondClose / baseBond) * 0.5)) * baseFundNav
      : null;
    const daysFromPlanBase = planBaseDate == null ? null : (new Date(`${item.recordDate}T00:00:00`).getTime() - planBaseDate) / (24 * 60 * 60 * 1000);
    const planNav = planBase && expectedReturn != null && daysFromPlanBase != null && daysFromPlanBase >= 0
      ? planBase.fundNav * ((1 + expectedReturn) ** (daysFromPlanBase / 365))
      : null;
    return {
      recordDate: item.recordDate,
      fundNav: item.fundNav,
      benchmarkNav,
      planNav,
    };
  });
}

function computeNavMetrics(items: PortfolioFundHistoryItem[], days: number): {
  annualizedReturnPct: number | null;
  maxDrawdownPct: number | null;
  volatilityPct: number | null;
  sharpe: number | null;
  calmar: number | null;
} {
  if (items.length < 2) {
    return { annualizedReturnPct: null, maxDrawdownPct: null, volatilityPct: null, sharpe: null, calmar: null };
  }

  const latest = items[items.length - 1];
  const cutoff = new Date(latest.recordDate).getTime() - days * 24 * 60 * 60 * 1000;
  const windowItems = items.filter((item) => new Date(item.recordDate).getTime() >= cutoff);
  const rows = windowItems.length >= 2 ? windowItems : items;

  let peak = rows[0].fundNav;
  let maxDrawdown = 0;
  const returns: number[] = [];
  for (let index = 1; index < rows.length; index += 1) {
    const previous = rows[index - 1].fundNav;
    const current = rows[index].fundNav;
    if (previous > 0 && current > 0) returns.push((current / previous) - 1);
    peak = Math.max(peak, current);
    if (peak > 0) maxDrawdown = Math.min(maxDrawdown, (current / peak) - 1);
  }

  const volatility = standardDeviation(returns) * Math.sqrt(252);
  const first = rows[0];
  const rangeDays = Math.max(1, (new Date(latest.recordDate).getTime() - new Date(first.recordDate).getTime()) / (24 * 60 * 60 * 1000));
  const annualizedReturn = first.fundNav > 0 && latest.fundNav > 0 ? (latest.fundNav / first.fundNav) ** (365 / rangeDays) - 1 : null;
  const maxDrawdownAbs = Math.abs(maxDrawdown);
  return {
    annualizedReturnPct: annualizedReturn == null ? null : annualizedReturn * 100,
    maxDrawdownPct: maxDrawdownAbs * 100,
    volatilityPct: returns.length > 1 ? volatility * 100 : null,
    sharpe: annualizedReturn != null && volatility > 0 ? (annualizedReturn - 0.02) / volatility : null,
    calmar: annualizedReturn != null && maxDrawdownAbs > 0 ? annualizedReturn / maxDrawdownAbs : null,
  };
}

function standardDeviation(values: number[]): number {
  if (values.length < 2) return 0;
  const avg = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + ((value - avg) ** 2), 0) / (values.length - 1);
  return Math.sqrt(variance);
}

export default AssetDiagnosisPage;
