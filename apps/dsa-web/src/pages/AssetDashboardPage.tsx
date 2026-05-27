import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Area, AreaChart, ResponsiveContainer, Tooltip } from 'recharts';
import { stocksApi } from '../api/stocks';
import { ApiErrorAlert, AppPage, Badge, Button, Card, EmptyState, PageHeader, StatCard } from '../components/common';
import type { KLineData } from '../types/stocks';
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

const INDEX_LABELS: Record<string, string> = {
  '000001': '上证指数',
  '399001': '深证成指',
  '399006': '创业板指',
  '000016': '上证50',
  '000300': '沪深300',
};

const MARKET_CARDS: MarketCard[] = [
  { key: 'sh', label: '上证指数', code: 'sh000001' },
  { key: 'sz', label: '深证成指', code: 'sz399001' },
  { key: 'cyb', label: '创业板指', code: 'sz399006' },
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
    document.title = '资产主界面 - DSA';
  }, []);

  const { accounts, positions, indices, error, syncData, isRefreshing } = usePortfolioOverview();
  const [seriesMap, setSeriesMap] = useState<Record<string, KLineData[]>>({});

  useEffect(() => {
    let active = true;
    void Promise.all(
      MARKET_CARDS.map(async (item) => {
        try {
          const response = await stocksApi.getHistory(item.code, 60);
          return [item.key, response.data] as const;
        } catch {
          return [item.key, []] as const;
        }
      }),
    ).then((entries) => {
      if (!active) return;
      setSeriesMap(Object.fromEntries(entries));
    });
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

  return (
    <AppPage className="max-w-[1600px] space-y-3">
      <PageHeader
        eyebrow="Asset Cockpit"
        title="资产主界面"
        description="先把资产全局看清楚，再进入分类管理、初始化与事件录入。"
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

      <section className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="总资产" value={formatMoney(totalMarketValue, 'CNY')} className="!rounded-xl !p-3" />
        <StatCard label="总收益" value={formatMoney(totalUnrealizedPnl, 'CNY')} hint={formatPct(totalCost > 0 ? (totalUnrealizedPnl / totalCost) * 100 : 0)} className="!rounded-xl !p-3" />
        <StatCard label="账户数量" value={accounts.length} hint={`持仓标的 ${positions.length} 个`} className="!rounded-xl !p-3" />
        <StatCard label="健康度" value={getStaticHealthLabel(healthScore)} hint={`Top1 ${formatPct(topPositionPct)}`} tone={getStaticHealthTone(healthScore)} className="!rounded-xl !p-3" />
      </section>

      {indices.length > 0 && (
        <section className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
          {indices.map((idx) => (
            <div key={idx.code} className="rounded-xl border border-border/60 bg-surface/60 p-3">
              <div className="text-xs text-secondary-text">{INDEX_LABELS[idx.code] || idx.code}</div>
              <div className="mt-1 text-lg font-semibold text-foreground">
                {idx.latestPrice != null ? idx.latestPrice.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--'}
              </div>
              {idx.pctChange != null && (
                <div className={`mt-0.5 text-xs ${idx.pctChange >= 0 ? 'text-red-500' : 'text-green-500'}`}>
                  {idx.pctChange >= 0 ? '+' : ''}{idx.pctChange.toFixed(2)}%
                </div>
              )}
            </div>
          ))}
        </section>
      )}

      <section className="grid gap-2 xl:grid-cols-12">
        <Card className="xl:col-span-8 !rounded-xl" padding="sm">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-base font-semibold text-foreground">主要市场日线概览</h2>
            <span className="text-xs text-secondary-text">近 60 个交易日，非实时</span>
          </div>
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {MARKET_CARDS.map((item) => {
              const points = seriesMap[item.key] || [];
              const latest = points.at(-1);
              const first = points[0];
              const change = latest && first ? ((latest.close - first.close) / first.close) * 100 : null;
              return (
                <div key={item.key} className="rounded-lg border border-border/60 bg-background/60 p-2.5">
                  <div className="mb-1.5 flex items-center justify-between">
                    <div>
                      <div className="text-sm font-medium text-foreground">{item.label}</div>
                      <div className="text-[11px] text-secondary-text">{item.code}</div>
                    </div>
                    <Badge variant={change != null && change >= 0 ? 'success' : 'danger'}>
                      {change == null ? '--' : `${change >= 0 ? '+' : ''}${change.toFixed(2)}%`}
                    </Badge>
                  </div>
                  <div className="h-24">
                    {points.length > 1 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={points}>
                          <Tooltip />
                          <Area type="monotone" dataKey="close" stroke="var(--color-cyan)" fill="rgba(0, 212, 255, 0.12)" strokeWidth={1.6} />
                        </AreaChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="flex h-full items-center justify-center text-xs text-secondary-text">暂无日线数据</div>
                    )}
                  </div>
                  <div className="mt-1.5 text-[11px] text-secondary-text">最新收盘 {latest?.close?.toFixed(2) ?? '--'}</div>
                </div>
              );
            })}
          </div>
        </Card>

        <Card className="xl:col-span-4 !rounded-xl" padding="sm">
          <div className="mb-2 flex items-center justify-between border-b border-border/50 pb-2">
            <h2 className="text-base font-semibold text-foreground">驾驶舱摘要</h2>
            <Badge variant={highRiskPositionCount > 0 ? 'warning' : 'success'}>{highRiskPositionCount > 0 ? '关注高风险仓位' : '结构稳定'}</Badge>
          </div>
          {assetSummary.length === 0 ? (
            <EmptyState title="暂无资产" description="先在资产初始化页创建账户并录入初始资产。" className="border-none bg-transparent px-2 py-8 shadow-none" />
          ) : (
            <div className="space-y-1.5">
              {assetSummary.map((item) => (
                <div key={item.market} className="grid grid-cols-[88px_1fr_112px] items-center gap-2 border-b border-border/40 py-1.5 text-[13px]">
                  <span className="text-secondary-text">{getMarketLabel(item.market)}</span>
                  <div className="h-2 overflow-hidden rounded-full bg-border/40">
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

          <div className="mt-3 grid gap-1.5 border-t border-border/50 pt-3 text-sm">
            {marketAlertRows.map((row) => (
              <div key={row.label} className="flex items-center justify-between rounded-lg bg-background/55 px-2.5 py-1.5">
                <span className="text-secondary-text">{row.label}</span>
                <Badge variant={row.tone === 'danger' ? 'danger' : row.tone === 'warning' ? 'warning' : 'success'}>{row.value}</Badge>
              </div>
            ))}
          </div>
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
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-base font-semibold text-foreground">健康度备注</h2>
            <Badge variant={getStaticHealthTone(healthScore) === 'danger' ? 'danger' : getStaticHealthTone(healthScore) === 'warning' ? 'warning' : 'success'}>
              {getStaticHealthLabel(healthScore)}
            </Badge>
          </div>
          <div className="space-y-2 text-sm text-secondary-text">
            <div className="rounded-lg border border-border/50 bg-background/60 p-2.5">
              <div className="text-foreground">组合健康结论</div>
              <div className="mt-1">当前页面按静态持仓结构展示，重点看仓位集中度、收益水平和高风险标的数量。</div>
            </div>
            <div className="rounded-lg border border-border/50 bg-background/60 p-2.5">
              <div className="text-foreground">当前关注点</div>
              <ul className="mt-1 space-y-1">
                <li>Top1 仓位占比：{formatPct(topPositionPct)}</li>
                <li>高风险标的：{highRiskPositionCount} 项</li>
                <li>静态未实现收益：{formatMoney(totalUnrealizedPnl, 'CNY')}</li>
              </ul>
            </div>
          </div>
        </Card>
      </section>
    </AppPage>
  );
};

export default AssetDashboardPage;
