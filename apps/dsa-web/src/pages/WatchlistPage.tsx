import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { ArrowDown, ArrowUp, Settings, Plus, Trash2, X } from 'lucide-react';
import { watchlistApi } from '../api/watchlist';
import { marketApi, type SectorEtfConfig, type SectorEtfDashboardResponse } from '../api/market';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { ApiErrorAlert, Badge, Button, Card, Input, Select, Textarea } from '../components/common';
import type { WatchlistAssetCategory, WatchlistItem, WatchlistItemInput } from '../types/watchlist';
import { cn } from '../utils/cn';

type FormState = WatchlistItemInput;

const initialForm: FormState = {
  market: 'cn',
  symbol: '',
  name: '',
  currency: 'CNY',
  assetCategory: 'stock',
  assetSubcategory: '',
  assetRiskClass: 'R4',
  watchPriority: 'medium',
  watchTags: [],
  watchReason: '',
  watchEnabled: true,
  analysisEnabled: true,
  analysisFrequency: 'daily',
  alertEnabled: true,
  source: 'manual',
  notes: '',
};

const marketOptions = [
  { value: 'cn', label: 'A股 / 中国' },
  { value: 'hk', label: '港股' },
  { value: 'us', label: '美股' },
];

const assetCategoryOptions: Array<{ value: WatchlistAssetCategory; label: string }> = [
  { value: 'stock', label: '股票' },
  { value: 'fund', label: '基金' },
  { value: 'index', label: '指数' },
];

const fundSubcategoryOptions = [
  { value: '', label: '请选择' },
  { value: 'pure_bond_fund', label: '纯债基金' },
  { value: 'fixed_income_plus', label: '固收+' },
  { value: 'index_fund', label: '指数基金' },
  { value: 'equity_fund', label: '股票基金' },
];

function splitTags(value: string): string[] {
  return value.split(',').map((tag) => tag.trim()).filter(Boolean);
}

function formatPrice(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
  return Number(value).toFixed(2);
}

function formatChangePct(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
  const numberValue = Number(value);
  const sign = numberValue > 0 ? '+' : '';
  return `${sign}${numberValue.toFixed(2)}%`;
}

function getChangeTone(value?: number | null): { className: string } {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return { className: 'text-muted-text' };
  if (Number(value) > 0) return { className: 'text-rose-400' };
  if (Number(value) < 0) return { className: 'text-emerald-400' };
  return { className: 'text-muted-text' };
}

function isIndexItem(item: WatchlistItem): boolean {
  return String(item.assetCategory || '').toLowerCase() === 'index';
}

const WatchlistPage: React.FC = () => {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState<FormState>(initialForm);
  const [tagInput, setTagInput] = useState('');
  const [sectorDashboard, setSectorDashboard] = useState<SectorEtfDashboardResponse | null>(null);
  const [sectorLoading, setSectorLoading] = useState(true);
  const [sectorConfigOpen, setSectorConfigOpen] = useState(false);
  const [sectorSaving, setSectorSaving] = useState(false);
  const [sectorDrafts, setSectorDrafts] = useState<Record<string, SectorEtfConfig>>({});
  const [signalRefreshing, setSignalRefreshing] = useState(false);
  const [actionItemId, setActionItemId] = useState<number | null>(null);

  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      const response = await watchlistApi.listItems();
      setItems(response.items);
      setError(null);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadSectorEtfs = useCallback(async () => {
    setSectorLoading(true);
    try {
      const response = await marketApi.getSectorEtfs();
      setSectorDashboard(response);
      setSectorDrafts(Object.fromEntries(response.configs.map((config) => [config.sector, config])));
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setSectorLoading(false);
    }
  }, []);

  useEffect(() => {
    document.title = '关注标的 - NestCheck';
    void loadItems();
    void loadSectorEtfs();
  }, [loadItems, loadSectorEtfs]);

  const openCreate = () => {
    setForm(initialForm);
    setTagInput('');
    setFormOpen(true);
  };

  const submitForm = async () => {
    if (!form.symbol.trim()) {
      setError(getParsedApiError('请输入标的代码'));
      return;
    }
    setSaving(true);
    try {
      const payload = { ...form, watchTags: splitTags(tagInput) };
      await watchlistApi.createItem(payload);
      setFormOpen(false);
      await loadItems();
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setSaving(false);
    }
  };

  const updateForm = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const updateSectorDraft = <K extends keyof SectorEtfConfig>(sector: string, key: K, value: SectorEtfConfig[K]) => {
    setSectorDrafts((prev) => ({
      ...prev,
      [sector]: { ...prev[sector], [key]: value },
    }));
  };

  const saveSectorConfig = async () => {
    setSectorSaving(true);
    try {
      for (const config of Object.values(sectorDrafts)) {
        await marketApi.updateSectorEtfConfig(config.sector, {
          tsCode: config.tsCode,
          name: config.name || '',
          weight: config.weight,
          isCore: config.isCore,
        });
      }
      setSectorConfigOpen(false);
      await loadSectorEtfs();
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setSectorSaving(false);
    }
  };

  const refreshSignals = async () => {
    setSignalRefreshing(true);
    try {
      await loadItems();
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setSignalRefreshing(false);
    }
  };

  const moveItem = async (item: WatchlistItem, direction: 'up' | 'down') => {
    setActionItemId(item.id);
    try {
      await watchlistApi.moveItem(item.id, direction);
      await loadItems();
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setActionItemId(null);
    }
  };

  const deleteItem = async (item: WatchlistItem) => {
    const label = item.name || item.displaySymbol || item.symbol;
    if (!window.confirm(`确认取消关注 ${label}？`)) return;
    setActionItemId(item.id);
    try {
      await watchlistApi.deleteItem(item.id);
      await loadItems();
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setActionItemId(null);
    }
  };

  const indexItems = items.filter(isIndexItem);
  const targetItems = items.filter((item) => !isIndexItem(item));
  void indexItems;

  return (
    <div className="flex h-[calc(100vh-5rem)] w-full flex-col overflow-hidden sm:h-[calc(100vh-5.5rem)] lg:h-[calc(100vh-2rem)]">
      <div className="flex-1 flex flex-col min-h-0 min-w-0 w-full">
        <header className="relative z-30 flex min-w-0 flex-shrink-0 items-center overflow-visible px-3 py-3 md:px-4 md:py-4">
          <div className="dashboard-card flex min-h-10 w-full min-w-0 items-center justify-between gap-3 rounded-xl px-4 py-3">
            <div className="min-w-0">
              <div className="label-uppercase">Watchlist</div>
              <h1 className="mt-1 truncate text-xl font-semibold tracking-tight text-foreground md:text-2xl">关注标的</h1>
              <p className="mt-1 line-clamp-1 text-sm text-secondary-text">按股票、基金、指数管理观察对象，每日只刷新红绿灯状态。</p>
            </div>
            <Button type="button" onClick={openCreate} className="h-10 flex-shrink-0"><Plus className="h-4 w-4" />添加标的</Button>
          </div>
        </header>

        <section className="flex-1 min-w-0 min-h-0 overflow-x-hidden overflow-y-auto px-3 pb-4 md:px-6 touch-pan-y">
          {error ? <ApiErrorAlert error={error} className="mb-3" onDismiss={() => setError(null)} /> : null}

          {formOpen ? (
            <Card className="mb-4 rounded-xl p-4">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-foreground">添加关注标的</h2>
            <button type="button" onClick={() => setFormOpen(false)} className="rounded-lg p-1 text-muted-text hover:bg-hover hover:text-foreground"><X className="h-4 w-4" /></button>
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            <Select label="市场" value={form.market} onChange={(value) => updateForm('market', value)} options={marketOptions} />
            <Select label="资产大类" value={form.assetCategory} onChange={(value) => setForm((prev) => ({ ...prev, assetCategory: value as WatchlistAssetCategory, assetSubcategory: value === 'fund' ? prev.assetSubcategory : '' }))} options={assetCategoryOptions} />
            <Input label="代码" value={form.symbol} onChange={(event) => updateForm('symbol', event.target.value)} placeholder="600519 / 013360" />
            <Input label="名称" value={form.name || ''} onChange={(event) => updateForm('name', event.target.value)} placeholder="贵州茅台" />
            <Input label="币种" value={form.currency} onChange={(event) => updateForm('currency', event.target.value)} placeholder="CNY" />
            <Select label="资产细类" value={form.assetSubcategory || ''} onChange={(value) => updateForm('assetSubcategory', value)} disabled={form.assetCategory !== 'fund'} options={form.assetCategory === 'fund' ? fundSubcategoryOptions : [{ value: '', label: '--' }]} />
            <Select label="风险分类" value={form.assetRiskClass || ''} onChange={(value) => updateForm('assetRiskClass', value)} options={[{ value: '', label: '未设置' }, { value: 'R1', label: 'R1' }, { value: 'R2', label: 'R2' }, { value: 'R3', label: 'R3' }, { value: 'R4', label: 'R4' }, { value: 'R5', label: 'R5' }]} />
            <Select label="关注优先级" value={form.watchPriority} onChange={(value) => updateForm('watchPriority', value)} options={[{ value: 'high', label: '高' }, { value: 'medium', label: '中' }, { value: 'low', label: '低' }]} />
            <Select label="分析频率" value={form.analysisFrequency} onChange={(value) => updateForm('analysisFrequency', value)} options={[{ value: 'daily', label: '每日' }, { value: 'weekly', label: '每周' }, { value: 'manual', label: '手动' }]} />
            <Input label="标签" value={tagInput} onChange={(event) => setTagInput(event.target.value)} placeholder="核心持仓, 长期观察" />
            <Input label="关注原因" value={form.watchReason || ''} onChange={(event) => updateForm('watchReason', event.target.value)} placeholder="估值进入观察区" />
            <Input label="来源" value={form.source || 'manual'} onChange={(event) => updateForm('source', event.target.value)} placeholder="manual" />
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-1">
            <Toggle label="关注启用" checked={form.watchEnabled} onChange={(value) => updateForm('watchEnabled', value)} />
          </div>
          <Textarea label="备注" value={form.notes || ''} onChange={(event) => updateForm('notes', event.target.value)} className="mt-3" />
          <div className="mt-4 flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setFormOpen(false)}>取消</Button>
            <Button type="button" onClick={() => void submitForm()} isLoading={saving} loadingText="保存中">保存</Button>
          </div>
            </Card>
          ) : null}

          {loading ? (
            <Card className="rounded-xl p-8 text-center text-sm text-muted-text">正在加载关注标的...</Card>
          ) : (
            <div className="grid min-h-full grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
              <SectorEtfPanel
                dashboard={sectorDashboard}
                loading={sectorLoading}
                configOpen={sectorConfigOpen}
                drafts={sectorDrafts}
                saving={sectorSaving}
                onOpenConfig={() => setSectorConfigOpen(true)}
                onCloseConfig={() => setSectorConfigOpen(false)}
                onUpdateDraft={updateSectorDraft}
                onSaveConfig={() => void saveSectorConfig()}
              />
              <WatchSectionCard
                title="关注标的"
                items={targetItems}
                emptyText="还没有关注标的。"
                refreshing={signalRefreshing}
                actionItemId={actionItemId}
                onRefresh={() => void refreshSignals()}
                onMove={(item, direction) => void moveItem(item, direction)}
                onDelete={(item) => void deleteItem(item)}
              />
            </div>
          )}
        </section>
      </div>
    </div>
  );
};

function SectorEtfPanel({
  dashboard,
  loading,
  configOpen,
  drafts,
  saving,
  onOpenConfig,
  onCloseConfig,
  onUpdateDraft,
  onSaveConfig,
}: {
  dashboard: SectorEtfDashboardResponse | null;
  loading: boolean;
  configOpen: boolean;
  drafts: Record<string, SectorEtfConfig>;
  saving: boolean;
  onOpenConfig: () => void;
  onCloseConfig: () => void;
  onUpdateDraft: <K extends keyof SectorEtfConfig>(sector: string, key: K, value: SectorEtfConfig[K]) => void;
  onSaveConfig: () => void;
}) {
  return (
    <Card className="flex min-h-[18rem] flex-col rounded-xl p-4 lg:min-h-full">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-foreground">行业 ETF 温度</h2>
          <div className="mt-0.5 text-[11px] text-muted-text">日涨跌、近一月表现、相对沪深300</div>
        </div>
        <Button type="button" variant="secondary" onClick={onOpenConfig} className="h-8 px-2 text-xs">
          <Settings className="h-3.5 w-3.5" />配置
        </Button>
      </div>

      {loading ? (
        <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-subtle p-5 text-sm text-muted-text">正在加载行业 ETF...</div>
      ) : dashboard === null ? (
        <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-subtle p-5 text-sm text-muted-text">暂无行业 ETF 数据。</div>
      ) : (
        <div className="grid gap-2 overflow-y-auto pr-1">
          <SectorRankingBlock title="今日涨幅前 5" items={dashboard.topGainers} metric="dailyPctChg" />
          <SectorRankingBlock title="今日跌幅前 5" items={dashboard.topLosers} metric="dailyPctChg" />
          <SectorRankingBlock title="近一月行业表现" items={dashboard.monthlyRankings} metric="monthPctChg" showRs />
        </div>
      )}

      {configOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-3 py-6">
          <Card className="max-h-[85vh] w-full max-w-4xl overflow-hidden rounded-xl p-0">
            <div className="flex items-center justify-between border-b border-subtle px-4 py-3">
              <div>
                <h3 className="text-base font-semibold text-foreground">行业 ETF 配置</h3>
                <p className="mt-0.5 text-xs text-muted-text">行业固定，代表性 ETF 可调整。</p>
              </div>
              <button type="button" onClick={onCloseConfig} className="rounded-lg p-1 text-muted-text hover:bg-hover hover:text-foreground"><X className="h-4 w-4" /></button>
            </div>
            <div className="max-h-[60vh] overflow-auto p-4">
              <div className="grid gap-2">
                {Object.values(drafts).sort((a, b) => a.sortOrder - b.sortOrder).map((config) => (
                  <div key={config.sector} className="grid gap-2 rounded-lg border border-subtle bg-surface/50 p-2 md:grid-cols-[5rem_minmax(8rem,1fr)_minmax(8rem,1fr)_5rem_4rem] md:items-end">
                    <div>
                      <div className="label-uppercase">行业</div>
                      <div className="mt-1 text-sm font-medium text-foreground">{config.sector}</div>
                    </div>
                    <Input label="ETF 代码" value={config.tsCode} onChange={(event) => onUpdateDraft(config.sector, 'tsCode', event.target.value)} />
                    <Input label="ETF 名称" value={config.name || ''} onChange={(event) => onUpdateDraft(config.sector, 'name', event.target.value)} />
                    <Input label="权重" type="number" value={String(config.weight)} onChange={(event) => onUpdateDraft(config.sector, 'weight', Number(event.target.value) || 1)} />
                    <Toggle label="核心" checked={config.isCore} onChange={(value) => onUpdateDraft(config.sector, 'isCore', value)} />
                  </div>
                ))}
              </div>
            </div>
            <div className="flex justify-end gap-2 border-t border-subtle px-4 py-3">
              <Button type="button" variant="secondary" onClick={onCloseConfig}>取消</Button>
              <Button type="button" onClick={onSaveConfig} isLoading={saving} loadingText="保存中">保存配置</Button>
            </div>
          </Card>
        </div>
      ) : null}
    </Card>
  );
}

function SectorRankingBlock({ title, items, metric, showRs = false }: { title: string; items: Array<SectorEtfDashboardResponse['items'][number]>; metric: 'dailyPctChg' | 'monthPctChg'; showRs?: boolean }) {
  return (
    <div className="rounded-lg border border-subtle bg-background/50 p-2">
      <div className="mb-1.5 grid grid-cols-[1.1rem_minmax(0,1fr)_auto] items-center gap-1.5 text-xs font-semibold text-secondary-text">
        <span />
        <span>{title}</span>
        {showRs ? <span className="grid grid-cols-[3.5rem_5.25rem] gap-3 text-right text-[10px] font-medium text-muted-text"><span>涨幅</span><span>相对沪深300</span></span> : null}
      </div>
      <div className="grid gap-1">
        {items.length === 0 ? <div className="text-xs text-muted-text">暂无数据</div> : items.map((item, index) => {
          const value = item[metric];
          const tone = getChangeTone(value);
          return (
            <div key={`${title}-${item.sector}`} className="grid grid-cols-[1.1rem_minmax(0,1fr)_auto] items-center gap-1.5 rounded-md bg-surface/45 px-1.5 py-1 text-[11px] leading-tight">
              <span className="text-muted-text">{index + 1}</span>
              <span className="min-w-0 truncate text-secondary-text">{item.name || item.sector}</span>
              {showRs ? (
                <span className="grid grid-cols-[3.5rem_5.25rem] gap-3 text-right font-mono">
                  <span className={`font-semibold ${tone.className}`}>{formatChangePct(value)}</span>
                  <span className="text-muted-text">{formatChangePct(item.rs)}</span>
                </span>
              ) : (
                <span className={`font-mono font-semibold ${tone.className}`}>{formatChangePct(value)}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function WatchSectionCard({
  title,
  items,
  emptyText,
  compact = false,
  refreshing = false,
  actionItemId = null,
  onRefresh,
  onMove,
  onDelete,
}: {
  title: string;
  items: WatchlistItem[];
  emptyText: string;
  compact?: boolean;
  refreshing?: boolean;
  actionItemId?: number | null;
  onRefresh?: () => void;
  onMove?: (item: WatchlistItem, direction: 'up' | 'down') => void;
  onDelete?: (item: WatchlistItem) => void;
}) {
  return (
    <Card className="flex min-h-[18rem] flex-col rounded-xl p-4 lg:min-h-full">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-base font-semibold text-foreground">{title}</h2>
        <div className="flex items-center gap-2">
          {onRefresh ? <Button type="button" variant="secondary" onClick={onRefresh} isLoading={refreshing} loadingText="刷新中" className="h-8 px-2 text-xs">刷新红绿灯</Button> : null}
          <Badge>{items.length}</Badge>
        </div>
      </div>
      {items.length === 0 ? (
        <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-subtle p-5 text-sm text-muted-text">{emptyText}</div>
      ) : (
        <div className="grid gap-3 overflow-y-auto pr-1">
          {items.map((item, index) => (
            <WatchCard
              key={item.id}
              item={item}
              compact={compact}
              actionLoading={actionItemId === item.id}
              canMoveUp={index > 0}
              canMoveDown={index < items.length - 1}
              onMove={onMove}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}
    </Card>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="flex items-center justify-between rounded-xl border border-subtle bg-surface/60 px-3 py-2 text-sm text-secondary-text">
      <span>{label}</span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="h-4 w-4 accent-primary" />
    </label>
  );
}

function WatchCard({
  item,
  compact = false,
  actionLoading = false,
  canMoveUp = false,
  canMoveDown = false,
  onMove,
  onDelete,
}: {
  item: WatchlistItem;
  compact?: boolean;
  actionLoading?: boolean;
  canMoveUp?: boolean;
  canMoveDown?: boolean;
  onMove?: (item: WatchlistItem, direction: 'up' | 'down') => void;
  onDelete?: (item: WatchlistItem) => void;
}) {
  return (
    <div className="rounded-xl border border-subtle bg-surface/60 p-3.5 transition-colors hover:border-subtle-hover">
      <div className={compact ? 'grid gap-3' : 'grid gap-3 xl:grid-cols-[minmax(7rem,0.55fr)_minmax(0,1.85fr)]'}>
        <InstrumentBlock
          item={item}
          actionLoading={actionLoading}
          canMoveUp={canMoveUp}
          canMoveDown={canMoveDown}
          onMove={onMove}
          onDelete={onDelete}
        />
        <TrafficLights item={item} />
      </div>
    </div>
  );
}

function CardActionButton({ label, disabled = false, danger = false, onClick, children }: { label: string; disabled?: boolean; danger?: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex h-7 w-7 items-center justify-center rounded-lg border border-subtle bg-background/70 text-muted-text transition-colors hover:bg-hover hover:text-foreground disabled:cursor-not-allowed disabled:opacity-35 ${danger ? 'hover:border-danger/50 hover:text-danger' : ''}`}
    >
      {children}
    </button>
  );
}

function InstrumentBlock({
  item,
  actionLoading = false,
  canMoveUp = false,
  canMoveDown = false,
  onMove,
  onDelete,
}: {
  item: WatchlistItem;
  actionLoading?: boolean;
  canMoveUp?: boolean;
  canMoveDown?: boolean;
  onMove?: (item: WatchlistItem, direction: 'up' | 'down') => void;
  onDelete?: (item: WatchlistItem) => void;
}) {
  const changeTone = getChangeTone(item.latestChangePct);
  const displaySymbol = item.displaySymbol || item.symbol;
  return (
    <div className="min-w-0">
      <div className="flex min-w-0 items-center gap-2">
        <span className="truncate text-sm font-semibold text-foreground">{item.name || item.symbol}</span>
        {item.signalVerdictCode ? <span className="shrink-0 rounded-full border border-subtle bg-background/70 px-2 py-0.5 text-[10px] font-semibold text-foreground">{item.signalVerdictCode}</span> : null}
      </div>
      <div className="mt-0.5 text-[11px] text-muted-text">{displaySymbol}</div>
      <div className="mt-2 flex items-baseline gap-2 text-[11px]">
        <span className="font-mono text-base font-semibold text-foreground">{formatPrice(item.latestPrice)}</span>
        <span className={`font-mono font-semibold ${changeTone.className}`}>{formatChangePct(item.latestChangePct)}</span>
      </div>
      <div className="mt-2 flex gap-1">
        <CardActionButton label="上移" disabled={!canMoveUp || actionLoading} onClick={() => onMove?.(item, 'up')}>
          <ArrowUp className="h-3.5 w-3.5" />
        </CardActionButton>
        <CardActionButton label="下移" disabled={!canMoveDown || actionLoading} onClick={() => onMove?.(item, 'down')}>
          <ArrowDown className="h-3.5 w-3.5" />
        </CardActionButton>
        <CardActionButton label="取消关注" disabled={actionLoading} danger onClick={() => onDelete?.(item)}>
          <Trash2 className="h-3.5 w-3.5" />
        </CardActionButton>
      </div>
    </div>
  );
}

function TrafficLights({ item }: { item: WatchlistItem }) {
  const lights = item.signalLights || [];
  return (
    <div className="rounded-lg border border-subtle bg-background/50 px-3 py-2 text-[11px] text-secondary-text">
      {lights.length === 0 ? (
        <div className="text-xs text-muted-text">红绿灯待刷新</div>
      ) : (
        <>
          <div className="grid grid-cols-5 gap-1.5">
            {lights.map((light) => (
              <div key={light.code} title={light.reason} className="flex min-w-0 flex-col items-center gap-1 rounded-lg border border-subtle bg-surface/70 px-1.5 py-1.5">
                <div className={cn(
                  'h-4 w-4 shrink-0 rounded-full shadow-sm',
                  light.status === 'G' ? 'bg-green-500' : light.status === 'R' ? 'bg-red-500' : light.status === 'Y' ? 'bg-yellow-500' : 'bg-slate-400'
                )} />
                <span className="text-[9px] font-bold leading-none text-foreground">{light.status}</span>
                <span className="max-w-full truncate text-[10px] font-medium text-secondary-text">{light.label}</span>
              </div>
            ))}
          </div>
          <div className="mt-2 flex items-start justify-between gap-2 text-[10px] text-muted-text">
            <span className="line-clamp-2 min-w-0 flex-1">{item.signalReason || '红绿灯已刷新'}</span>
            <span className="shrink-0 whitespace-nowrap">{item.signalAsOfDate || '--'}</span>
          </div>
        </>
      )}
    </div>
  );
}

export default WatchlistPage;
