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

export const marketApi = {
  async getIndices(): Promise<MarketIndexItem[]> {
    const response = await apiClient.get<Record<string, unknown>[]>('/api/v1/market/indices');
    return response.data.map((item) => toCamelCase<MarketIndexItem>(item));
  },
};
