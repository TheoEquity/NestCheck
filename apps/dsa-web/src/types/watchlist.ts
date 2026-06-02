export type WatchlistMarket = 'cn' | 'hk' | 'us';
export type WatchlistAssetCategory = 'fund' | 'stock';
export type WatchlistAssetSubcategory = '' | 'pure_bond_fund' | 'fixed_income_plus' | 'index_fund' | 'equity_fund';
export type WatchlistPriority = 'low' | 'medium' | 'high';
export type WatchlistAnalysisFrequency = 'daily' | 'weekly' | 'manual';

export interface WatchlistItem {
  id: number;
  market: WatchlistMarket | string;
  symbol: string;
  name?: string | null;
  currency: string;
  assetCategory: WatchlistAssetCategory | string;
  assetSubcategory?: WatchlistAssetSubcategory | string | null;
  assetRiskClass?: string | null;
  watchPriority: WatchlistPriority | string;
  watchTags: string[];
  watchReason?: string | null;
  watchEnabled: boolean;
  analysisEnabled: boolean;
  analysisFrequency: WatchlistAnalysisFrequency | string;
  alertEnabled: boolean;
  source: string;
  notes?: string | null;
  alertRuleCount: number;
  alertTriggerCount: number;
  latestAlertTriggeredAt?: string | null;
  latestPrice?: number | null;
  latestChangePct?: number | null;
  latestAnalysisId?: number | null;
  latestAnalysisAt?: string | null;
  latestAnalysisSummary?: string | null;
  latestOperationAdvice?: string | null;
  latestTrendPrediction?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface WatchlistItemListResponse {
  items: WatchlistItem[];
  total: number;
  marketReview?: WatchlistMarketReview | null;
}

export interface WatchlistMarketReview {
  latestAnalysisId?: number | null;
  latestAnalysisAt?: string | null;
  latestAnalysisSummary?: string | null;
  latestAnalysisContent?: string | null;
  latestAnalysisSections?: Record<string, string> | null;
  latestOperationAdvice?: string | null;
  latestTrendPrediction?: string | null;
}

export interface WatchlistItemInput {
  market: WatchlistMarket | string;
  symbol: string;
  name?: string;
  currency: string;
  assetCategory: WatchlistAssetCategory | string;
  assetSubcategory?: WatchlistAssetSubcategory | string;
  assetRiskClass?: string;
  watchPriority: WatchlistPriority | string;
  watchTags: string[];
  watchReason?: string;
  watchEnabled: boolean;
  analysisEnabled: boolean;
  analysisFrequency: WatchlistAnalysisFrequency | string;
  alertEnabled: boolean;
  source?: string;
  notes?: string;
}

export interface WatchlistAlertRule {
  id: number;
  name: string;
  targetScope: string;
  target: string;
  alertType: string;
  severity: string;
  enabled: boolean;
  source: string;
  updatedAt?: string | null;
}

export interface WatchlistAlertTrigger {
  id: number;
  ruleId?: number | null;
  target: string;
  observedValue?: number | null;
  threshold?: number | null;
  reason?: string | null;
  dataSource?: string | null;
  dataTimestamp?: string | null;
  triggeredAt?: string | null;
  status: string;
}

export interface WatchlistRelatedAlertsResponse {
  rules: WatchlistAlertRule[];
  triggers: WatchlistAlertTrigger[];
}
