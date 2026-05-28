import type React from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { stocksApi } from '../api/stocks';
import { marketApi, type MarketRiskResponse } from '../api/market';
import { ApiErrorAlert, AppPage, Badge, Button, Card, EmptyState, PageHeader } from '../components/common';
import type { StockQuote } from '../types/stocks';
import {
  formatMoney,
  formatPct,
  getMarketLabel,
  getPositionRiskLevel,
  usePortfolioOverview,
} from './assetsShared';

type MarketCard = {
  key: string;
  label: string;
  code: string;
};

const MARKET_CARDS: MarketCard[] = [
  { key: 'sh', label: '上证指数', code: 'sh000001' },
  { key: 'sz', label: '深圳成指', code: 'sz399001' },
  { key: 'cyb', label: '创业板指', code: 'sz399006' },
  { key: 'dji', label: '道琼斯', code: '^DJI' },
  { key: 'ixic', label: '纳斯达克', code: '^IXIC' },
  { key: 'gspc', label: '标普500', code: '^GSPC' },
  { key: 'dxy', label: '美元指数', code: 'DX-Y.NYB' },
  { key: 'usdcny', label: '美元/人民币汇率', code: 'USDCNY=X' },
  { key: 'tnx', label: '10年期美债', code: '^TNX' },
];

const getStaticHealthTone = (score: number): 'success' | 'warning' | 'danger' => {
  if (score >= 80) return 'success';
  if (score >= 60) return 'warning';
  return 'danger';
};

const getStaticHealthLabel = (score: number): string => {
  const tone = getStaticHealthTone(score);
  if (tone === 'success') return '健康';
  if (tone === 'warning') return '关注';
  return '预警';
};

const AssetDashboardPage: React.FC = () => {
  useEffect(() => {
    document.title = '资产主界面 - NestCheck';
  }, []);

  const { positions, error, syncData, isRefreshing } = usePortfolioOverview();
  const [quoteMap, setQuoteMap] = useState<Record<string, StockQuote | null>>({});
  const [marketRisk, setMarketRisk] = useState<MarketRiskResponse | null>(null);
  const [isRefreshingMarketData, setIsRefreshingMarketData] = useState(false);
  const [hasLoadedMarketRisk, setHasLoadedMarketRisk] = useState(false);
  const marketScrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let active = true;
    const loadMarketQuotes = async () => {
      setIsRefreshingMarketData(true);
      try {
        const results = await Promise.all(
          MARKET_CARDS.map(async (item) => {
            try {
              const response = await stocksApi.getQuote(item.code);
              return [item.key, response] as const;
            } catch {
              return [item.key, null] as const;
            }
          }),
        );
        if (!active) return;
        setQuoteMap(Object.fromEntries(results));
      } finally {
        if (!active) return;
        setIsRefreshingMarketData(false);
      }
    };

    void loadMarketQuotes();
    return () => {
      active = false;
    };
  }, []);

  const assetSummary = useMemo(() => {
    const byMarket = new Map<string, number>();
    for (const position of positions) {
      byMarket.set(position.market, (byMarket.get(position.market) || 0) + Number(position.marketValueBase || 0));
    }
    return Array.from(byMarket.entries()).map(([market, marketValue]) => ({ market, marketValue }));
  }, [positions]);

  const topHoldings = useMemo(() => positions.slice(0, 6), [positions]);
  const totalMarketValue = useMemo(
    () => positions.reduce((sum, item) => sum + Number(item.marketValueBase || 0), 0),
    [positions],
  );
  const totalCost = useMemo(
    () => positions.reduce((sum, item) => sum + Number(item.totalCost || 0), 0),
    [positions],
  );
  const totalUnrealizedPnl = useMemo(
    () => positions.reduce((sum, item) => sum + Number(item.unrealizedPnlBase || 0), 0),
    [positions],
  );
  const topPositionPct = useMemo(() => {
    if (totalMarketValue <= 0 || topHoldings.length === 0) return 0;
    return (Number(topHoldings[0]?.marketValueBase || 0) / totalMarketValue) * 100;
  }, [topHoldings, totalMarketValue]);
  const highRiskPositionCount = useMemo(
    () => positions.filter((item) => getPositionRiskLevel(item) === '高').length,
    [positions],
  );
  const healthScore = useMemo(() => {
    let score = 90;
    if (topPositionPct > 35) score -= 24;
    else if (topPositionPct > 25) score -= 12;
    if (highRiskPositionCount >= 3) score -= 18;
    else if (highRiskPositionCount >= 1) score -= 8;
    return Math.max(18, Math.min(96, score));
  }, [highRiskPositionCount, topPositionPct]);
  const marketAlertRows = useMemo(() => {
    const topThreeValue = topHoldings.slice(0, 3).reduce((sum, item) => sum + Number(item.marketValueBase || 0), 0);
    const topThreePct = totalMarketValue > 0 ? (topThreeValue / totalMarketValue) * 100 : 0;
    const profitPct = totalCost > 0 ? (totalUnrealizedPnl / totalCost) * 100 : 0;
    return [
      { label: 'Top1 仓位', value: formatPct(topPositionPct), tone: topPositionPct > 35 ? 'danger' : topPositionPct > 25 ? 'warning' : 'success' },
      { label: '前 3 仓位', value: formatPct(topThreePct), tone: topThreePct > 65 ? 'danger' : topThreePct > 50 ? 'warning' : 'success' },
      { label: '高风险标的', value: String(highRiskPositionCount), tone: highRiskPositionCount >= 3 ? 'danger' : highRiskPositionCount >= 1 ? 'warning' : 'success' },
      { label: '静态收益率', value: formatPct(profitPct), tone: profitPct < -10 ? 'danger' : profitPct < 0 ? 'warning' : 'success' },
    ] as const;
  }, [highRiskPositionCount, topHoldings, topPositionPct, totalCost, totalMarketValue, totalUnrealizedPnl]);

  const scrollMarketCards = (direction: 'left' | 'right') => {
    const container = marketScrollRef.current;
    if (!container) return;
    const step = Math.max(container.clientWidth * 0.92, 320);
    container.scrollBy({
      left: direction === 'left' ? -step : step,
      behavior: 'smooth',
    });
  };

  return (
    <AppPage className="max-w-[1600px] space-y-3">
      <PageHeader
        eyebrow="NestCheck"
        title="稳巢"
        description={'给个人投资者的资产体检与价值配置助手：不为你交易，只帮你把"巢"搭稳。'}
        className="!rounded-xl !px-4 !py-3"
        actions={
          <Button
            onClick={() => void syncData()}
            disabled={isRefreshing}
            variant="primary"
            size="sm"
            className="!px-4 !py-1.5"
          >
            {isRefreshing ? '重估中...' : '重估'}
          </Button>
        }
      />

      {error ? <ApiErrorAlert error={error} /> : null}

      <section className="grid gap-2 xl:grid-cols-12">
        <Card className="xl:col-span-8 !rounded-xl" padding="sm">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-base font-semibold text-foreground">市场实时风向</h2>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => {
                  setIsRefreshingMarketData(true);
                  void Promise.all(
                    MARKET_CARDS.map(async (item) => {
                      try {
                        const response = await stocksApi.getQuote(item.code);
                        return [item.key, response] as const;
                      } catch {
                        return [item.key, null] as const;
                      }
                    }),
                  ).then((entries) => {
                    setQuoteMap(Object.fromEntries(entries));
                  }).finally(() => {
                    setIsRefreshingMarketData(false);
                  });
                }}
                disabled={isRefreshingMarketData}
                className="!px-3 !py-1"
              >
                {isRefreshingMarketData ? '刷新中...' : '刷新数据'}
              </Button>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  aria-label="向左查看市场卡片"
                  onClick={() => scrollMarketCards('left')}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border/60 bg-background/60 text-secondary-text transition-colors hover:text-foreground"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  aria-label="向右查看市场卡片"
                  onClick={() => scrollMarketCards('right')}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border/60 bg-background/60 text-secondary-text transition-colors hover:text-foreground"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
          <div
            ref={marketScrollRef}
            className="flex gap-2 overflow-x-auto scroll-smooth pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          >
            {MARKET_CARDS.map((item) => {
              const quote = quoteMap[item.key];
              const tone = quote?.changePercent != null && quote.changePercent >= 0 ? 'success' : 'danger';
              const changeText = quote?.change == null
                ? '--'
                : `${quote.change >= 0 ? '+' : ''}${quote.change.toLocaleString('zh-CN', { maximumFractionDigits: 4 })}`;
              const changePctText = quote?.changePercent == null
                ? '--'
                : `${quote.changePercent >= 0 ? '+' : ''}${quote.changePercent.toFixed(2)}%`;
              const priceText = quote?.currentPrice != null
                ? quote.currentPrice.toLocaleString('zh-CN', { maximumFractionDigits: 4 })
                : '--';
              return (
                <div
                  key={item.key}
                  className="w-[85%] shrink-0 rounded-lg border border-border/60 bg-background/60 p-2.5 sm:w-[48%] xl:w-[calc((100%-1rem)/3)]"
                >
                  <div className="mb-1.5 flex items-center justify-between">
                    <div>
                      <div className="text-sm font-medium text-foreground">{item.label}</div>
                      <div className="text-[11px] text-secondary-text">{item.code}</div>
                    </div>
                    <Badge variant={tone}>
                      {changePctText}
                    </Badge>
                  </div>
                  <div className="rounded-lg border border-border/40 bg-surface/50 px-3 py-4">
                    <div className="text-2xl font-semibold text-foreground">{priceText}</div>
                    <div className={`mt-1 text-sm ${quote?.changePercent != null && quote.changePercent >= 0 ? 'text-red-500' : 'text-green-500'}`}>
                      {changeText}
                      <span className="ml-1">{quote?.changePercent == null ? '' : changePctText}</span>
                    </div>
                  </div>
                  <div className="mt-2 space-y-1 text-[11px] text-secondary-text">
                    <div>开盘 {quote?.open != null ? quote.open.toLocaleString('zh-CN', { maximumFractionDigits: 4 }) : '--'}</div>
                    <div>昨收 {quote?.prevClose != null ? quote.prevClose.toLocaleString('zh-CN', { maximumFractionDigits: 4 }) : '--'}</div>
                    <div>更新时间 {quote?.updateTime ? quote.updateTime.slice(11, 19) : '--'}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        <Card className="xl:col-span-4 !rounded-xl" padding="sm">
          <div className="mb-2 flex items-center justify-between border-b border-border/50 pb-2">
            <h2 className="text-base font-semibold text-foreground">市场风险</h2>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => {
                setIsRefreshingMarketData(true);
                void marketApi.getRisk().then((response) => {
                  setMarketRisk(response);
                  setHasLoadedMarketRisk(true);
                }).catch(() => {
                }).finally(() => {
                  setIsRefreshingMarketData(false);
                });
              }}
              disabled={isRefreshingMarketData}
              className="!px-2 !py-0.5 text-xs"
            >
              {isRefreshingMarketData ? '刷新中...' : '刷新'}
            </Button>
          </div>
          {!hasLoadedMarketRisk ? (
            <div className="space-y-2 text-xs text-secondary-text">
              <div className="flex items-center justify-between">
                <span>股市估值</span>
                <span className="text-foreground">点击刷新获取</span>
              </div>
              <div className="flex items-center justify-between">
                <span>债市信号</span>
                <span className="text-foreground">点击刷新获取</span>
              </div>
              <div className="flex items-center justify-between">
                <span>美元强弱</span>
                <span className="text-foreground">点击刷新获取</span>
              </div>
              <div className="mt-2 flex items-center justify-between rounded bg-surface/50 px-2 py-1.5">
                <span>综合体温</span>
                <span className="text-foreground">等待数据</span>
              </div>
              <div>请先点击"刷新"按钮加载市场风险数据</div>
            </div>
          ) : !marketRisk ? (
            <div className="space-y-2">
              <div className="h-6 animate-pulse rounded bg-border/20" />
              <div className="h-6 animate-pulse rounded bg-border/20" />
              <div className="h-6 animate-pulse rounded bg-border/20" />
              <div className="h-8 animate-pulse rounded bg-border/20" />
            </div>
          ) : (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="text-xs text-secondary-text">股市估值</div>
                <div className="flex items-center gap-2">
                  <Badge variant={marketRisk.stockValuation.badge as any}>{marketRisk.stockValuation.status}</Badge>
                  <span className="text-xs text-secondary-text">{marketRisk.stockValuation.description}</span>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <div className="text-xs text-secondary-text">债市信号</div>
                <div className="flex items-center gap-2">
                  <Badge variant={marketRisk.bondSignal.badge as any}>{marketRisk.bondSignal.status}</Badge>
                  <span className="text-xs text-secondary-text">{marketRisk.bondSignal.description}</span>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <div className="text-xs text-secondary-text">美元强弱</div>
                <div className="flex items-center gap-2">
                  <Badge variant={marketRisk.dollarStrength.badge as any}>{marketRisk.dollarStrength.status}</Badge>
                  <span className="text-xs text-secondary-text">{marketRisk.dollarStrength.description}</span>
                </div>
              </div>
              <div className="mt-2 flex items-center justify-between rounded bg-surface/50 px-2 py-1.5">
                <span className="text-xs text-secondary-text">综合体温</span>
                <Badge variant={marketRisk.badge as any}>{marketRisk.temperature}</Badge>
              </div>
              <div className="text-xs text-secondary-text">{marketRisk.advice}</div>
            </div>
          )}
        </Card>
      </section>

      <section className="grid gap-2 xl:grid-cols-12">
        <Card className="xl:col-span-7 !rounded-xl" padding="sm">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-base font-semibold text-foreground">核心持仓摘要</h2>
            <span className="text-xs text-secondary-text">按市值排序</span>
          </div>
          {topHoldings.length === 0 ? (
            <EmptyState title="暂无核心持仓" description="完成资产初始化后，这里会展示组合中的主要权重资产。" className="border-none bg-transparent px-2 py-8 shadow-none" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead className="border-b border-border/60 text-xs text-secondary-text">
                  <tr>
                    <th className="py-1.5 text-left">账户</th>
                    <th className="py-1.5 text-left">代码</th>
                    <th className="py-1.5 text-left">市场</th>
                    <th className="py-1.5 text-left">风险</th>
                    <th className="py-1.5 text-right">市值</th>
                    <th className="py-1.5 text-right">收益率</th>
                  </tr>
                </thead>
                <tbody>
                  {topHoldings.map((row) => (
                    <tr key={`${row.accountId}-${row.symbol}-${row.market}`} className="border-b border-border/30">
                      <td className="py-1.5">{row.accountName}</td>
                      <td className="py-1.5 font-mono text-foreground">{row.symbol}</td>
                      <td className="py-1.5 text-secondary-text">{getMarketLabel(row.market)}</td>
                      <td className="py-1.5">
                        <Badge variant={getPositionRiskLevel(row) === '高' ? 'danger' : getPositionRiskLevel(row) === '中' ? 'warning' : 'success'}>
                          {getPositionRiskLevel(row)}
                        </Badge>
                      </td>
                      <td className="py-1.5 text-right">{formatMoney(row.marketValueBase, 'CNY')}</td>
                      <td className="py-1.5 text-right">{formatPct(row.unrealizedPnlPct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card className="xl:col-span-5 !rounded-xl" padding="sm">
          <div className="mb-3 border-b border-border/50 pb-2">
            <h2 className="text-base font-semibold text-foreground">组合风险</h2>
          </div>
          {assetSummary.length === 0 ? (
            <EmptyState title="暂无资产" description="先在资产初始化页创建账户并录入初始资产。" className="border-none bg-transparent px-2 py-4 shadow-none" />
          ) : (
            <div className="space-y-2">
              <div className="text-xs text-secondary-text">市场分布</div>
              {assetSummary.map((item) => (
                <div key={item.market} className="grid grid-cols-[64px_1fr_96px] items-center gap-2 py-1 text-[12px]">
                  <span className="text-secondary-text">{getMarketLabel(item.market)}</span>
                  <div className="h-1.5 overflow-hidden rounded-full bg-border/40">
                    <div
                      className="h-full rounded-full bg-cyan"
                      style={{ width: `${Math.min(100, totalMarketValue ? (item.marketValue / totalMarketValue) * 100 : 0)}%` }}
                    />
                  </div>
                  <span className="text-right font-medium text-foreground">{formatMoney(item.marketValue, 'CNY')}</span>
                </div>
              ))}
            </div>
          )}

          <div className="mt-4 space-y-2 border-t border-border/50 pt-3">
            <div className="text-xs text-secondary-text">风险指标</div>
            {marketAlertRows.map((row) => (
              <div key={row.label} className="flex items-center justify-between rounded-lg bg-background/55 px-2.5 py-1.5 text-sm">
                <span className="text-secondary-text">{row.label}</span>
                <Badge variant={row.tone === 'danger' ? 'danger' : row.tone === 'warning' ? 'warning' : 'success'}>{row.value}</Badge>
              </div>
            ))}
          </div>

          <div className="mt-4 border-t border-border/50 pt-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-foreground">健康度</span>
              <Badge variant={getStaticHealthTone(healthScore) === 'danger' ? 'danger' : getStaticHealthTone(healthScore) === 'warning' ? 'warning' : 'success'}>
                {getStaticHealthLabel(healthScore)}
              </Badge>
            </div>
            <div className="mt-2 space-y-1.5 text-xs text-secondary-text">
              <div>Top1 仓位 {formatPct(topPositionPct)}</div>
              <div>高风险 {highRiskPositionCount} 项</div>
              <div>未实现收益 {formatMoney(totalUnrealizedPnl, 'CNY')}</div>
            </div>
          </div>
        </Card>
      </section>
    </AppPage>
  );
};

export default AssetDashboardPage;
