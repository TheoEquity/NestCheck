import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { ApiErrorAlert, AppPage, Badge, Button, Card, EmptyState, PageHeader, StatCard } from '../components/common';
import { portfolioApi } from '../api/portfolio';
import type { PortfolioLatestFxRateItem, PortfolioPositionRecordItem } from '../types/portfolio';
import {
  formatMoney,
  formatPct,
  formatSignedPct,
  getPositionRiskLevel,
  getMarketLabel,
  localizeAssetCategory,
  // localizeAssetSubcategory, // reserved for future use
  usePortfolioOverview,
} from './assetsShared';

const FILTER_CLASS = 'input-surface input-focus-glow h-9 rounded-lg border bg-transparent px-3 text-sm';
const PIE_COLORS = ['#0f766e', '#2563eb', '#7c3aed', '#ea580c', '#dc2626', '#64748b'];

const getRiskBadgeVariant = (level: string) => {
  if (level === 'R5' || level === 'R4' || level === '高') return 'danger';
  if (level === 'R3' || level === 'R2' || level === '中') return 'warning';
  if (level === 'R1' || level === '低') return 'success';
  if (level === '高') return 'danger';
  if (level === '中') return 'warning';
  return 'success';
};

const normalizeAssetRiskClass = (value: string | null | undefined) => (value || '').trim().toUpperCase();
// Reserved for future use
// const normalizeAssetCategory = (value: string | null | undefined) => (value || '').trim();
// const normalizeAssetSubcategory = (value: string | null | undefined) => (value || '').trim();

// const getPositionCategoryLabel = (position: { assetCategory?: string | null; assetSubcategory?: string | null }) => {
//   const category = localizeAssetCategory(position.assetCategory);
//   const subcategory = localizeAssetSubcategory(position.assetSubcategory);
//   if (category !== '未分类' && subcategory !== '未分类') return `${category} / ${subcategory}`;
//   if (category !== '未分类') return category;
//   if (subcategory !== '未分类') return subcategory;
//   return '未分类';
// };

const normalizePositionSymbol = (symbol: string) => {
  const upper = (symbol || '').trim().toUpperCase();
  if (upper.startsWith('SH') || upper.startsWith('SZ') || upper.startsWith('BJ') || upper.startsWith('HK')) {
    return upper.slice(2);
  }
  if (upper.includes('.')) {
    return upper.split('.')[0] || upper;
  }
  return upper;
};

const getPieColor = (index: number) => PIE_COLORS[index % PIE_COLORS.length];

const PIE_TOOLTIP_STYLE = {
  backgroundColor: 'rgba(15, 23, 42, 0.94)',
  border: '1px solid rgba(148, 163, 184, 0.18)',
  borderRadius: '12px',
  color: '#e2e8f0',
};

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

const getHealthScore = (positions: PortfolioPositionRecordItem[]) => {
  if (positions.length === 0) return 60;
  const totalMarketValue = positions.reduce((sum, item) => sum + Number(item.marketValueBase || 0), 0);
  const highRiskValue = positions.reduce((sum, item) => {
    const riskClass = normalizeAssetRiskClass(item.assetRiskClass);
    return riskClass === 'R4' || riskClass === 'R5' ? sum + Number(item.marketValueBase || 0) : sum;
  }, 0);
  const topPositionValue = positions.reduce((max, item) => Math.max(max, Number(item.marketValueBase || 0)), 0);
  const highRiskPct = totalMarketValue > 0 ? (highRiskValue / totalMarketValue) * 100 : 0;
  const topPositionPct = totalMarketValue > 0 ? (topPositionValue / totalMarketValue) * 100 : 0;
  let score = 90;
  if (highRiskPct > 35) score -= 28;
  else if (highRiskPct > 20) score -= 14;
  if (topPositionPct > 35) score -= 22;
  else if (topPositionPct > 25) score -= 10;
  return Math.max(18, Math.min(96, score));
};

const getLocalMarketValue = (position: PortfolioPositionRecordItem) => Number(position.quantity || 0) * Number(position.lastPrice || 0);

const getLocalUnrealizedPnl = (position: PortfolioPositionRecordItem) => getLocalMarketValue(position) - Number(position.totalCost || 0);

type AdjustModalProps = {
  position: PortfolioPositionRecordItem | null;
  onClose: () => void;
  onConfirm: (quantity: number, lastPrice: number) => void;
  isSubmitting: boolean;
};

const AdjustModal: React.FC<AdjustModalProps> = ({ position, onClose, onConfirm, isSubmitting }) => {
  const [quantity, setQuantity] = useState('');
  const [lastPrice, setLastPrice] = useState('');

  useEffect(() => {
    if (position) {
      setQuantity(String(position.quantity || ''));
      setLastPrice(String(position.lastPrice || ''));
    }
  }, [position]);

  if (!position) return null;

  const displaySymbol = (() => {
    return `${position.symbol}.${position.market.toUpperCase()}`;
  })();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60" />
      <div
        className="relative z-10 w-full max-w-md rounded-xl border border-border/40 bg-surface p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-base font-semibold text-foreground">
          调整持仓: {displaySymbol}
        </h3>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-xs text-secondary-text">证券代码</label>
            <div className="rounded-lg border border-border/40 bg-background/30 px-3 py-2 text-sm font-mono text-foreground">
              {displaySymbol}
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-secondary-text">币种</label>
            <div className="rounded-lg border border-border/40 bg-background/30 px-3 py-2 text-sm text-foreground">
              {position.currency}
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-secondary-text">数量</label>
            <input
              type="number"
              step="any"
              className="input-surface input-focus-glow h-10 w-full rounded-lg border bg-transparent px-3 text-sm"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              placeholder="持仓数量"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-secondary-text">现价</label>
            <div className="flex gap-2">
              <input
                type="number"
                step="any"
                className="input-surface input-focus-glow h-10 w-full rounded-lg border bg-transparent px-3 text-sm"
                value={lastPrice}
                onChange={(e) => setLastPrice(e.target.value)}
                placeholder="最新价格"
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-secondary-text">成本价 (只读)</label>
            <div className="rounded-lg border border-border/40 bg-background/30 px-3 py-2 text-sm text-foreground">
              {formatMoney(position.avgCost, position.currency)}
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-secondary-text">当前市值 (估算)</label>
            <div className="rounded-lg border border-border/40 bg-background/30 px-3 py-2 text-sm text-foreground">
              {formatMoney(Number(quantity || 0) * Number(lastPrice || 0), position.currency)}
            </div>
          </div>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            className="btn-secondary !rounded-lg !px-4 !py-2 !text-sm disabled:opacity-60"
            onClick={onClose}
            disabled={isSubmitting}
          >
            取消
          </button>
          <button
            type="button"
            className="btn-primary !rounded-lg !px-4 !py-2 !text-sm disabled:opacity-60"
            onClick={() => {
              const qty = parseFloat(quantity);
              const price = parseFloat(lastPrice);
              if (isNaN(qty) || isNaN(price)) return;
              onConfirm(qty, price);
            }}
            disabled={isSubmitting}
          >
            {isSubmitting ? '保存中...' : '确认调整'}
          </button>
        </div>
      </div>
    </div>
  );
};

const HealthGauge: React.FC<{ score: number; tone: 'success' | 'warning' | 'danger' }> = ({ score, tone }) => {
  const radius = 28;
  const circumference = Math.PI * radius;
  const progress = circumference * (score / 100);
  const color = tone === 'danger' ? '#ef4444' : tone === 'warning' ? '#f59e0b' : '#10b981';
  return (
    <div className="relative h-16 w-20 shrink-0">
      <svg viewBox="0 0 80 48" className="h-full w-full overflow-visible">
        <path d="M 12 40 A 28 28 0 0 1 68 40" fill="none" stroke="rgba(148,163,184,0.18)" strokeWidth="7" strokeLinecap="round" />
        <path
          d="M 12 40 A 28 28 0 0 1 68 40"
          fill="none"
          stroke={color}
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={`${progress} ${circumference}`}
        />
      </svg>
      <div className="absolute inset-x-0 bottom-0 text-center text-lg font-semibold text-foreground">{score}</div>
    </div>
  );
};

const MiniPieCard: React.FC<{
  title: string;
  subtitle?: React.ReactNode;
  data: Array<{ name: string; value: number; displayValue?: number; secondaryLabel?: string }>;
  showCurrency?: boolean;
}> = ({ title, subtitle, data, showCurrency = true }) => {
  const nonZeroData = data.filter((item) => item.value > 0);
  const total = nonZeroData.reduce((sum, item) => sum + item.value, 0);

  return (
    <Card className="!rounded-xl" padding="sm">
      <div className="mb-2">
        <h2 className="text-base font-semibold text-foreground">{title}</h2>
        {subtitle ? <div className="mt-0.5 text-xs text-secondary-text">{subtitle}</div> : null}
      </div>
      {nonZeroData.length === 0 ? <EmptyState title="暂无数据" description="当前没有可用于统计的资产数据。" className="border-none bg-transparent px-2 py-8 shadow-none" /> : (
        <div className="grid gap-2 xl:grid-cols-[220px_1fr]">
          <div className="h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={nonZeroData} dataKey="value" nameKey="name" innerRadius={52} outerRadius={82} paddingAngle={2} stroke="rgba(15,23,42,0.08)">
                  {nonZeroData.map((entry, index) => <Cell key={entry.name} fill={getPieColor(index)} />)}
                </Pie>
                <Tooltip
                  formatter={(value) => {
                    const num = Math.round(Number(value || 0)).toLocaleString();
                    return showCurrency ? [`${num}`, ''] : [num, ''];
                  }}
                  contentStyle={PIE_TOOLTIP_STYLE}
                  itemStyle={{ color: '#e2e8f0' }}
                  labelStyle={{ color: '#94a3b8' }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="space-y-1.5">
            {nonZeroData.map((item, index) => {
              const weight = total > 0 ? (item.value / total) * 100 : 0;
              const num = Math.round((item.displayValue ?? item.value)).toLocaleString();
              return (
                <div key={item.name} className="flex items-center justify-between rounded-lg border border-border/40 bg-background/20 px-3 py-2 text-sm">
                  <div className="flex items-center gap-2">
                     <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: getPieColor(index) }} />
                    <div>
                      <div className="text-foreground">{item.name}</div>
                      {item.secondaryLabel ? <div className="text-xs text-secondary-text">{item.secondaryLabel}</div> : null}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-medium text-foreground">{formatPct(weight)}</div>
                    <div className="text-xs text-secondary-text">{showCurrency ? formatMoney(item.value, 'RMB') : num}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Card>
  );
};

const AssetManagementPage: React.FC = () => {
  useEffect(() => {
    document.title = '资产管理 - NestCheck';
  }, []);

  const { accounts, positions, error, syncData, isRefreshing } = usePortfolioOverview();
  const [fxRates, setFxRates] = useState<PortfolioLatestFxRateItem[]>([]);
  const [categoryFilter, setCategoryFilter] = useState('全部');
  const [accountFilter, setAccountFilter] = useState('全部');
  const [riskFilter, setRiskFilter] = useState('全部');
  const [currencyFilter, setCurrencyFilter] = useState('全部');
  const [sortKey, setSortKey] = useState<'marketValueBase' | 'unrealizedPnlPct' | 'currency' | 'symbol'>('marketValueBase');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [adjustTarget, setAdjustTarget] = useState<PortfolioPositionRecordItem | null>(null);
  const [isAdjusting, setIsAdjusting] = useState(false);
  const accountOptions = useMemo(() => ['全部', ...new Set(positions.map((item) => item.accountName))], [positions]);
  const categoryOptions = useMemo(() => ['全部', ...new Set(positions.map((item) => localizeAssetCategory(item.assetCategory)))], [positions]);
  const riskOptions = useMemo(() => ['全部', ...new Set(positions.map((item) => normalizeAssetRiskClass(item.assetRiskClass) || getPositionRiskLevel(item)))], [positions]);
  const currencyOptions = useMemo(() => ['全部', ...new Set(positions.map((item) => item.currency))], [positions]);

  const filteredPositions = useMemo(() => {
    const rows = positions.filter((row) => {
      if (accountFilter !== '全部' && row.accountName !== accountFilter) return false;
      if (categoryFilter !== '全部' && localizeAssetCategory(row.assetCategory) !== categoryFilter) return false;
      if (riskFilter !== '全部' && (normalizeAssetRiskClass(row.assetRiskClass) || getPositionRiskLevel(row)) !== riskFilter) return false;
      if (currencyFilter !== '全部' && row.currency !== currencyFilter) return false;
      return true;
    });

    rows.sort((a, b) => {
      const direction = sortDirection === 'asc' ? 1 : -1;
      if (sortKey === 'marketValueBase') return (a.marketValueBase - b.marketValueBase) * direction;
      if (sortKey === 'unrealizedPnlPct') return ((a.unrealizedPnlPct || 0) - (b.unrealizedPnlPct || 0)) * direction;
      if (sortKey === 'currency') return a.currency.localeCompare(b.currency) * direction;
      return a.symbol.localeCompare(b.symbol) * direction;
    });
    return rows;
  }, [accountFilter, categoryFilter, currencyFilter, positions, riskFilter, sortDirection, sortKey]);

  const filteredMarketValue = useMemo(
    () => filteredPositions.reduce((sum, item) => sum + Number(item.marketValueBase || 0), 0),
    [filteredPositions],
  );

  const filteredAvgReturn = useMemo(
    () => (filteredPositions.length > 0
      ? filteredPositions.reduce((sum, item) => sum + Number(item.unrealizedPnlPct || 0), 0) / filteredPositions.length
      : null),
    [filteredPositions],
  );

  const totalMarketValue = useMemo(
    () => positions.reduce((sum, item) => sum + Number(item.marketValueBase || 0), 0),
    [positions],
  );

  const totalUnrealizedPnl = useMemo(
    () => positions.reduce((sum, item) => sum + Number(item.unrealizedPnlBase || 0), 0),
    [positions],
  );

  const totalCost = useMemo(
    () => positions.reduce((sum, item) => sum + Number(item.totalCost || 0), 0),
    [positions],
  );

  const highRiskPositionPct = useMemo(() => {
    if (totalMarketValue <= 0) return 0;
    const highRiskValue = positions.reduce((sum, item) => {
      const riskClass = normalizeAssetRiskClass(item.assetRiskClass);
      return riskClass === 'R4' || riskClass === 'R5' ? sum + Number(item.marketValueBase || 0) : sum;
    }, 0);
    return (highRiskValue / totalMarketValue) * 100;
  }, [positions, totalMarketValue]);

  const healthScore = getHealthScore(positions);
  const healthTone = getStaticHealthTone(healthScore);

  const riskAllocationData = useMemo(() => {
    const buckets = { 基座: 0, 主体: 0, 机会仓: 0 };
    for (const position of positions) {
      const riskClass = normalizeAssetRiskClass(position.assetRiskClass);
      const value = Number(position.marketValueBase || 0);
      if (riskClass === 'R1') buckets.基座 += value;
      else if (riskClass === 'R2' || riskClass === 'R3') buckets.主体 += value;
      else if (riskClass === 'R4' || riskClass === 'R5') buckets.机会仓 += value;
    }
    return [
      { name: '基座', value: buckets.基座 },
      { name: '主体', value: buckets.主体 },
      { name: '机会仓', value: buckets.机会仓 },
    ];
  }, [positions]);

  const stockConcentrationData = useMemo(() => {
    const stockRows = positions.filter((item) => {
      const category = (item.assetCategory || '').trim().toLowerCase();
      return category === 'stock';
    });
    const sorted = [...stockRows].sort((a, b) => Number(b.marketValueBase || 0) - Number(a.marketValueBase || 0));
    const topFive = sorted.slice(0, 5).map((item) => ({
      name: normalizePositionSymbol(item.symbol),
      secondaryLabel: item.name || undefined,
      value: Number(item.marketValueBase || 0),
    }));
    const otherValue = sorted.slice(5).reduce((sum, item) => sum + Number(item.marketValueBase || 0), 0);
    return otherValue > 0 ? [...topFive, { name: '其他', value: otherValue }] : topFive;
  }, [positions]);

  const currencyAllocationData = useMemo(() => {
    const rawTotals = new Map<string, number>();
    const baseTotals = new Map<string, number>();
    const rateMap = new Map<string, number>();
    for (const item of fxRates) {
      rateMap.set((item.fromCurrency || '').toUpperCase(), Number(item.rate || 0));
    }
    for (const position of positions) {
      const currency = (position.currency || '').toUpperCase();
      const rawValue = Number(position.quantity || 0) * Number(position.lastPrice || 0);
      rawTotals.set(currency, (rawTotals.get(currency) || 0) + rawValue);
      const rate = currency === 'CNY' ? 1 : (rateMap.get(currency) || 0);
      const baseValue = currency === 'CNY' ? rawValue : rawValue * rate;
      baseTotals.set(currency, (baseTotals.get(currency) || 0) + baseValue);
    }
    return [
      { name: 'CNY', value: baseTotals.get('CNY') || 0, displayValue: rawTotals.get('CNY') || 0 },
      { name: 'USD', value: baseTotals.get('USD') || 0, displayValue: rawTotals.get('USD') || 0 },
      { name: 'HKD', value: baseTotals.get('HKD') || 0, displayValue: rawTotals.get('HKD') || 0 },
    ];
  }, [fxRates, positions]);

  const fxSummaryText = useMemo(() => {
    const rates = new Map<string, number>();
    for (const item of fxRates) {
      if (!rates.has(item.pair)) {
        rates.set(item.pair, Number(item.rate || 0));
      }
    }
    const usdRate = rates.get('CNY/USD');
    const hkdRate = rates.get('CNY/HKD');
    return `CNY/USD ${usdRate ? usdRate.toFixed(2) : '--'} · CNY/HKD ${hkdRate ? hkdRate.toFixed(2) : '--'}`;
  }, [fxRates]);

  useEffect(() => {
    let active = true;
    void portfolioApi.getLatestFxRates({ toCurrency: 'CNY' })
      .then((response) => {
        if (!active) return;
        setFxRates(response.items || []);
      })
      .catch(() => {
        if (!active) return;
        setFxRates([]);
      });
    return () => {
      active = false;
    };
  }, [isRefreshing]);

  const toggleSort = (key: 'marketValueBase' | 'unrealizedPnlPct' | 'currency' | 'symbol') => {
    if (sortKey === key) {
      setSortDirection((prev) => prev === 'desc' ? 'asc' : 'desc');
      return;
    }
    setSortKey(key);
    setSortDirection(key === 'symbol' || key === 'currency' ? 'asc' : 'desc');
  };

  const getSortLabel = (key: 'marketValueBase' | 'unrealizedPnlPct' | 'currency' | 'symbol') => {
    if (sortKey !== key) return '';
    return sortDirection === 'desc' ? '↓' : '↑';
  };

  const handleAdjustConfirm = async (quantity: number, lastPrice: number) => {
    if (!adjustTarget) return;
    setIsAdjusting(true);
    try {
      await portfolioApi.adjustPosition(adjustTarget.id, { quantity, last_price: lastPrice });
      await syncData();
      setAdjustTarget(null);
    } catch (err) {
      console.error('调整持仓失败:', err);
    } finally {
      setIsAdjusting(false);
    }
  };

  return (
    <AppPage className="max-w-[1600px] space-y-3">
      <PageHeader
        eyebrow="Portfolio Governance"
        title="资产管理"
        description="面向组合层管理资产结构、健康度与配置比例。"
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

      <section className="grid gap-2 xl:grid-cols-[1.2fr_0.9fr_1.2fr]">
        <StatCard
          label="总资产"
          value={formatMoney(totalMarketValue, 'CNY')}
          hint={<span>账户数 {accounts.length}</span>}
          className="!rounded-xl !p-3"
        />
        <StatCard
          label="总收益"
          value={formatMoney(totalUnrealizedPnl, 'CNY')}
          hint={formatSignedPct(totalCost > 0 ? (totalUnrealizedPnl / totalCost) * 100 : 0)}
          className="!rounded-xl !p-3"
        />
        <Card className="!rounded-xl" padding="sm">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-xs uppercase tracking-[0.22em] text-secondary-text">健康度</div>
              <div className="mt-1 text-2xl font-semibold text-foreground">{getStaticHealthLabel(healthScore)}</div>
              <div className="mt-1 text-sm text-secondary-text">高风险仓位 {formatPct(highRiskPositionPct)}</div>
            </div>
            <div className="flex items-center gap-3">
              <HealthGauge score={healthScore} tone={healthTone} />
              <Button
                onClick={() => void syncData()}
                disabled={isRefreshing}
                variant="primary"
                size="sm"
                className="!px-3 !py-1.5"
              >
                {isRefreshing ? '重估中...' : '重估'}
              </Button>
            </div>
          </div>
        </Card>
      </section>

      <section className="grid gap-2 xl:grid-cols-3">
        <MiniPieCard
          title="风险等级占比"
          subtitle="按资产初始化风险分类聚合：基座=R1，主体=R2+R3，机会仓=R4+R5"
          data={riskAllocationData}
          showCurrency
        />
        <MiniPieCard
          title="股票仓位占比"
          subtitle="股票总金额取前五大仓位，剩余仓位并入其他"
          data={stockConcentrationData}
          showCurrency
        />
        <MiniPieCard
          title="币种占比"
          subtitle={<span>人民币、美元、港币 | <span className="font-mono">{fxSummaryText}</span></span>}
          data={currencyAllocationData}
          showCurrency={false}
        />
      </section>

      <Card className="!rounded-xl" padding="sm">
        <div className="mb-2 flex flex-col gap-2 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <h2 className="text-base font-semibold text-foreground">资产台账</h2>
            <p className="mt-0.5 text-xs text-secondary-text">以高密度表格视图管理所有持仓资产，支持手动调整。</p>
          </div>
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-[180px_160px_160px_140px_180px]">
            <select className={FILTER_CLASS} value={accountFilter} onChange={(e) => setAccountFilter(e.target.value)}>
              {accountOptions.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select className={FILTER_CLASS} value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
              {categoryOptions.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select className={FILTER_CLASS} value={riskFilter} onChange={(e) => setRiskFilter(e.target.value)}>
              {riskOptions.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select className={FILTER_CLASS} value={currencyFilter} onChange={(e) => setCurrencyFilter(e.target.value)}>
              {currencyOptions.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <div className="flex items-center rounded-lg border border-border/60 bg-background/60 px-3 text-xs text-secondary-text">
              当前 {filteredPositions.length} / {positions.length}
            </div>
          </div>
        </div>
        {positions.length === 0 ? <EmptyState title="暂无持仓数据" description="完成初始化后，这里会展示资产台账。" className="border-none bg-transparent px-2 py-8 shadow-none" /> : (
          <div className="overflow-x-auto rounded-lg border border-border/40 bg-background/15">
            <table className="min-w-full text-[13px]" style={{width: '100%'}}>
              <thead className="bg-surface/50 text-xs text-secondary-text">
                <tr>
                  <th className="px-2 py-1.5 text-left" style={{minWidth: '128px'}}>账户</th>
                  <th className="px-2 py-1.5 text-left">市场</th>
                  <th className="px-2 py-1.5 text-left" style={{minWidth: '64px'}}>
                    <button type="button" className="inline-flex items-center gap-1" onClick={() => toggleSort('symbol')}>
                      代码 {getSortLabel('symbol')}
                    </button>
                  </th>
                  <th className="px-2 py-1.5 text-left" style={{minWidth: '120px'}}>名称</th>
                  <th className="px-2 py-1.5 text-left">大类</th>
                  <th className="px-1 py-1.5 text-left" style={{minWidth: '50px'}}>风险等级</th>
                  <th className="px-1 py-1.5 text-right">数量</th>
                  <th className="px-1 py-1.5 text-right" style={{minWidth: '36px'}}>币种</th>
                  <th className="px-2 py-1.5 text-right">成本价</th>
                  <th className="px-2 py-1.5 text-right">现价</th>
                  <th className="px-2 py-1.5 text-right">
                    <button type="button" className="inline-flex items-center gap-1" onClick={() => toggleSort('marketValueBase')}>
                      市值(CNY) {getSortLabel('marketValueBase')}
                    </button>
                  </th>
                  <th className="px-2 py-1.5 text-right">未实现盈亏(CNY)</th>
                  <th className="px-2 py-1.5 text-right">
                    <button type="button" className="inline-flex items-center gap-1" onClick={() => toggleSort('unrealizedPnlPct')}>
                      收益率 {getSortLabel('unrealizedPnlPct')}
                    </button>
                  </th>
                  <th className="px-2 py-1.5 text-left" style={{minWidth: '48px'}}>操作</th>
                </tr>
              </thead>
                <tbody>
                  {filteredPositions.map((row) => {
                    const localMarketValue = getLocalMarketValue(row);
                    const localUnrealizedPnl = getLocalUnrealizedPnl(row);
                    return (
                    <tr key={`${row.accountId}-${row.symbol}-${row.market}`} className="border-t border-border/30 odd:bg-background/70 even:bg-surface/15">
                      <td className="px-2 py-1.5 font-medium text-foreground whitespace-nowrap" style={{minWidth: '128px', maxWidth: '160px'}}>{row.accountName}</td>
                      <td className="px-2 py-1.5">{getMarketLabel(row.market)}</td>
                      <td className="px-2 py-1.5 font-mono">{row.symbol}</td>
                      <td className="px-2 py-1.5 text-foreground">{row.name || '--'}</td>
                      <td className="px-2 py-1.5">{localizeAssetCategory(row.assetCategory)}</td>
                      <td className="px-1 py-1.5">
                        <Badge variant={getRiskBadgeVariant(normalizeAssetRiskClass(row.assetRiskClass))} className="!px-1.5 !py-0 text-[11px]">
                          {normalizeAssetRiskClass(row.assetRiskClass)}
                        </Badge>
                      </td>
                      <td className="px-1 py-1.5 text-right">{Number(row.quantity || 0).toLocaleString('zh-CN', { maximumFractionDigits: 4 })}</td>
                      <td className="px-1 py-1.5 text-right text-[11px]">{row.currency}</td>
                      <td className="px-3 py-1.5 text-right" style={{minWidth: '112px'}}>{formatMoney(row.avgCost, row.currency)}</td>
                      <td className="px-2 py-1.5 text-right">{formatMoney(row.lastPrice, row.currency)}</td>
                      <td className="px-2 py-1.5 text-right font-medium">
                        <div>{formatMoney(row.marketValueBase, 'CNY')}</div>
                        <div className="text-[11px] font-normal text-secondary-text">{formatMoney(localMarketValue, row.currency)}</div>
                      </td>
                      <td className="px-2 py-1.5 text-right">
                        <div>{formatMoney(row.unrealizedPnlBase, 'CNY')}</div>
                        <div className="text-[11px] text-secondary-text">{formatMoney(localUnrealizedPnl, row.currency)}</div>
                      </td>
                      <td className="px-2 py-1.5 text-right">{formatSignedPct(row.unrealizedPnlPct)}</td>
                      <td className="px-2 py-1.5">
                        <button
                          type="button"
                          className="rounded-md border border-border/40 bg-background/40 px-2.5 py-1 text-xs text-foreground hover:bg-surface/80"
                          onClick={() => setAdjustTarget(row)}
                        >
                          调整
                        </button>
                      </td>
                    </tr>
                  );})}
                </tbody>
                <tfoot>
                  <tr className="border-t border-border/60 bg-background/50 text-sm font-medium">
                    <td className="px-2 py-2" colSpan={10}>当前筛选汇总</td>
                    <td className="px-2 py-2 text-right">{formatMoney(filteredMarketValue, 'CNY')}</td>
                    <td className="px-2 py-2 text-right">{formatMoney(filteredPositions.reduce((sum, item) => sum + Number(item.unrealizedPnlBase || 0), 0), 'CNY')}</td>
                    <td className="px-2 py-2 text-right">{formatSignedPct(filteredAvgReturn)}</td>
                    <td className="px-2 py-2"></td>
                  </tr>
                </tfoot>
              </table>
          </div>
        )}
      </Card>

      <AdjustModal
        position={adjustTarget}
        onClose={() => setAdjustTarget(null)}
        onConfirm={handleAdjustConfirm}
        isSubmitting={isAdjusting}
      />
    </AppPage>
  );
};

export default AssetManagementPage;
