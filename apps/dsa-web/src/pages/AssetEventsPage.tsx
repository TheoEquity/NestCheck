import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { portfolioApi } from '../api/portfolio';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { ApiErrorAlert, AppPage, Button, Card, ConfirmDialog, EmptyState, PageHeader } from '../components/common';
import { toDateInputValue } from '../utils/format';
import type {
  PortfolioAccountItem,
  PortfolioCashDirection,
  PortfolioCashLedgerListItem,
  PortfolioCorporateActionListItem,
  PortfolioCorporateActionType,
  PortfolioSide,
  PortfolioTradeListItem,
} from '../types/portfolio';

type EventType = 'trade' | 'cash' | 'corporate';
type PendingDelete =
  | { eventType: 'trade'; id: number; message: string }
  | { eventType: 'cash'; id: number; message: string }
  | { eventType: 'corporate'; id: number; message: string };

const INPUT_CLASS = 'input-surface input-focus-glow h-9 w-full rounded-lg border bg-transparent px-3 text-sm transition-all focus:outline-none';
const SELECT_CLASS = `${INPUT_CLASS} appearance-none pr-10`;
const PAGE_SIZE = 20;

const getTodayIso = () => toDateInputValue(new Date());
const formatSideLabel = (value: PortfolioSide) => (value === 'buy' ? '买入' : '卖出');
const formatDirectionLabel = (value: PortfolioCashDirection) => (value === 'in' ? '流入' : '流出');
const formatActionLabel = (value: PortfolioCorporateActionType) => (value === 'cash_dividend' ? '现金分红' : '拆并股调整');
const TEXTAREA_CLASS = 'input-surface input-focus-glow min-h-[80px] w-full rounded-lg border bg-transparent px-3 py-2 text-sm transition-all focus:outline-none';

const formatNumericCell = (value: number | string | undefined | null) => {
  if (value == null || value === '') return '--';
  return String(value);
};

const formatTextCell = (value: string | undefined | null, fallback = '--') => {
  const normalized = value?.trim();
  return normalized && normalized.length > 0 ? normalized : fallback;
};

const formatMoneyCell = (amount: number | string | undefined | null, currency?: string | null) => {
  const amountText = formatNumericCell(amount);
  const currencyText = formatTextCell(currency, '');
  return currencyText ? `${amountText} ${currencyText}` : amountText;
};

const AssetEventsPage: React.FC = () => {
  useEffect(() => {
    document.title = '资产事件 - DSA';
  }, []);

  const [accounts, setAccounts] = useState<PortfolioAccountItem[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<'all' | number>('all');
  const [eventType, setEventType] = useState<EventType>('trade');
  const [eventPage, setEventPage] = useState(1);
  const [eventTotal, setEventTotal] = useState(0);
  const [eventDateFrom, setEventDateFrom] = useState('');
  const [eventDateTo, setEventDateTo] = useState('');
  const [eventSymbol, setEventSymbol] = useState('');
  const [eventSide, setEventSide] = useState<'' | PortfolioSide>('');
  const [eventDirection, setEventDirection] = useState<'' | PortfolioCashDirection>('');
  const [eventActionType, setEventActionType] = useState<'' | PortfolioCorporateActionType>('');
  const [tradeEvents, setTradeEvents] = useState<PortfolioTradeListItem[]>([]);
  const [cashEvents, setCashEvents] = useState<PortfolioCashLedgerListItem[]>([]);
  const [corporateEvents, setCorporateEvents] = useState<PortfolioCorporateActionListItem[]>([]);
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [eventLoading, setEventLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);

  const [tradeForm, setTradeForm] = useState({ symbol: '', tradeDate: getTodayIso(), side: 'buy' as PortfolioSide, quantity: '', price: '', fee: '', tax: '', tradeUid: '', note: '' });
  const [cashForm, setCashForm] = useState({ eventDate: getTodayIso(), direction: 'in' as PortfolioCashDirection, amount: '', currency: '', note: '' });
  const [corpForm, setCorpForm] = useState({ symbol: '', effectiveDate: getTodayIso(), actionType: 'cash_dividend' as PortfolioCorporateActionType, cashDividendPerShare: '', splitRatio: '', note: '' });

  const writableAccountId = selectedAccount === 'all' ? undefined : selectedAccount;
  const totalPages = Math.max(1, Math.ceil(eventTotal / PAGE_SIZE));

  const loadAccounts = useCallback(async () => {
    try {
      const response = await portfolioApi.getAccounts(false);
      setAccounts(response.accounts || []);
    } catch (err) {
      setError(getParsedApiError(err));
    }
  }, []);

  const loadEvents = useCallback(async (page: number) => {
    setEventLoading(true);
    try {
      const accountId = selectedAccount === 'all' ? undefined : selectedAccount;
      if (eventType === 'trade') {
        const response = await portfolioApi.listTrades({ accountId, dateFrom: eventDateFrom || undefined, dateTo: eventDateTo || undefined, symbol: eventSymbol || undefined, side: eventSide || undefined, page, pageSize: PAGE_SIZE });
        setTradeEvents(response.items || []);
        setEventTotal(response.total || 0);
      } else if (eventType === 'cash') {
        const response = await portfolioApi.listCashLedger({ accountId, dateFrom: eventDateFrom || undefined, dateTo: eventDateTo || undefined, direction: eventDirection || undefined, page, pageSize: PAGE_SIZE });
        setCashEvents(response.items || []);
        setEventTotal(response.total || 0);
      } else {
        const response = await portfolioApi.listCorporateActions({ accountId, dateFrom: eventDateFrom || undefined, dateTo: eventDateTo || undefined, symbol: eventSymbol || undefined, actionType: eventActionType || undefined, page, pageSize: PAGE_SIZE });
        setCorporateEvents(response.items || []);
        setEventTotal(response.total || 0);
      }
      setError(null);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setEventLoading(false);
    }
  }, [eventActionType, eventDateFrom, eventDateTo, eventDirection, eventSide, eventSymbol, eventType, selectedAccount]);

  useEffect(() => {
    void loadAccounts();
  }, [loadAccounts]);

  useEffect(() => {
    void loadEvents(eventPage);
  }, [eventPage, loadEvents]);

  useEffect(() => {
    setEventPage(1);
  }, [eventType, selectedAccount, eventDateFrom, eventDateTo, eventDirection, eventSide, eventSymbol, eventActionType]);

  const handleTradeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!writableAccountId) return;
    try {
      await portfolioApi.createTrade({ accountId: writableAccountId, symbol: tradeForm.symbol, tradeDate: tradeForm.tradeDate, side: tradeForm.side, quantity: Number(tradeForm.quantity), price: Number(tradeForm.price), fee: Number(tradeForm.fee || 0), tax: Number(tradeForm.tax || 0), tradeUid: tradeForm.tradeUid || undefined, note: tradeForm.note || undefined });
      await loadEvents(1);
      setEventPage(1);
      setTradeForm((prev) => ({ ...prev, symbol: '', quantity: '', price: '', fee: '', tax: '', tradeUid: '', note: '' }));
    } catch (err) {
      setError(getParsedApiError(err));
    }
  };

  const handleCashSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!writableAccountId) return;
    try {
      await portfolioApi.createCashLedger({ accountId: writableAccountId, eventDate: cashForm.eventDate, direction: cashForm.direction, amount: Number(cashForm.amount), currency: cashForm.currency || undefined, note: cashForm.note || undefined });
      await loadEvents(1);
      setEventPage(1);
      setCashForm((prev) => ({ ...prev, amount: '', currency: '', note: '' }));
    } catch (err) {
      setError(getParsedApiError(err));
    }
  };

  const handleCorporateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!writableAccountId) return;
    try {
      await portfolioApi.createCorporateAction({ accountId: writableAccountId, symbol: corpForm.symbol, effectiveDate: corpForm.effectiveDate, actionType: corpForm.actionType, cashDividendPerShare: corpForm.cashDividendPerShare ? Number(corpForm.cashDividendPerShare) : undefined, splitRatio: corpForm.splitRatio ? Number(corpForm.splitRatio) : undefined, note: corpForm.note || undefined });
      await loadEvents(1);
      setEventPage(1);
      setCorpForm((prev) => ({ ...prev, symbol: '', cashDividendPerShare: '', splitRatio: '', note: '' }));
    } catch (err) {
      setError(getParsedApiError(err));
    }
  };

  const currentItems = useMemo(() => eventType === 'trade' ? tradeEvents : eventType === 'cash' ? cashEvents : corporateEvents, [cashEvents, corporateEvents, eventType, tradeEvents]);
  const selectedAccountLabel = selectedAccount === 'all'
    ? '全部账户'
    : accounts.find((item) => item.id === selectedAccount)?.name || `账户 #${selectedAccount}`;

  const handleDelete = async () => {
    if (!pendingDelete) return;
    try {
      setDeleteLoading(true);
      if (pendingDelete.eventType === 'trade') await portfolioApi.deleteTrade(pendingDelete.id);
      if (pendingDelete.eventType === 'cash') await portfolioApi.deleteCashLedger(pendingDelete.id);
      if (pendingDelete.eventType === 'corporate') await portfolioApi.deleteCorporateAction(pendingDelete.id);
      setPendingDelete(null);
      await loadEvents(eventPage);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setDeleteLoading(false);
    }
  };

  return (
    <AppPage className="max-w-[1600px] space-y-3">
      <PageHeader eyebrow="Portfolio Ledger" title="资产事件" description="把交易、资金流水和公司行为集中管理，初始化页只负责账户和初始资产。" className="!rounded-xl !px-4 !py-3" />
      {error ? <ApiErrorAlert error={error} /> : null}

      <div className="grid gap-2 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Card className="!rounded-xl" padding="sm">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-secondary">Event Workflow</p>
              <h2 className="mt-1.5 text-base font-semibold text-foreground">增量台账维护</h2>
              <p className="mt-1 text-sm text-secondary">资产事件页负责初始化之后的持续流水录入、筛选、核对与删除修正。</p>
            </div>
            <span className="rounded-full border border-border/40 px-2.5 py-1 text-xs text-secondary">{selectedAccountLabel}</span>
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-3">
            <div className="rounded-lg border border-border/40 bg-surface/40 px-2.5 py-2">
              <p className="text-xs text-secondary">事件类型</p>
              <p className="mt-0.5 text-sm font-semibold text-foreground">{eventType === 'trade' ? '交易流水' : eventType === 'cash' ? '资金流水' : '公司行为'}</p>
            </div>
            <div className="rounded-lg border border-border/40 bg-surface/40 px-2.5 py-2">
              <p className="text-xs text-secondary">当前页记录数</p>
              <p className="mt-0.5 text-sm font-semibold text-foreground">{currentItems.length}</p>
            </div>
            <div className="rounded-lg border border-border/40 bg-surface/40 px-2.5 py-2">
              <p className="text-xs text-secondary">筛选结果总数</p>
              <p className="mt-0.5 text-sm font-semibold text-foreground">{eventTotal}</p>
            </div>
          </div>
        </Card>

        <Card className="!rounded-xl" padding="sm">
          <h2 className="text-base font-semibold text-foreground">维护提示</h2>
          <div className="mt-2 space-y-1.5 text-sm text-secondary">
            <p>账户切到具体账户后，可以直接录入和删除修正流水。</p>
            <p>交易、资金、公司行为三类记录共用筛选区，便于核对同一时间窗口的资产变动。</p>
            <p>初始化建账继续在资产初始化页完成，增量维护集中在这里。</p>
          </div>
        </Card>
      </div>

      <Card className="!rounded-xl" padding="sm">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-foreground">筛选条件</h2>
            <p className="mt-0.5 text-xs text-secondary">先锁定账户和事件类型，再按日期、方向或代码过滤台账记录。</p>
          </div>
          <Button onClick={() => void loadEvents(1)} disabled={eventLoading}>{eventLoading ? '刷新中...' : '刷新台账'}</Button>
        </div>
        <div className="mt-3 grid gap-2 md:grid-cols-[200px_1fr] xl:grid-cols-[200px_200px_1fr]">
          <select className={SELECT_CLASS} value={selectedAccount} onChange={(e) => setSelectedAccount(e.target.value === 'all' ? 'all' : Number(e.target.value))}>
            <option value="all">全部账户</option>
            {accounts.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
          <select className={SELECT_CLASS} value={eventType} onChange={(e) => setEventType(e.target.value as EventType)}>
            <option value="trade">交易流水</option>
            <option value="cash">资金流水</option>
            <option value="corporate">公司行为</option>
          </select>
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
            <input className={INPUT_CLASS} type="date" value={eventDateFrom} onChange={(e) => setEventDateFrom(e.target.value)} />
            <input className={INPUT_CLASS} type="date" value={eventDateTo} onChange={(e) => setEventDateTo(e.target.value)} />
            {(eventType === 'trade' || eventType === 'corporate') ? <input className={INPUT_CLASS} placeholder="股票代码" value={eventSymbol} onChange={(e) => setEventSymbol(e.target.value)} /> : (
              eventType === 'cash' ? (
                <select className={SELECT_CLASS} value={eventDirection} onChange={(e) => setEventDirection(e.target.value as '' | PortfolioCashDirection)}>
                  <option value="">全部资金方向</option>
                  <option value="in">流入</option>
                  <option value="out">流出</option>
                </select>
                ) : <div className="rounded-lg border border-border/30 px-3 py-2 text-xs text-secondary">按资金方向核对出入金</div>
             )}
            {eventType === 'trade' ? (
              <select className={SELECT_CLASS} value={eventSide} onChange={(e) => setEventSide(e.target.value as '' | PortfolioSide)}>
                <option value="">全部买卖方向</option>
                <option value="buy">买入</option>
                <option value="sell">卖出</option>
              </select>
            ) : eventType === 'corporate' ? (
              <select className={SELECT_CLASS} value={eventActionType} onChange={(e) => setEventActionType(e.target.value as '' | PortfolioCorporateActionType)}>
                <option value="">全部公司行为</option>
                <option value="cash_dividend">现金分红</option>
                <option value="split_adjustment">拆并股调整</option>
              </select>
             ) : <div className="rounded-lg border border-border/30 px-3 py-2 text-xs text-secondary">按公司行为类型筛选股本或分红调整</div>}
          </div>
        </div>
      </Card>

      <section className="grid gap-2 xl:grid-cols-3">
        <Card className="!rounded-xl" padding="sm">
          <h3 className="mb-1 text-sm font-semibold">交易录入</h3>
          <p className="mb-2 text-xs text-secondary">适合补录买卖成交、手续费和税费。</p>
          <form className="space-y-2" onSubmit={handleTradeSubmit}>
            <input className={INPUT_CLASS} placeholder="股票代码" value={tradeForm.symbol} onChange={(e) => setTradeForm((prev) => ({ ...prev, symbol: e.target.value }))} required />
            <div className="grid grid-cols-2 gap-2">
              <input className={INPUT_CLASS} type="date" value={tradeForm.tradeDate} onChange={(e) => setTradeForm((prev) => ({ ...prev, tradeDate: e.target.value }))} required />
              <select className={SELECT_CLASS} value={tradeForm.side} onChange={(e) => setTradeForm((prev) => ({ ...prev, side: e.target.value as PortfolioSide }))}><option value="buy">买入</option><option value="sell">卖出</option></select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <input className={INPUT_CLASS} type="number" min="0" step="0.0001" placeholder="数量" value={tradeForm.quantity} onChange={(e) => setTradeForm((prev) => ({ ...prev, quantity: e.target.value }))} required />
              <input className={INPUT_CLASS} type="number" min="0" step="0.0001" placeholder="价格" value={tradeForm.price} onChange={(e) => setTradeForm((prev) => ({ ...prev, price: e.target.value }))} required />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <input className={INPUT_CLASS} type="number" min="0" step="0.0001" placeholder="手续费" value={tradeForm.fee} onChange={(e) => setTradeForm((prev) => ({ ...prev, fee: e.target.value }))} />
              <input className={INPUT_CLASS} type="number" min="0" step="0.0001" placeholder="税费" value={tradeForm.tax} onChange={(e) => setTradeForm((prev) => ({ ...prev, tax: e.target.value }))} />
            </div>
            <input className={INPUT_CLASS} placeholder="流水编号（可选）" value={tradeForm.tradeUid} onChange={(e) => setTradeForm((prev) => ({ ...prev, tradeUid: e.target.value }))} />
            <textarea className={TEXTAREA_CLASS} placeholder="备注（可选）" value={tradeForm.note} onChange={(e) => setTradeForm((prev) => ({ ...prev, note: e.target.value }))} />
            <button type="submit" className="btn-secondary w-full !py-1.5" disabled={!writableAccountId}>提交交易</button>
          </form>
        </Card>

        <Card className="!rounded-xl" padding="sm">
          <h3 className="mb-1 text-sm font-semibold">资金流水</h3>
          <p className="mb-2 text-xs text-secondary">用于登记入金、出金、分红到账等现金变化。</p>
          <form className="space-y-2" onSubmit={handleCashSubmit}>
            <div className="grid grid-cols-2 gap-2">
              <input className={INPUT_CLASS} type="date" value={cashForm.eventDate} onChange={(e) => setCashForm((prev) => ({ ...prev, eventDate: e.target.value }))} required />
              <select className={SELECT_CLASS} value={cashForm.direction} onChange={(e) => setCashForm((prev) => ({ ...prev, direction: e.target.value as PortfolioCashDirection }))}><option value="in">流入</option><option value="out">流出</option></select>
            </div>
            <input className={INPUT_CLASS} type="number" min="0" step="0.0001" placeholder="金额" value={cashForm.amount} onChange={(e) => setCashForm((prev) => ({ ...prev, amount: e.target.value }))} required />
            <input className={INPUT_CLASS} placeholder="币种" value={cashForm.currency} onChange={(e) => setCashForm((prev) => ({ ...prev, currency: e.target.value }))} />
            <textarea className={TEXTAREA_CLASS} placeholder="备注（可选）" value={cashForm.note} onChange={(e) => setCashForm((prev) => ({ ...prev, note: e.target.value }))} />
            <button type="submit" className="btn-secondary w-full !py-1.5" disabled={!writableAccountId}>提交资金流水</button>
          </form>
        </Card>

        <Card className="!rounded-xl" padding="sm">
          <h3 className="mb-1 text-sm font-semibold">公司行为</h3>
          <p className="mb-2 text-xs text-secondary">用于维护现金分红、拆并股等影响持仓口径的事件。</p>
          <form className="space-y-2" onSubmit={handleCorporateSubmit}>
            <input className={INPUT_CLASS} placeholder="股票代码" value={corpForm.symbol} onChange={(e) => setCorpForm((prev) => ({ ...prev, symbol: e.target.value }))} required />
            <div className="grid grid-cols-2 gap-2">
              <input className={INPUT_CLASS} type="date" value={corpForm.effectiveDate} onChange={(e) => setCorpForm((prev) => ({ ...prev, effectiveDate: e.target.value }))} required />
              <select className={SELECT_CLASS} value={corpForm.actionType} onChange={(e) => setCorpForm((prev) => ({ ...prev, actionType: e.target.value as PortfolioCorporateActionType }))}><option value="cash_dividend">现金分红</option><option value="split_adjustment">拆并股调整</option></select>
            </div>
            {corpForm.actionType === 'cash_dividend' ? (
              <input className={INPUT_CLASS} type="number" min="0" step="0.000001" placeholder="每股分红" value={corpForm.cashDividendPerShare} onChange={(e) => setCorpForm((prev) => ({ ...prev, cashDividendPerShare: e.target.value, splitRatio: '' }))} required />
            ) : (
              <input className={INPUT_CLASS} type="number" min="0" step="0.000001" placeholder="拆并股比例" value={corpForm.splitRatio} onChange={(e) => setCorpForm((prev) => ({ ...prev, splitRatio: e.target.value, cashDividendPerShare: '' }))} required />
            )}
            <textarea className={TEXTAREA_CLASS} placeholder="备注（可选）" value={corpForm.note} onChange={(e) => setCorpForm((prev) => ({ ...prev, note: e.target.value }))} />
            <button type="submit" className="btn-secondary w-full !py-1.5" disabled={!writableAccountId}>提交公司行为</button>
          </form>
        </Card>
      </section>

      <Card className="!rounded-xl" padding="sm">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-base font-semibold">事件台账</h2>
          <span className="text-xs text-secondary-text">第 {eventPage} / {totalPages} 页</span>
        </div>
        <div className="overflow-x-auto rounded-lg border border-border/40">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="bg-surface/60 text-xs text-secondary">
              <tr>
                <th className="px-3 py-2 text-left">日期</th>
                <th className="px-3 py-2 text-left">类型</th>
                <th className="px-3 py-2 text-left">标的/方向</th>
                <th className="px-3 py-2 text-right">数量/金额</th>
                <th className="px-3 py-2 text-right">价格/比率</th>
                <th className="px-3 py-2 text-left">附加信息</th>
                <th className="px-3 py-2 text-left">备注</th>
                <th className="px-3 py-2 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {currentItems.length === 0 && !eventLoading ? (
                <tr>
                  <td colSpan={8} className="px-3 py-6"><EmptyState title="暂无事件" description="先录入第一笔交易、资金或公司行为。" className="border-none bg-transparent px-2 py-4 shadow-none" /></td>
                </tr>
              ) : null}
              {eventType === 'trade' && tradeEvents.map((item) => <tr key={item.id} className="border-t border-border/30"><td className="px-3 py-2">{item.tradeDate}</td><td className="px-3 py-2">交易流水</td><td className="px-3 py-2">{item.symbol} · {formatSideLabel(item.side)}</td><td className="px-3 py-2 text-right">{formatNumericCell(item.quantity)}</td><td className="px-3 py-2 text-right">{formatNumericCell(item.price)}</td><td className="px-3 py-2 text-[11px] text-secondary"><div>手续费 {formatNumericCell(item.fee)}</div><div className="mt-0.5">税费 {formatNumericCell(item.tax)}</div><div className="mt-0.5">{item.tradeUid ? `流水号 ${item.tradeUid}` : '未填写流水号'}</div></td><td className="max-w-[240px] px-3 py-2 text-secondary"><div className="line-clamp-2">{formatTextCell(item.note, '成交附加说明为空')}</div></td><td className="px-3 py-2 text-right"><button type="button" className="btn-secondary !px-2.5 !py-1 !text-xs" onClick={() => setPendingDelete({ eventType: 'trade', id: item.id, message: `确认删除 ${item.tradeDate} ${item.symbol} 交易流水吗？` })}>删除</button></td></tr>)}
              {eventType === 'cash' && cashEvents.map((item) => <tr key={item.id} className="border-t border-border/30"><td className="px-3 py-2">{item.eventDate}</td><td className="px-3 py-2">资金流水</td><td className="px-3 py-2">{formatDirectionLabel(item.direction)}</td><td className="px-3 py-2 text-right">{formatMoneyCell(item.amount, item.currency)}</td><td className="px-3 py-2 text-right">--</td><td className="px-3 py-2 text-[11px] text-secondary">现金调拨</td><td className="max-w-[240px] px-3 py-2 text-secondary"><div className="line-clamp-2">{formatTextCell(item.note, '现金变动记录')}</div></td><td className="px-3 py-2 text-right"><button type="button" className="btn-secondary !px-2.5 !py-1 !text-xs" onClick={() => setPendingDelete({ eventType: 'cash', id: item.id, message: `确认删除 ${item.eventDate} 资金流水吗？` })}>删除</button></td></tr>)}
              {eventType === 'corporate' && corporateEvents.map((item) => <tr key={item.id} className="border-t border-border/30"><td className="px-3 py-2">{item.effectiveDate}</td><td className="px-3 py-2">公司行为</td><td className="px-3 py-2">{item.symbol} · {formatActionLabel(item.actionType)}</td><td className="px-3 py-2 text-right">{formatNumericCell(item.cashDividendPerShare)}</td><td className="px-3 py-2 text-right">{formatNumericCell(item.splitRatio)}</td><td className="px-3 py-2 text-[11px] text-secondary">{item.actionType === 'cash_dividend' ? '现金分配' : '股本调整'}</td><td className="max-w-[240px] px-3 py-2 text-secondary"><div className="line-clamp-2">{formatTextCell(item.note, '公司行为调整')}</div></td><td className="px-3 py-2 text-right"><button type="button" className="btn-secondary !px-2.5 !py-1 !text-xs" onClick={() => setPendingDelete({ eventType: 'corporate', id: item.id, message: `确认删除 ${item.effectiveDate} 公司行为吗？` })}>删除</button></td></tr>)}
            </tbody>
          </table>
        </div>
        <div className="mt-2 flex justify-end gap-2">
          <button type="button" className="btn-secondary !px-3 !py-1 !text-xs" disabled={eventPage <= 1} onClick={() => setEventPage((prev) => Math.max(1, prev - 1))}>上一页</button>
          <button type="button" className="btn-secondary !px-3 !py-1 !text-xs" disabled={eventPage >= totalPages} onClick={() => setEventPage((prev) => Math.min(totalPages, prev + 1))}>下一页</button>
        </div>
      </Card>

      <ConfirmDialog isOpen={Boolean(pendingDelete)} title="删除事件" message={pendingDelete?.message || '确认删除该事件吗？'} confirmText={deleteLoading ? '删除中...' : '确认删除'} cancelText="取消" isDanger onConfirm={() => void handleDelete()} onCancel={() => !deleteLoading && setPendingDelete(null)} />
    </AppPage>
  );
};

export default AssetEventsPage;
