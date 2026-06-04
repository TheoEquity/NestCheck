export type PortfolioCostMethod = 'fifo' | 'avg';
export type PortfolioSide = 'buy' | 'sell';
export type PortfolioCashDirection = 'in' | 'out';
export type PortfolioCorporateActionType = 'cash_dividend';

export interface PortfolioAccountItem {
  id: number;
  ownerId?: string | null;
  name: string;
  broker?: string | null;
  market: 'cn' | 'hk' | 'us';
  baseCurrency: string;
  isActive: boolean;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface PortfolioAccountListResponse {
  accounts: PortfolioAccountItem[];
}

export interface PortfolioAccountCreateRequest {
  name: string;
  broker?: string;
  market: 'cn' | 'hk' | 'us';
  baseCurrency: string;
  ownerId?: string;
}

export interface PortfolioAccountUpdateRequest {
  name?: string;
  broker?: string;
  market?: 'cn' | 'hk' | 'us';
  baseCurrency?: string;
  ownerId?: string;
  isActive?: boolean;
}

export interface PortfolioPositionItem {
  id: number;
  symbol: string;
  name?: string | null;
  market: string;
  currency: string;
  quantity: number;
  avgCost: number;
  totalCost: number;
  lastPrice: number;
  priceChangePct?: number | null;
  marketValueBase: number;
  unrealizedPnlBase: number;
  realizedPnlBase: number;
  unrealizedPnlPct?: number | null;
  assetCategory?: string | null;
  assetSubcategory?: string | null;
  assetRiskClass?: string | null;
  valuationCurrency: string;
  priceSource?: 'realtime_quote' | 'history_close' | 'missing' | string;
  priceProvider?: string | null;
  priceDate?: string | null;
  priceStale?: boolean;
  priceAvailable?: boolean;
}

export interface PortfolioPositionRecordItem extends PortfolioPositionItem {
  accountId: number;
  accountName: string;
  ownerId?: string | null;
  baseCurrency: string;
  costMethod: PortfolioCostMethod;
  updatedAt?: string | null;
}

export interface PortfolioPositionListResponse {
  items: PortfolioPositionRecordItem[];
  total: number;
}

export interface PortfolioCashByCurrencyItem {
  currency: string;
  amount: number;
  amountBase: number;
}

export interface PortfolioFxRateItem {
  pair: string;
  rate: number;
  isStale?: boolean;
}

export interface PortfolioLatestFxRateItem {
  pair: string;
  fromCurrency: string;
  toCurrency: string;
  rate: number;
  rateDate: string;
  source: string;
  isStale?: boolean;
}

export interface PortfolioLatestFxRateListResponse {
  asOf: string;
  toCurrency: string;
  items: PortfolioLatestFxRateItem[];
}

export interface PortfolioAccountSnapshot {
  accountId: number;
  accountName: string;
  ownerId?: string | null;
  broker?: string | null;
  market: string;
  baseCurrency: string;
  asOf: string;
  costMethod: PortfolioCostMethod;
  totalCash: number;
  totalMarketValue: number;
  totalEquity: number;
  realizedPnl: number;
  unrealizedPnl: number;
  feeTotal: number;
  taxTotal: number;
  fxStale: boolean;
  cashByCurrency: PortfolioCashByCurrencyItem[];
  fxRates: PortfolioFxRateItem[];
  positions: PortfolioPositionItem[];
}

export interface PortfolioSnapshotResponse {
  asOf: string;
  costMethod: PortfolioCostMethod;
  currency: string;
  accountCount: number;
  totalCash: number;
  totalMarketValue: number;
  totalEquity: number;
  realizedPnl: number;
  unrealizedPnl: number;
  feeTotal: number;
  taxTotal: number;
  fxStale: boolean;
  accounts: PortfolioAccountSnapshot[];
}

export interface PortfolioConcentrationItem {
  symbol: string;
  marketValueBase: number;
  weightPct: number;
  isAlert: boolean;
}

export interface PortfolioSectorConcentrationItem {
  sector: string;
  marketValueBase: number;
  weightPct: number;
  symbolCount: number;
  isAlert: boolean;
}

export interface PortfolioDrawdownBlock {
  seriesPoints: number;
  maxDrawdownPct: number;
  currentDrawdownPct: number;
  alert: boolean;
  fxStale: boolean;
}

export interface PortfolioStopLossItem {
  accountId: number;
  symbol: string;
  avgCost: number;
  lastPrice: number;
  lossPct: number;
  nearThresholdPct: number;
  isTriggered: boolean;
}

export interface PortfolioRiskResponse {
  asOf: string;
  accountId?: number | null;
  costMethod: PortfolioCostMethod;
  currency: string;
  thresholds: Record<string, number>;
  concentration: {
    totalMarketValue: number;
    topWeightPct: number;
    alert: boolean;
    topPositions: PortfolioConcentrationItem[];
  };
  sectorConcentration: {
    totalMarketValue: number;
    topWeightPct: number;
    alert: boolean;
    topSectors: PortfolioSectorConcentrationItem[];
    coverage: Record<string, number>;
    errors: string[];
  };
  drawdown: PortfolioDrawdownBlock;
  stopLoss: {
    nearAlert: boolean;
    triggeredCount: number;
    nearCount: number;
    items: PortfolioStopLossItem[];
  };
}

export interface PortfolioTradeCreateRequest {
  accountId: number;
  assetCategory?: string;
  assetSubcategory?: string;
  assetRiskClass?: string;
  symbol: string;
  name?: string;
  tradeDate: string;
  side: PortfolioSide;
  quantity: number;
  price: number;
  fee?: number;
  tax?: number;
  market?: 'cn' | 'hk' | 'us';
  currency?: string;
  tradeUid?: string;
  note?: string;
}

export interface PortfolioCashLedgerCreateRequest {
  accountId: number;
  assetCategory?: string;
  assetSubcategory?: string;
  assetRiskClass?: string;
  eventDate: string;
  direction: PortfolioCashDirection;
  amount: number;
  currency?: string;
  note?: string;
}

export interface PortfolioCorporateActionCreateRequest {
  accountId: number;
  symbol: string;
  assetCategory?: string;
  assetSubcategory?: string;
  effectiveDate: string;
  actionType: PortfolioCorporateActionType;
  market?: 'cn' | 'hk' | 'us';
  currency?: string;
  dividendAmount: number;
  note?: string;
}

export interface PortfolioEventCreatedResponse {
  id: number;
}

export interface PortfolioDeleteResponse {
  deleted: number;
}

export interface PortfolioTradeListItem {
  id: number;
  accountId: number;
  tradeUid?: string | null;
  assetCategory?: string | null;
  assetSubcategory?: string | null;
  assetRiskClass?: string | null;
  symbol: string;
  name?: string | null;
  market: string;
  currency: string;
  tradeDate: string;
  side: PortfolioSide;
  quantity: number;
  price: number;
  fee: number;
  tax: number;
  realizedPnl: number;
  note?: string | null;
  createdAt?: string | null;
}

export interface PortfolioTradeListResponse {
  items: PortfolioTradeListItem[];
  total: number;
  page: number;
  pageSize: number;
}

export interface PortfolioCashLedgerListItem {
  id: number;
  accountId: number;
  assetCategory?: string | null;
  assetSubcategory?: string | null;
  assetRiskClass?: string | null;
  eventDate: string;
  direction: PortfolioCashDirection;
  amount: number;
  currency: string;
  note?: string | null;
  createdAt?: string | null;
}

export interface PortfolioCashLedgerListResponse {
  items: PortfolioCashLedgerListItem[];
  total: number;
  page: number;
  pageSize: number;
}

export interface PortfolioCorporateActionListItem {
  id: number;
  accountId: number;
  symbol: string;
  market: string;
  currency: string;
  assetCategory?: string | null;
  assetSubcategory?: string | null;
  effectiveDate: string;
  actionType: PortfolioCorporateActionType;
  dividendAmount?: number | null;
  realizedPnl: number;
  note?: string | null;
  createdAt?: string | null;
}

export interface PortfolioCorporateActionListResponse {
  items: PortfolioCorporateActionListItem[];
  total: number;
  page: number;
  pageSize: number;
}

export interface PortfolioImportTradeItem {
  tradeDate: string;
  symbol: string;
  side: PortfolioSide;
  quantity: number;
  price: number;
  fee: number;
  tax: number;
  tradeUid?: string | null;
  dedupHash: string;
  currency?: string | null;
}

export interface PortfolioImportParseResponse {
  broker: string;
  recordCount: number;
  skippedCount: number;
  errorCount: number;
  records: PortfolioImportTradeItem[];
  errors: string[];
}

export interface PortfolioImportCommitResponse {
  accountId: number;
  recordCount: number;
  insertedCount: number;
  duplicateCount: number;
  failedCount: number;
  dryRun: boolean;
  errors: string[];
}

export interface PortfolioImportBrokerItem {
  broker: string;
  aliases: string[];
  displayName?: string;
}

export interface PortfolioImportBrokerListResponse {
  brokers: PortfolioImportBrokerItem[];
}

export interface PortfolioFxRefreshResponse {
  asOf: string;
  accountCount: number;
  refreshEnabled?: boolean;
  disabledReason?: string | null;
  pairCount: number;
  updatedCount: number;
  staleCount: number;
  errorCount: number;
}

export interface PortfolioPositionAdjustRequest {
  quantity?: number;
  avg_cost?: number;
  last_price?: number;
}

export interface PortfolioPositionAdjustResponse {
  id: number;
  symbol: string;
  market: string;
  currency: string;
  quantity: number;
  avgCost: number;
  lastPrice: number;
  totalCost: number;
  updatedAt?: string | null;
}

export interface PortfolioInitializeAssetRow {
  assetCategory: string;
  assetSubcategory?: string;
  assetRiskClass?: string;
  symbol: string;
  name?: string;
  market: 'cn' | 'hk' | 'us';
  quantity: number;
  avgCost: number;
  currency: string;
  note?: string;
}

export interface PortfolioInitializeCashRow {
  assetCategory: string;
  assetRiskClass?: string;
  name?: string;
  amount: number;
  currency: string;
  note?: string;
}

export interface PortfolioInitializeRequest {
  accountId: number;
  initDate: string;
  assets: PortfolioInitializeAssetRow[];
  cashItems: PortfolioInitializeCashRow[];
}

export interface PortfolioInitializeResponse {
  accountId: number;
  assetCount: number;
  cashCount: number;
  clearedTradeCount: number;
  clearedCashCount: number;
  clearedCorporateCount: number;
}

export interface AssetRiskDefinitionItem {
  assetRiskClass: string;
  name: string;
  expectedReturn?: number | null;
  volatility?: number | null;
  maxDrawdown?: number | null;
  equityWeight: number;
  description?: string | null;
}

export interface AssetRiskDefinitionListResponse {
  definitions: AssetRiskDefinitionItem[];
}

export interface AssetAllocationSolveRequest {
  targetReturnMin?: number;
  targetReturnMax?: number;
  maxDrawdownTolerance?: number;
  baseRatioMin?: number;
  baseRatioMax?: number;
  opportunityRatioMin?: number;
  opportunityRatioMax?: number;
}

export interface AssetAllocationSolveResponse {
  expectedReturn: number;
  maxDrawdown: number;
  volatility: number;
  allocation: Record<string, number>;
  method: string;
}

export interface AssetAllocationPlanItem {
  id: number;
  isActive: boolean;
  generatedAt: string;
  r1Ratio: number;
  r2Ratio: number;
  r3Ratio: number;
  r4Ratio: number;
  r5Ratio: number;
}

export interface AssetAllocationPlanListResponse {
  plans: AssetAllocationPlanItem[];
}

export interface AssetAllocationPlanCreateRequest {
  r1Ratio: number;
  r2Ratio: number;
  r3Ratio: number;
  r4Ratio: number;
  r5Ratio: number;
}

export interface AssetAllocationPlanActivateResponse {
  activePlanId?: number | null;
  isActive: boolean;
}
