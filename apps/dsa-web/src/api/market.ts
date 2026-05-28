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
}

export interface MarketRiskResponse {
  snapshotDate: string;
  stockValuation: MarketRiskItem;
  bondSignal: MarketRiskItem;
  dollarStrength: MarketRiskItem;
  vix: MarketRiskItem;
  temperature: string;
  badge: string;
  advice: string;
  score: number;
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
};
