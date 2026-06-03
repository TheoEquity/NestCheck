import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  WatchlistItem,
  WatchlistItemInput,
  WatchlistItemListResponse,
  WatchlistRefreshResponse,
  WatchlistRelatedAlertsResponse,
} from '../types/watchlist';

function toSnakePayload(input: Partial<WatchlistItemInput>): Record<string, unknown> {
  return {
    market: input.market,
    symbol: input.symbol,
    name: input.name,
    currency: input.currency,
    asset_category: input.assetCategory,
    asset_subcategory: input.assetSubcategory,
    asset_risk_class: input.assetRiskClass,
    watch_priority: input.watchPriority,
    watch_tags: input.watchTags,
    watch_reason: input.watchReason,
    watch_enabled: input.watchEnabled,
    analysis_enabled: input.analysisEnabled,
    analysis_frequency: input.analysisFrequency,
    alert_enabled: input.alertEnabled,
    source: input.source,
    notes: input.notes,
  };
}

export const watchlistApi = {
  async listItems(): Promise<WatchlistItemListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/watchlist/items');
    return toCamelCase<WatchlistItemListResponse>(response.data);
  },

  async createItem(input: WatchlistItemInput): Promise<WatchlistItem> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/watchlist/items', toSnakePayload(input));
    return toCamelCase<WatchlistItem>(response.data);
  },

  async updateItem(itemId: number, input: Partial<WatchlistItemInput>): Promise<WatchlistItem> {
    const response = await apiClient.patch<Record<string, unknown>>(`/api/v1/watchlist/items/${itemId}`, toSnakePayload(input));
    return toCamelCase<WatchlistItem>(response.data);
  },

  async deleteItem(itemId: number): Promise<void> {
    await apiClient.delete(`/api/v1/watchlist/items/${itemId}`);
  },

  async moveItem(itemId: number, direction: 'up' | 'down'): Promise<WatchlistItem> {
    const response = await apiClient.post<Record<string, unknown>>(`/api/v1/watchlist/items/${itemId}/move`, { direction });
    return toCamelCase<WatchlistItem>(response.data);
  },

  async refreshSignals(): Promise<WatchlistRefreshResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/watchlist/signals/refresh');
    return toCamelCase<WatchlistRefreshResponse>(response.data);
  },

  async refreshItemSignal(itemId: number): Promise<WatchlistRefreshResponse> {
    const response = await apiClient.post<Record<string, unknown>>(`/api/v1/watchlist/items/${itemId}/signals/refresh`);
    return toCamelCase<WatchlistRefreshResponse>(response.data);
  },

  async getRelatedAlerts(itemId: number): Promise<WatchlistRelatedAlertsResponse> {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/watchlist/items/${itemId}/alerts`);
    return toCamelCase<WatchlistRelatedAlertsResponse>(response.data);
  },
};
