export type WatchlistMarket = 'cn' | 'hk' | 'us';
export type WatchlistAssetCategory = 'fund' | 'stock';
export type WatchlistAssetSubcategory = string;
export type WatchlistPriority = 'low' | 'medium' | 'high';
export type WatchlistAnalysisFrequency = 'daily' | 'weekly' | 'manual';

export interface WatchlistItem {
  id: number;
  market: WatchlistMarket | string;
  symbol: string;
  displaySymbol?: string | null;
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
  source: string;
  sortOrder: number;
  notes?: string | null;
  latestPrice?: number | null;
  latestChangePct?: number | null;
  signalAsOfDate?: string | null;
  signalVerdictCode?: string | null;
  signalReason?: string | null;
  signalLights: WatchlistSignalLight[];
  signalDataQualityFlags: string[];
  latestAnalysisId?: number | null;
  latestAnalysisAt?: string | null;
  latestAnalysisSummary?: string | null;
  latestOperationAdvice?: string | null;
  latestTrendPrediction?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface WatchlistSignalLight {
  code: string;
  label: string;
  status: 'G' | 'Y' | 'R' | string;
  reason: string;
  value?: number | null;
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
  source?: string;
  notes?: string;
}

export interface WatchlistRefreshResponse {
  status: string;
  total: number;
  success: number;
  failed: number;
  items: Array<Record<string, unknown>>;
}
