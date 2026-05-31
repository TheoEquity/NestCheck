import type React from 'react';
import { useEffect, useMemo, useState, useCallback } from 'react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { portfolioApi } from '../api/portfolio';
import { ApiErrorAlert, AppPage, Badge, Button, Card, InlineAlert, PageHeader } from '../components/common';
import type { PortfolioAccountItem } from '../types/portfolio';
import type { StockIndexItem } from '../types/stockIndex';
import { loadStockIndex } from '../utils/stockIndexLoader';
import { toDateInputValue } from '../utils/format';

type AccountMarket = 'cn' | 'hk' | 'us';
type AssetCategory = 'cash' | 'fund' | 'stock' | 'bond';
type AssetSubcategory = '' | 'pure_bond_fund' | 'fixed_income_plus' | 'index_fund' | 'equity_fund';
type AssetRiskClass = '' | 'R1' | 'R2' | 'R3' | 'R4' | 'R5';

type AccountFormState = {
  name: string;
  broker: string;
  market: AccountMarket;
  baseCurrency: CurrencyCode;
};

type AccountMode = 'create' | 'edit';

type AssetRow = {
  id: string;
  assetCategory: AssetCategory;
  assetSubcategory: AssetSubcategory;
  assetRiskClass: AssetRiskClass;
  symbol: string;
  name: string;
  market: AccountMarket;
  quantity: string;
  price: string;
  currency: CurrencyCode;
  note: string;
};

type CurrencyCode = 'CNY' | 'HKD' | 'USD';

const CURRENCY_OPTIONS: Array<{ value: CurrencyCode; label: string }> = [
  { value: 'CNY', label: '人民币 CNY' },
  { value: 'HKD', label: '港币 HKD' },
  { value: 'USD', label: '美元 USD' },
];

const ASSET_CATEGORY_OPTIONS: Array<{ value: AssetCategory; label: string }> = [
  { value: 'cash', label: '现金' },
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

const ASSET_RISK_CLASS_OPTIONS: AssetRiskClass[] = ['', 'R1', 'R2', 'R3', 'R4', 'R5'];

// Reserved for future use
// const ASSET_CATEGORY_LABELS: Record<AssetCategory, string> = {
//   cash: '现金',
//   fund: '基金',
//   stock: '股票',
//   bond: '债券',
// };

// const ASSET_SUBCATEGORY_LABELS: Record<Exclude<AssetSubcategory, ''>, string> = {
//   pure_bond_fund: '纯债基金',
//   fixed_income_plus: '固收+',
//   index_fund: '指数基金',
//   equity_fund: '股票基金',
// };

// Reserved - not used after refactoring
// const ASSET_CATEGORY_VALUES: Record<string, AssetCategory> = {};
// const ASSET_SUBCATEGORY_VALUES: Record<string, Exclude<AssetSubcategory, ''>> = {};

const normalizeCurrencyCode = (value?: string | null): CurrencyCode => {
  if (value === 'HKD' || value === 'USD') return value;
  return 'CNY';
};

const INPUT_CLASS = 'input-surface input-focus-glow h-9 w-full rounded-lg border bg-transparent px-3 text-sm transition-all focus:outline-none';
const SELECT_CLASS = `${INPUT_CLASS} appearance-none pr-10`;

const createEmptyRow = (market: AccountMarket = 'cn', currency: CurrencyCode = 'CNY'): AssetRow => ({
  id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
  assetCategory: 'stock',
  assetSubcategory: '',
  assetRiskClass: 'R3',
  symbol: '',
  name: '',
  market,
  quantity: '',
  price: '',
  currency,
  note: '',
});

const getTodayIso = () => toDateInputValue(new Date());

const formatMoney = (value: number | undefined | null, currency: string) => {
  if (value == null || Number.isNaN(value)) return '--';
  return `${currency} ${Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

const isCashCategory = (assetCategory: AssetCategory) => assetCategory === 'cash';

const buildAssetNote = (row: AssetRow) => {
  const parts = [
    row.name.trim() ? `name:${row.name.trim()}` : '',
    row.note.trim() ? `remark:${row.note.trim()}` : '',
  ].filter(Boolean);
  return parts.join(' | ') || undefined;
};

const buildNextOwnerId = (accounts: PortfolioAccountItem[], currency: CurrencyCode) => {
  const maxIndex = accounts.reduce((currentMax, account) => {
    if (account.baseCurrency !== currency) return currentMax;
    const matched = account.ownerId?.match(new RegExp(`^${currency}(\\d{3})$`));
    if (!matched) return currentMax;
    return Math.max(currentMax, Number(matched[1]));
  }, 0);
  return `${currency}${String(maxIndex + 1).padStart(3, '0')}`;
};

const AssetInitializationPage: React.FC = () => {
  useEffect(() => {
    document.title = '资产初始化 - NestCheck';
  }, []);

  const [accounts, setAccounts] = useState<PortfolioAccountItem[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [accountMode, setAccountMode] = useState<AccountMode>('create');
  const [accountForm, setAccountForm] = useState<AccountFormState>({
    name: '',
    broker: '',
    market: 'cn',
    baseCurrency: 'CNY',
  });
  const [assetDate] = useState(getTodayIso());
  const [assetRows, setAssetRows] = useState<AssetRow[]>([createEmptyRow()]);
  const [pageError, setPageError] = useState<ParsedApiError | null>(null);
  const [accountError, setAccountError] = useState<string | null>(null);
  const [accountSuccess, setAccountSuccess] = useState<string | null>(null);
  const [saveFeedback, setSaveFeedback] = useState<string | null>(null);
  const [accountCreating, setAccountCreating] = useState(false);
  const [accountDeleting, setAccountDeleting] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);
  const [saved, setSaved] = useState(false);
  const [stockIndex, setStockIndex] = useState<StockIndexItem[]>([]);
  const [accountListOpen, setAccountListOpen] = useState(false);
  const [accountListPosition, setAccountListPosition] = useState({left: 0, top: 0});

  const selectedAccount = useMemo(
    () => accounts.find((item) => item.id === selectedAccountId) || null,
    [accounts, selectedAccountId],
  );
  const nextOwnerId = useMemo(
    () => buildNextOwnerId(accounts, accountForm.baseCurrency),
    [accounts, accountForm.baseCurrency],
  );
  const currentOwnerId = accountMode === 'edit'
    ? selectedAccount?.ownerId || '--'
    : nextOwnerId;
  const [viewingOnly, setViewingOnly] = useState(false);

  const resetAccountForm = () => {
    setAccountMode('create');
    setSelectedAccountId(null);
    setAccountForm({
      name: '',
      broker: '',
      market: 'cn',
      baseCurrency: 'CNY',
    });
    setAssetRows([createEmptyRow()]);
    setViewingOnly(false);
    setSaved(false);
  };

  const loadAccountAssets = useCallback(async (account: PortfolioAccountItem) => {
    const positionsResp = await portfolioApi.listPositions({ accountId: account.id, costMethod: 'fifo' });
    const positionRows = (positionsResp.items || []).map((pos) => {
      const isCash = pos.assetCategory === 'cash' || pos.symbol?.startsWith('CASH_');
      return {
        id: `pos-${pos.id}`,
        assetCategory: (pos.assetCategory || (isCash ? 'cash' : 'stock')) as AssetCategory,
        assetSubcategory: (pos.assetSubcategory || '') as AssetSubcategory,
        assetRiskClass: (pos.assetRiskClass || (isCash ? 'R1' : 'R3')) as AssetRiskClass,
        symbol: isCash ? '' : pos.symbol,
        name: pos.name || '',
        market: pos.market as AccountMarket,
        quantity: isCash ? '' : String(pos.quantity || ''),
        price: String(isCash ? (pos.totalCost || pos.quantity) : (pos.avgCost || '')),
        currency: pos.currency as CurrencyCode,
        note: '',
      };
    });
    setAssetRows(positionRows.length > 0 ? positionRows : [createEmptyRow(account.market, normalizeCurrencyCode(account.baseCurrency))]);
  }, []);

  const handleSelectAccount = useCallback(async (account: PortfolioAccountItem) => {
    setSelectedAccountId(account.id);
    setAccountMode('edit');
    setViewingOnly(true);
    setAccountError(null);
    setAccountSuccess(null);
    setSaveFeedback(null);
    setSaved(false);
    setPageError(null);
    setAccountListOpen(false);
    setAccountForm({
      name: account.name,
      broker: account.broker || '',
      market: account.market,
      baseCurrency: normalizeCurrencyCode(account.baseCurrency),
    });
    try {
      await loadAccountAssets(account);
    } catch (err) {
      setPageError(getParsedApiError(err));
    }
  }, [loadAccountAssets]);

  const loadAccounts = useCallback(async () => {
    try {
      const response = await portfolioApi.getAccounts(false);
      const nextAccounts = (response.accounts || []).map((account) => ({
        ...account,
        baseCurrency: normalizeCurrencyCode(account.baseCurrency),
      }));
      setAccounts(nextAccounts);
      setPageError(null);
    } catch (err) {
      setPageError(getParsedApiError(err));
    } finally {
      // no-op
    }
  }, []);

  useEffect(() => {
    void loadAccounts();
  }, [loadAccounts]);

  useEffect(() => {
    if (!accountListOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      // 点击下拉菜单内部不关闭
      if (target.closest('.fixed.z-\\[9999\\]')) return;
      // 点击触发按钮不关闭
      if (target.closest('[data-account-badge]')) return;
      setAccountListOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [accountListOpen]);

  useEffect(() => {
    let active = true;
    const loadIndex = async () => {
      const result = await loadStockIndex();
      if (!active || !result.loaded) return;
      setStockIndex(result.data);
    };
    void loadIndex();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedAccount) return;
    setAssetRows((prev) => prev.map((row) => ({
      ...row,
      market: isCashCategory(row.assetCategory) ? selectedAccount.market : row.market,
      currency: row.currency || selectedAccount.baseCurrency,
    })));
  }, [selectedAccount]);

  useEffect(() => {
    if (!selectedAccount || accountMode !== 'edit') return;
    setAccountForm({
      name: selectedAccount.name,
      broker: selectedAccount.broker || '',
      market: selectedAccount.market,
      baseCurrency: normalizeCurrencyCode(selectedAccount.baseCurrency),
    });
  }, [selectedAccount, accountMode]);

  const updateRow = (rowId: string, patch: Partial<AssetRow>) => {
    setAssetRows((prev) => prev.map((row) => (row.id === rowId ? { ...row, ...patch } : row)));
  };

  const handleSymbolChange = (rowId: string, symbol: string) => {
    const nextSymbol = symbol.trim().toUpperCase();
    const currentMarket = selectedAccount?.market || accountForm.market;
    // 优先匹配当前市场的股票（注意市场代码大小写转换）
    const matched = stockIndex.find((item) => 
      item.market.toLowerCase() === currentMarket && (item.displayCode.toUpperCase() === nextSymbol || item.canonicalCode.toUpperCase() === nextSymbol)
    ) || stockIndex.find((item) => item.displayCode.toUpperCase() === nextSymbol || item.canonicalCode.toUpperCase() === nextSymbol);
    updateRow(rowId, {
      symbol: nextSymbol,
      name: matched?.nameZh || '',
      market: matched ? (matched.market.toLowerCase() as AccountMarket) : currentMarket,
    });
  };

  const addRow = () => {
    setAssetRows((prev) => [...prev, createEmptyRow(selectedAccount?.market || accountForm.market, normalizeCurrencyCode(selectedAccount?.baseCurrency || accountForm.baseCurrency))]);
  };

  const removeRow = (rowId: string) => {
    setAssetRows((prev) => {
      if (prev.length === 1) {
        return [createEmptyRow(selectedAccount?.market || accountForm.market, normalizeCurrencyCode(selectedAccount?.baseCurrency || accountForm.baseCurrency))];
      }
      return prev.filter((row) => row.id !== rowId);
    });
  };

  const handleCreateAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!accountForm.name.trim()) {
      setAccountError('请先填写账户名称。');
      return;
    }

    try {
      setAccountCreating(true);
      setAccountError(null);
      setAccountSuccess(null);
      const created = await portfolioApi.createAccount({
        name: accountForm.name.trim(),
        broker: accountForm.broker.trim() || undefined,
        market: accountForm.market,
        baseCurrency: accountForm.baseCurrency,
        ownerId: nextOwnerId,
      });
      const normalizedCreated = {
        ...created,
        baseCurrency: normalizeCurrencyCode(created.baseCurrency),
      };
      await loadAccounts();
      // Auto-select the created account for immediate asset initialization
      setSelectedAccountId(normalizedCreated.id);
      setAccountMode('edit');
      setAccountListOpen(false);
      setAccountSuccess(`账户"${normalizedCreated.name}"已创建，账户编号 ${normalizedCreated.ownerId || nextOwnerId}。请在下方表格填写初始资产后，点击"保存到资产库"。`);
      setAccountForm({ name: normalizedCreated.name, broker: normalizedCreated.broker || '', market: normalizedCreated.market, baseCurrency: normalizedCreated.baseCurrency });
      setViewingOnly(false);
    } catch (err) {
      setAccountError(getParsedApiError(err).message);
    } finally {
      setAccountCreating(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (!selectedAccount) return;

    try {
      setAccountDeleting(true);
      setAccountError(null);
      setAccountSuccess(null);
      await portfolioApi.deleteAccount(selectedAccount.id);
      const deletedName = selectedAccount.name;
      const remainingAccounts = accounts.filter((account) => account.id !== selectedAccount.id);
      setAccounts(remainingAccounts);
      resetAccountForm();
      setAccountListOpen(false);
      setSaved(false);
      setAccountSuccess(`账户"${deletedName}"已删除。`);
    } catch (err) {
      setAccountError(getParsedApiError(err).message);
    } finally {
      setAccountDeleting(false);
    }
  };

  const handleSaveAssets = async () => {
    let currentAccount = selectedAccount;

    // Auto-create account if not selected
    if (!currentAccount) {
      if (!accountForm.name.trim()) {
        setPageError({
          title: '缺少账户',
          message: '请先填写账户名称，或选择一个已有的账户。',
          rawMessage: 'missing account name',
          category: 'missing_params',
        });
        return;
      }

      try {
        setAccountCreating(true);
        setAccountError(null);
        const created = await portfolioApi.createAccount({
          name: accountForm.name.trim(),
          broker: accountForm.broker.trim() || undefined,
          market: accountForm.market,
          baseCurrency: accountForm.baseCurrency,
          ownerId: nextOwnerId,
        });
        const normalizedCreated = {
          ...created,
          baseCurrency: normalizeCurrencyCode(created.baseCurrency),
        };
        await loadAccounts();
        currentAccount = normalizedCreated;
        setSelectedAccountId(normalizedCreated.id);
        setAccountMode('edit');
        setAccountListOpen(false);
        setAccountForm({ name: normalizedCreated.name, broker: normalizedCreated.broker || '', market: normalizedCreated.market, baseCurrency: normalizedCreated.baseCurrency });
        setViewingOnly(false);
      } catch (err) {
        setAccountError(getParsedApiError(err).message);
        setAccountCreating(false);
        return;
      } finally {
        setAccountCreating(false);
      }
    }

    const filledRows = assetRows.filter((row) => {
      if (isCashCategory(row.assetCategory)) {
        return row.price.trim() || row.name.trim() || row.note.trim();
      }
      return row.symbol.trim() || row.name.trim() || row.quantity.trim() || row.price.trim();
    });

    if (filledRows.length === 0) {
      setSaveFeedback('表格里还没有可保存的资产行。');
      return;
    }

    try {
      setSaveLoading(true);
      setSaveFeedback(null);
      setPageError(null);

      const assetRowsList = filledRows.filter((row) => !isCashCategory(row.assetCategory)).map((row) => {
        if (!row.symbol.trim() || !row.quantity.trim() || !row.price.trim()) {
          throw new Error(`资产行 ${row.symbol || row.name || '未填写代码'} 缺少代码、数量或成本价。`);
        }
        return {
          assetCategory: row.assetCategory,
          assetSubcategory: row.assetSubcategory || undefined,
          assetRiskClass: row.assetRiskClass || undefined,
          symbol: row.symbol.trim().toUpperCase(),
          name: row.name.trim() || undefined,
          market: row.market,
          quantity: Number(row.quantity),
          avgCost: Number(row.price),
          currency: currentAccount.baseCurrency,
          note: buildAssetNote(row),
        };
      });

      const cashRowsList = filledRows.filter((row) => isCashCategory(row.assetCategory)).map((row) => {
        if (!row.price.trim()) {
          throw new Error(`现金行 ${row.name || row.currency || currentAccount.baseCurrency} 缺少合计金额。`);
        }
        return {
          assetCategory: row.assetCategory,
          assetRiskClass: row.assetRiskClass || 'R1',
          name: row.name.trim() || undefined,
          amount: Number(row.price),
          currency: normalizeCurrencyCode(row.currency.trim().toUpperCase() || currentAccount.baseCurrency),
          note: buildAssetNote(row),
        };
      });

      await portfolioApi.initializePortfolio({
        accountId: currentAccount.id,
        initDate: assetDate,
        assets: assetRowsList,
        cashItems: cashRowsList,
      });

      await loadAccountAssets(currentAccount);
      setSaveFeedback(`已完成初始化，写入 ${assetRowsList.length} 个持仓和 ${cashRowsList.length} 个现金项。已清除该账户历史流水。`);
      setSaved(true);
    } catch (err) {
      setPageError(getParsedApiError(err));
    } finally {
      setSaveLoading(false);
    }
  };

  const totalPositionCost = assetRows.reduce((sum, row) => {
    if (isCashCategory(row.assetCategory)) return sum;
    return sum + Number(row.quantity || 0) * Number(row.price || 0);
  }, 0);

  const totalCashAmount = assetRows.reduce((sum, row) => {
    if (!isCashCategory(row.assetCategory)) return sum;
    return sum + Number(row.price || 0);
  }, 0);
  const totalAssetAmount = totalPositionCost + totalCashAmount;

  return (
    <AppPage className="max-w-[1600px] space-y-3">
      <PageHeader
        eyebrow="Asset Onboarding"
        title="资产初始化"
        description="先建账户，再按表格录入初始证券和现金。保存后数据会直接进入资产库，并在资产管理页展示。"
        className="!rounded-xl !px-4 !py-3"
      />

      {pageError ? <ApiErrorAlert error={pageError} onDismiss={() => setPageError(null)} /> : null}

      {accountListOpen ? (
        <div className="fixed z-[9999]" style={{left: accountListPosition.left, top: accountListPosition.top}} onClick={(e) => e.stopPropagation()}>
          <div className="w-80 rounded-xl border border-border/60 bg-background p-2 shadow-lg">
            <div className="mb-2 px-2 text-xs font-medium text-secondary-text">选择账户后会回填账户信息和已入库资产。</div>
            <div className="max-h-72 space-y-1 overflow-y-auto rounded-lg bg-background">
              {accounts.length > 0 ? accounts.map((account) => (
                <button
                  key={account.id}
                  type="button"
                  onClick={() => {
                    void handleSelectAccount(account);
                    setAccountListOpen(false);
                  }}
                  className={`flex w-full items-start justify-between rounded-lg px-3 py-2 text-left text-sm transition ${selectedAccountId === account.id ? 'bg-primary/10 text-foreground' : 'hover:bg-surface/60 text-foreground'}`}
                >
                  <span>
                    <span className="block font-medium">{account.ownerId || `账户 ${account.id}`} · {account.name}</span>
                    <span className="block text-xs text-secondary-text">{account.broker || '未填券商'} · {account.baseCurrency} · {account.market.toUpperCase()}</span>
                  </span>
                  {selectedAccountId === account.id ? <span className="text-xs text-primary">当前</span> : null}
                </button>
              )) : (
                <div className="px-2 py-3 text-xs text-secondary-text">当前还没有已建账户。</div>
              )}
            </div>
          </div>
        </div>
      ) : null}

      <section>
        <Card className="!rounded-xl" padding="sm">
          <div className="mb-2 flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-foreground">1. 建账户</h2>
              <p className="mt-0.5 text-xs text-secondary-text">先创建当前账户，再在下方一次性录入该账户的初始资产。</p>
            </div>
            <div className="relative">
              <button type="button" data-account-badge onClick={(e) => {
                const rect = e.currentTarget.getBoundingClientRect();
                setAccountListPosition({left: rect.right - 320, top: rect.top});
                setAccountListOpen((prev) => !prev);
              }} className="rounded-full">
                <Badge variant={accounts.length > 0 ? 'success' : 'warning'}>{accounts.length > 0 ? `已建 ${accounts.length} 个账户` : '等待建账'}</Badge>
              </button>
            </div>
          </div>

          {accountError ? <InlineAlert variant="danger" className="mb-2 rounded-lg px-3 py-2 text-xs shadow-none" message={accountError} /> : null}
          {accountSuccess ? <InlineAlert variant="success" className="mb-2 rounded-lg px-3 py-2 text-xs shadow-none" message={accountSuccess} /> : null}

           <form className="grid gap-2 md:grid-cols-2 xl:grid-cols-[112px_200px_168px_108px_132px_240px]" onSubmit={handleCreateAccount}>
             <input className={`${INPUT_CLASS} bg-background/40 text-secondary-text`} value={currentOwnerId} readOnly aria-label="账户编号" />
             <input className={INPUT_CLASS} placeholder="账户名称" value={accountForm.name} onChange={(e) => setAccountForm((prev) => ({ ...prev, name: e.target.value }))} disabled={viewingOnly} />
             <input className={INPUT_CLASS} placeholder="券商，可选" value={accountForm.broker} onChange={(e) => setAccountForm((prev) => ({ ...prev, broker: e.target.value }))} disabled={viewingOnly} />
             <select className={SELECT_CLASS} value={accountForm.market} disabled={accountMode === 'edit' || viewingOnly} onChange={(e) => setAccountForm((prev) => ({ ...prev, market: e.target.value as AccountMarket }))}>
               <option value="cn">A 股</option>
               <option value="hk">港股</option>
               <option value="us">美股</option>
             </select>
             <select className={SELECT_CLASS} value={accountForm.baseCurrency} disabled={accountMode === 'edit' || viewingOnly} onChange={(e) => setAccountForm((prev) => ({ ...prev, baseCurrency: e.target.value as CurrencyCode }))}>
               {CURRENCY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
             </select>
              <div className="flex gap-1.5">
                <Button type="submit" variant="primary" size="sm" className="flex-1" disabled={accountCreating || accountDeleting || accountMode === 'edit' || viewingOnly}>
                  {accountCreating && accountMode === 'create' ? '创建中...' : '创建'}
                </Button>
                <Button type="button" variant="danger-subtle" size="sm" className="flex-1" disabled={!selectedAccount || accountCreating || accountDeleting} onClick={() => void handleDeleteAccount()}>
                  {accountDeleting ? '删除中...' : '删除'}
                </Button>
              </div>
           </form>
        </Card>
      </section>

      <Card className="!rounded-xl" padding="sm">
        <div className="mb-2 flex flex-col gap-2 xl:flex-row xl:items-end xl:justify-between">
          <div>
             <h2 className="mt-1.5 text-base font-semibold text-foreground">2. {viewingOnly ? '查看初始资产' : '表格录入初始资产'}</h2>
             <p className="mt-0.5 text-xs text-secondary-text">{viewingOnly ? '已初始化账户的资产清单为只读模式。如需修改，请删除本账户后重新录入。' : '按资产大类、细类和风险等级录入。现金按合计金额入账，其它资产按数量和成本价建仓。'}</p>
          </div>
           <div className="grid gap-2 md:grid-cols-[180px_120px]">
             <div className="flex items-center rounded-lg border border-border/60 bg-background/50 px-3 text-xs text-secondary-text">资产总计 {formatMoney(totalAssetAmount, selectedAccount?.baseCurrency || 'CNY')}</div>
             <Button onClick={addRow} disabled={viewingOnly}>新增一行</Button>
           </div>
        </div>

        {saveFeedback ? <InlineAlert variant="success" className="mb-2 rounded-lg px-3 py-2 text-xs shadow-none" message={saveFeedback} /> : null}

        <div className="overflow-x-auto rounded-lg border border-border/50 bg-background/20">
          <table className="w-full min-w-[1450px] table-fixed text-[13px]">
            <thead className="bg-surface/60 text-xs text-secondary-text">
              <tr>
                <th className="w-[52px] px-3 py-2 text-left">行</th>
                <th className="w-[120px] px-3 py-2 text-left">资产大类</th>
                <th className="w-[168px] px-3 py-2 text-left">资产细类</th>
                 <th className="w-[108px] px-3 py-2 text-left">风险分类</th>
                <th className="w-[132px] px-3 py-2 text-left">代码</th>
                <th className="w-[180px] px-3 py-2 text-left">名称</th>
                <th className="w-[98px] px-3 py-2 text-right">数量</th>
                <th className="w-[98px] px-3 py-2 text-right">成本价</th>
                <th className="w-[126px] px-3 py-2 text-right">合计</th>
                <th className="w-[180px] px-3 py-2 text-left">备注</th>
                <th className="w-[84px] px-3 py-2 text-right">操作</th>
              </tr>
            </thead>
             <tbody className={viewingOnly ? 'opacity-50 pointer-events-none' : ''}>
              {assetRows.map((row, index) => (
                <tr key={row.id} className="border-t border-border/50 align-top odd:bg-background/70 even:bg-surface/20">
                  <td className="px-3 py-2">
                    <div className="flex h-9 items-center text-xs font-medium text-secondary-text">{String(index + 1).padStart(2, '0')}</div>
                  </td>
                  <td className="px-3 py-2">
                    <select
                      className={SELECT_CLASS}
                      value={row.assetCategory}
                      onChange={(e) => {
                        const nextCategory = e.target.value as AssetCategory;
                        const defaultRiskClass: Record<AssetCategory, AssetRiskClass> = {
                          cash: 'R1',
                          fund: 'R3',
                          stock: 'R3',
                          bond: 'R2',
                        };
                        updateRow(row.id, {
                          assetCategory: nextCategory,
                          assetSubcategory: nextCategory === 'fund' ? row.assetSubcategory : '',
                          assetRiskClass: defaultRiskClass[nextCategory],
                          market: selectedAccount?.market || accountForm.market,
                          currency: normalizeCurrencyCode(selectedAccount?.baseCurrency || accountForm.baseCurrency),
                          quantity: '',
                          price: '',
                        });
                      }}
                    >
                      {ASSET_CATEGORY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    <select className={SELECT_CLASS} value={row.assetSubcategory} disabled={row.assetCategory !== 'fund'} onChange={(e) => updateRow(row.id, { assetSubcategory: e.target.value as AssetSubcategory })}>
                      {row.assetCategory === 'fund' ? (
                        FUND_SUBCATEGORY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)
                      ) : (
                        <option value="">--</option>
                      )}
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    <select className={SELECT_CLASS} value={row.assetRiskClass} onChange={(e) => updateRow(row.id, { assetRiskClass: e.target.value as AssetRiskClass })}>
                      {ASSET_RISK_CLASS_OPTIONS.map((level) => <option key={level || 'empty'} value={level}>{level || '请选择'}</option>)}
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    {isCashCategory(row.assetCategory) ? (
                      <div className="flex h-9 items-center rounded-lg border border-border/40 bg-background/40 px-3 text-xs text-secondary-text">
                        {selectedAccount?.baseCurrency || accountForm.baseCurrency}
                      </div>
                    ) : (
                      <input className={INPUT_CLASS} placeholder="如 600100 / AAPL" value={row.symbol} onChange={(e) => handleSymbolChange(row.id, e.target.value)} />
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <input className={INPUT_CLASS} placeholder={isCashCategory(row.assetCategory) ? '如 活期存款' : '资产名称'} value={row.name} onChange={(e) => updateRow(row.id, { name: e.target.value })} />
                  </td>
                  <td className="px-3 py-2">
                    {isCashCategory(row.assetCategory) ? (
                      <div className="flex h-9 items-center justify-end rounded-lg border border-border/40 bg-background/40 px-3 text-xs text-secondary-text">--</div>
                    ) : (
                      <input className={INPUT_CLASS} type="number" min="0" step="0.0001" placeholder="数量" value={row.quantity} onChange={(e) => updateRow(row.id, { quantity: e.target.value })} />
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <input
                      className={INPUT_CLASS}
                      type="number"
                      min="0"
                      step="0.0001"
                      placeholder={isCashCategory(row.assetCategory) ? '合计金额' : '成本价'}
                      value={row.price}
                      onChange={(e) => updateRow(row.id, { price: e.target.value })}
                    />
                  </td>
                  <td className="px-3 py-2">
                    {isCashCategory(row.assetCategory) ? (
                      <div className="flex h-9 items-center justify-end rounded-lg border border-border/40 bg-background/40 px-3 text-sm font-medium text-foreground">{formatMoney(Number(row.price || 0), row.currency || selectedAccount?.baseCurrency || 'CNY')}</div>
                    ) : (
                      <div className="flex h-9 items-center justify-end rounded-lg border border-border/40 bg-background/40 px-3 text-sm font-medium text-foreground">{formatMoney(Number(row.quantity || 0) * Number(row.price || 0), selectedAccount?.baseCurrency || 'CNY')}</div>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <input className={INPUT_CLASS} placeholder="备注，可选" value={row.note} onChange={(e) => updateRow(row.id, { note: e.target.value })} />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex h-full min-h-9 items-start justify-end">
                      <button type="button" className="btn-secondary !px-2.5 !py-1 !text-xs" onClick={() => removeRow(row.id)}>删除</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-2 flex items-center justify-between gap-3">
          <div />
          <Button onClick={() => void handleSaveAssets()} disabled={!selectedAccount || saveLoading || viewingOnly || saved} variant="primary" size="md" className="!px-6 !py-2 text-base font-semibold shadow-lg shadow-primary/20">
            {saveLoading ? '保存中...' : '保存到资产库'}
          </Button>
        </div>
      </Card>
    </AppPage>
  );
};

export default AssetInitializationPage;
