import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  marketApi,
  type CorrelationMatrixResponse,
  type MarketRiskResponse,
  type MarketTrendResponse,
  type MonthlySeasonalityResponse,
  type RiskRadarResponse,
  type EquityRatioResponse,
} from '../api/market';
import { ApiErrorAlert, AppPage, Button, Card, EmptyState, PageHeader } from '../components/common';
import { WeeklyTrendChart } from '../components/WeeklyTrendChart';
import { RiskRadar } from '../components/RiskRadar';
import { SeasonalityChart } from '../components/SeasonalityChart';
import { CorrelationHeatmap } from '../components/CorrelationHeatmap';
import { PositionLiquidGauge } from '../components/PositionLiquidGauge';
import { TrafficLightLabel } from '../components/TrafficLightLabel';
import { Gauge } from '../components/Gauge';
import {
  usePortfolioOverview,
} from './assetsShared';

const TREND_GROUPS = [
  { key: 'cn', label: 'A 股重要指数', order: ['sh', 'sz', 'cyb'] },
  { key: 'core-cn', label: '中国核心宽基', order: ['a500', 'hs300', 'zz500'] },
  { key: 'us', label: '美股重要指数', order: ['dji', 'ixic', 'gspc'] },
  { key: 'macro', label: '宏观流动性', order: ['dxy', 'usdcny', 'tnx'] },
];

const GAUGE_SEGMENTS = {
  sentiment: [
    { label: '安全', min: 0, max: 20, color: '#22c55e' },
    { label: '警惕', min: 20, max: 30, color: '#f59e0b' },
    { label: '恐慌', min: 30, max: 50, color: '#ef4444' },
  ],
  fx: [
    { label: '偏弱', min: 6.5, max: 7.0, color: '#22c55e' },
    { label: '偏强', min: 7.0, max: 7.3, color: '#f59e0b' },
    { label: '强势', min: 7.3, max: 7.8, color: '#ef4444' },
  ],
  spread: [
    { label: '正常', min: -2, max: 1, color: '#22c55e' },
    { label: '偏高', min: 1, max: 3, color: '#f59e0b' },
    { label: '倒挂', min: 3, max: 4, color: '#ef4444' },
  ],
};

const FALLBACK_ENVIRONMENT = {
  label: '数据加载中',
  color: 'gray',
  trend: 'unknown',
  volatility: 'unknown',
  supportPct: null,
  supportStatus: 'unknown',
};

type MarketDashboardResults = [
  PromiseSettledResult<MarketRiskResponse>,
  PromiseSettledResult<MarketTrendResponse>,
  PromiseSettledResult<MonthlySeasonalityResponse>,
  PromiseSettledResult<RiskRadarResponse>,
  PromiseSettledResult<CorrelationMatrixResponse>,
];

const fetchMarketDashboardData = async (): Promise<MarketDashboardResults> => {
  const results = await Promise.allSettled([
    marketApi.getRisk(),
    marketApi.getTrend(),
    marketApi.getSeasonality(),
    marketApi.getRadar(),
    marketApi.getCorrelation(),
  ]);
  return results as MarketDashboardResults;
};

const getRadarLabel = (label?: string): string => {
  if (label === 'green') return '低风险';
  if (label === 'yellow') return '中风险';
  if (label === 'red') return '高风险';
  return '...';
};

const getRadarLabelClass = (label?: string): string => {
  if (label === 'green') return 'bg-green-100 text-green-700';
  if (label === 'yellow') return 'bg-yellow-100 text-yellow-700';
  if (label === 'red') return 'bg-red-100 text-red-700';
  return 'bg-gray-100 text-gray-500';
};

const GaugeSkeletonGrid: React.FC = () => (
  <div className="grid grid-cols-2 gap-3 p-1">
    {Array.from({ length: 4 }).map((_, index) => (
      <div key={index} className="h-28 animate-pulse rounded-lg bg-border/20" />
    ))}
  </div>
);

const AssetDashboardPage: React.FC = () => {
  useEffect(() => {
    document.title = '资产主界面 - NestCheck';
  }, []);

  const { error, syncData } = usePortfolioOverview();
  const [marketRisk, setMarketRisk] = useState<MarketRiskResponse | null>(null);
  const [marketTrend, setMarketTrend] = useState<MarketTrendResponse | null>(null);
  const [seasonality, setSeasonality] = useState<MonthlySeasonalityResponse | null>(null);
  const [riskRadar, setRiskRadar] = useState<RiskRadarResponse | null>(null);
  const [correlation, setCorrelation] = useState<CorrelationMatrixResponse | null>(null);
  const [equityRatio, setEquityRatio] = useState<EquityRatioResponse | null>(null);
  const [isRefreshingAll, setIsRefreshingAll] = useState(false);
  const [hasLoadedRiskAndTrend, setHasLoadedRiskAndTrend] = useState(false);
  const [trendGroupIdx, setTrendGroupIdx] = useState(0);

  const applyMarketResults = useCallback((results: MarketDashboardResults) => {
    const [riskResult, trendResult, seasonResult, radarResult, corrResult] = results;

    if (riskResult.status === 'fulfilled') setMarketRisk(riskResult.value);
    if (trendResult.status === 'fulfilled') setMarketTrend(trendResult.value);
    if (seasonResult.status === 'fulfilled') setSeasonality(seasonResult.value);
    if (radarResult.status === 'fulfilled') setRiskRadar(radarResult.value);
    if (corrResult.status === 'fulfilled') setCorrelation(corrResult.value);
    setHasLoadedRiskAndTrend(true);
  }, []);

  const refreshAllData = useCallback(() => {
    setIsRefreshingAll(true);
    void Promise.allSettled([
      syncData(),
      marketApi.refreshDashboard(),
    ]).then(fetchMarketDashboardData)
      .then(applyMarketResults)
      .finally(() => setIsRefreshingAll(false));
  }, [applyMarketResults, syncData]);

  useEffect(() => {
    let active = true;
    const loadData = async () => {
      const results = await fetchMarketDashboardData();
      if (!active) return;
      applyMarketResults(results);
    };
    void loadData();
    return () => { active = false; };
  }, [applyMarketResults]);

  // Load equity ratio once on mount
  useEffect(() => {
    let active = true;
    void marketApi.getEquityRatio().then((r) => {
      if (active) setEquityRatio(r);
    });
    return () => { active = false; };
  }, []);

  // Map trend data by key for quick lookup
  const trendMap = useMemo(() => {
    if (!marketTrend?.data) return new Map();
    const map = new Map<string, NonNullable<MarketTrendResponse['data']>[string]>();
    for (const [key, value] of Object.entries(marketTrend.data)) {
      if (value) map.set(key, value);
    }
    return map;
  }, [marketTrend]);

  const currentTrendItems = useMemo(() => {
    const group = TREND_GROUPS[trendGroupIdx];
    return group.order
      .map((key) => {
        const item = trendMap.get(key);
        if (!item) return { key, label: key.toUpperCase(), weeklyData: [], environment: FALLBACK_ENVIRONMENT };
        return { key, ...item };
      });
  }, [trendMap, trendGroupIdx]);

  const goPrev = useCallback(() => {
    setTrendGroupIdx((prev) => (prev - 1 + TREND_GROUPS.length) % TREND_GROUPS.length);
  }, []);

  const goNext = useCallback(() => {
    setTrendGroupIdx((prev) => (prev + 1) % TREND_GROUPS.length);
  }, []);

  return (
    <AppPage className="max-w-[1920px] space-y-3">
      <PageHeader
        eyebrow="NestCheck"
        title="稳巢"
        description={'给个人投资者的资产体检与价值配置助手：不为你交易，只帮你把"巢"搭稳。'}
        className="!rounded-xl !px-4 !py-3"
        actions={
          <Button
            onClick={() => void refreshAllData()}
            disabled={isRefreshingAll}
            variant="primary"
            size="sm"
            className="!px-4 !py-1.5"
          >
            {isRefreshingAll ? '刷新中...' : '实时数据刷新'}
          </Button>
        }
      />

      {error ? <ApiErrorAlert error={error} /> : null}

      {/* 上方：左侧趋势卡片 + 右侧市场情绪仪表盘 */}
      <section className="grid gap-3 xl:grid-cols-12 items-stretch">
        {/* 左侧：市场趋势 (3指标/组，箭头切换) */}
        <Card className="xl:col-span-8 !rounded-xl !p-4">
          <div className="flex items-center justify-between px-1 mb-3">
            <h2 className="text-base font-semibold text-foreground">市场趋势</h2>
            <span className="text-xs text-secondary-text">周线级别 · MA10/20/50 均线系统</span>
          </div>

          {!hasLoadedRiskAndTrend ? (
            <div className="h-40 animate-pulse rounded-xl bg-border/20" />
          ) : (
            <>
              {/* 分组切换工具栏 */}
              <div className="flex items-center justify-center gap-3 mb-4">
                <button
                  type="button"
                  onClick={goPrev}
                  className="flex h-8 w-8 items-center justify-center rounded-lg border border-border/50 bg-background/60 text-secondary-text hover:text-foreground hover:border-border transition-colors"
                >
                  <svg className="h-4 w-4" fill="none" strokeWidth="2" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>
                </button>
                <span className="text-sm font-medium text-foreground min-w-[120px] text-center">
                  {TREND_GROUPS[trendGroupIdx].label}
                  <span className="ml-1 text-xs text-secondary-text">({trendGroupIdx + 1}/{TREND_GROUPS.length})</span>
                </span>
                <div className="flex gap-1">
                  {TREND_GROUPS.map((_, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => setTrendGroupIdx(i)}
                      className={`h-2 rounded-full transition-all ${i === trendGroupIdx ? 'w-5 bg-cyan' : 'w-2 bg-border/50 hover:bg-border'}`}
                    />
                  ))}
                </div>
                <button
                  type="button"
                  onClick={goNext}
                  className="flex h-8 w-8 items-center justify-center rounded-lg border border-border/50 bg-background/60 text-secondary-text hover:text-foreground hover:border-border transition-colors"
                >
                  <svg className="h-4 w-4" fill="none" strokeWidth="2" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
                </button>
              </div>

              {/* 当前组 3 个指标 */}
              <div className="grid min-h-[238px] grid-cols-3 gap-6">
                {currentTrendItems.map((item) => {
                  const dailyClose = item.dailyClose;
                  const dailyPct = item.dailyPctChg;

                  return (
                    <div key={item.key} className="flex h-[238px] flex-col gap-1">
                      <div className="h-4 text-center text-xs font-medium text-foreground">{item.label}</div>

                      {/* 现价 + 涨跌幅 */}
                      <div className="relative h-8 flex items-center justify-center">
                        <div className="text-xl font-bold text-foreground tabular-nums">
                          {(dailyClose ?? item.close)?.toFixed(2)}
                        </div>
                        <div className={`absolute right-0 text-sm font-semibold tabular-nums ${dailyPct != null && dailyPct >= 0 ? 'text-[#ef4444]' : 'text-[#22c55e]'}`}>
                          {(dailyPct ?? 0) >= 0 ? '+' : ''}{(dailyPct ?? 0).toFixed(2)}%
                        </div>
                      </div>

                      {/* 趋势图 */}
                      <div className="h-28 w-full bg-background/40 rounded border border-border/30 p-1">
                        {item.weeklyData && item.weeklyData.length > 0 ? (
                          <WeeklyTrendChart data={item.weeklyData} height={100} maValues={{ ma10: item.ma10 ?? null, ma20: item.ma20 ?? null, ma50: item.ma50 ?? null }} />
                        ) : (
                          <div className="h-full flex items-center justify-center text-[10px] text-gray-400">加载中...</div>
                        )}
                      </div>

                      <TrafficLightLabel env={item.environment} className="min-h-[76px]" />
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </Card>

        {/* 右侧：市场情绪仪表盘 (2x2 Gauge) */}
        <Card className="xl:col-span-4 !rounded-xl !p-3">
          <div className="mb-2 border-b border-border/50 pb-2">
            <h2 className="text-base font-semibold text-foreground">市场情绪</h2>
          </div>
          {!hasLoadedRiskAndTrend ? (
            <GaugeSkeletonGrid />
          ) : !marketRisk ? (
            <GaugeSkeletonGrid />
          ) : (
            <div className="grid grid-cols-2 gap-3 p-1">
              <Gauge
                title="A 股情绪"
                unit=""
                value={marketRisk.chineseVix.value ?? 0}
                minValue={0}
                maxValue={50}
                segments={GAUGE_SEGMENTS.sentiment}
                description={marketRisk.chineseVix.description}
              />
              <Gauge
                title="美股情绪"
                unit=""
                value={marketRisk.usVix.value ?? 0}
                minValue={0}
                maxValue={50}
                segments={GAUGE_SEGMENTS.sentiment}
                description={marketRisk.usVix.description}
              />
              <Gauge
                title="美元强弱"
                unit=""
                value={marketRisk.dollarStrength.value ?? 7.0}
                minValue={6.5}
                maxValue={7.8}
                segments={GAUGE_SEGMENTS.fx}
                description={marketRisk.dollarStrength.description}
              />
              <Gauge
                title="中美利差"
                unit="%"
                value={marketRisk.bondSpread.spread ?? 0}
                minValue={-2}
                maxValue={4}
                segments={GAUGE_SEGMENTS.spread}
                description={marketRisk.bondSpread.description}
              />
            </div>
          )}
        </Card>

        {/* 中间行：风险雷达 + 相关性热力图 + 仓位水球图 */}
        <Card className="col-span-full !rounded-xl !p-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-stretch" style={{ minHeight: 240 }}>
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between px-3">
                <h3 className="text-xs font-semibold text-foreground">风险体检</h3>
                {riskRadar?.error ? (
                  <span className="text-[10px] text-red-500">异常</span>
                ) : (
                  <span className={`rounded px-1.5 py-0.5 text-[10px] ${getRadarLabelClass(riskRadar?.label)}`}>
                    {getRadarLabel(riskRadar?.label)}
                  </span>
                )}
              </div>
              {!hasLoadedRiskAndTrend || !riskRadar ? (
                <div className="h-48 rounded-lg bg-border/20 animate-pulse" />
              ) : riskRadar.error ? (
                <div className="h-48 rounded-lg bg-border/10 flex items-center justify-center text-[10px] text-gray-400">数据加载失败</div>
              ) : (
                <RiskRadar
                  volatility={riskRadar.volatility}
                  drawdown={riskRadar.drawdown}
                  correlation={riskRadar.correlation}
                  spread={riskRadar.spread}
                  fx={riskRadar.fx}
                  valuation={riskRadar.valuation}
                  details={riskRadar.details}
                />
              )}
            </div>
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between px-3">
                <h3 className="text-xs font-semibold text-foreground">相关性热力图</h3>
                <span className="text-[10px] text-secondary-text">52周滚动</span>
              </div>
              {!hasLoadedRiskAndTrend || !correlation ? (
                <div className="h-48 rounded-lg bg-border/20 animate-pulse" />
              ) : correlation.error || correlation.labels.length === 0 ? (
                <div className="h-48 rounded-lg bg-border/10 flex items-center justify-center text-[10px] text-gray-400">数据不足</div>
              ) : (
                <CorrelationHeatmap data={correlation} />
              )}
            </div>
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between px-3">
                <h3 className="text-xs font-semibold text-foreground">权益仓位水球</h3>
                <span className="text-[10px] text-secondary-text">动态配置建议</span>
              </div>
              {!hasLoadedRiskAndTrend || !riskRadar ? (
                <div className="h-48 rounded-lg bg-border/20 animate-pulse" />
              ) : (
                <PositionLiquidGauge data={riskRadar} currentRatio={equityRatio?.equityRatio} />
              )}
            </div>
          </div>
        </Card>

        {/* 底部全宽：全年择时热力图 */}
        <Card className="col-span-full !rounded-xl !p-3">
          <div className="mb-1 border-b border-border/50 pb-2">
            <h2 className="text-base font-semibold text-foreground">全年择时</h2>
            <span className="text-xs text-secondary-text">{seasonality ? `${seasonality.index} · 近${seasonality.yearsStat}年统计` : '加载中...'}</span>
          </div>
          {!hasLoadedRiskAndTrend || !seasonality ? (
            <div className="h-52 rounded-lg bg-border/20 animate-pulse" />
          ) : seasonality.avgReturns.every((v) => v === 0) ? (
            <EmptyState title="季节性数据暂不可用" description="数据加载中或统计结果不足。" className="border-none bg-transparent px-2 py-8 shadow-none" />
          ) : (
            <SeasonalityChart data={seasonality} />
          )}
        </Card>
      </section>
    </AppPage>
  );
};

export default AssetDashboardPage;
