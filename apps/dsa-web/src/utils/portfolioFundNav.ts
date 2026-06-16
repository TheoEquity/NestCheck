import type { PortfolioFundHistoryItem } from '../types/portfolio';

const RESET_NAV_EPSILON = 1e-6;

export function isFundNavResetBaselinePoint(item: PortfolioFundHistoryItem | null | undefined): boolean {
  if (!item) return false;
  return Math.abs(Number(item.fundNav || 0) - 1) <= RESET_NAV_EPSILON
    && Math.abs(Number(item.fundShares || 0) - Number(item.totalEquity || 0)) <= RESET_NAV_EPSILON;
}

export function computeFundDailyNavChange(items: PortfolioFundHistoryItem[]): number | null {
  if (items.length < 2) return null;
  const latest = items[items.length - 1];
  const previous = items[items.length - 2];
  if (!latest || !previous || previous.fundNav <= 0 || latest.recordDate === previous.recordDate) return null;
  if (isFundNavResetBaselinePoint(latest)) return 0;
  return ((latest.fundNav / previous.fundNav) - 1) * 100;
}
