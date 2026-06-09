import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { ApiErrorAlert, Button, Card, EmptyState, PageHeader } from '../components/common';
import { portfolioApi } from '../api/portfolio';
import type { PortfolioPositionRecordItem } from '../types/portfolio';
import { formatMoney, formatPct, formatPrice, formatSignedPct, getMarketLabel, localizeAssetCategory } from './assetsShared';
import { getParsedApiError, type ParsedApiError } from '../api/error';

const FILTER_CLASS = 'input-surface input-focus-glow h-9 rounded-lg border bg-transparent px-3 text-sm';

const normalizePositionSymbol = (symbol: string) => {
  const upper = (symbol || '').trim().toUpperCase();
  if (upper.startsWith('SH') || upper.startsWith('SZ') || upper.startsWith('BJ') || upper.startsWith('HK')) return upper.slice(2);
  if (upper.includes('.')) return upper.split('.')[0] || upper;
  return upper;
};

const getLocalMarketValue = (position: PortfolioPositionRecordItem) => Number(position.quantity || 0) * Number(position.lastPrice || 0);
const getLocalUnrealizedPnl = (position: PortfolioPositionRecordItem) => getLocalMarketValue(position) - Number(position.totalCost || 0);

const AssetOpenDatesPage: React.FC = () => {
  const [positions, setPositions] = useState<PortfolioPositionRecordItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [dismissingId, setDismissingId] = useState<number | null>(null);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [accountFilter, setAccountFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [currencyFilter, setCurrencyFilter] = useState('');
  const [openDateStart, setOpenDateStart] = useState('');
  const [openDateEnd, setOpenDateEnd] = useState('');

  useEffect(() => {
    document.title = '开放日跟踪 - NestCheck';
  }, []);

  const load = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await portfolioApi.listOpenDatePositions();
      setPositions(response.items || []);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const accountOptions = useMemo(
    () => Array.from(new Set(positions.map((item) => item.accountName).filter(Boolean))).sort(),
    [positions],
  );
  const categoryOptions = useMemo(
    () => Array.from(new Set(positions.map((item) => item.assetCategory || '').filter(Boolean))).sort(),
    [positions],
  );
  const currencyOptions = useMemo(
    () => Array.from(new Set(positions.map((item) => item.currency).filter(Boolean))).sort(),
    [positions],
  );

  const filteredPositions = useMemo(() => {
    return positions.filter((item) => {
      if (accountFilter && item.accountName !== accountFilter) return false;
      if (categoryFilter && (item.assetCategory || '') !== categoryFilter) return false;
      if (currencyFilter && item.currency !== currencyFilter) return false;
      const availableDate = item.availableDate || '';
      if (openDateStart && (!availableDate || availableDate < openDateStart)) return false;
      if (openDateEnd && (!availableDate || availableDate > openDateEnd)) return false;
      return true;
    });
  }, [accountFilter, categoryFilter, currencyFilter, openDateEnd, openDateStart, positions]);

  const totals = useMemo(() => {
    const marketValue = filteredPositions.reduce((sum, item) => sum + Number(item.marketValueBase || 0), 0);
    const unrealized = filteredPositions.reduce((sum, item) => sum + Number(item.unrealizedPnlBase || 0), 0);
    const totalCost = filteredPositions.reduce((sum, item) => sum + Number(item.totalCost || 0), 0);
    return { marketValue, unrealized, pnlPct: totalCost > 0 ? (unrealized / totalCost) * 100 : null };
  }, [filteredPositions]);

  const dismiss = async (id: number) => {
    setDismissingId(id);
    setError(null);
    try {
      await portfolioApi.dismissOpenDatePosition(id);
      setPositions((prev) => prev.filter((item) => item.id !== id));
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setDismissingId(null);
    }
  };

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Open Date Watch"
        title="开放日跟踪"
        description="集中跟踪交易事件中填写了开放日的资产，过期项目也会保留，取消关注后不再显示。"
      />
      {error ? <ApiErrorAlert error={error} /> : null}
      <Card className="!rounded-xl" padding="sm">
        <div className="mb-3 grid gap-2 text-sm md:grid-cols-3">
          <div className="rounded-lg border border-border/40 bg-background/40 px-3 py-2">跟踪项：{filteredPositions.length}</div>
          <div className="rounded-lg border border-border/40 bg-background/40 px-3 py-2">市值：{formatMoney(totals.marketValue, 'CNY')}</div>
          <div className="rounded-lg border border-border/40 bg-background/40 px-3 py-2">持仓收益：{formatMoney(totals.unrealized, 'CNY')} · {formatSignedPct(totals.pnlPct)}</div>
        </div>
        <div className="mb-3 grid gap-2 rounded-lg border border-border/40 bg-background/25 p-3 md:grid-cols-5">
          <select className={FILTER_CLASS} value={accountFilter} onChange={(event) => setAccountFilter(event.target.value)}>
            <option value="">全部账户</option>
            {accountOptions.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
          <select className={FILTER_CLASS} value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
            <option value="">全部大类</option>
            {categoryOptions.map((category) => <option key={category} value={category}>{localizeAssetCategory(category)}</option>)}
          </select>
          <select className={FILTER_CLASS} value={currencyFilter} onChange={(event) => setCurrencyFilter(event.target.value)}>
            <option value="">全部货币</option>
            {currencyOptions.map((currency) => <option key={currency} value={currency}>{currency}</option>)}
          </select>
          <input className={FILTER_CLASS} type="date" value={openDateStart} onChange={(event) => setOpenDateStart(event.target.value)} aria-label="开放日开始" />
          <input className={FILTER_CLASS} type="date" value={openDateEnd} onChange={(event) => setOpenDateEnd(event.target.value)} aria-label="开放日结束" />
        </div>
        {isLoading ? (
          <div className="h-40 animate-pulse rounded-xl bg-border/20" />
        ) : filteredPositions.length === 0 ? (
          <EmptyState title="暂无开放日资产" description="在资产事件的交易事件中填写开放日后，这里会展示跟踪列表。" />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border/40 bg-background/15">
            <table className="min-w-full text-[13px]" style={{ width: '100%' }}>
              <thead className="bg-surface/50 text-xs text-secondary-text">
                <tr>
                  <th className="px-2 py-1.5 text-left" style={{ minWidth: '128px' }}>账户</th>
                  <th className="px-2 py-1.5 text-left">市场</th>
                  <th className="px-2 py-1.5 text-left">代码</th>
                  <th className="px-2 py-1.5 text-left" style={{ minWidth: '120px' }}>名称</th>
                  <th className="px-2 py-1.5 text-left">大类</th>
                  <th className="px-1 py-1.5 text-right">数量</th>
                  <th className="px-1 py-1.5 text-right">币种</th>
                  <th className="px-2 py-1.5 text-right">成本价</th>
                  <th className="px-2 py-1.5 text-right">现价</th>
                  <th className="px-2 py-1.5 text-right">市值(CNY)</th>
                  <th className="px-2 py-1.5 text-right">持仓收益(CNY)</th>
                  <th className="px-2 py-1.5 text-right">收益率</th>
                  <th className="px-2 py-1.5 text-left">开放日</th>
                  <th className="px-2 py-1.5 text-left">取消关注</th>
                </tr>
              </thead>
              <tbody>
                {filteredPositions.map((row) => {
                  const localMarketValue = getLocalMarketValue(row);
                  const localUnrealizedPnl = getLocalUnrealizedPnl(row);
                  return (
                    <tr key={row.id} className="border-t border-border/30 odd:bg-background/70 even:bg-surface/15">
                      <td className="px-2 py-1.5 font-medium text-foreground whitespace-nowrap">{row.accountName}</td>
                      <td className="px-2 py-1.5">{getMarketLabel(row.market)}</td>
                      <td className="px-2 py-1.5 font-mono">{normalizePositionSymbol(row.symbol)}</td>
                      <td className="px-2 py-1.5 text-foreground">{row.name || '--'}</td>
                      <td className="px-2 py-1.5">{localizeAssetCategory(row.assetCategory)}</td>
                      <td className="px-1 py-1.5 text-right">{Number(row.quantity || 0).toLocaleString('zh-CN', { maximumFractionDigits: 4 })}</td>
                      <td className="px-1 py-1.5 text-right text-[11px]">{row.currency}</td>
                      <td className="px-3 py-1.5 text-right">{formatPrice(row.avgCost, row.currency, row)}</td>
                      <td className="px-2 py-1.5 text-right">{formatPrice(row.lastPrice, row.currency, row)}</td>
                      <td className="px-2 py-1.5 text-right font-medium"><div>{formatMoney(row.marketValueBase, 'CNY')}</div><div className="text-[11px] font-normal text-secondary-text">{formatMoney(localMarketValue, row.currency)}</div></td>
                      <td className="px-2 py-1.5 text-right"><div>{formatMoney(row.unrealizedPnlBase, 'CNY')}</div><div className="text-[11px] text-secondary-text">{formatMoney(localUnrealizedPnl, row.currency)}</div></td>
                      <td className="px-2 py-1.5 text-right">{formatPct(row.unrealizedPnlPct)}</td>
                      <td className="px-2 py-1.5 font-mono">{row.availableDate || '--'}</td>
                      <td className="px-2 py-1.5"><Button size="sm" variant="secondary" disabled={dismissingId === row.id} onClick={() => void dismiss(row.id)}>{dismissingId === row.id ? '处理中' : '取消关注'}</Button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
};

export default AssetOpenDatesPage;
