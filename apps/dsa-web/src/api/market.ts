import apiClient from './index';
import { toCamelCase } from './utils';

export interface MarketIndexItem {
  code: string;
  name: string;
  latestPrice: number | null;
  pctChange: number | null;
  volume: number | null;
  updatedAt: string | null;
}

export interface MarketRiskItem {
  status: string;
  badge: string;
  description?: string;
  value?: number;
  percentile?: number;
  spread?: number;
  us10y?: number;
  cn10y?: number;
}

export interface MarketRiskResponse {
  snapshotDate: string;
  chineseVix: MarketRiskItem;
  usVix: MarketRiskItem;
  dollarStrength: MarketRiskItem;
  bondSpread: MarketRiskItem;
}

export interface WeeklyDataPoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ma10?: number | null;
  ma20?: number | null;
  ma50?: number | null;
}

export interface MarketEnvironment {
  trend: string;
  volatility: string;
  supportPct: number | null;
  supportStatus: string;
  label: string;
  color: string;
}

export interface MarketTrendItem {
  label: string;
  code: string;
  close: number;
  dailyClose: number | null;
  dailyPctChg: number | null;
  ma10: number;
  ma20: number;
  ma50: number;
  weeklyData: WeeklyDataPoint[];
  environment: MarketEnvironment;
  error?: string;
}

export interface MarketTrendResponse {
  snapshotDate: string;
  data: Record<string, MarketTrendItem>;
}

export interface MonthlySeasonalityResponse {
  index: string;
  yearsStat: number;
  months: string[];
  avgReturns: number[];
  winRates: number[];
}

export interface RiskRadarResponse {
  volatility: number;
  drawdown: number;
  correlation: number;
  spread: number;
  fx: number;
  valuation: number;
  details: Record<string, number | null>;
  error: string | null;
  label: string;
}

export interface CorrelationMatrixResponse {
  labels: string[];
  data: Array<[number, number, number]>;
  error: string | null;
}

export interface MarketRefreshResponse {
  refreshedAt: string;
  items: Record<string, { status: string; refreshedAt?: string | null; error?: string }>;
}

export interface EquityRatioResponse {
  equityRatio: number;
  plannedEquityRatio?: number | null;
  activeAllocationPlanId?: number | null;
  activeAllocationPlanGeneratedAt?: string | null;
  totalCny: number;
  equityCny: number;
  detail: Record<string, { total: number; equity: number; weight: number }>;
}

export interface SectorEtfConfig {
  id: number;
  sector: string;
  tsCode: string;
  name: string | null;
  weight: number;
  isCore: boolean;
  sortOrder: number;
  updatedAt?: string | null;
}

export interface SectorEtfItem extends SectorEtfConfig {
  date: string | null;
  close: number | null;
  dailyPctChg: number | null;
  monthPctChg: number | null;
  rs: number | null;
  status: string;
}

export interface SectorEtfDashboardResponse {
  snapshotDate: string;
  benchmark: { code: string; monthPctChg: number | null };
  items: SectorEtfItem[];
  topGainers: SectorEtfItem[];
  topLosers: SectorEtfItem[];
  monthlyRankings: SectorEtfItem[];
  configs: SectorEtfConfig[];
  updatedAt: string;
}

export const marketApi = {
  async getIndices(): Promise<MarketIndexItem[]> {
    const response = await apiClient.get<Record<string, unknown>[]>('/api/v1/market/indices');
    return response.data.map((item) => toCamelCase<MarketIndexItem>(item));
  },

  async getRisk(): Promise<MarketRiskResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/market/risk');
    return toCamelCase<MarketRiskResponse>(response.data);
  },

  async getTrend(refreshToken?: number): Promise<MarketTrendResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/market/trend', {
      params: refreshToken ? { t: refreshToken } : undefined,
    });
    return toCamelCase<MarketTrendResponse>(response.data);
  },

  async getSeasonality(): Promise<MonthlySeasonalityResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/market/seasonality');
    return toCamelCase<MonthlySeasonalityResponse>(response.data);
  },

  async getRadar(): Promise<RiskRadarResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/market/radar');
    return toCamelCase<RiskRadarResponse>(response.data);
  },

  async getCorrelation(): Promise<CorrelationMatrixResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/market/correlation');
    return toCamelCase<CorrelationMatrixResponse>(response.data);
  },

  async refreshDashboard(): Promise<MarketRefreshResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/market/refresh');
    return toCamelCase<MarketRefreshResponse>(response.data);
  },

  async getEquityRatio(): Promise<EquityRatioResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/market/equity-ratio');
    return toCamelCase<EquityRatioResponse>(response.data);
  },

  async getSectorEtfs(forceRefresh = false): Promise<SectorEtfDashboardResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/market/sector-etfs', {
      params: forceRefresh ? { force_refresh: true } : undefined,
    });
    return toCamelCase<SectorEtfDashboardResponse>(response.data);
  },

  async updateSectorEtfConfig(sector: string, input: Partial<Pick<SectorEtfConfig, 'tsCode' | 'name' | 'weight' | 'isCore'>>): Promise<SectorEtfConfig> {
    const response = await apiClient.patch<Record<string, unknown>>(`/api/v1/market/sector-etfs/configs/${encodeURIComponent(sector)}`, {
      ts_code: input.tsCode,
      name: input.name,
      weight: input.weight,
      is_core: input.isCore,
    });
    return toCamelCase<SectorEtfConfig>(response.data);
  },
};
