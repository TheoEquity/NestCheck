import type React from 'react';
import { useState, useCallback } from 'react';
import { PieChart, LineChart, TrendingUp, FileText, RefreshCw } from 'lucide-react';
import { fundApi, type FundItem, type NavItem, type HoldingItem, type FundAnalysisResult } from '../api/fund';
import { ApiErrorAlert, Card, Badge, EmptyState, Button } from '../components/common';
import { getParsedApiError, type ParsedApiError } from '../api/error';

const FUND_INPUT_CLASS =
  'input-surface input-focus-glow h-11 w-full rounded-xl border bg-transparent px-4 text-sm transition-all focus:outline-none disabled:cursor-not-allowed disabled:opacity-60';

type FundAssetInputState = {
  market: string;
  assetCategory: string;
  symbol: string;
  name: string;
};

// ============ Structured Fund Asset Input ============

const FundAssetInput: React.FC<{
  value: FundAssetInputState;
  onChange: (value: FundAssetInputState) => void;
  onSubmit: () => void;
  loading: boolean;
}> = ({ value, onChange, onSubmit, loading }) => {
  const updateField = (key: keyof FundAssetInputState, nextValue: string) => {
    onChange({ ...value, [key]: nextValue });
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  };

  return (
    <Card variant="bordered" padding="md" className="space-y-3">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
        <label className="space-y-1.5">
          <span className="text-xs font-medium text-muted-text">市场</span>
          <select
            value={value.market}
            onChange={(e) => updateField('market', e.target.value)}
            disabled={loading}
            className={FUND_INPUT_CLASS}
          >
            <option value="cn">A股</option>
          </select>
        </label>
        <label className="space-y-1.5">
          <span className="text-xs font-medium text-muted-text">大类</span>
          <select
            value={value.assetCategory}
            onChange={(e) => updateField('assetCategory', e.target.value)}
            disabled={loading}
            className={FUND_INPUT_CLASS}
          >
            <option value="fund">基金</option>
          </select>
        </label>
        <label className="space-y-1.5">
          <span className="text-xs font-medium text-muted-text">代码</span>
          <input
            type="text"
            value={value.symbol}
            onChange={(e) => updateField('symbol', e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="013360"
            disabled={loading}
            className={FUND_INPUT_CLASS}
          />
        </label>
        <label className="space-y-1.5">
          <span className="text-xs font-medium text-muted-text">名称</span>
          <input
            type="text"
            value={value.name}
            onChange={(e) => updateField('name', e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="华夏磐泰混合C"
            disabled={loading}
            className={FUND_INPUT_CLASS}
          />
        </label>
      </div>
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <p className="text-xs text-muted-text">
          按资产主数据约定输入：市场 + 大类 + 代码 + 名称。分析时按代码从 AKShare 获取净值和持仓数据。
        </p>
        <Button
          variant="primary"
          onClick={onSubmit}
          disabled={!value.symbol.trim() || !value.name.trim() || loading}
          isLoading={loading}
          loadingText="分析中..."
          className="btn-primary flex-shrink-0 h-11"
        >
          <PieChart className="h-4 w-4 mr-1.5" />
          一次性分析
        </Button>
      </div>
    </Card>
  );
};

// ============ Nav Chart (simple line visualization) ============

const NavChart: React.FC<{ data: NavItem[] }> = ({ data }) => {
  if (!data.length) {
    return <EmptyState title="暂无净值数据" description="请点击刷新获取净值历史" />;
  }

  const sorted = [...data].sort((a, b) => (a.nav_date || '').localeCompare(b.nav_date || '')).reverse();
  const navValues = sorted.slice(0, 90).reverse().map((d) => d.unit_nav ?? 0);
  if (navValues.length < 2) {
    return <EmptyState title="净值数据不足" />;
  }

  const min = Math.min(...navValues);
  const max = Math.max(...navValues);
  const range = max - min || 1;
  const height = 120;
  const points = navValues
    .map((v, i) => {
      const x = (i / (navValues.length - 1)) * 100;
      const y = height - ((v - min) / range) * (height - 16) - 8;
      return `${x},${y}`;
    })
    .join(' ');

  const first = navValues[0];
  const last = navValues[navValues.length - 1];
  const change = ((last - first) / first) * 100;
  const isUp = change >= 0;

  return (
    <Card variant="bordered" padding="sm">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-foreground flex items-center gap-1.5">
          <LineChart className="h-4 w-4" />
          净值走势
        </h3>
        <Badge variant={isUp ? 'success' : 'danger'}>
          <TrendingUp className={`h-3 w-3 ${isUp ? '' : 'rotate-180'}`} />
          {isUp ? '+' : ''}{change.toFixed(2)}%
        </Badge>
      </div>
      <div className="relative">
        <svg viewBox="0 0 100 120" className="w-full" style={{ maxHeight: '160px' }}>
          <defs>
            <linearGradient id="navGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={isUp ? 'var(--color-success)' : 'var(--color-danger)'} stopOpacity="0.3" />
              <stop offset="100%" stopColor={isUp ? 'var(--color-success)' : 'var(--color-danger)'} stopOpacity="0.02" />
            </linearGradient>
          </defs>
          {/* Area fill */}
          <polygon
            points={`0,${height} ${points} 100,${height}`}
            fill="url(#navGradient)"
          />
          {/* Line */}
          <polyline
            points={points}
            fill="none"
            stroke={isUp ? 'var(--color-success)' : 'var(--color-danger)'}
            strokeWidth="0.6"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      </div>
      <div className="flex justify-between text-xs text-muted-text mt-1">
        <span>{sorted[navValues.length - 1]?.nav_date}</span>
        <span>{sorted[0]?.nav_date}</span>
      </div>
    </Card>
  );
};

// ============ Holdings Table ============

const HoldingsTable: React.FC<{ data: HoldingItem[] }> = ({ data }) => {
  if (!data.length) {
    return <EmptyState title="暂无持仓数据" description="最新一期季报尚未披露持仓" />;
  }

  const totalPct = data.reduce((sum, h) => sum + (h.holding_pct ?? 0), 0);

  return (
    <Card variant="bordered" padding="sm">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-foreground flex items-center gap-1.5">
          <FileText className="h-4 w-4" />
          前十大持仓
        </h3>
        <Badge variant="info">合计占比 {totalPct.toFixed(1)}%</Badge>
      </div>
      <div className="space-y-2">
        {data.map((h) => (
          <div key={`${h.stock_code}-${h.rank}`} className="flex items-center justify-between py-1.5 border-b border-border/5 last:border-b-0">
            <div className="flex items-center gap-3">
              <span className="flex items-center justify-center w-6 h-6 rounded-full text-xs font-mono bg-surface/60 text-muted-text">
                {h.rank ?? '--'}
              </span>
              <div>
                <p className="text-sm text-foreground font-medium">{h.stock_name}</p>
                <p className="text-xs text-muted-text font-mono">{h.stock_code}{h.stock_market !== 'A' ? ` · ${h.stock_market}` : ''}</p>
              </div>
            </div>
            <div className="text-right">
              <p className="text-sm font-semibold text-foreground">{h.holding_pct ?? '--'}%</p>
              {h.holding_amount && (
                <p className="text-xs text-muted-text">{h.holding_amount}万</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
};

// ============ Fund Info Card ============

const FundInfoCard: React.FC<{ info: FundItem }> = ({ info }) => (
  <Card variant="gradient" padding="md">
    <div className="flex items-start justify-between">
      <div className="flex-1">
        <h2 className="text-xl font-bold text-foreground">{info.fund_name}</h2>
        <div className="flex items-center gap-2 mt-1.5">
          <span className="home-accent-chip px-2 py-0.5 font-mono text-xs">{info.fund_code}</span>
          {info.fund_type && <Badge variant="info">{info.fund_type}</Badge>}
          {info.risk_level && <Badge variant="warning">{info.risk_level}</Badge>}
        </div>
      </div>
    </div>
    <div className="home-divider border-t pt-4 mt-4">
      <div className="grid grid-cols-2 gap-3 text-sm">
        {info.fund_manager && (
          <div>
            <p className="text-xs text-muted-text uppercase tracking-wider">基金经理</p>
            <p className="text-foreground font-medium mt-0.5">{info.fund_manager}</p>
          </div>
        )}
        {info.management_company && (
          <div>
            <p className="text-xs text-muted-text uppercase tracking-wider">基金公司</p>
            <p className="text-foreground font-medium mt-0.5">{info.management_company}</p>
          </div>
        )}
        {info.fund_size != null && (
          <div>
            <p className="text-xs text-muted-text uppercase tracking-wider">基金规模</p>
            <p className="text-foreground font-medium mt-0.5">{info.fund_size.toFixed(2)} 亿</p>
          </div>
        )}
        {info.inception_date && (
          <div>
            <p className="text-xs text-muted-text uppercase tracking-wider">成立日期</p>
            <p className="text-foreground font-medium mt-0.5">{info.inception_date}</p>
          </div>
        )}
      </div>
    </div>
  </Card>
);

// ============ Analysis Report ============

const AnalysisReportView: React.FC<{ report: FundAnalysisResult }> = ({ report }) => (
  <Card variant="bordered" padding="md" className="animate-fade-in">
    <h3 className="text-base font-bold text-foreground mb-4 flex items-center gap-2">
      <PieChart className="h-5 w-5 text-primary" />
      {report.fund_name} ({report.fund_code}) 分析报告
    </h3>
    <div className="space-y-5">
      <div>
        <h4 className="text-sm font-semibold text-foreground mb-2">净值趋势分析</h4>
        <p className="text-sm text-secondary-text leading-7 whitespace-pre-wrap">{report.net_value_trend}</p>
      </div>
      <div>
        <h4 className="text-sm font-semibold text-foreground mb-2">持仓集中度分析</h4>
        <p className="text-sm text-secondary-text leading-7 whitespace-pre-wrap">{report.holding_concentration}</p>
      </div>
      <div className="rounded-lg bg-surface/60 border border-border/30 px-4 py-3">
        <h4 className="text-sm font-semibold text-foreground mb-1">操作建议</h4>
        <p className="text-sm text-foreground leading-7 whitespace-pre-wrap">{report.investment_advice}</p>
      </div>
    </div>
  </Card>
);

// ============ Main Page ============

const FundAnalysisPage: React.FC = () => {
  const [assetInput, setAssetInput] = useState<FundAssetInputState>({
    market: 'cn',
    assetCategory: 'fund',
    symbol: '',
    name: '',
  });
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [statusText, setStatusText] = useState('');
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [fundInfo, setFundInfo] = useState<FundItem | null>(null);
  const [navData, setNavData] = useState<NavItem[]>([]);
  const [holdings, setHoldings] = useState<HoldingItem[]>([]);
  const [report, setReport] = useState<FundAnalysisResult | null>(null);

  const handleAnalyzeAsset = useCallback(async () => {
    const symbol = assetInput.symbol.trim();
    const name = assetInput.name.trim();
    if (!symbol || !name) return;
    setLoading(true);
    setAnalyzing(true);
    setStatusText('正在获取基金净值和持仓数据...');
    setError(null);
    setReport(null);
    setNavData([]);
    setHoldings([]);

    try {
      const result = await fundApi.analyzeAsset({
        market: assetInput.market,
        assetCategory: assetInput.assetCategory,
        symbol,
        name,
        queryText: `${assetInput.market}/${assetInput.assetCategory}/${symbol}/${name}`,
      });
      setStatusText('正在读取本地缓存数据...');
      setFundInfo(result.info);
      setReport(result.report);

      const [nav, hold] = await Promise.all([
        fundApi.getNav(result.fund_code, { limit: 365 }),
        fundApi.getHoldings(result.fund_code),
      ]);
      setNavData(nav);
      setHoldings(hold);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setLoading(false);
      setAnalyzing(false);
      setStatusText('');
    }
  }, [assetInput]);

  const handleRefreshData = useCallback(async () => {
    if (!fundInfo) return;
    setLoading(true);
    setStatusText('正在刷新基金数据...');
    setError(null);
    try {
      await fundApi.analyzeAsset({
        market: assetInput.market,
        assetCategory: assetInput.assetCategory,
        symbol: fundInfo.fund_code,
        name: fundInfo.fund_name,
        queryText: `${assetInput.market}/${assetInput.assetCategory}/${fundInfo.fund_code}/${fundInfo.fund_name}`,
      });
      const [nav, hold] = await Promise.all([
        fundApi.getNav(fundInfo.fund_code, { limit: 365 }),
        fundApi.getHoldings(fundInfo.fund_code),
      ]);
      setNavData(nav);
      setHoldings(hold);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setLoading(false);
      setStatusText('');
    }
  }, [assetInput.assetCategory, assetInput.market, fundInfo]);

  return (
    <div
      data-testid="fund-analysis-page"
      className="flex h-[calc(100vh-5rem)] w-full flex-col overflow-hidden sm:h-[calc(100vh-5.5rem)] lg:h-[calc(100vh-2rem)]"
    >
      <div className="flex-1 flex flex-col min-h-0 min-w-0 w-full">
        <header className="relative z-30 flex min-w-0 flex-shrink-0 items-center overflow-visible px-3 py-3 md:px-4 md:py-4">
          <div className="flex min-w-0 flex-1 flex-col gap-2.5 md:flex-row md:items-center">
            <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
              <PieChart className="h-6 w-6 text-primary" />
              基金分析
            </h1>
            <p className="text-secondary-text text-sm">输入基金代码或名称，获取净值走势、持仓分析和AI投资建议。</p>
          </div>
        </header>

        <div className="px-3 pb-3 md:px-6">
          <FundAssetInput
            value={assetInput}
            onChange={setAssetInput}
            onSubmit={handleAnalyzeAsset}
            loading={loading}
          />
        </div>

        {error && (
          <div className="px-3 pb-3 md:px-6">
            <ApiErrorAlert error={error} onDismiss={() => setError(null)} />
          </div>
        )}

        <section className="flex-1 min-w-0 min-h-0 overflow-x-auto overflow-y-auto px-3 pb-4 md:px-6 touch-pan-y">
          {!fundInfo && !loading ? (
            <div className="flex h-full items-center justify-center">
              <EmptyState
                title="开始基金分析"
                description="按资产主数据约定输入市场、大类、代码和名称，例如 A股 / 基金 / 013360 / 华夏磐泰混合C。"
                className="max-w-xl border-dashed"
                icon={<PieChart className="h-8 w-8" />}
              />
            </div>
          ) : (
            <div className="space-y-4 pb-8 animate-fade-in">
              {fundInfo && <FundInfoCard info={fundInfo} />}
              {analyzing || statusText ? (
                <Card variant="bordered" padding="md">
                  <div className="flex items-center gap-3 text-secondary-text">
                    <svg className="h-5 w-5 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    {statusText || '正在生成分析报告...'}
                  </div>
                </Card>
              ) : (
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => void handleRefreshData()}
                    disabled={!fundInfo}
                  >
                    <RefreshCw className="h-4 w-4 mr-1.5" />
                    刷新数据
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleAnalyzeAsset}
                    disabled={!assetInput.symbol.trim() || !assetInput.name.trim()}
                  >
                    <PieChart className="h-4 w-4 mr-1.5" />
                    重新分析
                  </Button>
                </div>
              )}

              {report && <AnalysisReportView report={report} />}

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <NavChart data={navData} />
                <HoldingsTable data={holdings} />
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
};

export default FundAnalysisPage;
