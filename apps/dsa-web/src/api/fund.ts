import apiClient from './index';
import { toCamelCase, toSnakeCase } from './utils';

export interface FundItem {
  fund_code: string;
  fund_name: string;
  fund_type?: string;
  fund_manager?: string;
  management_company?: string;
  inception_date?: string;
  fund_size?: number;
  risk_level?: string;
  status?: string;
}

export interface NavItem {
  fund_code: string;
  nav_date: string;
  unit_nav: number;
  accumulated_nav?: number;
  daily_return?: number;
  daily_change?: number;
}

export interface HoldingItem {
  fund_code: string;
  report_date: string;
  stock_code: string;
  stock_name: string;
  stock_market?: string;
  holding_pct?: number;
  holding_shares?: number;
  holding_amount?: number;
  rank?: number;
}

export interface FundAnalysisResult {
  fund_code: string;
  fund_name: string;
  fund_type: string;
  fund_manager: string;
  net_value_trend: string;
  holding_concentration: string;
  investment_advice: string;
  raw_nav_summary?: Record<string, unknown>;
  raw_holdings?: string[];
}

export interface FundAnalyzeResponse {
  fund_code: string;
  market?: string;
  asset_category?: string;
  elapsed: number;
  report: FundAnalysisResult;
  info: FundItem;
  nav_summary: Record<string, unknown>;
  top_holdings: string[];
}

export interface FundAnalyzeInput {
  market: string;
  assetCategory: string;
  symbol: string;
  name: string;
  queryText?: string;
}

export const fundApi = {
  /** 基金搜索 */
  search: async (q: string, limit = 20): Promise<FundItem[]> => {
    const response = await apiClient.get('/api/v1/funds/search', { params: { q, limit } });
    const data = response.data as Record<string, unknown>;
    const items = data.items as Record<string, unknown>[] | undefined;
    return items?.map((item) => toCamelCase<FundItem>(item)) ?? [];
  },

  /** 获取基金基本信息 */
  getInfo: async (fundCode: string): Promise<FundItem | null> => {
    const response = await apiClient.get(`/api/v1/funds/${fundCode}/info`);
    return toCamelCase<FundItem>(response.data);
  },

  /** 获取净值历史 */
  getNav: async (fundCode: string, options?: {
    startDate?: string;
    endDate?: string;
    limit?: number;
  }): Promise<NavItem[]> => {
    const response = await apiClient.get(`/api/v1/funds/${fundCode}/nav`, {
      params: {
        start_date: options?.startDate,
        end_date: options?.endDate,
        limit: options?.limit ?? 500,
      },
    });
    const data = response.data as Record<string, unknown>;
    const items = data.items as Record<string, unknown>[] | undefined;
    return items?.map((item) => toCamelCase<NavItem>(item)) ?? [];
  },

  /** 获取持仓 */
  getHoldings: async (fundCode: string): Promise<HoldingItem[]> => {
    const response = await apiClient.get(`/api/v1/funds/${fundCode}/holdings`);
    const data = response.data as Record<string, unknown>;
    const items = data.items as Record<string, unknown>[] | undefined;
    return items?.map((item) => toCamelCase<HoldingItem>(item)) ?? [];
  },

  /** 刷新净值 */
  refreshNav: async (fundCode: string): Promise<{ total: number; new: number }> => {
    const response = await apiClient.post(`/api/v1/funds/${fundCode}/nav/refresh`);
    return response.data;
  },

  /** 刷新持仓 */
  refreshHoldings: async (fundCode: string): Promise<{ count: number }> => {
    const response = await apiClient.post(`/api/v1/funds/${fundCode}/holdings/refresh`);
    return response.data;
  },

  /** 分析基金 */
  analyze: async (fundCode: string, queryText = ''): Promise<FundAnalyzeResponse> => {
    const response = await apiClient.post('/api/v1/funds/analyze', null, {
      params: { fund_code: fundCode, query_text: queryText },
    });
    return toSnakeCase<FundAnalyzeResponse>(toCamelCase(response.data));
  },

  analyzeAsset: async (input: FundAnalyzeInput): Promise<FundAnalyzeResponse> => {
    const response = await apiClient.post('/api/v1/funds/analyze', null, {
      params: {
        market: input.market,
        asset_category: input.assetCategory,
        symbol: input.symbol,
        name: input.name,
        query_text: input.queryText ?? '',
      },
    });
    return toSnakeCase<FundAnalyzeResponse>(toCamelCase(response.data));
  },
};
