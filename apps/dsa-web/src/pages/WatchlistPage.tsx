import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { BarChart3, Plus, X } from 'lucide-react';
import { watchlistApi } from '../api/watchlist';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { ApiErrorAlert, Badge, Button, Card, Input, Select, Textarea } from '../components/common';
import type { WatchlistAssetCategory, WatchlistItem, WatchlistItemInput, WatchlistMarketReview } from '../types/watchlist';
import { formatDateTime } from '../utils/format';

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

const WatchlistPage: React.FC = () => {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [marketReview, setMarketReview] = useState<WatchlistMarketReview | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState<FormState>(initialForm);
  const [tagInput, setTagInput] = useState('');

  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      const response = await watchlistApi.listItems();
      setItems(response.items);
      setMarketReview(response.marketReview ?? null);
      setError(null);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    document.title = '关注标的 - NestCheck';
    void loadItems();
  }, [loadItems]);

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

  return (
    <div className="flex h-[calc(100vh-5rem)] w-full flex-col overflow-hidden sm:h-[calc(100vh-5.5rem)] lg:h-[calc(100vh-2rem)]">
      <div className="flex-1 flex flex-col min-h-0 min-w-0 w-full">
        <header className="relative z-30 flex min-w-0 flex-shrink-0 items-center overflow-visible px-3 py-3 md:px-4 md:py-4">
          <div className="dashboard-card flex min-h-10 w-full min-w-0 items-center justify-between gap-3 rounded-xl px-4 py-3">
            <div className="min-w-0">
              <div className="label-uppercase">Watchlist</div>
              <h1 className="mt-1 truncate text-xl font-semibold tracking-tight text-foreground md:text-2xl">关注标的</h1>
              <p className="mt-1 line-clamp-1 text-sm text-secondary-text">按大盘、股票、基金管理分析对象；大盘使用系统默认市场口径。</p>
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
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            <Toggle label="关注启用" checked={form.watchEnabled} onChange={(value) => updateForm('watchEnabled', value)} />
            <Toggle label="定期分析" checked={form.analysisEnabled} onChange={(value) => updateForm('analysisEnabled', value)} />
            <Toggle label="告警启用" checked={form.alertEnabled} onChange={(value) => updateForm('alertEnabled', value)} />
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
            <div className="grid min-h-full grid-cols-1 gap-4 lg:grid-cols-3">
              <MarketOverviewCard marketReview={marketReview} />
              <WatchSectionCard items={items} />
            </div>
          )}
        </section>
      </div>
    </div>
  );
};

function MarketOverviewCard({ marketReview }: { marketReview: WatchlistMarketReview | null }) {
  const sections = marketReview?.latestAnalysisSections ?? {};
  return (
    <Card className="flex min-h-[18rem] flex-col rounded-xl p-4 lg:min-h-full">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-base font-semibold text-foreground"><BarChart3 className="h-4 w-4" />大盘</h2>
        <Badge variant="info">默认</Badge>
      </div>
      <div className="flex min-h-0 flex-1 flex-col rounded-lg border border-subtle bg-surface/60 p-4 text-sm text-secondary-text">
        <div className="flex items-center justify-between gap-2 text-[11px] uppercase tracking-wide text-muted-text">
          <span className="font-semibold">大盘复盘</span>
          {marketReview?.latestAnalysisAt ? <span className="shrink-0 normal-case tracking-normal">{formatDateTime(marketReview.latestAnalysisAt)}</span> : null}
        </div>
        {marketReview?.latestAnalysisSummary || marketReview?.latestOperationAdvice || marketReview?.latestTrendPrediction ? (
          <div className="mt-3 flex min-h-0 flex-1 flex-col gap-3 text-xs">
            {marketReview.latestAnalysisSummary ? (
              <div className="rounded-lg border border-subtle bg-background/50 p-3 leading-5 text-secondary-text">
                <span className="font-medium text-foreground">摘要：</span>{marketReview.latestAnalysisSummary}
              </div>
            ) : null}
            <div className="grid gap-2">
              <MarketReviewSnippet label="主线板块" value={sections.mainThemes} />
              <MarketReviewSnippet label="风险提示" value={sections.riskAlert} />
              <MarketReviewSnippet label="明日观察" value={sections.tomorrowWatch} />
            </div>
            {(marketReview.latestOperationAdvice || marketReview.latestTrendPrediction) ? (
              <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-subtle pt-2 text-[11px]">
                {marketReview.latestOperationAdvice ? <CompactInsight label="操作建议" value={marketReview.latestOperationAdvice} /> : null}
                {marketReview.latestTrendPrediction ? <CompactInsight label="趋势预测" value={marketReview.latestTrendPrediction} /> : null}
              </div>
            ) : null}
          </div>
        ) : (
          <div className="mt-3 leading-6">大盘按系统默认市场复盘口径分析，无需在关注标的中单独录入。</div>
        )}
      </div>
    </Card>
  );
}

function MarketReviewSnippet({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div className="min-h-[6.5rem] rounded-lg border border-subtle bg-background/50 p-3.5 text-xs leading-5 text-secondary-text">
      <div className="mb-1 text-[10px] font-semibold text-muted-text">{label}</div>
      <div>{value}</div>
    </div>
  );
}

function WatchSectionCard({ items }: { items: WatchlistItem[] }) {
  return (
    <Card className="flex min-h-[18rem] flex-col rounded-xl p-4 lg:col-span-2 lg:min-h-full">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-base font-semibold text-foreground">关注标的</h2>
        <Badge>{items.length}</Badge>
      </div>
      {items.length === 0 ? (
        <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-subtle p-5 text-sm text-muted-text">还没有关注标的。</div>
      ) : (
        <div className="grid gap-3 overflow-y-auto pr-1">
          {items.map((item) => <WatchCard key={item.id} item={item} />)}
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

function WatchCard({ item }: { item: WatchlistItem }) {
  return (
    <div className="min-h-[8.5rem] rounded-xl border border-subtle bg-surface/60 p-3.5 transition-colors hover:border-subtle-hover">
      <div className="grid h-full gap-3 lg:grid-cols-[minmax(4.5rem,0.32fr)_minmax(10rem,0.78fr)_minmax(0,1.55fr)]">
        <InstrumentBlock item={item} />
        <MonitorLightBlock item={item} />
        <div className="flex min-w-0 flex-col rounded-lg border border-subtle bg-background/50 p-3 text-[11px] text-secondary-text">
          <div className="mb-1 flex items-center justify-between gap-2 text-[10px] uppercase tracking-wide text-muted-text">
            <span className="font-semibold">AI 分析</span>
            {item.latestAnalysisAt ? <span className="shrink-0 normal-case tracking-normal">{formatDateTime(item.latestAnalysisAt)}</span> : null}
          </div>
          <StockInsight item={item} />
        </div>
      </div>
    </div>
  );
}

function InstrumentBlock({ item }: { item: WatchlistItem }) {
  const changeTone = getChangeTone(item.latestChangePct);
  return (
    <div className="min-w-0">
      <div className="truncate text-sm font-semibold text-foreground">{item.name || item.symbol}</div>
      <div className="mt-0.5 text-[11px] text-muted-text">{item.symbol}</div>
      <div className="mt-2 flex items-baseline gap-2 text-[11px]">
        <span className="font-mono text-base font-semibold text-foreground">{formatPrice(item.latestPrice)}</span>
        <span className={`font-mono font-semibold ${changeTone.className}`}>{formatChangePct(item.latestChangePct)}</span>
      </div>
    </div>
  );
}

function MonitorLightBlock({ item }: { item: WatchlistItem }) {
  const hasTriggered = item.alertTriggerCount > 0;
  return (
    <div className="h-full rounded-lg border border-subtle bg-background/50 p-3 text-[11px] text-secondary-text">
      <div className="flex items-center gap-2">
        <span className={`h-3 w-3 rounded-full ring-2 ${hasTriggered ? 'bg-rose-400 ring-rose-400/25' : 'bg-emerald-400 ring-emerald-400/25'}`} />
        <span className="font-medium text-foreground">{hasTriggered ? '触发告警' : '监控正常'}</span>
      </div>
      <div className="mt-1.5 line-clamp-2 text-muted-text">
        {item.alertEnabled ? (hasTriggered ? `已有 ${item.alertTriggerCount} 次触发` : '暂无触发，报警监控开启') : '报警监控关闭'}
      </div>
      <div className="mt-1 text-[10px] text-muted-text">规则 {item.alertRuleCount}</div>
    </div>
  );
}

function StockInsight({ item }: { item: WatchlistItem }) {
  if (!item.latestAnalysisSummary && !item.latestOperationAdvice && !item.latestTrendPrediction) {
    return <div className="text-muted-text">暂无股票分析结果</div>;
  }
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1">
        {item.latestAnalysisSummary ? <InsightLine label="核心洞察" value={item.latestAnalysisSummary} multiline /> : null}
      </div>
      {(item.latestOperationAdvice || item.latestTrendPrediction) ? (
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-subtle pt-2 text-[11px]">
          {item.latestOperationAdvice ? <CompactInsight label="操作建议" value={item.latestOperationAdvice} /> : null}
          {item.latestTrendPrediction ? <CompactInsight label="趋势预测" value={item.latestTrendPrediction} /> : null}
        </div>
      ) : null}
    </div>
  );
}

function CompactInsight({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 truncate">
      <span className="font-medium text-foreground">{label}：</span>
      <span>{value}</span>
    </div>
  );
}

function InsightLine({ label, value, multiline = false }: { label: string; value: string; multiline?: boolean }) {
  return (
    <div>
      <span className="font-medium text-foreground">{label}：</span>
      <span className={multiline ? 'line-clamp-4' : 'line-clamp-1'}>{value}</span>
    </div>
  );
}

export default WatchlistPage;
