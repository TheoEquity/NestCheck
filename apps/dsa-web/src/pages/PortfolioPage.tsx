import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Pie, PieChart, ResponsiveContainer, Tooltip, Legend, Cell } from 'recharts';
import { portfolioApi } from '../api/portfolio';
import type { ParsedApiError } from '../api/error';
import { getParsedApiError } from '../api/error';
import { ApiErrorAlert, Card, Badge, ConfirmDialog, EmptyState, InlineAlert } from '../components/common';
import { toDateInputValue } from '../utils/format';
import type {
  PortfolioAccountItem,
  PortfolioCashDirection,
  PortfolioCashLedgerListItem,
  PortfolioCorporateActionListItem,
  PortfolioCorporateActionType,
  PortfolioCostMethod,
  PortfolioFxRefreshResponse,
  PortfolioLatestFxRateItem,
  PortfolioImportBrokerItem,
  PortfolioImportCommitResponse,
  PortfolioImportParseResponse,
  PortfolioPositionRecordItem,
  PortfolioSide,
  PortfolioTradeListItem,
} from '../types/portfolio';

const PIE_COLORS = ['#00d4ff', '#00ff88', '#ffaa00', '#ff7a45', '#7f8cff', '#ff4466'];
const DEFAULT_PAGE_SIZE = 20;
const FALLBACK_BROKERS: PortfolioImportBrokerItem[] = [
  { broker: 'huatai', aliases: [], displayName: '华泰' },
  { broker: 'citic', aliases: ['zhongxin'], displayName: '中信' },
  { broker: 'cmb', aliases: ['cmbchina', 'zhaoshang'], displayName: '招商' },
];

type AccountOption = 'all' | number;
type EventType = 'trade' | 'cash' | 'corporate';

type PendingDelete =
  | { eventType: 'trade'; id: number; message: string }
  | { eventType: 'cash'; id: number; message: string }
  | { eventType: 'corporate'; id: number; message: string };

type FxRefreshFeedback = {
  tone: 'neutral' | 'success' | 'warning';
  text: string;
};

type FxRefreshContext = {
  viewKey: string;
  requestId: number;
};

type SummaryBlockItem = {
  label: string;
  value: string | number;
  description: string;
};

type StepBlockItem = {
  label: string;
  title: string;
  description: string;
};

type PortfolioAlertVariant = 'info' | 'success' | 'warning' | 'danger';

const PORTFOLIO_INPUT_CLASS =
  'input-surface input-focus-glow h-10 w-full rounded-lg border bg-transparent px-3 text-sm transition-all focus:outline-none disabled:cursor-not-allowed disabled:opacity-60';
const PORTFOLIO_SELECT_CLASS = `${PORTFOLIO_INPUT_CLASS} appearance-none pr-10`;
const PORTFOLIO_TEXTAREA_CLASS =
  'input-surface input-focus-glow min-h-[80px] w-full rounded-lg border bg-transparent px-3 py-2 text-sm transition-all focus:outline-none disabled:cursor-not-allowed disabled:opacity-60';
const PORTFOLIO_FILE_PICKER_CLASS =
  'input-surface input-focus-glow flex h-10 w-full cursor-pointer items-center justify-center rounded-lg border bg-transparent px-3 text-sm transition-all focus:outline-none disabled:cursor-not-allowed disabled:opacity-60';

function getTodayIso(): string {
  return toDateInputValue(new Date());
}

function formatMoney(value: number | undefined | null, currency = 'CNY'): string {
  if (value == null || Number.isNaN(value)) return '--';
  return `${currency} ${Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatPct(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return '--';
  return `${value.toFixed(2)}%`;
}

function formatSignedPct(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return '--';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

function hasPositionPrice(row: PortfolioPositionRecordItem): boolean {
  return row.priceAvailable !== false && row.priceSource !== 'missing';
}

function formatPositionPrice(row: PortfolioPositionRecordItem): string {
  if (!hasPositionPrice(row)) return '--';
  return row.lastPrice.toFixed(4);
}

function formatPositionMoney(value: number, row: PortfolioPositionRecordItem): string {
  if (!hasPositionPrice(row)) return '--';
  return formatMoney(value, row.valuationCurrency);
}

function getPositionPriceLabel(row: PortfolioPositionRecordItem): string {
  if (!hasPositionPrice(row)) return '缺价';
  if (row.priceSource === 'realtime_quote') {
    return row.priceProvider ? `实时价 · ${row.priceProvider}` : '实时价';
  }
  if (row.priceSource === 'history_close') {
    return row.priceStale && row.priceDate ? `收盘价 · ${row.priceDate}` : '收盘价';
  }
  return row.priceSource || '未知来源';
}

function formatSideLabel(value: PortfolioSide): string {
  return value === 'buy' ? '买入' : '卖出';
}

function formatCashDirectionLabel(value: PortfolioCashDirection): string {
  return value === 'in' ? '流入' : '流出';
}

function formatCorporateActionLabel(value: PortfolioCorporateActionType): string {
  return value === 'cash_dividend' ? '现金分红' : '拆并股调整';
}

function formatBrokerLabel(value: string, displayName?: string): string {
  if (displayName && displayName.trim()) return `${value}（${displayName.trim()}）`;
  if (value === 'huatai') return 'huatai（华泰）';
  if (value === 'citic') return 'citic（中信）';
  if (value === 'cmb') return 'cmb（招商）';
  return value;
}

function buildFxRefreshFeedback(data: PortfolioFxRefreshResponse): FxRefreshFeedback {
  if (data.refreshEnabled === false) {
    return {
      tone: 'neutral',
      text: '汇率在线刷新已被禁用。',
    };
  }

  if (data.pairCount === 0) {
    return {
      tone: 'neutral',
      text: '当前范围无可刷新的汇率对。',
    };
  }

  if (data.updatedCount > 0 && data.staleCount === 0 && data.errorCount === 0) {
    return {
      tone: 'success',
      text: `汇率已刷新，共更新 ${data.updatedCount} 对。`,
    };
  }

  const summary = `更新 ${data.updatedCount} 对，仍过期 ${data.staleCount} 对，失败 ${data.errorCount} 对。`;
  if (data.staleCount > 0) {
    return {
      tone: 'warning',
      text: `已尝试刷新，但仍有部分货币对使用 stale/fallback 汇率。${summary}`,
    };
  }

  return {
    tone: 'warning',
    text: `在线刷新未完全成功。${summary}`,
  };
}

function getFxRefreshFeedbackVariant(tone: FxRefreshFeedback['tone']): PortfolioAlertVariant {
  if (tone === 'success') return 'success';
  if (tone === 'warning') return 'warning';
  return 'info';
}

function getCsvParseVariant(result: PortfolioImportParseResponse): PortfolioAlertVariant {
  return result.errorCount > 0 || result.skippedCount > 0 ? 'warning' : 'info';
}

function getCsvCommitVariant(result: PortfolioImportCommitResponse, isDryRun: boolean): PortfolioAlertVariant {
  if (isDryRun) return 'info';
  return result.failedCount > 0 || result.duplicateCount > 0 ? 'warning' : 'success';
}

const InitializationStepGrid: React.FC<{ items: StepBlockItem[] }> = ({ items }) => (
  <div className="mt-3 grid gap-2 md:grid-cols-3">
    {items.map((item) => (
      <div key={item.label} className="rounded-lg border border-white/10 bg-white/[0.03] p-2.5">
        <p className="text-xs text-secondary">{item.label}</p>
        <p className="mt-0.5 text-sm font-semibold text-foreground">{item.title}</p>
        <p className="mt-1.5 text-xs leading-5 text-secondary">{item.description}</p>
      </div>
    ))}
  </div>
);

const InitializationStatusGrid: React.FC<{ items: SummaryBlockItem[] }> = ({ items }) => (
  <div className="mt-3 grid gap-2 sm:grid-cols-2">
    {items.map((item) => (
      <div key={item.label} className="rounded-lg border border-white/10 bg-white/[0.03] p-2.5">
        <p className="text-xs text-secondary">{item.label}</p>
        <p className="mt-0.5 text-sm font-semibold text-foreground">{item.value}</p>
        <p className="mt-1.5 text-xs text-secondary">{item.description}</p>
      </div>
    ))}
  </div>
);

type PortfolioPageProps = {
  mode?: 'full' | 'initialization';
};

const PortfolioPage: React.FC<PortfolioPageProps> = ({ mode = 'full' }) => {
  const initializationOnly = mode === 'initialization';
  // Set page title
  useEffect(() => {
    document.title = initializationOnly ? '资产初始化 - NestCheck' : '持仓分析 - NestCheck';
  }, [initializationOnly]);

  const [accounts, setAccounts] = useState<PortfolioAccountItem[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<AccountOption>('all');
  const [showCreateAccount, setShowCreateAccount] = useState(false);
  const [accountCreating, setAccountCreating] = useState(false);
  const [accountCreateError, setAccountCreateError] = useState<string | null>(null);
  const [accountCreateSuccess, setAccountCreateSuccess] = useState<string | null>(null);
  const [accountForm, setAccountForm] = useState({
    name: '',
    broker: 'Demo',
    market: 'cn' as 'cn' | 'hk' | 'us',
    baseCurrency: 'CNY',
  });
  const [costMethod, setCostMethod] = useState<PortfolioCostMethod>('fifo');
  const [positions, setPositions] = useState<PortfolioPositionRecordItem[]>([]);
  const [fxRates, setFxRates] = useState<PortfolioLatestFxRateItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [fxRefreshing, setFxRefreshing] = useState(false);
  const [fxRefreshFeedback, setFxRefreshFeedback] = useState<FxRefreshFeedback | null>(null);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [writeWarning, setWriteWarning] = useState<string | null>(null);

  const [brokers, setBrokers] = useState<PortfolioImportBrokerItem[]>([]);
  const [selectedBroker, setSelectedBroker] = useState('huatai');
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvDryRun, setCsvDryRun] = useState(true);
  const [csvParsing, setCsvParsing] = useState(false);
  const [csvCommitting, setCsvCommitting] = useState(false);
  const [csvParseResult, setCsvParseResult] = useState<PortfolioImportParseResponse | null>(null);
  const [csvCommitResult, setCsvCommitResult] = useState<PortfolioImportCommitResponse | null>(null);
  const [brokerLoadWarning, setBrokerLoadWarning] = useState<string | null>(null);

  const [eventType, setEventType] = useState<EventType>('trade');
  const [eventDateFrom, setEventDateFrom] = useState('');
  const [eventDateTo, setEventDateTo] = useState('');
  const [eventSymbol, setEventSymbol] = useState('');
  const [eventSide, setEventSide] = useState<'' | PortfolioSide>('');
  const [eventDirection, setEventDirection] = useState<'' | PortfolioCashDirection>('');
  const [eventActionType, setEventActionType] = useState<'' | PortfolioCorporateActionType>('');
  const [eventPage, setEventPage] = useState(1);
  const [eventTotal, setEventTotal] = useState(0);
  const [eventLoading, setEventLoading] = useState(false);
  const [tradeEvents, setTradeEvents] = useState<PortfolioTradeListItem[]>([]);
  const [cashEvents, setCashEvents] = useState<PortfolioCashLedgerListItem[]>([]);
  const [corporateEvents, setCorporateEvents] = useState<PortfolioCorporateActionListItem[]>([]);
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const [tradeForm, setTradeForm] = useState({
    symbol: '',
    tradeDate: getTodayIso(),
    side: 'buy' as PortfolioSide,
    quantity: '',
    price: '',
    fee: '',
    tax: '',
    tradeUid: '',
    note: '',
  });
  const [cashForm, setCashForm] = useState({
    eventDate: getTodayIso(),
    direction: 'in' as PortfolioCashDirection,
    amount: '',
    currency: '',
    note: '',
  });
  const [corpForm, setCorpForm] = useState({
    symbol: '',
    effectiveDate: getTodayIso(),
    actionType: 'cash_dividend' as PortfolioCorporateActionType,
    cashDividendPerShare: '',
    splitRatio: '',
    note: '',
  });

  const queryAccountId = selectedAccount === 'all' ? undefined : selectedAccount;
  const refreshViewKey = `${selectedAccount === 'all' ? 'all' : `account:${selectedAccount}`}:cost:${costMethod}`;
  const refreshContextRef = useRef<FxRefreshContext>({ viewKey: refreshViewKey, requestId: 0 });
  const hasAccounts = accounts.length > 0;
  const writableAccount = selectedAccount === 'all' ? undefined : accounts.find((item) => item.id === selectedAccount);
  const writableAccountId = writableAccount?.id;
  const writeBlocked = !writableAccountId;
  const totalEventPages = Math.max(1, Math.ceil(eventTotal / DEFAULT_PAGE_SIZE));
  const currentEventCount = eventType === 'trade'
    ? tradeEvents.length
    : eventType === 'cash'
      ? cashEvents.length
      : corporateEvents.length;

  const isActiveRefreshContext = (requestedViewKey: string, requestedRequestId: number) => {
    return (
      refreshContextRef.current.viewKey === requestedViewKey
      && refreshContextRef.current.requestId === requestedRequestId
    );
  };

  const loadAccounts = useCallback(async () => {
    try {
      const response = await portfolioApi.getAccounts(false);
      const items = response.accounts || [];
      setAccounts(items);
      setSelectedAccount((prev) => {
        if (items.length === 0) return 'all';
        if (prev !== 'all' && !items.some((item) => item.id === prev)) return items[0].id;
        return prev;
      });
      if (items.length === 0) setShowCreateAccount(true);
    } catch (err) {
      setError(getParsedApiError(err));
    }
  }, []);

  const loadBrokers = useCallback(async () => {
    try {
      const response = await portfolioApi.listImportBrokers();
      const brokerItems = response.brokers || [];
      if (brokerItems.length === 0) {
        setBrokers(FALLBACK_BROKERS);
        setBrokerLoadWarning('券商列表接口返回为空，已回退为内置券商列表（华泰/中信/招商）。');
        if (!FALLBACK_BROKERS.some((item) => item.broker === selectedBroker)) {
          setSelectedBroker(FALLBACK_BROKERS[0].broker);
        }
        return;
      }
      setBrokers(brokerItems);
      setBrokerLoadWarning(null);
      if (!brokerItems.some((item) => item.broker === selectedBroker)) {
        setSelectedBroker(brokerItems[0].broker);
      }
    } catch {
      setBrokers(FALLBACK_BROKERS);
      setBrokerLoadWarning('券商列表接口不可用，已回退为内置券商列表（华泰/中信/招商）。');
      if (!FALLBACK_BROKERS.some((item) => item.broker === selectedBroker)) {
        setSelectedBroker(FALLBACK_BROKERS[0].broker);
      }
    }
  }, [selectedBroker]);

  const loadPositions = useCallback(async () => {
    setIsLoading(true);
    try {
      const [positionsData, latestFxData] = await Promise.all([
        portfolioApi.listPositions({
          accountId: queryAccountId,
          costMethod,
        }),
        portfolioApi.getLatestFxRates({ toCurrency: 'CNY' }),
      ]);
      setPositions((positionsData.items || []).slice().sort((a, b) => Number(b.marketValueBase || 0) - Number(a.marketValueBase || 0)));
      setFxRates(latestFxData.items || []);
      setError(null);
    } catch (err) {
      setPositions([]);
      setFxRates([]);
      setError(getParsedApiError(err));
    } finally {
      setIsLoading(false);
    }
  }, [queryAccountId, costMethod]);

  const refreshStaticDataForScope = useCallback(async (
    requestedViewKey: string,
    requestedRequestId: number,
    requestedAccountId: number | undefined,
    requestedCostMethod: PortfolioCostMethod,
  ): Promise<boolean> => {
    if (!isActiveRefreshContext(requestedViewKey, requestedRequestId)) {
      return false;
    }

    try {
      const [positionsData, latestFxData] = await Promise.all([
        portfolioApi.listPositions({
          accountId: requestedAccountId,
          costMethod: requestedCostMethod,
        }),
        portfolioApi.getLatestFxRates({ toCurrency: 'CNY' }),
      ]);
      if (!isActiveRefreshContext(requestedViewKey, requestedRequestId)) {
        return false;
      }
      setPositions((positionsData.items || []).slice().sort((a, b) => Number(b.marketValueBase || 0) - Number(a.marketValueBase || 0)));
      setFxRates(latestFxData.items || []);
      setError(null);
      return true;
    } catch (err) {
      if (!isActiveRefreshContext(requestedViewKey, requestedRequestId)) {
        return false;
      }
      setPositions([]);
      setFxRates([]);
      setError(getParsedApiError(err));
      return false;
    }
  }, []);

  const loadEventsPage = useCallback(async (page: number) => {
    setEventLoading(true);
    try {
      if (eventType === 'trade') {
        const response = await portfolioApi.listTrades({
          accountId: queryAccountId,
          dateFrom: eventDateFrom || undefined,
          dateTo: eventDateTo || undefined,
          symbol: eventSymbol || undefined,
          side: eventSide || undefined,
          page,
          pageSize: DEFAULT_PAGE_SIZE,
        });
        setTradeEvents(response.items || []);
        setEventTotal(response.total || 0);
      } else if (eventType === 'cash') {
        const response = await portfolioApi.listCashLedger({
          accountId: queryAccountId,
          dateFrom: eventDateFrom || undefined,
          dateTo: eventDateTo || undefined,
          direction: eventDirection || undefined,
          page,
          pageSize: DEFAULT_PAGE_SIZE,
        });
        setCashEvents(response.items || []);
        setEventTotal(response.total || 0);
      } else {
        const response = await portfolioApi.listCorporateActions({
          accountId: queryAccountId,
          dateFrom: eventDateFrom || undefined,
          dateTo: eventDateTo || undefined,
          symbol: eventSymbol || undefined,
          actionType: eventActionType || undefined,
          page,
          pageSize: DEFAULT_PAGE_SIZE,
        });
        setCorporateEvents(response.items || []);
        setEventTotal(response.total || 0);
      }
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setEventLoading(false);
    }
  }, [
    eventActionType,
    eventDateFrom,
    eventDateTo,
    eventDirection,
    eventSide,
    eventSymbol,
    eventType,
    queryAccountId,
  ]);

  const loadEvents = useCallback(async () => {
    await loadEventsPage(eventPage);
  }, [eventPage, loadEventsPage]);

  const refreshPortfolioData = useCallback(async (page = eventPage) => {
    await Promise.all([loadPositions(), loadEventsPage(page)]);
  }, [eventPage, loadEventsPage, loadPositions]);

  useEffect(() => {
    void loadAccounts();
    void loadBrokers();
  }, [loadAccounts, loadBrokers]);

  useEffect(() => {
    void loadPositions();
  }, [loadPositions]);

  useEffect(() => {
    void loadEvents();
  }, [loadEvents]);

  useEffect(() => {
    refreshContextRef.current = {
      viewKey: refreshViewKey,
      requestId: refreshContextRef.current.requestId + 1,
    };
    setFxRefreshing(false);
    setFxRefreshFeedback(null);
  }, [refreshViewKey]);

  useEffect(() => {
    setEventPage(1);
  }, [eventType, queryAccountId, eventDateFrom, eventDateTo, eventSymbol, eventSide, eventDirection, eventActionType]);

  useEffect(() => {
    if (!writeBlocked) {
      setWriteWarning(null);
    }
  }, [writeBlocked]);

  const positionRows = positions;
  const totalMarketValue = useMemo(
    () => positionRows.reduce((sum, item) => sum + Number(item.marketValueBase || 0), 0),
    [positionRows],
  );
  const totalCost = useMemo(
    () => positionRows.reduce((sum, item) => sum + Number(item.totalCost || 0), 0),
    [positionRows],
  );
  const totalUnrealizedPnl = useMemo(
    () => positionRows.reduce((sum, item) => sum + Number(item.unrealizedPnlBase || 0), 0),
    [positionRows],
  );
  const cashByCurrency = useMemo(() => {
    const totals = new Map<string, number>();
    for (const row of positionRows) {
      const category = (row.assetCategory || '').trim().toLowerCase();
      const isCash = category === 'cash' || (row.symbol || '').toUpperCase().startsWith('CASH_');
      if (!isCash) continue;
      totals.set(row.currency, (totals.get(row.currency) || 0) + Number(row.marketValueBase || 0));
    }
    return Array.from(totals.entries()).map(([currency, amount]) => ({ currency, amount }));
  }, [positionRows]);
  const totalCash = useMemo(
    () => cashByCurrency.reduce((sum, item) => sum + Number(item.amount || 0), 0),
    [cashByCurrency],
  );
  const fxStale = useMemo(
    () => fxRates.some((item) => item.isStale),
    [fxRates],
  );
  const concentrationPieData = useMemo(() => {
    return positionRows
      .slice(0, 6)
      .map((item) => ({
        name: item.symbol,
        value: totalMarketValue > 0 ? (Number(item.marketValueBase || 0) / totalMarketValue) * 100 : 0,
      }))
      .filter((item) => item.value > 0);
  }, [positionRows, totalMarketValue]);

  const handleTradeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!writableAccountId) {
      setWriteWarning('请先在右上角选择具体账户，再进行录入或导入提交。');
      return;
    }
    try {
      setWriteWarning(null);
      await portfolioApi.createTrade({
        accountId: writableAccountId,
        symbol: tradeForm.symbol,
        tradeDate: tradeForm.tradeDate,
        side: tradeForm.side,
        quantity: Number(tradeForm.quantity),
        price: Number(tradeForm.price),
        fee: Number(tradeForm.fee || 0),
        tax: Number(tradeForm.tax || 0),
        tradeUid: tradeForm.tradeUid || undefined,
        note: tradeForm.note || undefined,
      });
      await refreshPortfolioData();
      setTradeForm((prev) => ({ ...prev, symbol: '', tradeUid: '', note: '' }));
    } catch (err) {
      setError(getParsedApiError(err));
    }
  };

  const handleCashSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!writableAccountId) {
      setWriteWarning('请先在右上角选择具体账户，再进行录入或导入提交。');
      return;
    }
    try {
      setWriteWarning(null);
      await portfolioApi.createCashLedger({
        accountId: writableAccountId,
        eventDate: cashForm.eventDate,
        direction: cashForm.direction,
        amount: Number(cashForm.amount),
        currency: cashForm.currency || undefined,
        note: cashForm.note || undefined,
      });
      await refreshPortfolioData();
      setCashForm((prev) => ({ ...prev, note: '' }));
    } catch (err) {
      setError(getParsedApiError(err));
    }
  };

  const handleCorporateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!writableAccountId) {
      setWriteWarning('请先在右上角选择具体账户，再进行录入或导入提交。');
      return;
    }
    try {
      setWriteWarning(null);
      await portfolioApi.createCorporateAction({
        accountId: writableAccountId,
        symbol: corpForm.symbol,
        effectiveDate: corpForm.effectiveDate,
        actionType: corpForm.actionType,
        cashDividendPerShare: corpForm.cashDividendPerShare ? Number(corpForm.cashDividendPerShare) : undefined,
        splitRatio: corpForm.splitRatio ? Number(corpForm.splitRatio) : undefined,
        note: corpForm.note || undefined,
      });
      await refreshPortfolioData();
      setCorpForm((prev) => ({ ...prev, symbol: '', note: '' }));
    } catch (err) {
      setError(getParsedApiError(err));
    }
  };

  const handleParseCsv = async () => {
    if (!csvFile) return;
    try {
      setCsvParsing(true);
      const parsed = await portfolioApi.parseCsvImport(selectedBroker, csvFile);
      setCsvParseResult(parsed);
      setCsvCommitResult(null);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setCsvParsing(false);
    }
  };

  const handleCommitCsv = async () => {
    if (!csvFile) return;
    if (!writableAccountId) {
      setWriteWarning('请先在右上角选择具体账户，再进行录入或导入提交。');
      return;
    }
    try {
      setWriteWarning(null);
      setCsvCommitting(true);
      const committed = await portfolioApi.commitCsvImport(writableAccountId, selectedBroker, csvFile, csvDryRun);
      setCsvCommitResult(committed);
      if (!csvDryRun) {
        await refreshPortfolioData();
      }
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setCsvCommitting(false);
    }
  };

  const openDeleteDialog = (item: PendingDelete) => {
    if (!writableAccountId) {
      setWriteWarning('请先在右上角选择具体账户，再进行删除修正。');
      return;
    }
    setPendingDelete(item);
  };

  const handleConfirmDelete = async () => {
    if (!pendingDelete || deleteLoading) return;
    if (!writableAccountId) {
      setWriteWarning('请先在右上角选择具体账户，再进行删除修正。');
      setPendingDelete(null);
      return;
    }

    const nextPage = currentEventCount === 1 && eventPage > 1 ? eventPage - 1 : eventPage;
    try {
      setDeleteLoading(true);
      setWriteWarning(null);
      if (pendingDelete.eventType === 'trade') {
        await portfolioApi.deleteTrade(pendingDelete.id);
      } else if (pendingDelete.eventType === 'cash') {
        await portfolioApi.deleteCashLedger(pendingDelete.id);
      } else {
        await portfolioApi.deleteCorporateAction(pendingDelete.id);
      }
      setPendingDelete(null);
      if (nextPage !== eventPage) {
        setEventPage(nextPage);
      }
      await refreshPortfolioData(nextPage);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleCreateAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = accountForm.name.trim();
    if (!name) {
      setAccountCreateError('账户名称不能为空。');
      setAccountCreateSuccess(null);
      return;
    }
    try {
      setAccountCreating(true);
      setAccountCreateError(null);
      setAccountCreateSuccess(null);
      const created = await portfolioApi.createAccount({
        name,
        broker: accountForm.broker.trim() || undefined,
        market: accountForm.market,
        baseCurrency: accountForm.baseCurrency.trim() || 'CNY',
      });
      await loadAccounts();
      setSelectedAccount(created.id);
      setShowCreateAccount(false);
      setWriteWarning(null);
      setAccountForm({
        name: '',
        broker: 'Demo',
        market: accountForm.market,
        baseCurrency: accountForm.baseCurrency,
      });
      setAccountCreateSuccess('账户创建成功，已自动切换到该账户。');
    } catch (err) {
      const parsed = getParsedApiError(err);
      setAccountCreateError(parsed.message || '创建账户失败，请稍后重试。');
      setAccountCreateSuccess(null);
    } finally {
      setAccountCreating(false);
    }
  };

  const handleRefresh = async () => {
    await Promise.all([loadAccounts(), loadPositions(), loadEvents(), loadBrokers()]);
  };

  const handleRefreshFx = async () => {
    if (!hasAccounts || isLoading || fxRefreshing) {
      return;
    }

    const requestedViewKey = refreshViewKey;
    const requestedAccountId = queryAccountId;
    const requestedCostMethod = costMethod;
    const requestedRequestId = refreshContextRef.current.requestId + 1;
    refreshContextRef.current = {
      viewKey: requestedViewKey,
      requestId: requestedRequestId,
    };

    try {
      setFxRefreshing(true);
      setFxRefreshFeedback(null);
      const result = await portfolioApi.refreshFx({
        accountId: requestedAccountId,
      });
      if (!isActiveRefreshContext(requestedViewKey, requestedRequestId)) {
        return;
      }
      const reloaded = await refreshStaticDataForScope(
        requestedViewKey,
        requestedRequestId,
        requestedAccountId,
        requestedCostMethod,
      );
      if (!reloaded || !isActiveRefreshContext(requestedViewKey, requestedRequestId)) {
        return;
      }
      setFxRefreshFeedback(buildFxRefreshFeedback(result));
    } catch (err) {
      if (!isActiveRefreshContext(requestedViewKey, requestedRequestId)) {
        return;
      }
      setError(getParsedApiError(err));
    } finally {
      if (isActiveRefreshContext(requestedViewKey, requestedRequestId)) {
        setFxRefreshing(false);
      }
    }
  };

  const pageTitle = initializationOnly ? '资产初始化' : '持仓管理';
  const pageDescription = initializationOnly
    ? '先完成账户建账、初始资产录入和券商 CSV 导入，再转入资产事件页维护持续流水。'
    : '组合快照、手工录入、CSV 导入与风险分析（支持全组合 / 单账户切换）';
  const selectedAccountLabel = selectedAccount === 'all'
    ? '全部账户'
    : `${writableAccount?.name || '账户'} (#${selectedAccount})`;
  const initializationSteps: StepBlockItem[] = [
    {
      label: '步骤 01',
      title: '新建账户',
      description: '设置账户名称、市场、基准币和券商，形成后续资产录入口径。',
    },
    {
      label: '步骤 02',
      title: '导入初始资产',
      description: '优先用券商 CSV 建账，也支持手工录入交易、现金和公司行为作为起始快照。',
    },
    {
      label: '步骤 03',
      title: '核对持仓结果',
      description: '确认总权益、现金与持仓明细后，再进入资产事件页持续维护台账。',
    },
  ];
  const initializationStatusItems: SummaryBlockItem[] = [
    {
      label: '账户数量',
      value: accounts.length,
      description: '已创建账户越完整，后续事件维护越顺畅。',
    },
    {
      label: '当前录入口径',
      value: selectedAccountLabel,
      description: '录入与导入提交都会写入当前选中的具体账户。',
    },
    {
      label: '初始持仓条数',
      value: positionRows.length,
      description: '用于判断初始化资产是否已经完整落账。',
    },
    {
      label: '初始化提示',
      value: '先录入起始状态',
      description: '增量交易、资金流水和公司行为统一放在资产事件页维护。',
    },
  ];
  const staticSummaryItems: SummaryBlockItem[] = [
    {
      label: 'Top1 仓位',
      value: formatPct(totalMarketValue > 0 ? (Number(positionRows[0]?.marketValueBase || 0) / totalMarketValue) * 100 : 0),
      description: '用于识别单一标的集中度。',
    },
    {
      label: '现金资产',
      value: formatMoney(totalCash, 'CNY'),
      description: '按静态持仓中的现金类资产汇总。',
    },
    {
      label: '高风险标的',
      value: positionRows.filter((row) => (row.assetRiskClass || '').toUpperCase() === 'R4' || (row.assetRiskClass || '').toUpperCase() === 'R5').length,
      description: '按初始化风险等级 R4/R5 统计。',
    },
    {
      label: '口径',
      value: costMethod.toUpperCase(),
      description: '当前视图按所选成本法计算持仓收益。',
    },
  ];

  return (
    <div className="portfolio-page min-h-screen space-y-3 p-3 md:p-4">
      <section className="space-y-2.5">
        <div className="space-y-2">
          <h1 className="text-xl font-semibold text-foreground md:text-2xl">{pageTitle}</h1>
          <p className="text-xs md:text-sm text-secondary">{pageDescription}</p>
        </div>
        {initializationOnly ? (
          <div className="grid grid-cols-1 gap-2 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
            <Card className="!rounded-xl" padding="sm">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-secondary">Initialization Workflow</p>
                  <h2 className="mt-1.5 text-base font-semibold text-foreground">三段式建账流程</h2>
                  <p className="mt-1 text-sm text-secondary">先建账户，再导入或录入初始资产，最后切到资产事件页维护后续交易与资金流水。</p>
                </div>
                <Badge variant={hasAccounts ? 'success' : 'warning'}>{hasAccounts ? '可开始录入' : '等待建账'}</Badge>
              </div>
              <InitializationStepGrid items={initializationSteps} />
            </Card>

            <Card className="!rounded-xl" padding="sm">
              <h2 className="text-base font-semibold text-foreground">当前建账状态</h2>
              <InitializationStatusGrid items={initializationStatusItems} />
            </Card>
          </div>
        ) : null}
        {hasAccounts ? (
          <div className="rounded-lg border border-white/10 bg-white/[0.02] p-2.5">
            <div className="grid grid-cols-1 items-end gap-2 xl:grid-cols-[minmax(0,1fr)_220px_280px]">
              <div>
                <p className="text-xs text-secondary mb-1">账户视图</p>
                <select
                  value={String(selectedAccount)}
                  onChange={(e) => setSelectedAccount(e.target.value === 'all' ? 'all' : Number(e.target.value))}
                  className={PORTFOLIO_SELECT_CLASS}
                >
                  <option value="all">全部账户</option>
                  {accounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name} (#{account.id})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <p className="text-xs text-secondary mb-1">成本口径</p>
                <select
                  value={costMethod}
                  onChange={(e) => setCostMethod(e.target.value as PortfolioCostMethod)}
                  className={PORTFOLIO_SELECT_CLASS}
                >
                  <option value="fifo">先进先出（FIFO）</option>
                  <option value="avg">均价成本（AVG）</option>
                </select>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  className="btn-secondary text-sm flex-1"
                  onClick={() => {
                    setShowCreateAccount((prev) => !prev);
                    setAccountCreateError(null);
                    setAccountCreateSuccess(null);
                  }}
                >
                  {showCreateAccount ? '收起账户表单' : '新建账户'}
                </button>
                <button
                  type="button"
                  onClick={() => void handleRefresh()}
                  disabled={isLoading || fxRefreshing}
                  className="btn-secondary text-sm flex-1"
                >
                  {isLoading ? '刷新中...' : '刷新数据'}
                </button>
              </div>
            </div>
          </div>
        ) : (
          <InlineAlert
            variant="warning"
            className="inline-block rounded-lg px-3 py-2 text-xs shadow-none"
            message="还没有可用账户，请先创建账户后再录入交易或导入 CSV。"
          />
        )}
      </section>

      {error ? <ApiErrorAlert error={error} onDismiss={() => setError(null)} /> : null}
      {writeWarning ? (
        <InlineAlert
          variant="warning"
          title="操作提示"
          message={writeWarning}
        />
      ) : null}

      {(showCreateAccount || !hasAccounts) ? (
        <Card className="!rounded-xl" padding="sm">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-foreground">新建账户</h2>
            {hasAccounts ? (
              <button
                type="button"
                className="btn-secondary text-xs px-3 py-1"
                onClick={() => {
                  setShowCreateAccount(false);
                  setAccountCreateError(null);
                  setAccountCreateSuccess(null);
                }}
              >
                收起
              </button>
            ) : (
              <span className="text-xs text-secondary">创建后自动切换到该账户</span>
            )}
          </div>
          {accountCreateError ? (
            <InlineAlert
              variant="danger"
              className="mt-2 rounded-lg px-2 py-1 text-xs shadow-none"
              title="创建账户失败"
              message={accountCreateError}
            />
          ) : null}
          {accountCreateSuccess ? (
            <InlineAlert
              variant="success"
              className="mt-2 rounded-lg px-2 py-1 text-xs shadow-none"
              title="创建账户成功"
              message={accountCreateSuccess}
            />
          ) : null}
          <form className="mt-2.5 grid grid-cols-1 gap-2 md:grid-cols-2" onSubmit={handleCreateAccount}>
            <input
              className={`${PORTFOLIO_INPUT_CLASS} md:col-span-2`}
              placeholder="账户名称（必填）"
              value={accountForm.name}
              onChange={(e) => setAccountForm((prev) => ({ ...prev, name: e.target.value }))}
            />
            <input
              className={PORTFOLIO_INPUT_CLASS}
              placeholder="券商（可选，如 Demo/华泰）"
              value={accountForm.broker}
              onChange={(e) => setAccountForm((prev) => ({ ...prev, broker: e.target.value }))}
            />
            <input
              className={PORTFOLIO_INPUT_CLASS}
              placeholder="基准币（如 CNY/USD/HKD）"
              value={accountForm.baseCurrency}
              onChange={(e) => setAccountForm((prev) => ({ ...prev, baseCurrency: e.target.value.toUpperCase() }))}
            />
            <select
              className={PORTFOLIO_SELECT_CLASS}
              value={accountForm.market}
              onChange={(e) => setAccountForm((prev) => ({ ...prev, market: e.target.value as 'cn' | 'hk' | 'us' }))}
            >
              <option value="cn">市场：A 股（cn）</option>
              <option value="hk">市场：港股（hk）</option>
              <option value="us">市场：美股（us）</option>
            </select>
            <button type="submit" className="btn-secondary text-sm !py-1.5" disabled={accountCreating}>
              {accountCreating ? '创建中...' : '创建账户'}
            </button>
          </form>
        </Card>
      ) : null}

      <section className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-4">
        <Card className="!rounded-xl" variant="gradient" padding="sm">
          <p className="text-xs text-secondary">总权益</p>
          <p className="mt-1 text-xl font-semibold text-foreground">{formatMoney(totalMarketValue, 'CNY')}</p>
        </Card>
        <Card className="!rounded-xl" variant="gradient" padding="sm">
          <p className="text-xs text-secondary">总市值</p>
          <p className="mt-1 text-xl font-semibold text-foreground">{formatMoney(totalMarketValue, 'CNY')}</p>
        </Card>
        <Card className="!rounded-xl" variant="gradient" padding="sm">
          <p className="text-xs text-secondary">总现金</p>
          <p className="mt-1 text-xl font-semibold text-foreground">{formatMoney(totalCash, 'CNY')}</p>
        </Card>
        <Card className="!rounded-xl" variant="gradient" padding="sm">
          <div className="flex items-start justify-between gap-3">
            <p className="text-xs text-secondary">汇率状态</p>
            <button
              type="button"
              className="btn-secondary !px-3 !py-1 !text-xs shrink-0"
              onClick={() => void handleRefreshFx()}
              disabled={!hasAccounts || isLoading || fxRefreshing}
            >
              {fxRefreshing ? '刷新中...' : '刷新汇率'}
            </button>
          </div>
          <div className="mt-2">{fxStale ? <Badge variant="warning">过期</Badge> : <Badge variant="success">最新</Badge>}</div>
          {fxRefreshFeedback ? (
            <InlineAlert
              variant={getFxRefreshFeedbackVariant(fxRefreshFeedback.tone)}
              title="汇率刷新结果"
              message={fxRefreshFeedback.text}
              className="mt-2 rounded-lg px-3 py-2 text-xs shadow-none"
            />
          ) : null}
        </Card>
      </section>

      <section className="grid grid-cols-1 gap-2 xl:grid-cols-3">
        <Card className="xl:col-span-2 !rounded-xl" padding="sm">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-foreground">持仓明细</h2>
            <span className="text-xs text-secondary">共 {positionRows.length} 项</span>
          </div>
          {positionRows.length === 0 ? (
              <EmptyState
                title={initializationOnly ? '当前无初始化资产' : '当前无持仓数据'}
                description={initializationOnly ? '导入券商 CSV 或录入第一笔初始资产后，这里会展示建账结果。' : '录入交易或导入 CSV 后，这里会展示按账户汇总的持仓明细。'}
                className="border-none bg-transparent px-4 py-8 shadow-none"
              />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead className="text-xs text-secondary border-b border-white/10">
                  <tr>
                    <th className="py-1.5 pr-2 text-left">账户</th>
                    <th className="py-1.5 pr-2 text-left">代码</th>
                    <th className="py-1.5 pr-2 text-right">数量</th>
                    <th className="py-1.5 pr-2 text-right">均价</th>
                    <th className="py-1.5 pr-2 text-right">现价</th>
                    <th className="py-1.5 pr-2 text-right">市值</th>
                    <th className="py-1.5 text-right">未实现盈亏</th>
                    <th className="py-1.5 text-right">收益率</th>
                  </tr>
                </thead>
                <tbody>
                  {positionRows.map((row) => (
                    <tr key={`${row.accountId}-${row.symbol}-${row.market}`} className="border-b border-white/5">
                      <td className="py-1.5 pr-2 text-secondary">{row.accountName}</td>
                      <td className="py-1.5 pr-2 font-mono text-foreground">{row.symbol}</td>
                      <td className="py-1.5 pr-2 text-right">{row.quantity.toFixed(2)}</td>
                      <td className="py-1.5 pr-2 text-right">{row.avgCost.toFixed(4)}</td>
                      <td className="py-1.5 pr-2 text-right">
                        <div>{formatPositionPrice(row)}</div>
                        <div className={`text-[11px] ${hasPositionPrice(row) ? 'text-secondary' : 'text-warning'}`}>
                          {getPositionPriceLabel(row)}
                        </div>
                      </td>
                      <td className="py-1.5 pr-2 text-right">{formatPositionMoney(row.marketValueBase, row)}</td>
                      <td
                        className={`py-1.5 text-right ${
                          hasPositionPrice(row)
                            ? row.unrealizedPnlBase >= 0
                              ? 'text-success'
                              : 'text-danger'
                            : 'text-secondary'
                        }`}
                      >
                        {formatPositionMoney(row.unrealizedPnlBase, row)}
                      </td>
                      <td
                        className={`py-1.5 text-right ${
                          hasPositionPrice(row) && row.unrealizedPnlPct !== null && row.unrealizedPnlPct !== undefined
                            ? row.unrealizedPnlPct >= 0
                              ? 'text-success'
                              : 'text-danger'
                            : 'text-secondary'
                        }`}
                      >
                        {formatSignedPct(row.unrealizedPnlPct)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {initializationOnly ? (
          <Card className="!rounded-xl" padding="sm">
            <h2 className="mb-2 text-sm font-semibold text-foreground">初始化核对要点</h2>
            <div className="space-y-2 text-sm text-secondary">
              <p>核对总权益、现金余额和持仓数量是否与券商期初资产一致。</p>
              <p>如需补录历史交易、资金流水或公司行为，请切换到资产事件页统一维护台账。</p>
              <p>成本口径会影响快照展示，建账完成后再根据习惯选择 FIFO 或 AVG。</p>
            </div>
          </Card>
        ) : (
          <Card padding="md">
            <h2 className="text-sm font-semibold text-foreground mb-3">静态持仓集中度</h2>
            {concentrationPieData.length > 0 ? (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={concentrationPieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90}>
                      {concentrationPieData.map((entry, index) => (
                        <Cell key={`cell-${entry.name}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value) => `${Number(value).toFixed(2)}%`} />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <EmptyState
                title="暂无集中度数据"
                description="完成资产录入后，这里会展示静态持仓的前六大集中度分布。"
                className="border-none bg-transparent px-4 py-10 shadow-none"
              />
            )}
            <div className="mt-3 text-xs text-secondary space-y-1">
              {staticSummaryItems.map((item) => (
                <div key={item.label}>{item.label}: {item.value}</div>
              ))}
            </div>
          </Card>
        )}
      </section>

      {writeBlocked && hasAccounts ? (
        <InlineAlert
          variant="warning"
          className="rounded-lg px-3 py-2 text-xs shadow-none"
          message="当前处于“全部账户”视图。为避免误写，请先选择一个具体账户后再进行手工录入或 CSV 提交。"
        />
      ) : null}

      {!initializationOnly ? (
      <section className="grid grid-cols-1 gap-2 md:grid-cols-3">
        <Card className="!rounded-xl" padding="sm">
          <h3 className="text-sm font-semibold text-foreground mb-2">集中度观察</h3>
          <div className="text-xs text-secondary space-y-1">
            <div>Top1 仓位: {formatPct(totalMarketValue > 0 ? (Number(positionRows[0]?.marketValueBase || 0) / totalMarketValue) * 100 : 0)}</div>
            <div>前 3 仓位: {formatPct(totalMarketValue > 0 ? (positionRows.slice(0, 3).reduce((sum, row) => sum + Number(row.marketValueBase || 0), 0) / totalMarketValue) * 100 : 0)}</div>
            <div>持仓总数: {positionRows.length}</div>
          </div>
        </Card>
        <Card className="!rounded-xl" padding="sm">
          <h3 className="text-sm font-semibold text-foreground mb-2">收益观察</h3>
          <div className="text-xs text-secondary space-y-1">
            <div>未实现收益: {formatMoney(totalUnrealizedPnl, 'CNY')}</div>
            <div>静态收益率: {formatPct(totalCost > 0 ? (totalUnrealizedPnl / totalCost) * 100 : 0)}</div>
            <div>盈利标的: {positionRows.filter((row) => Number(row.unrealizedPnlBase || 0) > 0).length}</div>
          </div>
        </Card>
        <Card className="!rounded-xl" padding="sm">
          <h3 className="text-sm font-semibold text-foreground mb-2">口径</h3>
          <div className="text-xs text-secondary space-y-1">
            <div>账户数: {selectedAccount === 'all' ? accounts.length : (writableAccount ? 1 : 0)}</div>
            <div>计价币种: CNY</div>
            <div>成本法: {costMethod.toUpperCase()}</div>
          </div>
        </Card>
      </section>
      ) : null}

      <section className="grid grid-cols-1 gap-2 xl:grid-cols-3">
        <Card className="!rounded-xl" padding="sm">
          <h3 className="mb-2 text-sm font-semibold text-foreground">{initializationOnly ? '初始资产录入：交易' : '手工录入：交易'}</h3>
          <form className="space-y-2" onSubmit={handleTradeSubmit}>
            <input className={PORTFOLIO_INPUT_CLASS} placeholder="股票代码（例如 600519）" value={tradeForm.symbol}
              onChange={(e) => setTradeForm((prev) => ({ ...prev, symbol: e.target.value }))} required />
            <div className="grid grid-cols-2 gap-2">
              <input className={PORTFOLIO_INPUT_CLASS} type="date" value={tradeForm.tradeDate}
                onChange={(e) => setTradeForm((prev) => ({ ...prev, tradeDate: e.target.value }))} required />
              <select className={PORTFOLIO_SELECT_CLASS} value={tradeForm.side}
                onChange={(e) => setTradeForm((prev) => ({ ...prev, side: e.target.value as PortfolioSide }))}>
                <option value="buy">买入</option>
                <option value="sell">卖出</option>
              </select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <input className={PORTFOLIO_INPUT_CLASS} type="number" min="0" step="0.0001" placeholder="数量（必填）" value={tradeForm.quantity}
                onChange={(e) => setTradeForm((prev) => ({ ...prev, quantity: e.target.value }))} required />
              <input className={PORTFOLIO_INPUT_CLASS} type="number" min="0" step="0.0001" placeholder="成交价（必填）" value={tradeForm.price}
                onChange={(e) => setTradeForm((prev) => ({ ...prev, price: e.target.value }))} required />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <input className={PORTFOLIO_INPUT_CLASS} type="number" min="0" step="0.0001" placeholder="手续费（可选）" value={tradeForm.fee}
                onChange={(e) => setTradeForm((prev) => ({ ...prev, fee: e.target.value }))} />
              <input className={PORTFOLIO_INPUT_CLASS} type="number" min="0" step="0.0001" placeholder="税费（可选）" value={tradeForm.tax}
                onChange={(e) => setTradeForm((prev) => ({ ...prev, tax: e.target.value }))} />
            </div>
            <input className={PORTFOLIO_INPUT_CLASS} placeholder="流水编号（可选）" value={tradeForm.tradeUid}
              onChange={(e) => setTradeForm((prev) => ({ ...prev, tradeUid: e.target.value }))} />
            <textarea className={PORTFOLIO_TEXTAREA_CLASS} placeholder="备注（可选）" value={tradeForm.note}
              onChange={(e) => setTradeForm((prev) => ({ ...prev, note: e.target.value }))} />
            <p className="text-xs text-secondary">手续费和税费可留空，系统将按 0 处理。</p>
            <button type="submit" className="btn-secondary w-full !py-1.5" disabled={!writableAccountId}>提交交易</button>
          </form>
        </Card>

        <Card className="!rounded-xl" padding="sm">
          <h3 className="mb-2 text-sm font-semibold text-foreground">{initializationOnly ? '初始资产录入：资金' : '手工录入：资金流水'}</h3>
          <form className="space-y-2" onSubmit={handleCashSubmit}>
            <div className="grid grid-cols-2 gap-2">
              <input className={PORTFOLIO_INPUT_CLASS} type="date" value={cashForm.eventDate}
                onChange={(e) => setCashForm((prev) => ({ ...prev, eventDate: e.target.value }))} required />
              <select className={PORTFOLIO_SELECT_CLASS} value={cashForm.direction}
                onChange={(e) => setCashForm((prev) => ({ ...prev, direction: e.target.value as PortfolioCashDirection }))}>
                <option value="in">流入</option>
                <option value="out">流出</option>
              </select>
            </div>
            <input className={PORTFOLIO_INPUT_CLASS} type="number" min="0" step="0.0001" placeholder="金额"
              value={cashForm.amount} onChange={(e) => setCashForm((prev) => ({ ...prev, amount: e.target.value }))} required />
            <input className={PORTFOLIO_INPUT_CLASS} placeholder={`币种（可选，默认 ${writableAccount?.baseCurrency || '账户基准币'}）`} value={cashForm.currency}
              onChange={(e) => setCashForm((prev) => ({ ...prev, currency: e.target.value }))} />
            <textarea className={PORTFOLIO_TEXTAREA_CLASS} placeholder="备注（可选）" value={cashForm.note}
              onChange={(e) => setCashForm((prev) => ({ ...prev, note: e.target.value }))} />
            <button type="submit" className="btn-secondary w-full !py-1.5" disabled={!writableAccountId}>提交资金流水</button>
          </form>
        </Card>

        <Card className="!rounded-xl" padding="sm">
          <h3 className="mb-2 text-sm font-semibold text-foreground">{initializationOnly ? '初始资产录入：公司行为' : '手工录入：公司行为'}</h3>
          <form className="space-y-2" onSubmit={handleCorporateSubmit}>
            <input className={PORTFOLIO_INPUT_CLASS} placeholder="股票代码" value={corpForm.symbol}
              onChange={(e) => setCorpForm((prev) => ({ ...prev, symbol: e.target.value }))} required />
            <div className="grid grid-cols-2 gap-2">
              <input className={PORTFOLIO_INPUT_CLASS} type="date" value={corpForm.effectiveDate}
                onChange={(e) => setCorpForm((prev) => ({ ...prev, effectiveDate: e.target.value }))} required />
              <select className={PORTFOLIO_SELECT_CLASS} value={corpForm.actionType}
                onChange={(e) => setCorpForm((prev) => ({ ...prev, actionType: e.target.value as PortfolioCorporateActionType }))}>
                <option value="cash_dividend">现金分红</option>
                <option value="split_adjustment">拆并股调整</option>
              </select>
            </div>
            {corpForm.actionType === 'cash_dividend' ? (
              <input className={PORTFOLIO_INPUT_CLASS} type="number" min="0" step="0.000001" placeholder="每股分红"
                value={corpForm.cashDividendPerShare}
                onChange={(e) => setCorpForm((prev) => ({ ...prev, cashDividendPerShare: e.target.value, splitRatio: '' }))} required />
            ) : (
              <input className={PORTFOLIO_INPUT_CLASS} type="number" min="0" step="0.000001" placeholder="拆并股比例"
                value={corpForm.splitRatio}
                onChange={(e) => setCorpForm((prev) => ({ ...prev, splitRatio: e.target.value, cashDividendPerShare: '' }))} required />
            )}
            <textarea className={PORTFOLIO_TEXTAREA_CLASS} placeholder="备注（可选）" value={corpForm.note}
              onChange={(e) => setCorpForm((prev) => ({ ...prev, note: e.target.value }))} />
            <button type="submit" className="btn-secondary w-full !py-1.5" disabled={!writableAccountId}>提交企业行为</button>
          </form>
        </Card>
      </section>

      <section className="grid grid-cols-1 gap-2 xl:grid-cols-2">
        <Card className="!rounded-xl" padding="sm">
          <h3 className="mb-2 text-sm font-semibold text-foreground">券商 CSV 导入</h3>
          {initializationOnly ? <p className="mb-2 text-xs text-secondary">优先导入期初持仓或历史对账单，形成初始化资产底稿。</p> : null}
          <div className="space-y-2">
            {brokerLoadWarning ? (
              <InlineAlert
                variant="warning"
                className="rounded-lg px-2 py-1 text-xs shadow-none"
                message={brokerLoadWarning}
              />
            ) : null}
            <div className="grid grid-cols-2 gap-2">
              <select className={PORTFOLIO_SELECT_CLASS} value={selectedBroker} onChange={(e) => setSelectedBroker(e.target.value)}>
                {brokers.length > 0 ? (
                  brokers.map((item) => <option key={item.broker} value={item.broker}>{formatBrokerLabel(item.broker, item.displayName)}</option>)
                ) : (
                  <option value="huatai">huatai（华泰）</option>
                )}
              </select>
              <label className={PORTFOLIO_FILE_PICKER_CLASS}>
                选择 CSV
                <input type="file" accept=".csv" className="hidden"
                  onChange={(e) => setCsvFile(e.target.files && e.target.files[0] ? e.target.files[0] : null)} />
              </label>
            </div>
            <div className="flex items-center gap-2 text-xs text-secondary">
              <input id="csv-dry-run" type="checkbox" checked={csvDryRun} onChange={(e) => setCsvDryRun(e.target.checked)} />
              <label htmlFor="csv-dry-run">仅预演（不写入）</label>
            </div>
            <div className="flex gap-2">
              <button type="button" className="btn-secondary flex-1 !py-1.5" disabled={!csvFile || csvParsing} onClick={() => void handleParseCsv()}>
                {csvParsing ? '解析中...' : '解析文件'}
              </button>
              <button type="button" className="btn-secondary flex-1 !py-1.5"
                disabled={!csvFile || !writableAccountId || csvCommitting} onClick={() => void handleCommitCsv()}>
                {csvCommitting ? '提交中...' : '提交导入'}
              </button>
            </div>
            {csvParseResult ? (
              <InlineAlert
                variant={getCsvParseVariant(csvParseResult)}
                title="CSV 解析结果"
                message={`有效 ${csvParseResult.recordCount} 条，跳过 ${csvParseResult.skippedCount} 条，错误 ${csvParseResult.errorCount} 条。`}
                className="rounded-lg px-3 py-2 text-xs shadow-none"
              />
            ) : null}
            {csvCommitResult ? (
              <InlineAlert
                variant={getCsvCommitVariant(csvCommitResult, csvDryRun)}
                title={csvDryRun ? 'CSV 预演结果' : 'CSV 提交结果'}
                message={`${csvDryRun ? '预演检查' : '实际写入'}：写入 ${csvCommitResult.insertedCount} 条，重复 ${csvCommitResult.duplicateCount} 条，失败 ${csvCommitResult.failedCount} 条。`}
                className="rounded-lg px-3 py-2 text-xs shadow-none"
              />
            ) : null}
          </div>
        </Card>

        {!initializationOnly ? (
        <Card className="!rounded-xl" padding="sm">
          <h3 className="mb-2 text-sm font-semibold text-foreground">事件记录</h3>
          <div className="space-y-2">
            <div className="grid grid-cols-2 gap-2">
              <select className={PORTFOLIO_SELECT_CLASS} value={eventType} onChange={(e) => setEventType(e.target.value as EventType)}>
                <option value="trade">交易流水</option>
                <option value="cash">资金流水</option>
                <option value="corporate">公司行为</option>
              </select>
              <button type="button" className="btn-secondary text-sm !py-1.5" onClick={() => void loadEvents()} disabled={eventLoading}>
                {eventLoading ? '加载中...' : '刷新流水'}
              </button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <input className={PORTFOLIO_INPUT_CLASS} type="date" value={eventDateFrom} onChange={(e) => setEventDateFrom(e.target.value)} />
              <input className={PORTFOLIO_INPUT_CLASS} type="date" value={eventDateTo} onChange={(e) => setEventDateTo(e.target.value)} />
            </div>
            {(eventType === 'trade' || eventType === 'corporate') ? (
              <input className={PORTFOLIO_INPUT_CLASS} placeholder="按股票代码筛选" value={eventSymbol}
                onChange={(e) => setEventSymbol(e.target.value)} />
            ) : null}
            {eventType === 'trade' ? (
              <select className={PORTFOLIO_SELECT_CLASS} value={eventSide} onChange={(e) => setEventSide(e.target.value as '' | PortfolioSide)}>
                <option value="">全部买卖方向</option>
                <option value="buy">买入</option>
                <option value="sell">卖出</option>
              </select>
            ) : null}
            {eventType === 'cash' ? (
              <select className={PORTFOLIO_SELECT_CLASS} value={eventDirection}
                onChange={(e) => setEventDirection(e.target.value as '' | PortfolioCashDirection)}>
                <option value="">全部资金方向</option>
                <option value="in">流入</option>
                <option value="out">流出</option>
              </select>
            ) : null}
            {eventType === 'corporate' ? (
              <select className={PORTFOLIO_SELECT_CLASS} value={eventActionType}
                onChange={(e) => setEventActionType(e.target.value as '' | PortfolioCorporateActionType)}>
                <option value="">全部公司行为</option>
                <option value="cash_dividend">现金分红</option>
                <option value="split_adjustment">拆并股调整</option>
              </select>
            ) : null}
            <div className="text-[11px] text-secondary">
              {writeBlocked ? '删除修正仅在单账户视图可用。请先选择具体账户后再删除错误流水。' : '如有错误流水，可直接删除后重新录入。'}
            </div>
            <div className="max-h-64 overflow-auto rounded-lg border border-white/10 p-2">
              {eventType === 'trade' && tradeEvents.map((item) => (
                <div key={`t-${item.id}`} className="flex items-start justify-between gap-2 border-b border-white/5 py-1.5 text-xs text-secondary">
                  <div className="min-w-0">
                    {item.tradeDate} {formatSideLabel(item.side)} {item.symbol} 数量={item.quantity} 价格={item.price}
                  </div>
                  {!writeBlocked ? (
                    <button
                      type="button"
                      className="btn-secondary shrink-0 !px-2.5 !py-1 !text-[11px]"
                      onClick={() => openDeleteDialog({
                        eventType: 'trade',
                        id: item.id,
                        message: `确认删除 ${item.tradeDate} 的${formatSideLabel(item.side)}流水 ${item.symbol}（数量 ${item.quantity}，价格 ${item.price}）吗？`,
                      })}
                    >
                      删除
                    </button>
                  ) : null}
                </div>
              ))}
              {eventType === 'cash' && cashEvents.map((item) => (
                <div key={`c-${item.id}`} className="flex items-start justify-between gap-2 border-b border-white/5 py-1.5 text-xs text-secondary">
                  <div className="min-w-0">
                    {item.eventDate} {formatCashDirectionLabel(item.direction)} {item.amount} {item.currency}
                  </div>
                  {!writeBlocked ? (
                    <button
                      type="button"
                      className="btn-secondary shrink-0 !px-2.5 !py-1 !text-[11px]"
                      onClick={() => openDeleteDialog({
                        eventType: 'cash',
                        id: item.id,
                        message: `确认删除 ${item.eventDate} 的资金流水（${formatCashDirectionLabel(item.direction)} ${item.amount} ${item.currency}）吗？`,
                      })}
                    >
                      删除
                    </button>
                  ) : null}
                </div>
              ))}
              {eventType === 'corporate' && corporateEvents.map((item) => (
                <div key={`ca-${item.id}`} className="flex items-start justify-between gap-2 border-b border-white/5 py-1.5 text-xs text-secondary">
                  <div className="min-w-0">
                    {item.effectiveDate} {formatCorporateActionLabel(item.actionType)} {item.symbol}
                  </div>
                  {!writeBlocked ? (
                    <button
                      type="button"
                      className="btn-secondary shrink-0 !px-2.5 !py-1 !text-[11px]"
                      onClick={() => openDeleteDialog({
                        eventType: 'corporate',
                        id: item.id,
                        message: `确认删除 ${item.effectiveDate} 的公司行为 ${formatCorporateActionLabel(item.actionType)}（${item.symbol}）吗？`,
                      })}
                    >
                      删除
                    </button>
                  ) : null}
                </div>
              ))}
              {!eventLoading
                && ((eventType === 'trade' && tradeEvents.length === 0)
                  || (eventType === 'cash' && cashEvents.length === 0)
                  || (eventType === 'corporate' && corporateEvents.length === 0)) ? (
                    <EmptyState
                      title="暂无流水"
                      description="调整筛选条件或先录入一笔交易、资金流水或公司行为。"
                      className="border-none bg-transparent px-3 py-6 shadow-none"
                    />
                  ) : null}
            </div>
            <div className="flex items-center justify-between text-xs text-secondary">
              <span>第 {eventPage} / {totalEventPages} 页</span>
              <div className="flex gap-2">
                <button type="button" className="btn-secondary text-xs px-3 py-1" disabled={eventPage <= 1}
                  onClick={() => setEventPage((prev) => Math.max(1, prev - 1))}>
                  上一页
                </button>
                <button type="button" className="btn-secondary text-xs px-3 py-1" disabled={eventPage >= totalEventPages}
                  onClick={() => setEventPage((prev) => Math.min(totalEventPages, prev + 1))}>
                  下一页
                </button>
              </div>
            </div>
          </div>
        </Card>
        ) : (
        <Card className="!rounded-xl" padding="sm">
          <h3 className="mb-2 text-sm font-semibold text-foreground">初始化说明</h3>
          <div className="space-y-2 text-sm text-secondary">
            <p>当前页面只负责三件事：新建账户、导入券商 CSV、录入初始持仓。</p>
            <p>交易流水、资金流水、公司行为的持续维护，已经迁移到“资产事件”页面统一管理。</p>
            <p>第一阶段先把账本起好，后续再补资产分类、估值口径和多资产扩展。</p>
          </div>
        </Card>
        )}
      </section>
      <ConfirmDialog
        isOpen={Boolean(pendingDelete)}
        title="删除错误流水"
        message={pendingDelete?.message || '确认删除这条流水吗？'}
        confirmText={deleteLoading ? '删除中...' : '确认删除'}
        cancelText="取消"
        isDanger
        onConfirm={() => void handleConfirmDelete()}
        onCancel={() => {
          if (!deleteLoading) {
            setPendingDelete(null);
          }
        }}
      />
    </div>
  );
};

export default PortfolioPage;
