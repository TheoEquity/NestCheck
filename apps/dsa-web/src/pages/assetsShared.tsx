import { useCallback, useEffect, useState } from 'react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { portfolioApi } from '../api/portfolio';
import { marketApi, type MarketIndexItem } from '../api/market';
import type {
  PortfolioAccountItem,
  PortfolioPositionRecordItem,
  PortfolioRiskResponse,
  PortfolioSnapshotResponse,
} from '../types/portfolio';

export type FlatPosition = PortfolioPositionRecordItem;

export function formatMoney(value: number | undefined | null, currency = 'CNY'): string {
  if (value == null || Number.isNaN(value)) return '--';
  return `${currency} ${Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function formatPct(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return '--';
  return `${value.toFixed(2)}%`;
}

export function formatSignedPct(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return '--';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

export function getMarketLabel(market: string): string {
  if (market === 'cn') return 'A 股';
  if (market === 'hk') return '港股';
  if (market === 'us') return '美股';
  return market.toUpperCase();
}

export function getHealthTone(risk: PortfolioRiskResponse | null): 'success' | 'warning' | 'danger' {
  if (!risk) return 'warning';
  if (risk.drawdown.alert || risk.stopLoss.triggeredCount > 0) return 'danger';
  if (risk.concentration.alert || risk.stopLoss.nearAlert || risk.sectorConcentration.alert) return 'warning';
  return 'success';
}

export function getHealthLabel(risk: PortfolioRiskResponse | null): string {
  const tone = getHealthTone(risk);
  if (tone === 'success') return '健康';
  if (tone === 'warning') return '关注';
  return '预警';
}

export function getPositionRiskLevel(position: FlatPosition): '低' | '中' | '高' {
  const pct = position.unrealizedPnlPct ?? 0;
  if (position.market === 'us' || pct <= -12) return '高';
  if (position.market === 'hk' || pct <= -5) return '中';
  return '低';
}

export function getAssetCategory(position: FlatPosition): string {
  const symbol = position.symbol.toUpperCase();
  if (symbol.includes('ETF') || symbol.startsWith('51') || symbol.startsWith('15')) return 'ETF';
  if (position.market === 'us') return '美股';
  if (position.market === 'hk') return '港股';
  return 'A股';
}

const CATEGORY_LABELS: Record<string, string> = {
  stock: '股票',
  fund: '基金',
  bond: '债券',
  cash: '现金',
};

const SUBCATEGORY_LABELS: Record<string, string> = {
  pure_bond_fund: '纯债基金',
  fixed_income_plus: '固收+',
  index_fund: '指数基金',
  equity_fund: '股票基金',
};

export function localizeAssetCategory(value: string | null | undefined): string {
  const v = (value || '').trim().toLowerCase();
  return CATEGORY_LABELS[v] || (v ? v.charAt(0).toUpperCase() + v.slice(1) : '未分类');
}

export function localizeAssetSubcategory(value: string | null | undefined): string {
  const v = (value || '').trim().toLowerCase();
  return SUBCATEGORY_LABELS[v] || (v || '未分类');
}

export function usePortfolioOverview() {
  const [accounts, setAccounts] = useState<PortfolioAccountItem[]>([]);
  const [snapshot, setSnapshot] = useState<PortfolioSnapshotResponse | null>(null);
  const [risk, setRisk] = useState<PortfolioRiskResponse | null>(null);
  const [positions, setPositions] = useState<FlatPosition[]>([]);
  const [indices, setIndices] = useState<MarketIndexItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [accountsResp, positionsResp, indicesResp] = await Promise.all([
        portfolioApi.getAccounts(false),
        portfolioApi.listPositions({ costMethod: 'fifo' }),
        marketApi.getIndices(),
      ]);
      setAccounts(accountsResp.accounts || []);
      setPositions((positionsResp.items || []).slice().sort((a, b) => Number(b.marketValueBase || 0) - Number(a.marketValueBase || 0)));
      setIndices(indicesResp || []);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setIsLoading(false);
    }

    setSnapshot(null);
    setRisk(null);
  }, []);

  const refreshPrices = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const positionsResp = await portfolioApi.realtimeRevaluePositions({ costMethod: 'fifo' });
      setPositions((positionsResp.items || []).slice().sort((a, b) => Number(b.marketValueBase || 0) - Number(a.marketValueBase || 0)));
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  const syncData = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const positionsResp = await portfolioApi.realtimeRevaluePositions({ costMethod: 'fifo' });
      setPositions((positionsResp.items || []).slice().sort((a, b) => Number(b.marketValueBase || 0) - Number(a.marketValueBase || 0)));
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return { accounts, snapshot, risk, positions, indices, isLoading, error, reload: load, refreshPrices, syncData, isRefreshing };
}
