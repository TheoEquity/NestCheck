import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { portfolioApi } from '../api/portfolio';
import { ApiErrorAlert, AppPage, Button, Card, InlineAlert, PageHeader } from '../components/common';
import { toDateInputValue } from '../utils/format';
import type {
  PortfolioAccountItem,
  PortfolioCashLedgerListItem,
  PortfolioCorporateActionListItem,
  PortfolioPositionRecordItem,
  PortfolioTradeListItem,
} from '../types/portfolio';

type AccountMarket = 'cn' | 'hk' | 'us';
type CurrencyCode = 'CNY' | 'HKD' | 'USD';
type AssetCategory = 'fund' | 'stock' | 'bond';
type AssetSubcategory = '' | 'pure_bond_fund' | 'fixed_income_plus' | 'index_fund' | 'equity_fund';
type AssetRiskClass = 'R1' | 'R2' | 'R3' | 'R4' | 'R5';
type LedgerEventType = 'all' | 'trade' | 'cash' | 'cash_dividend';

type LedgerFilters = {
  accountId: number | '';
  eventType: LedgerEventType;
  symbol: string;
  dateFrom: string;
  dateTo: string;
};

type LedgerRow = {
  key: string;
  date: string;
  typeLabel: string;
  accountId: number;
  accountName: string;
  symbol: string;
  name: string;
  direction: string;
  amount: string;
  price: string;
  note: string;
};

const INPUT_CLASS = 'input-surface input-focus-glow h-8 w-full rounded-lg border bg-transparent px-2.5 text-xs transition-all focus:outline-none';
const SELECT_CLASS = `${INPUT_CLASS} appearance-none pr-8`;

const ASSET_CATEGORY_OPTIONS: Array<{ value: AssetCategory; label: string }> = [
  { value: 'fund', label: '基金' },
  { value: 'stock', label: '股票' },
  { value: 'bond', label: '债券' },
];

const FUND_SUBCATEGORY_OPTIONS: Array<{ value: AssetSubcategory; label: string }> = [
  { value: '', label: '请选择' },
  { value: 'pure_bond_fund', label: '纯债基金' },
  { value: 'fixed_income_plus', label: '固收+' },
  { value: 'index_fund', label: '指数基金' },
  { value: 'equity_fund', label: '股票基金' },
];

const RISK_CLASS_OPTIONS: AssetRiskClass[] = ['R1', 'R2', 'R3', 'R4', 'R5'];

const LEDGER_EVENT_TYPE_OPTIONS: Array<{ value: LedgerEventType; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'trade', label: '交易' },
  { value: 'cash', label: '资金' },
  { value: 'cash_dividend', label: '现金分红' },
];

const normalizeCurrencyCode = (value?: string | null): CurrencyCode => {
  if (value === 'HKD' || value === 'USD') return value;
  return 'CNY';
};

const getTodayIso = () => toDateInputValue(new Date());

const formatNumber = (value: number) => Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 4 });

const AssetEventsPage: React.FC = () => {
  const navigate = useNavigate();
  const [accounts, setAccounts] = useState<PortfolioAccountItem[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<number | ''>('');
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [positions, setPositions] = useState<PortfolioPositionRecordItem[]>([]);
  const [recentTrades, setRecentTrades] = useState<PortfolioTradeListItem[]>([]);
  const [recentCashLedgers, setRecentCashLedgers] = useState<PortfolioCashLedgerListItem[]>([]);
  const [recentCorporateActions, setRecentCorporateActions] = useState<PortfolioCorporateActionListItem[]>([]);
  const [ledgerFilters, setLedgerFilters] = useState<LedgerFilters>({ accountId: '', eventType: 'all', symbol: '', dateFrom: '', dateTo: '' });
  const [tradeForm, setTradeForm] = useState({
    assetCategory: 'stock' as AssetCategory,
    assetSubcategory: '' as AssetSubcategory,
    assetRiskClass: 'R3' as AssetRiskClass,
    symbol: '',
    name: '',
    tradeDate: getTodayIso(),
    side: 'buy' as 'buy' | 'sell',
    quantity: '',
    price: '',
    fee: '',
    tax: '',
    note: '',
  });
  const [cashForm, setCashForm] = useState({
    eventDate: getTodayIso(),
    direction: 'in' as 'in' | 'out',
    amount: '',
    note: '',
  });
  const [corpForm, setCorpForm] = useState({
    symbol: '',
    effectiveDate: getTodayIso(),
    dividendAmount: '',
    note: '',
  });

  useEffect(() => {
    document.title = '资产事件 - NestCheck';
  }, []);

  useEffect(() => {
    let mounted = true;
    const loadData = async () => {
      setLoading(true);
      try {
        const [accountData, positionData, tradeData, cashData, corporateData] = await Promise.all([
          portfolioApi.getAccounts(false),
          portfolioApi.listPositions(),
          portfolioApi.listTrades({ page: 1, pageSize: 8 }),
          portfolioApi.listCashLedger({ page: 1, pageSize: 8 }),
          portfolioApi.listCorporateActions({ page: 1, pageSize: 8 }),
        ]);
        if (!mounted) return;
        setAccounts(accountData.accounts);
        setPositions(positionData.items);
        setRecentTrades(tradeData.items);
        setRecentCashLedgers(cashData.items);
        setRecentCorporateActions(corporateData.items);
        setSelectedAccountId((prev) => prev || accountData.accounts[0]?.id || '');
      } catch (err) {
        if (mounted) setError(getParsedApiError(err));
      } finally {
        if (mounted) setLoading(false);
      }
    };
    void loadData();
    return () => {
      mounted = false;
    };
  }, []);

  const selectedAccount = useMemo(
    () => accounts.find((item) => item.id === selectedAccountId) || null,
    [accounts, selectedAccountId],
  );

  const accountNameById = useMemo(() => {
    const map = new Map<number, string>();
    accounts.forEach((account) => map.set(account.id, account.name));
    return map;
  }, [accounts]);

  const positionNameByAccountSymbol = useMemo(() => {
    const map = new Map<string, string>();
    positions.forEach((position) => {
      if (position.name) {
        map.set(`${position.accountId}:${position.symbol}`, position.name);
      }
    });
    return map;
  }, [positions]);

  const tradeAmount = useMemo(() => {
    const quantity = Number(tradeForm.quantity || 0);
    const price = Number(tradeForm.price || 0);
    const fee = Number(tradeForm.fee || 0);
    const tax = Number(tradeForm.tax || 0);
    const gross = quantity * price;
    return tradeForm.side === 'buy' ? gross + fee + tax : gross - fee - tax;
  }, [tradeForm.fee, tradeForm.price, tradeForm.quantity, tradeForm.side, tradeForm.tax]);

  const cashAmount = Number(cashForm.amount || 0);
  const corporateDividendAmount = Number(corpForm.dividendAmount || 0);

  const selectedAccountPositions = useMemo(
    () => positions.filter((item) => item.accountId === selectedAccountId && item.assetCategory !== 'cash' && item.quantity > 0),
    [positions, selectedAccountId],
  );

  const selectedCorporatePosition = useMemo(
    () => selectedAccountPositions.find((item) => item.symbol === corpForm.symbol) || null,
    [corpForm.symbol, selectedAccountPositions],
  );

  const updateTradeForm = (patch: Partial<typeof tradeForm>) => {
    setTradeForm((prev) => ({ ...prev, ...patch }));
  };

  const updateCashForm = (patch: Partial<typeof cashForm>) => {
    setCashForm((prev) => ({ ...prev, ...patch }));
  };

  const updateCorpForm = (patch: Partial<typeof corpForm>) => {
    setCorpForm((prev) => ({ ...prev, ...patch }));
  };

  const updateLedgerFilters = (patch: Partial<LedgerFilters>) => {
    setLedgerFilters((prev) => ({ ...prev, ...patch }));
  };

  const buildLedgerQuery = (eventType: LedgerEventType) => {
    const query: { accountId?: number; symbol?: string; dateFrom?: string; dateTo?: string; actionType?: 'cash_dividend'; page: number; pageSize: number } = {
      page: 1,
      pageSize: 50,
    };
    if (ledgerFilters.accountId !== '') {
      query.accountId = ledgerFilters.accountId;
    }
    const symbol = ledgerFilters.symbol.trim();
    if (symbol && eventType !== 'cash') {
      query.symbol = symbol;
    }
    if (ledgerFilters.dateFrom) {
      query.dateFrom = ledgerFilters.dateFrom;
    }
    if (ledgerFilters.dateTo) {
      query.dateTo = ledgerFilters.dateTo;
    }
    if (eventType === 'cash_dividend') {
      query.actionType = 'cash_dividend';
    }
    return query;
  };

  const ledgerRows = useMemo<LedgerRow[]>(() => {
    const rows: LedgerRow[] = [];
    recentTrades.forEach((item) => {
      rows.push({
        key: `trade-${item.id}`,
        date: item.tradeDate,
        typeLabel: '交易',
        accountId: item.accountId,
        accountName: accountNameById.get(item.accountId) || '--',
        symbol: item.symbol,
        name: item.name || positionNameByAccountSymbol.get(`${item.accountId}:${item.symbol}`) || '--',
        direction: item.side === 'buy' ? '买入' : '卖出',
        amount: formatNumber(item.quantity),
        price: formatNumber(item.price),
        note: item.note || `本单盈利 ${formatNumber(item.realizedPnl || 0)}`,
      });
    });
    recentCashLedgers.forEach((item) => {
      rows.push({
        key: `cash-${item.id}`,
        date: item.eventDate,
        typeLabel: '资金',
        accountId: item.accountId,
        accountName: accountNameById.get(item.accountId) || '--',
        symbol: 'CASH',
        name: '现金',
        direction: item.direction === 'in' ? '流入' : '流出',
        amount: `${item.currency} ${formatNumber(item.amount)}`,
        price: '--',
        note: item.note || '现金流水',
      });
    });
    recentCorporateActions.forEach((item) => {
      const dividendAmount = item.realizedPnl || item.dividendAmount || 0;
      rows.push({
        key: `cash-dividend-${item.id}`,
        date: item.effectiveDate,
        typeLabel: '现金分红',
        accountId: item.accountId,
        accountName: accountNameById.get(item.accountId) || '--',
        symbol: item.symbol,
        name: positionNameByAccountSymbol.get(`${item.accountId}:${item.symbol}`) || '--',
        direction: '现金分红',
        amount: `${item.currency} ${formatNumber(dividendAmount)}`,
        price: '--',
        note: item.note || `现金分红，本单盈利${formatNumber(dividendAmount)}元，不影响成本`,
      });
    });
    return rows.sort((a, b) => b.date.localeCompare(a.date));
  }, [accountNameById, positionNameByAccountSymbol, recentCashLedgers, recentCorporateActions, recentTrades]);

  const refreshLedger = async () => {
    const requests: Array<Promise<void>> = [];
    if (ledgerFilters.eventType === 'all' || ledgerFilters.eventType === 'trade') {
      requests.push(portfolioApi.listTrades(buildLedgerQuery('trade')).then((data) => setRecentTrades(data.items)));
    } else {
      setRecentTrades([]);
    }
    if (ledgerFilters.eventType === 'all' || ledgerFilters.eventType === 'cash') {
      requests.push(portfolioApi.listCashLedger(buildLedgerQuery('cash')).then((data) => setRecentCashLedgers(data.items)));
    } else {
      setRecentCashLedgers([]);
    }
    if (ledgerFilters.eventType === 'all' || ledgerFilters.eventType === 'cash_dividend') {
      requests.push(portfolioApi.listCorporateActions(buildLedgerQuery('cash_dividend')).then((data) => setRecentCorporateActions(data.items)));
    } else {
      setRecentCorporateActions([]);
    }
    await Promise.all(requests);
  };

  const refreshRecentTrades = async () => {
    const data = await portfolioApi.listTrades({ page: 1, pageSize: 8 });
    setRecentTrades(data.items);
  };

  const refreshRecentCashLedgers = async () => {
    const data = await portfolioApi.listCashLedger({ page: 1, pageSize: 8 });
    setRecentCashLedgers(data.items);
  };

  const refreshPositions = async () => {
    const data = await portfolioApi.listPositions();
    setPositions(data.items);
  };

  const refreshRecentCorporateActions = async () => {
    const data = await portfolioApi.listCorporateActions({ page: 1, pageSize: 8 });
    setRecentCorporateActions(data.items);
  };

  const handleTradeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAccount) {
      setError({ title: '请选择账户', message: '请先选择账户后再保存交易事件。', rawMessage: 'account is required', category: 'missing_params' });
      return;
    }
    setSubmitting(true);
    setError(null);
    setSuccessMessage(null);
    try {
      await portfolioApi.createTrade({
        accountId: selectedAccount.id,
        assetCategory: tradeForm.assetCategory,
        assetSubcategory: tradeForm.assetCategory === 'fund' ? tradeForm.assetSubcategory || undefined : undefined,
        assetRiskClass: tradeForm.assetRiskClass,
        symbol: tradeForm.symbol.trim(),
        name: tradeForm.name.trim() || undefined,
        tradeDate: tradeForm.tradeDate,
        side: tradeForm.side,
        quantity: Number(tradeForm.quantity),
        price: Number(tradeForm.price),
        fee: Number(tradeForm.fee || 0),
        tax: Number(tradeForm.tax || 0),
        market: selectedAccount.market as AccountMarket,
        currency: normalizeCurrencyCode(selectedAccount.baseCurrency),
        note: tradeForm.note.trim() || undefined,
      });
      await Promise.all([refreshRecentTrades(), refreshPositions()]);
      setSuccessMessage('交易事件已写入，持仓主数据和现金资产已同步更新。');
      setTradeForm((prev) => ({ ...prev, symbol: '', name: '', quantity: '', price: '', fee: '', tax: '', note: '' }));
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleCashSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAccount) {
      setError({ title: '请选择账户', message: '请先选择账户后再保存资金流水。', rawMessage: 'account is required', category: 'missing_params' });
      return;
    }
    setSubmitting(true);
    setError(null);
    setSuccessMessage(null);
    try {
      await portfolioApi.createCashLedger({
        accountId: selectedAccount.id,
        assetCategory: 'cash',
        assetRiskClass: 'R1',
        eventDate: cashForm.eventDate,
        direction: cashForm.direction,
        amount: Number(cashForm.amount),
        currency: normalizeCurrencyCode(selectedAccount.baseCurrency),
        note: cashForm.note.trim() || undefined,
      });
      await refreshRecentCashLedgers();
      setSuccessMessage('资金流水已写入，对应账户现金金额已同步更新。');
      setCashForm((prev) => ({ ...prev, amount: '', note: '' }));
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleCorporateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAccount || !selectedCorporatePosition) {
      setError({ title: '请选择标的', message: '请先选择当前账户下已有持仓标的。', rawMessage: 'position is required', category: 'missing_params' });
      return;
    }
    setSubmitting(true);
    setError(null);
    setSuccessMessage(null);
    try {
      await portfolioApi.createCorporateAction({
        accountId: selectedAccount.id,
        symbol: selectedCorporatePosition.symbol,
        assetCategory: selectedCorporatePosition.assetCategory || undefined,
        assetSubcategory: selectedCorporatePosition.assetSubcategory || undefined,
        effectiveDate: corpForm.effectiveDate,
        actionType: 'cash_dividend',
        market: selectedCorporatePosition.market as AccountMarket,
        currency: selectedCorporatePosition.currency,
        dividendAmount: Number(corpForm.dividendAmount),
        note: corpForm.note.trim() || undefined,
      });
      await Promise.all([refreshRecentCorporateActions(), refreshPositions()]);
      setSuccessMessage('现金分红事件已写入，对应账户现金金额已同步增加。');
      setCorpForm((prev) => ({ ...prev, dividendAmount: '', note: '' }));
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppPage className="max-w-[1600px] space-y-3">
      <PageHeader
        eyebrow="Portfolio Ledger"
        title="资产事件"
        description="把交易、资金流水和现金分红集中管理，初始化页只负责账户和初始资产。"
        className="!rounded-xl !px-4 !py-3"
        actions={(
          <Button type="button" variant="secondary" onClick={() => navigate('/assets/init')}>
            账户初始化
          </Button>
        )}
      />
      {error ? <ApiErrorAlert error={error} onDismiss={() => setError(null)} /> : null}
      {successMessage ? <InlineAlert variant="success" title="已保存" message={successMessage} /> : null}
      <section className="grid gap-2 xl:grid-cols-3">
        <Card className="!rounded-xl" padding="sm">
          <form className="flex h-full flex-col gap-2" onSubmit={handleTradeSubmit}>
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-secondary">Trade Event</p>
              <h2 className="mt-1 text-base font-semibold text-foreground">交易事件</h2>
              <p className="mt-1 text-sm text-secondary">写入事件记录，同步更新持仓主数据和现金资产。</p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <label className="text-xs text-secondary">账户
                <select className={`${SELECT_CLASS} mt-1`} value={selectedAccountId} onChange={(e) => setSelectedAccountId(e.target.value ? Number(e.target.value) : '')} disabled={loading}>
                  <option value="">请选择账户</option>
                  {accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
                </select>
              </label>
              <div className="text-xs text-secondary">市场/币种
                <div className="mt-1 flex h-8 items-center rounded-lg border border-border/40 bg-background/40 px-2.5 text-xs text-foreground">
                  {selectedAccount ? `${selectedAccount.market.toUpperCase()} / ${selectedAccount.baseCurrency}` : '--'}
                </div>
              </div>
              <label className="text-xs text-secondary">资产大类
                <select className={`${SELECT_CLASS} mt-1`} value={tradeForm.assetCategory} onChange={(e) => {
                  const nextCategory = e.target.value as AssetCategory;
                  const defaultRiskClass: Record<AssetCategory, AssetRiskClass> = { fund: 'R3', stock: 'R3', bond: 'R2' };
                  updateTradeForm({ assetCategory: nextCategory, assetSubcategory: nextCategory === 'fund' ? tradeForm.assetSubcategory : '', assetRiskClass: defaultRiskClass[nextCategory] });
                }}>
                  {ASSET_CATEGORY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
              <label className="text-xs text-secondary">资产子类
                <select className={`${SELECT_CLASS} mt-1`} value={tradeForm.assetSubcategory} disabled={tradeForm.assetCategory !== 'fund'} onChange={(e) => updateTradeForm({ assetSubcategory: e.target.value as AssetSubcategory })}>
                  {tradeForm.assetCategory === 'fund' ? FUND_SUBCATEGORY_OPTIONS.map((option) => <option key={option.value || 'empty'} value={option.value}>{option.label}</option>) : <option value="">--</option>}
                </select>
              </label>
              <label className="text-xs text-secondary">风险分类
                <select className={`${SELECT_CLASS} mt-1`} value={tradeForm.assetRiskClass} onChange={(e) => updateTradeForm({ assetRiskClass: e.target.value as AssetRiskClass })}>
                  {RISK_CLASS_OPTIONS.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
              <label className="text-xs text-secondary">方向
                <select className={`${SELECT_CLASS} mt-1`} value={tradeForm.side} onChange={(e) => updateTradeForm({ side: e.target.value as 'buy' | 'sell' })}>
                  <option value="buy">买入</option>
                  <option value="sell">卖出</option>
                </select>
              </label>
              <label className="text-xs text-secondary">代码
                <input className={`${INPUT_CLASS} mt-1`} required placeholder="600100 / AAPL" value={tradeForm.symbol} onChange={(e) => updateTradeForm({ symbol: e.target.value })} />
              </label>
              <label className="text-xs text-secondary">标的名称
                <input className={`${INPUT_CLASS} mt-1`} placeholder="资产名称" value={tradeForm.name} onChange={(e) => updateTradeForm({ name: e.target.value })} />
              </label>
              <label className="text-xs text-secondary">交易日期
                <input className={`${INPUT_CLASS} mt-1`} required type="date" value={tradeForm.tradeDate} onChange={(e) => updateTradeForm({ tradeDate: e.target.value })} />
              </label>
              <label className="text-xs text-secondary">数量
                <input className={`${INPUT_CLASS} mt-1`} required type="number" min="0" step="0.0001" value={tradeForm.quantity} onChange={(e) => updateTradeForm({ quantity: e.target.value })} />
              </label>
              <label className="text-xs text-secondary">价格
                <input className={`${INPUT_CLASS} mt-1`} required type="number" min="0" step="0.0001" value={tradeForm.price} onChange={(e) => updateTradeForm({ price: e.target.value })} />
              </label>
              <label className="text-xs text-secondary">费用/税费
                <div className="mt-1 grid grid-cols-2 gap-1">
                  <input className={INPUT_CLASS} type="number" min="0" step="0.0001" placeholder="手续费" value={tradeForm.fee} onChange={(e) => updateTradeForm({ fee: e.target.value })} />
                  <input className={INPUT_CLASS} type="number" min="0" step="0.0001" placeholder="税费" value={tradeForm.tax} onChange={(e) => updateTradeForm({ tax: e.target.value })} />
                </div>
              </label>
            </div>
            <label className="text-xs text-secondary">备注
              <input className={`${INPUT_CLASS} mt-1`} placeholder="可选" value={tradeForm.note} onChange={(e) => updateTradeForm({ note: e.target.value })} />
            </label>
            <div className="mt-auto flex items-center justify-between gap-2 rounded-lg border border-border/40 bg-surface/40 px-3 py-2 text-xs text-secondary">
              <span>{tradeForm.side === 'buy' ? '现金扣减' : '现金增加'}：{selectedAccount?.baseCurrency || '--'} {formatNumber(tradeAmount)}</span>
              <Button type="submit" size="sm" variant="primary" disabled={submitting || !selectedAccount}>{submitting ? '保存中...' : '保存交易'}</Button>
            </div>
          </form>
        </Card>

        <Card className="!rounded-xl" padding="sm">
          <form className="flex h-full flex-col gap-2" onSubmit={handleCashSubmit}>
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-secondary">Cash Ledger</p>
              <h2 className="mt-1 text-base font-semibold text-foreground">资金流水</h2>
              <p className="mt-1 text-sm text-secondary">记录现金流入/流出，提交后直接增减账户现金金额。</p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <label className="text-xs text-secondary">账户
                <select className={`${SELECT_CLASS} mt-1`} value={selectedAccountId} onChange={(e) => setSelectedAccountId(e.target.value ? Number(e.target.value) : '')} disabled={loading}>
                  <option value="">请选择账户</option>
                  {accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
                </select>
              </label>
              <div className="text-xs text-secondary">市场/币种
                <div className="mt-1 flex h-8 items-center rounded-lg border border-border/40 bg-background/40 px-2.5 text-xs text-foreground">
                  {selectedAccount ? `${selectedAccount.market.toUpperCase()} / ${selectedAccount.baseCurrency}` : '--'}
                </div>
              </div>
              <label className="text-xs text-secondary">交易方向
                <select className={`${SELECT_CLASS} mt-1`} value={cashForm.direction} onChange={(e) => updateCashForm({ direction: e.target.value as 'in' | 'out' })}>
                  <option value="in">流入</option>
                  <option value="out">流出</option>
                </select>
              </label>
              <div className="text-xs text-secondary">标的
                <div className="mt-1 flex h-8 items-center rounded-lg border border-border/40 bg-background/40 px-2.5 text-xs text-foreground">现金</div>
              </div>
              <label className="text-xs text-secondary">交易日期
                <input className={`${INPUT_CLASS} mt-1`} required type="date" value={cashForm.eventDate} onChange={(e) => updateCashForm({ eventDate: e.target.value })} />
              </label>
              <label className="text-xs text-secondary">金额
                <input className={`${INPUT_CLASS} mt-1`} required type="number" min="0" step="0.0001" value={cashForm.amount} onChange={(e) => updateCashForm({ amount: e.target.value })} />
              </label>
            </div>
            <label className="text-xs text-secondary">备注
              <input className={`${INPUT_CLASS} mt-1`} placeholder="可选" value={cashForm.note} onChange={(e) => updateCashForm({ note: e.target.value })} />
            </label>
            <div className="mt-auto rounded-lg border border-border/40 bg-surface/40 px-3 py-2 text-xs text-secondary">
              <div className="flex items-center justify-between gap-2">
                <span>{cashForm.direction === 'in' ? '现金增加' : '现金减少'}：{selectedAccount?.baseCurrency || '--'} {formatNumber(cashAmount)}</span>
                <Button type="submit" size="sm" variant="primary" disabled={submitting || !selectedAccount}>{submitting ? '保存中...' : '保存流水'}</Button>
              </div>
            </div>
          </form>
        </Card>

        <Card className="!rounded-xl" padding="sm">
          <form className="flex h-full flex-col gap-2" onSubmit={handleCorporateSubmit}>
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-secondary">Cash Dividend</p>
              <h2 className="mt-1 text-base font-semibold text-foreground">现金分红</h2>
              <p className="mt-1 text-sm text-secondary">记录标的物现金分红事件。</p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <label className="text-xs text-secondary">账户
                <select className={`${SELECT_CLASS} mt-1`} value={selectedAccountId} onChange={(e) => setSelectedAccountId(e.target.value ? Number(e.target.value) : '')} disabled={loading}>
                  <option value="">请选择账户</option>
                  {accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
                </select>
              </label>
              <div className="text-xs text-secondary">市场/币种
                <div className="mt-1 flex h-8 items-center rounded-lg border border-border/40 bg-background/40 px-2.5 text-xs text-foreground">
                  {selectedCorporatePosition ? `${selectedCorporatePosition.market.toUpperCase()} / ${selectedCorporatePosition.currency}` : selectedAccount ? `${selectedAccount.market.toUpperCase()} / ${selectedAccount.baseCurrency}` : '--'}
                </div>
              </div>
              <label className="text-xs text-secondary">标的
                <select className={`${SELECT_CLASS} mt-1`} required value={corpForm.symbol} onChange={(e) => updateCorpForm({ symbol: e.target.value })}>
                  <option value="">选择已有持仓</option>
                  {selectedAccountPositions.map((item) => <option key={`${item.accountId}-${item.market}-${item.symbol}`} value={item.symbol}>{item.symbol} {item.name || ''}</option>)}
                </select>
              </label>
              <label className="text-xs text-secondary">事件日期
                <input className={`${INPUT_CLASS} mt-1`} required type="date" value={corpForm.effectiveDate} onChange={(e) => updateCorpForm({ effectiveDate: e.target.value })} />
              </label>
              <label className="text-xs text-secondary">分红金额
                <input className={`${INPUT_CLASS} mt-1`} required type="number" min="0" step="0.0001" value={corpForm.dividendAmount} onChange={(e) => updateCorpForm({ dividendAmount: e.target.value })} />
              </label>
              <div className="text-xs text-secondary">当前持仓数量
                <div className="mt-1 flex h-8 items-center rounded-lg border border-border/40 bg-background/40 px-2.5 text-xs text-foreground">
                  {selectedCorporatePosition ? formatNumber(selectedCorporatePosition.quantity) : '--'}
                </div>
              </div>
            </div>
            <label className="text-xs text-secondary">备注
              <input className={`${INPUT_CLASS} mt-1`} placeholder="可选" value={corpForm.note} onChange={(e) => updateCorpForm({ note: e.target.value })} />
            </label>
            <div className="mt-auto rounded-lg border border-border/40 bg-surface/40 px-3 py-2 text-xs text-secondary">
              <div className="flex items-center justify-between gap-2">
                <span>现金增加：{selectedCorporatePosition?.currency || selectedAccount?.baseCurrency || '--'} {formatNumber(corporateDividendAmount)}</span>
                <Button type="submit" size="sm" variant="primary" disabled={submitting || !selectedAccount || !selectedCorporatePosition}>{submitting ? '保存中...' : '保存分红'}</Button>
              </div>
            </div>
          </form>
        </Card>
      </section>

      <Card className="!rounded-xl" padding="sm">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-secondary">Event Ledger</p>
            <h2 className="mt-1 text-base font-semibold text-foreground">交易台账</h2>
            <p className="mt-1 text-sm text-secondary">展示交易、资金流水和现金分红；事件记录用于审计，账面调整通过新增反向事件处理。</p>
          </div>
          <div className="grid gap-2 md:grid-cols-3 xl:grid-cols-6">
            <label className="text-xs text-secondary">账户名称
              <select className={`${SELECT_CLASS} mt-1`} value={ledgerFilters.accountId} onChange={(e) => updateLedgerFilters({ accountId: e.target.value ? Number(e.target.value) : '' })}>
                <option value="">全部账户</option>
                {accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
              </select>
            </label>
            <label className="text-xs text-secondary">事件类型
              <select className={`${SELECT_CLASS} mt-1`} value={ledgerFilters.eventType} onChange={(e) => updateLedgerFilters({ eventType: e.target.value as LedgerEventType })}>
                {LEDGER_EVENT_TYPE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label className="text-xs text-secondary">标的代码
              <input className={`${INPUT_CLASS} mt-1`} value={ledgerFilters.symbol} onChange={(e) => updateLedgerFilters({ symbol: e.target.value })} placeholder="如 510500" />
            </label>
            <label className="text-xs text-secondary">起始日期
              <input className={`${INPUT_CLASS} mt-1`} type="date" value={ledgerFilters.dateFrom} onChange={(e) => updateLedgerFilters({ dateFrom: e.target.value })} />
            </label>
            <label className="text-xs text-secondary">终止日期
              <input className={`${INPUT_CLASS} mt-1`} type="date" value={ledgerFilters.dateTo} onChange={(e) => updateLedgerFilters({ dateTo: e.target.value })} />
            </label>
            <div className="flex items-end gap-2">
              <Button size="sm" type="button" onClick={() => void refreshLedger()} disabled={loading}>筛选</Button>
              <Button size="sm" variant="ghost" type="button" onClick={() => setLedgerFilters({ accountId: '', eventType: 'all', symbol: '', dateFrom: '', dateTo: '' })}>重置</Button>
            </div>
          </div>
        </div>
        <div className="mt-3 overflow-x-auto rounded-lg border border-border/40">
          <table className="w-full min-w-[980px] text-sm">
            <thead className="bg-surface/60 text-xs text-secondary">
              <tr>
                <th className="px-3 py-2 text-left">日期</th>
                <th className="px-3 py-2 text-left">事件类型</th>
                <th className="px-3 py-2 text-left">账户ID</th>
                <th className="px-3 py-2 text-left">账户名称</th>
                <th className="px-3 py-2 text-left">标的代码</th>
                <th className="px-3 py-2 text-left">标的名称</th>
                <th className="px-3 py-2 text-left">方向</th>
                <th className="px-3 py-2 text-right">数量/金额</th>
                <th className="px-3 py-2 text-right">价格/比率</th>
                <th className="px-3 py-2 text-left">备注</th>
                <th className="px-3 py-2 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {ledgerRows.length === 0 ? (
                <tr>
                  <td colSpan={11} className="px-3 py-8 text-center text-sm text-secondary">
                    暂无事件记录。
                  </td>
                </tr>
              ) : null}
              {ledgerRows.map((item) => (
                <tr key={item.key} className="border-t border-border/50 odd:bg-background/70 even:bg-surface/20">
                  <td className="px-3 py-2 text-left">{item.date}</td>
                  <td className="px-3 py-2 text-left">{item.typeLabel}</td>
                  <td className="px-3 py-2 text-left">#{item.accountId}</td>
                  <td className="px-3 py-2 text-left">{item.accountName}</td>
                  <td className="px-3 py-2 text-left">{item.symbol}</td>
                  <td className="px-3 py-2 text-left">{item.name}</td>
                  <td className="px-3 py-2 text-left">{item.direction}</td>
                  <td className="px-3 py-2 text-right">{item.amount}</td>
                  <td className="px-3 py-2 text-right">{item.price}</td>
                  <td className="px-3 py-2 text-left">{item.note}</td>
                  <td className="px-3 py-2 text-right text-secondary">--</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </AppPage>
  );
};

export default AssetEventsPage;
