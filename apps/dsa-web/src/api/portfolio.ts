import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  PortfolioAccountItem,
  PortfolioAccountCreateRequest,
  PortfolioAccountUpdateRequest,
  PortfolioAccountListResponse,
  PortfolioCashLedgerCreateRequest,
  PortfolioCashLedgerListResponse,
  PortfolioCorporateActionCreateRequest,
  PortfolioCorporateActionType,
  PortfolioCorporateActionListResponse,
  PortfolioCostMethod,
  PortfolioDeleteResponse,
  PortfolioEventCreatedResponse,
  PortfolioLatestFxRateListResponse,
  PortfolioFxRefreshResponse,
  PortfolioImportBrokerListResponse,
  PortfolioImportCommitResponse,
  PortfolioImportParseResponse,
  PortfolioInitializeRequest,
  PortfolioInitializeResponse,
  PortfolioPositionAdjustRequest,
  PortfolioPositionAdjustResponse,
  PortfolioPositionListResponse,
  PortfolioRiskResponse,
  PortfolioSnapshotResponse,
  PortfolioTradeCreateRequest,
  PortfolioTradeListResponse,
  AssetCategoryDefinitionListResponse,
  AssetRiskDefinitionListResponse,
  AssetRiskDefinitionItem,
  AssetAllocationSolveRequest,
  AssetAllocationSolveResponse,
  AssetAllocationPlanListResponse,
  AssetAllocationPlanCreateRequest,
  AssetAllocationPlanItem,
  AssetAllocationPlanActivateResponse,
  PortfolioFundHistoryResponse,
  PortfolioFundStatusResponse,
} from '../types/portfolio';

type SnapshotQuery = {
  accountId?: number;
  asOf?: string;
  costMethod?: PortfolioCostMethod;
};

type FxRefreshQuery = {
  accountId?: number;
  asOf?: string;
};

type FxLatestQuery = {
  toCurrency?: string;
  asOf?: string;
};

type EventQuery = {
  accountId?: number;
  dateFrom?: string;
  dateTo?: string;
  page?: number;
  pageSize?: number;
};

type TradeListQuery = EventQuery & {
  symbol?: string;
  side?: 'buy' | 'sell';
};

type CashListQuery = EventQuery & {
  direction?: 'in' | 'out';
};

type CorporateListQuery = EventQuery & {
  symbol?: string;
  actionType?: PortfolioCorporateActionType;
};

function buildSnapshotParams(query: SnapshotQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {};
  if (query.accountId != null) {
    params.account_id = query.accountId;
  }
  if (query.asOf) {
    params.as_of = query.asOf;
  }
  if (query.costMethod) {
    params.cost_method = query.costMethod;
  }
  return params;
}

function buildFxRefreshParams(query: FxRefreshQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {};
  if (query.accountId != null) {
    params.account_id = query.accountId;
  }
  if (query.asOf) {
    params.as_of = query.asOf;
  }
  return params;
}

function buildFxLatestParams(query: FxLatestQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {};
  if (query.toCurrency) {
    params.to_currency = query.toCurrency;
  }
  if (query.asOf) {
    params.as_of = query.asOf;
  }
  return params;
}

function buildEventParams(query: EventQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {};
  if (query.accountId != null) {
    params.account_id = query.accountId;
  }
  if (query.dateFrom) {
    params.date_from = query.dateFrom;
  }
  if (query.dateTo) {
    params.date_to = query.dateTo;
  }
  if (query.page != null) {
    params.page = query.page;
  }
  if (query.pageSize != null) {
    params.page_size = query.pageSize;
  }
  return params;
}

export const portfolioApi = {
  async getAccounts(includeInactive = false): Promise<PortfolioAccountListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/accounts', {
      params: { include_inactive: includeInactive },
    });
    return toCamelCase<PortfolioAccountListResponse>(response.data);
  },

  async createAccount(payload: PortfolioAccountCreateRequest): Promise<PortfolioAccountItem> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/accounts', {
      name: payload.name,
      broker: payload.broker,
      market: payload.market,
      base_currency: payload.baseCurrency,
      owner_id: payload.ownerId,
    });
    return toCamelCase<PortfolioAccountItem>(response.data);
  },

  async updateAccount(accountId: number, payload: PortfolioAccountUpdateRequest): Promise<PortfolioAccountItem> {
    const response = await apiClient.put<Record<string, unknown>>(`/api/v1/portfolio/accounts/${accountId}`, {
      name: payload.name,
      broker: payload.broker,
      market: payload.market,
      base_currency: payload.baseCurrency,
      owner_id: payload.ownerId,
      is_active: payload.isActive,
    });
    return toCamelCase<PortfolioAccountItem>(response.data);
  },

  async deleteAccount(accountId: number): Promise<PortfolioDeleteResponse> {
    const response = await apiClient.delete<Record<string, unknown>>(`/api/v1/portfolio/accounts/${accountId}`);
    return toCamelCase<PortfolioDeleteResponse>(response.data);
  },

  async getSnapshot(query: SnapshotQuery = {}): Promise<PortfolioSnapshotResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/snapshot', {
      params: buildSnapshotParams(query),
    });
    return toCamelCase<PortfolioSnapshotResponse>(response.data);
  },

  async listPositions(query: SnapshotQuery = {}): Promise<PortfolioPositionListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/positions', {
      params: buildSnapshotParams(query),
    });
    return toCamelCase<PortfolioPositionListResponse>(response.data);
  },

  async listOpenDatePositions(): Promise<PortfolioPositionListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/positions/open-dates');
    return toCamelCase<PortfolioPositionListResponse>(response.data);
  },

  async dismissOpenDatePosition(tradeId: number): Promise<PortfolioEventCreatedResponse> {
    const response = await apiClient.post<Record<string, unknown>>(`/api/v1/portfolio/positions/open-dates/${tradeId}/dismiss`);
    return toCamelCase<PortfolioEventCreatedResponse>(response.data);
  },

  async getRisk(query: SnapshotQuery = {}): Promise<PortfolioRiskResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/risk', {
      params: buildSnapshotParams(query),
    });
    return toCamelCase<PortfolioRiskResponse>(response.data);
  },

  async refreshFx(query: FxRefreshQuery = {}): Promise<PortfolioFxRefreshResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/fx/refresh', undefined, {
      params: buildFxRefreshParams(query),
    });
    return toCamelCase<PortfolioFxRefreshResponse>(response.data);
  },

  async getLatestFxRates(query: FxLatestQuery = {}): Promise<PortfolioLatestFxRateListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/fx/latest', {
      params: buildFxLatestParams(query),
    });
    return toCamelCase<PortfolioLatestFxRateListResponse>(response.data);
  },

  async createTrade(payload: PortfolioTradeCreateRequest): Promise<PortfolioEventCreatedResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/trades', {
      account_id: payload.accountId,
      asset_category: payload.assetCategory,
      asset_subcategory: payload.assetSubcategory,
      asset_risk_class: payload.assetRiskClass,
      symbol: payload.symbol,
      name: payload.name,
      trade_date: payload.tradeDate,
      available_date: payload.availableDate || undefined,
      side: payload.side,
      quantity: payload.quantity,
      price: payload.price,
      fee: payload.fee,
      tax: payload.tax,
      market: payload.market,
      currency: payload.currency,
      trade_uid: payload.tradeUid,
      note: payload.note,
    });
    return toCamelCase<PortfolioEventCreatedResponse>(response.data);
  },

  async createCashLedger(payload: PortfolioCashLedgerCreateRequest): Promise<PortfolioEventCreatedResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/cash-ledger', {
      account_id: payload.accountId,
      asset_category: payload.assetCategory,
      asset_subcategory: payload.assetSubcategory,
      asset_risk_class: payload.assetRiskClass,
      event_date: payload.eventDate,
      direction: payload.direction,
      amount: payload.amount,
      currency: payload.currency,
      note: payload.note,
    });
    return toCamelCase<PortfolioEventCreatedResponse>(response.data);
  },

  async createCorporateAction(payload: PortfolioCorporateActionCreateRequest): Promise<PortfolioEventCreatedResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/corporate-actions', {
      account_id: payload.accountId,
      symbol: payload.symbol,
      asset_category: payload.assetCategory,
      asset_subcategory: payload.assetSubcategory,
      effective_date: payload.effectiveDate,
      action_type: payload.actionType,
      market: payload.market,
      currency: payload.currency,
      dividend_amount: payload.dividendAmount,
      split_ratio: payload.splitRatio,
      note: payload.note,
    });
    return toCamelCase<PortfolioEventCreatedResponse>(response.data);
  },

  async listTrades(query: TradeListQuery = {}): Promise<PortfolioTradeListResponse> {
    const params = buildEventParams(query);
    if (query.symbol) {
      params.symbol = query.symbol;
    }
    if (query.side) {
      params.side = query.side;
    }
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/trades', { params });
    return toCamelCase<PortfolioTradeListResponse>(response.data);
  },

  async listCashLedger(query: CashListQuery = {}): Promise<PortfolioCashLedgerListResponse> {
    const params = buildEventParams(query);
    if (query.direction) {
      params.direction = query.direction;
    }
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/cash-ledger', { params });
    return toCamelCase<PortfolioCashLedgerListResponse>(response.data);
  },

  async listCorporateActions(query: CorporateListQuery = {}): Promise<PortfolioCorporateActionListResponse> {
    const params = buildEventParams(query);
    if (query.symbol) {
      params.symbol = query.symbol;
    }
    if (query.actionType) {
      params.action_type = query.actionType;
    }
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/corporate-actions', { params });
    return toCamelCase<PortfolioCorporateActionListResponse>(response.data);
  },

  async listImportBrokers(): Promise<PortfolioImportBrokerListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/imports/csv/brokers');
    return toCamelCase<PortfolioImportBrokerListResponse>(response.data);
  },

  async parseCsvImport(broker: string, file: File): Promise<PortfolioImportParseResponse> {
    const formData = new FormData();
    formData.append('broker', broker);
    formData.append('file', file);
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/imports/csv/parse', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return toCamelCase<PortfolioImportParseResponse>(response.data);
  },

  async commitCsvImport(
    accountId: number,
    broker: string,
    file: File,
    dryRun = false,
  ): Promise<PortfolioImportCommitResponse> {
    const formData = new FormData();
    formData.append('account_id', String(accountId));
    formData.append('broker', broker);
    formData.append('dry_run', dryRun ? 'true' : 'false');
    formData.append('file', file);
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/imports/csv/commit', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return toCamelCase<PortfolioImportCommitResponse>(response.data);
  },

  async adjustPosition(
    positionId: number,
    body: PortfolioPositionAdjustRequest,
    accountId?: number,
  ): Promise<PortfolioPositionAdjustResponse> {
    const params: Record<string, string | number> = {};
    if (accountId !== undefined) {
      params.account_id = accountId;
    }
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/portfolio/positions/${positionId}/adjust`,
      body,
      { params },
    );
    return toCamelCase<PortfolioPositionAdjustResponse>(response.data);
  },

  async initializePortfolio(payload: PortfolioInitializeRequest): Promise<PortfolioInitializeResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/initialize', {
      account_id: payload.accountId,
      init_date: payload.initDate,
      assets: payload.assets.map((row) => ({
        asset_category: row.assetCategory,
        asset_subcategory: row.assetSubcategory,
        asset_risk_class: row.assetRiskClass,
        symbol: row.symbol,
        name: row.name,
        market: row.market,
        quantity: row.quantity,
        avg_cost: row.avgCost,
        last_price: row.lastPrice,
        currency: row.currency,
        note: row.note,
      })),
      cash_items: payload.cashItems.map((item) => ({
        asset_category: item.assetCategory,
        asset_risk_class: item.assetRiskClass,
        name: item.name,
        amount: item.amount,
        currency: item.currency,
        note: item.note,
      })),
    });
    return toCamelCase<PortfolioInitializeResponse>(response.data);
  },

  async getRiskDefinitions(): Promise<AssetRiskDefinitionListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/risk-definitions');
    return toCamelCase<AssetRiskDefinitionListResponse>(response.data);
  },

  async updateRiskDefinition(riskClass: string, payload: Record<string, unknown>): Promise<AssetRiskDefinitionItem> {
    const response = await apiClient.put<Record<string, unknown>>(
      `/api/v1/portfolio/risk-definitions/${riskClass}`,
      payload,
    );
    return toCamelCase<AssetRiskDefinitionItem>(response.data);
  },

  async solveAllocation(payload: AssetAllocationSolveRequest): Promise<AssetAllocationSolveResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/allocation/solve', {
      target_return_min: payload.targetReturnMin,
      target_return_max: payload.targetReturnMax,
      max_drawdown_tolerance: payload.maxDrawdownTolerance,
      base_ratio_min: payload.baseRatioMin,
      base_ratio_max: payload.baseRatioMax,
      opportunity_ratio_min: payload.opportunityRatioMin,
      opportunity_ratio_max: payload.opportunityRatioMax,
    });
    const result = toCamelCase<AssetAllocationSolveResponse>(response.data);
    return {
      ...result,
      allocation: Object.fromEntries(
        Object.entries(result.allocation || {}).map(([key, value]) => [key.toUpperCase(), value]),
      ),
    };
  },

  async listAllocationPlans(): Promise<AssetAllocationPlanListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/allocation/plans');
    return toCamelCase<AssetAllocationPlanListResponse>(response.data);
  },

  async createAllocationPlan(payload: AssetAllocationPlanCreateRequest): Promise<AssetAllocationPlanItem> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/allocation/plans', {
      r1_ratio: payload.r1Ratio,
      r2_ratio: payload.r2Ratio,
      r3_ratio: payload.r3Ratio,
      r4_ratio: payload.r4Ratio,
      r5_ratio: payload.r5Ratio,
    });
    return toCamelCase<AssetAllocationPlanItem>(response.data);
  },

  async activateAllocationPlan(planId: number): Promise<AssetAllocationPlanActivateResponse> {
    const response = await apiClient.put<Record<string, unknown>>(`/api/v1/portfolio/allocation/plans/${planId}/activate`);
    return toCamelCase<AssetAllocationPlanActivateResponse>(response.data);
  },

  async getAssetCategories(): Promise<string[]> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/asset-categories');
    return (response.data.categories as string[]) || [];
  },

  async getAssetCategoryDefinitions(): Promise<AssetCategoryDefinitionListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/asset-category-definitions');
    return toCamelCase<AssetCategoryDefinitionListResponse>(response.data);
  },

  async getFundStatus(): Promise<PortfolioFundStatusResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/fund-status');
    const data = toCamelCase<PortfolioFundStatusResponse>(response.data);
    return data;
  },

  async getFundHistory(limit = 365): Promise<PortfolioFundHistoryResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/fund-history', {
      params: { limit },
    });
    return toCamelCase<PortfolioFundHistoryResponse>(response.data);
  },

  async resetFund(): Promise<Record<string, unknown>> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/fund-reset', {});
    const data = toCamelCase<Record<string, unknown>>(response.data);
    return data;
  },

  async deleteAllocationPlan(planId: number): Promise<PortfolioDeleteResponse> {
    const response = await apiClient.delete<Record<string, unknown>>(`/api/v1/portfolio/allocation/plans/${planId}`);
    return toCamelCase<PortfolioDeleteResponse>(response.data);
  },
};
