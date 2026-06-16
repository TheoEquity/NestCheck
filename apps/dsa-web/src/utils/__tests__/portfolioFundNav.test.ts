import { describe, expect, it } from 'vitest';
import { computeFundDailyNavChange, isFundNavResetBaselinePoint } from '../portfolioFundNav';

describe('portfolioFundNav', () => {
  it('computes daily nav change from the previous record on normal days', () => {
    const value = computeFundDailyNavChange([
      { recordDate: '2026-06-15', fundNav: 1.2, fundShares: 100, totalEquity: 120 },
      { recordDate: '2026-06-16', fundNav: 1.26, fundShares: 100, totalEquity: 126 },
    ]);

    expect(value).toBeCloseTo(5, 6);
  });

  it('returns zero when the latest point is a reset baseline', () => {
    const value = computeFundDailyNavChange([
      { recordDate: '2026-06-15', fundNav: 1.26, fundShares: 100, totalEquity: 126 },
      { recordDate: '2026-06-16', fundNav: 1, fundShares: 80, totalEquity: 80 },
    ]);

    expect(value).toBe(0);
    expect(isFundNavResetBaselinePoint({ recordDate: '2026-06-16', fundNav: 1, fundShares: 80, totalEquity: 80 })).toBe(true);
  });

  it('returns null when there is not enough history', () => {
    expect(computeFundDailyNavChange([{ recordDate: '2026-06-16', fundNav: 1, fundShares: 80, totalEquity: 80 }])).toBeNull();
  });
});
