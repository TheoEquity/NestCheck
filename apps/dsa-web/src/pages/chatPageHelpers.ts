import type { ChatFollowUpContext } from '../utils/chatFollowUp';

export const DEFAULT_CHAT_PROFILE_ID = 'stock_chat_auto';
export const FUND_CHAT_PROFILE_ID = 'fund_analysis';
export const MARKET_CHAT_PROFILE_ID = 'market_analysis';

export type ActiveChatTopic = { market: string; assetType: string; code: string; name: string; sessionId: string };

export const getDefaultChatProfileId = (assetType?: string | null) => (
  assetType === 'fund' ? FUND_CHAT_PROFILE_ID : assetType === 'market' ? MARKET_CHAT_PROFILE_ID : DEFAULT_CHAT_PROFILE_ID
);

export const buildChatTopicContext = (
  topic: ActiveChatTopic,
  followUpContext?: ChatFollowUpContext | null,
) => ({
  ...(followUpContext ?? {}),
  agent_chat_mode: true,
  stock_code: topic.assetType === 'stock' ? topic.code : undefined,
  stock_name: topic.assetType === 'stock' ? topic.name || undefined : undefined,
  fund_code: topic.assetType === 'fund' ? topic.code : undefined,
  fund_name: topic.assetType === 'fund' ? topic.name || undefined : undefined,
  asset_code: topic.code,
  asset_name: topic.name || undefined,
  market: topic.market,
  asset_type: topic.assetType,
});
