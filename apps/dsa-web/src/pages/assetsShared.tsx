import { useCallback, useEffect, useState } from 'react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { portfolioApi } from '../api/portfolio';
import { marketApi, type MarketIndexItem } from '../api/market';
import type {
  PortfolioAccountItem,
  PortfolioPositionRecordItem,
  PortfolioRiskResponse,
} from '../types/portfolio';

export type FlatPosition = PortfolioPositionRecordItem;

export function formatMoney(value: number | undefined | null, currency = 'CNY'): string {
  if (value == null || Number.isNaN(value)) return '--';
  return `${currency} ${Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function getAssetPriceDecimals(position: { symbol?: string | null; assetCategory?: string | null; assetSubcategory?: string | null }): number {
  const category = (position.assetCategory || '').trim().toLowerCase();
  const subcategory = (position.assetSubcategory || '').trim().toLowerCase();
  const symbol = (position.symbol || '').trim().toUpperCase().split('.')[0];
  const isExchangeFund = category.includes('etf')
    || category.includes('lof')
    || subcategory.includes('etf')
    || subcategory.includes('lof')
    || /^(510|511|512|513|515|516|517|518|159|160|161|162|163|164|165)/.test(symbol);
  if (isExchangeFund) return 3;
  if (category === 'fund') return 4;
  return 2;
}

export function formatPrice(
  value: number | undefined | null,
  currency = 'CNY',
  position?: { symbol?: string | null; assetCategory?: string | null; assetSubcategory?: string | null },
): string {
  if (value == null || Number.isNaN(value)) return '--';
  const decimals = position ? getAssetPriceDecimals(position) : 2;
  return `${currency} ${Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}

export function formatNav(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return '--';
  return Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
  });
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
  const hasDanger = risk.drawdown.alert || (risk.stopLoss?.triggeredCount ?? 0) > 0;
  const hasWarning = risk.concentration.alert
    || (risk.singleNameConcentration?.alert ?? false)
    || (risk.stopLoss?.nearCount ?? 0) > 0;
  if (hasDanger) return 'danger';
  if (hasWarning) return 'warning';
  return 'success';
}

export function getHealthLabel(risk: PortfolioRiskResponse | null): string {
  const tone = getHealthTone(risk);
  if (tone === 'success') return '健康';
  if (tone === 'warning') return '关注';
  return '预警';
}

export function getHealthDeductions(
  risk: PortfolioRiskResponse | null,
  positions: PortfolioPositionRecordItem[],
): Array<{ label: string; points: number }> {
  if (!risk) return [];
  const buckets = new Map<string, number>();

  // 1. Concentration (R4+R5)
  if (risk.concentration?.alert) {
    buckets.set('风险资产占比', 20);
  } else {
    const actual = risk.concentration?.r4R5ActualPct ?? risk.concentration?.topWeightPct ?? 0;
    const plan = risk.concentration?.r4R5PlannedPct ?? risk.thresholds?.concentrationAlertPct ?? 30;
    if (plan > 0 && actual / plan > 0.7) {
      buckets.set('风险资产占比', 10);
    }
  }

  // 2. Single Name Concentration
  const snc = risk.singleNameConcentration;
  let sncPoints = 0;
  if (snc?.stockBreachCount) sncPoints += 10;
  if (snc?.fundBreachCount) sncPoints += 10;
  if (sncPoints > 0) buckets.set('单票集中度', sncPoints);

  // 3. Drawdown
  if (risk.drawdown?.alert) {
    buckets.set('最大回撤', 30);
  } else if (risk.drawdown?.maxDrawdownPct) {
    const dd = risk.drawdown.maxDrawdownPct;
    const th = risk.thresholds?.drawdownAlertPct ?? 6;
    if (dd > th * 0.5) {
      buckets.set('最大回撤', 15);
    }
  }

  // 4. Stop Loss
  if (risk.stopLoss?.items && positions.length > 0) {
    const stockMap = new Set(positions.filter(p => (p.assetCategory || '').toLowerCase() === 'stock').map(p => p.symbol));
    const fundMap = new Set(positions.filter(p => (p.assetCategory || '').toLowerCase() === 'fund').map(p => p.symbol));

    const triggeredStocks = risk.stopLoss.items.filter(i => stockMap.has(i.symbol) && i.lossPct > 10).length;
    const triggeredFunds = risk.stopLoss.items.filter(i => fundMap.has(i.symbol) && i.lossPct > 2).length;
    const totalSlPoints = triggeredStocks * 5 + triggeredFunds * 5;
    
    if (totalSlPoints > 0) buckets.set('止损预警', totalSlPoints);
  }

  return Array.from(buckets.entries()).map(([label, points]) => ({ label, points }));
}

export function computeHealthScore(
  risk: PortfolioRiskResponse | null,
  positions: PortfolioPositionRecordItem[],
): number {
  if (!risk) {
    if (positions.length === 0) return 60;
    const totalMarketValue = positions.reduce((sum, p) => sum + Number(p.marketValueBase || 0), 0);
    const topPosValue = positions.reduce((max, p) => Math.max(max, Number(p.marketValueBase || 0)), 0);
    const topPosPct = totalMarketValue > 0 ? (topPosValue / totalMarketValue) * 100 : 0;
    let base = 90;
    if (topPosPct > 35) base -= 22;
    else if (topPosPct > 25) base -= 10;
    return Math.max(18, Math.min(100, base));
  }

  let score = 100;

  // 1. R4+R5 concentration (max 20 points)
  if (risk.concentration?.alert) {
    score -= 20;
  } else {
    const actualPct = risk.concentration?.r4R5ActualPct ?? risk.concentration?.topWeightPct ?? 0;
      const plannedPct = risk.concentration?.r4R5PlannedPct ?? risk.thresholds?.concentrationAlertPct ?? 30;
    if (plannedPct > 0 && actualPct / plannedPct > 0.7) score -= 10;
  }

  // 2. Single-name concentration (max 20 points)
  const snc = risk.singleNameConcentration;
  if (snc) {
    const stockBreaches = snc.stockBreachCount ?? 0;
    const fundBreaches = snc.fundBreachCount ?? 0;
    if (stockBreaches > 0) score -= Math.min(10, stockBreaches * 10);
    if (fundBreaches > 0) score -= Math.min(10, fundBreaches * 10);
  }

  // 3. Max drawdown (max 30 points)
  if (risk.drawdown?.alert) {
    score -= 30;
  } else if (risk.drawdown?.maxDrawdownPct) {
    const ddPct = risk.drawdown.maxDrawdownPct;
    const threshold = risk.thresholds?.drawdownAlertPct ?? 6;
    if (threshold > 0 && ddPct > threshold * 0.5) score -= 15;
  }

  // 4. Stop-loss alert (max 30 points)
  const sl = risk.stopLoss;
  if (sl?.items) {
    const stockPositions = new Map<string, string>();
    const fundPositions = new Map<string, string>();
    for (const p of positions) {
      const cat = (p.assetCategory || '').trim().toLowerCase();
      const sym = (p.symbol || '').toUpperCase();
      if (cat === 'stock') stockPositions.set(sym, cat);
      else if (cat === 'fund') fundPositions.set(sym, cat);
    }

    let stockLossCount = 0;
    let fundLossCount = 0;
    for (const item of sl.items) {
      const sym = (item.symbol || '').toUpperCase();
      if (stockPositions.has(sym) && item.lossPct > 10) stockLossCount++;
      if (fundPositions.has(sym) && item.lossPct > 2) fundLossCount++;
    }
    const totalStopLossDeduction = (stockLossCount + fundLossCount) * 5;
    score -= Math.min(30, totalStopLossDeduction);
  }

  return Math.max(18, Math.min(100, score));
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
  index: '指数',
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
  const [risk, setRisk] = useState<PortfolioRiskResponse | null>(null);
  const [positions, setPositions] = useState<FlatPosition[]>([]);
  const [indices, setIndices] = useState<MarketIndexItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<ParsedApiError | null>(null);

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

    // Load risk data in background; failure should not block the page
    setRisk(null);
    portfolioApi.getRisk({ costMethod: 'fifo' }).then((resp) => {
      setRisk(resp);
    }).catch(() => {
      // Silently ignore risk errors; page still works without health score
    });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return { accounts, risk, positions, indices, isLoading, error, reload: load };
}
