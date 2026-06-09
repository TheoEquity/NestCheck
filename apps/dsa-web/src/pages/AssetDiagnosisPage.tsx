import type React from 'react';
import { useEffect, useMemo } from 'react';
import { Activity, BarChart3, HeartPulse, Scale, WalletCards } from 'lucide-react';
import { ApiErrorAlert, Card, EmptyState, PageHeader } from '../components/common';
import { usePortfolioOverview, formatMoney, formatSignedPct, formatPct, localizeAssetCategory } from './assetsShared';

const benchmarkRows = [
  { label: '沪深300', value: '+0.00%', note: 'A 股权益参照物' },
  { label: '中证全债', value: '+0.00%', note: '低波动资产参照物' },
  { label: '同类资产', value: '待接入', note: '按股票/基金类别拆分比较' },
];

const AssetDiagnosisPage: React.FC = () => {
  const { positions, risk, isLoading, error } = usePortfolioOverview();

  useEffect(() => {
    document.title = '资产诊断 - NestCheck';
  }, []);

  const totalMarketValue = positions.reduce((sum, item) => sum + Number(item.marketValueBase || 0), 0);
  const totalPnl = positions.reduce((sum, item) => sum + Number(item.unrealizedPnlBase || 0), 0);
  const totalCost = positions.reduce((sum, item) => sum + Number(item.totalCost || 0), 0);
  const totalPnlPct = totalCost > 0 ? (totalPnl / totalCost) * 100 : null;

  const categoryRows = useMemo(() => {
    const map = new Map<string, { value: number; count: number }>();
    positions.forEach((position) => {
      const label = localizeAssetCategory(position.assetCategory || 'stock');
      const current = map.get(label) || { value: 0, count: 0 };
      current.value += Number(position.marketValueBase || 0);
      current.count += 1;
      map.set(label, current);
    });
    return Array.from(map.entries())
      .map(([label, data]) => ({ label, ...data, pct: totalMarketValue > 0 ? (data.value / totalMarketValue) * 100 : 0 }))
      .sort((a, b) => b.value - a.value);
  }, [positions, totalMarketValue]);

  const healthItems = [
    { label: '收益表现', value: totalPnlPct == null ? '--' : formatSignedPct(totalPnlPct), icon: BarChart3 },
    { label: '资产质量', value: risk ? (risk.drawdown.alert ? '需关注' : '稳定') : '待评估', icon: HeartPulse },
    { label: '操作频率', value: '待接入交易记录', icon: Activity },
    { label: '配置均衡', value: categoryRows.length > 1 ? '已分散' : '偏集中', icon: Scale },
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title="资产诊断"
        description="聚焦收益、风险、参照物对比、资产质量和操作行为，用轻量指标支撑后续 AI 诊断。"
      />

      {error ? <ApiErrorAlert error={error} /> : null}

      <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <Card className="p-5">
          <div className="mb-4 flex items-center gap-2">
            <WalletCards className="h-5 w-5 text-primary" />
            <h2 className="text-base font-semibold text-foreground">资产概览</h2>
          </div>
          {isLoading ? (
            <div className="h-40 animate-pulse rounded-xl bg-border/20" />
          ) : positions.length === 0 ? (
            <EmptyState title="暂无资产数据" description="先在资产初始化或资产管理中录入持仓。" />
          ) : (
            <div className="grid gap-3 sm:grid-cols-3">
              <Metric label="总市值" value={formatMoney(totalMarketValue)} />
              <Metric label="浮动盈亏" value={formatMoney(totalPnl)} />
              <Metric label="收益率" value={totalPnlPct == null ? '--' : formatSignedPct(totalPnlPct)} />
            </div>
          )}
        </Card>

        <Card className="p-5">
          <h2 className="mb-4 text-base font-semibold text-foreground">诊断维度</h2>
          <div className="grid gap-2">
            {healthItems.map(({ label, value, icon: Icon }) => (
              <div key={label} className="flex items-center justify-between rounded-xl border border-subtle bg-background/50 px-3 py-2 text-sm">
                <span className="flex items-center gap-2 text-secondary-text"><Icon className="h-4 w-4" />{label}</span>
                <span className="font-medium text-foreground">{value}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <h2 className="mb-4 text-base font-semibold text-foreground">资产结构</h2>
          <div className="space-y-2">
            {categoryRows.length ? categoryRows.map((row) => (
              <div key={row.label} className="rounded-xl border border-subtle bg-background/50 px-3 py-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-secondary-text">{row.label} · {row.count} 项</span>
                  <span className="font-medium text-foreground">{formatPct(row.pct)}</span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-border/30">
                  <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(100, row.pct)}%` }} />
                </div>
              </div>
            )) : <EmptyState title="暂无结构数据" description="录入资产后展示股票、基金、现金等配置比例。" />}
          </div>
        </Card>

        <Card className="p-5">
          <h2 className="mb-4 text-base font-semibold text-foreground">参照物对比</h2>
          <div className="space-y-2">
            {benchmarkRows.map((row) => (
              <div key={row.label} className="flex items-center justify-between rounded-xl border border-subtle bg-background/50 px-3 py-2 text-sm">
                <div>
                  <div className="font-medium text-foreground">{row.label}</div>
                  <div className="text-xs text-muted-text">{row.note}</div>
                </div>
                <div className="font-mono text-secondary-text">{row.value}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card className="p-5">
        <h2 className="mb-2 text-base font-semibold text-foreground">AI 诊断定位</h2>
        <p className="text-sm leading-6 text-secondary-text">
          后续这里接入 LLM，把收益、参照物、资产质量、操作频率和盈亏归因整理成一份个人可读的资产体检报告。当前页面先固定数据骨架，避免让 AI 主导基础判断。
        </p>
      </Card>
    </div>
  );
};

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-subtle bg-background/50 p-3">
      <div className="text-xs text-muted-text">{label}</div>
      <div className="mt-1 truncate text-lg font-semibold text-foreground">{value}</div>
    </div>
  );
}

export default AssetDiagnosisPage;
