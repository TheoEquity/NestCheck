import type React from 'react';
import { useEffect, useState } from 'react';
import { AppPage, Badge, Button, Card, EmptyState, PageHeader } from '../components/common';
import { portfolioApi } from '../api/portfolio';
import type { AssetAllocationPlanItem, AssetRiskDefinitionItem } from '../types/portfolio';

const INPUT_CLASS = 'w-full rounded border bg-transparent px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary';
const CARD_TITLE_CLASS = 'text-lg font-semibold text-foreground';
const CARD_DESC_CLASS = 'text-sm text-secondary-text';

const formatPlanDate = (value: string) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
};

type SolverResult = {
  expectedReturn: number;
  maxDrawdown: number;
  allocation: Record<string, number>;
};

type BadgeVariant = React.ComponentProps<typeof Badge>['variant'];

const AssetAllocationPage: React.FC = () => {
  const [definitions, setDefinitions] = useState<AssetRiskDefinitionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [formData, setFormData] = useState<AssetRiskDefinitionItem[]>([]);
  const [saving, setSaving] = useState(false);
  const [solverInput, setSolverInput] = useState({
    targetReturnMin: '',
    targetReturnMax: '',
    maxDrawdownTolerance: '',
    baseRatioMin: '',
    baseRatioMax: '',
  });
  const [allocationDraft, setAllocationDraft] = useState<Record<string, string>>({});
  const [plans, setPlans] = useState<AssetAllocationPlanItem[]>([]);
  const [planSaving, setPlanSaving] = useState(false);
  const [planActionId, setPlanActionId] = useState<number | null>(null);
  const [planMessage, setPlanMessage] = useState<string | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [solverResult, setSolverResult] = useState<SolverResult | null>(null);
  const [solverError, setSolverError] = useState<string | null>(null);

  useEffect(() => {
    loadDefinitions();
    void loadPlans();
  }, []);

  const loadDefinitions = async () => {
    try {
      setLoading(true);
      const data = await portfolioApi.getRiskDefinitions();
      setDefinitions(data.definitions);
      setFormData(data.definitions);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载风险等级定义失败');
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = () => {
    setFormData(definitions.map(d => ({ ...d })));
    setEditing(true);
  };

  const handleCancel = () => {
    setEditing(false);
    setFormData(definitions.map(d => ({ ...d })));
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      for (const item of formData) {
        await portfolioApi.updateRiskDefinition(item.assetRiskClass, {
          name: item.name,
          expected_return: item.expectedReturn,
          volatility: item.volatility,
          max_drawdown: item.maxDrawdown,
          equity_weight: item.equityWeight,
          description: item.description,
        });
      }
      setEditing(false);
      await loadDefinitions();
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const updateField = (riskClass: string, field: keyof AssetRiskDefinitionItem, value: string | number | null) => {
    setFormData(prev => prev.map(item =>
      item.assetRiskClass === riskClass ? { ...item, [field]: value } : item
    ));
  };

  const updateSolverInput = (field: keyof typeof solverInput, value: string) => {
    setSolverInput(prev => ({ ...prev, [field]: value }));
  };

  const updateAllocationDraft = (riskClass: string, value: string) => {
    setAllocationDraft(prev => ({ ...prev, [riskClass]: value }));
  };

  const loadPlans = async () => {
    try {
      const data = await portfolioApi.listAllocationPlans();
      setPlans(data.plans);
      setPlanError(null);
    } catch (err) {
      setPlanError(err instanceof Error ? err.message : '加载配置计划失败');
    }
  };

  const fetchLatestDefinitions = async () => {
    const data = await portfolioApi.getRiskDefinitions();
    setDefinitions(data.definitions);
    setFormData(data.definitions);
    return data.definitions;
  };

  const calculatePortfolioResult = (allocation: Record<string, number>, sourceDefinitions = definitions) => {
    const result = sourceDefinitions.reduce(
      (sum, item) => {
        const weight = (allocation[item.assetRiskClass] ?? 0) / 100;
        return {
          expectedReturn: sum.expectedReturn + weight * Number(item.expectedReturn ?? 0),
          maxDrawdown: sum.maxDrawdown + weight * Number(item.maxDrawdown ?? 0),
        };
      },
      { expectedReturn: 0, maxDrawdown: 0 },
    );

    setSolverResult({
      ...result,
      allocation,
    });
    setSolverError(null);
  };

  const handleActualPortfolioSolve = async () => {
    try {
      const latestDefinitions = await fetchLatestDefinitions();
      const response = await portfolioApi.listPositions({ costMethod: 'fifo' });
      const totals = response.items.reduce<Record<string, number>>((acc, item) => {
        const riskClass = (item.assetRiskClass || 'R5').toUpperCase();
        acc[riskClass] = (acc[riskClass] || 0) + Number(item.marketValueBase || 0);
        return acc;
      }, {});
      const totalMarketValue = Object.values(totals).reduce((sum, value) => sum + value, 0);

      if (totalMarketValue <= 0) {
        setSolverError('当前实仓市值为空，无法测算');
        return;
      }

      const allocation = Object.fromEntries(
        latestDefinitions.map(item => {
          const value = ((totals[item.assetRiskClass] || 0) / totalMarketValue) * 100;
          return [item.assetRiskClass, Number(value.toFixed(2))];
        }),
      );

      setAllocationDraft(Object.fromEntries(Object.entries(allocation).map(([key, value]) => [key, String(value)])));
      calculatePortfolioResult(allocation, latestDefinitions);
    } catch (err) {
      setSolverError(err instanceof Error ? err.message : '实仓测算失败');
    }
  };

  const parsePercentInput = (value: string, fallback: number) => {
    if (value.trim() === '') return fallback;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed / 100 : fallback;
  };

  const parseOptionalPercentInput = (value: string) => {
    if (value.trim() === '') return undefined;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed / 100 : undefined;
  };

  const getDraftRatio = (riskClass: string) => {
    const parsed = Number(allocationDraft[riskClass] ?? '');
    return Number.isFinite(parsed) ? parsed : 0;
  };

  const handleCreatePlan = async () => {
    const payload = {
      r1Ratio: getDraftRatio('R1'),
      r2Ratio: getDraftRatio('R2'),
      r3Ratio: getDraftRatio('R3'),
      r4Ratio: getDraftRatio('R4'),
      r5Ratio: getDraftRatio('R5'),
    };
    const totalRatio = payload.r1Ratio + payload.r2Ratio + payload.r3Ratio + payload.r4Ratio + payload.r5Ratio;
    if (Math.abs(totalRatio - 100) > 0.05) {
      setPlanError('R1-R5 配置比例合计需为 100%');
      setPlanMessage(null);
      return;
    }

    try {
      setPlanSaving(true);
      const plan = await portfolioApi.createAllocationPlan(payload);
      setPlanMessage(`已生成配置计划 #${plan.id}`);
      setPlanError(null);
      await loadPlans();
    } catch (err) {
      setPlanError(err instanceof Error ? err.message : '生成配置计划失败');
      setPlanMessage(null);
    } finally {
      setPlanSaving(false);
    }
  };

  const handleTogglePlanActive = async (plan: AssetAllocationPlanItem) => {
    try {
      setPlanActionId(plan.id);
      const result = await portfolioApi.activateAllocationPlan(plan.id);
      setPlanMessage(result.isActive ? `配置计划 #${plan.id} 已生效` : `配置计划 #${plan.id} 已取消生效`);
      setPlanError(null);
      await loadPlans();
    } catch (err) {
      setPlanError(err instanceof Error ? err.message : '切换生效状态失败');
      setPlanMessage(null);
    } finally {
      setPlanActionId(null);
    }
  };

  const handleDeletePlan = async (plan: AssetAllocationPlanItem) => {
    try {
      setPlanActionId(plan.id);
      await portfolioApi.deleteAllocationPlan(plan.id);
      setPlanMessage(`配置计划 #${plan.id} 已删除`);
      setPlanError(null);
      await loadPlans();
    } catch (err) {
      setPlanError(err instanceof Error ? err.message : '删除配置计划失败');
      setPlanMessage(null);
    } finally {
      setPlanActionId(null);
    }
  };

  const handleSolveAllocation = () => {
    void solveAllocationWithSlsqp();
  };

  const solveAllocationWithSlsqp = async () => {
    try {
      const result = await portfolioApi.solveAllocation({
        targetReturnMin: parseOptionalPercentInput(solverInput.targetReturnMin),
        targetReturnMax: parseOptionalPercentInput(solverInput.targetReturnMax),
        maxDrawdownTolerance: parseOptionalPercentInput(solverInput.maxDrawdownTolerance),
        baseRatioMin: parseOptionalPercentInput(solverInput.baseRatioMin),
        baseRatioMax: parseOptionalPercentInput(solverInput.baseRatioMax),
      });
      await fetchLatestDefinitions();
      setSolverResult({
        expectedReturn: result.expectedReturn,
        maxDrawdown: result.maxDrawdown,
        allocation: result.allocation,
      });
      setSolverError(null);
      setAllocationDraft(Object.fromEntries(Object.entries(result.allocation).map(([key, value]) => [key, String(value)])));
    } catch {
      await solveAllocationWithLatestDefinitions();
    }
  };

  const solveAllocationWithLatestDefinitions = async () => {
    const latestDefinitions = await fetchLatestDefinitions();
    const sortedDefinitions = [...latestDefinitions].sort((a, b) => a.assetRiskClass.localeCompare(b.assetRiskClass));
    const requiredClasses = ['R1', 'R2', 'R3', 'R4', 'R5'];
    if (sortedDefinitions.length < requiredClasses.length || !requiredClasses.every(code => sortedDefinitions.some(item => item.assetRiskClass === code))) {
      setSolverError('风险等级定义不完整，需包含 R1-R5');
      return;
    }

    const profiles = requiredClasses.map(code => {
      const item = sortedDefinitions.find(def => def.assetRiskClass === code)!;
      return {
        code,
        expectedReturn: Number(item.expectedReturn ?? 0),
        maxDrawdown: Number(item.maxDrawdown ?? 0),
      };
    });

    const rawTargetMin = parsePercentInput(solverInput.targetReturnMin, 0);
    const rawTargetMax = parsePercentInput(solverInput.targetReturnMax, rawTargetMin);
    const targetMin = Math.min(rawTargetMin, rawTargetMax);
    const targetMax = Math.max(rawTargetMin, rawTargetMax);
    const maxDrawdownTolerance = parsePercentInput(solverInput.maxDrawdownTolerance, 1);
    const rawBaseMin = parsePercentInput(solverInput.baseRatioMin, 0);
    const rawBaseMax = parsePercentInput(solverInput.baseRatioMax, 1);
    const baseMin = Math.min(rawBaseMin, rawBaseMax);
    const baseMax = Math.max(rawBaseMin, rawBaseMax);
    const target = targetMax || targetMin;
    const alpha = 1000;
    const beta = 1;

    let best: SolverResult | null = null;
    let bestScore = Number.POSITIVE_INFINITY;

    for (let r1 = 0; r1 <= 100; r1 += 1) {
      for (let r2 = 0; r2 <= 100 - r1; r2 += 1) {
        const baseRatio = (r1 + r2) / 100;
        if (baseRatio < baseMin || baseRatio > baseMax) continue;

        for (let r3 = 0; r3 <= 100 - r1 - r2; r3 += 1) {
          for (let r4 = 0; r4 <= 100 - r1 - r2 - r3; r4 += 1) {
            const r5 = 100 - r1 - r2 - r3 - r4;
            const weights = [r1, r2, r3, r4, r5].map(value => value / 100);
            const expectedReturn = weights.reduce((sum, weight, idx) => sum + weight * profiles[idx].expectedReturn, 0);
            const maxDrawdown = weights.reduce((sum, weight, idx) => sum + weight * profiles[idx].maxDrawdown, 0);
            if (maxDrawdown > maxDrawdownTolerance) continue;

            const targetDistance = expectedReturn < targetMin
              ? targetMin - expectedReturn
              : expectedReturn > targetMax
                ? expectedReturn - targetMax
                : Math.abs(expectedReturn - target);
            const score = alpha * targetDistance ** 2 + beta * (maxDrawdown ** 2);
            if (score < bestScore) {
              bestScore = score;
              best = {
                expectedReturn,
                maxDrawdown,
                allocation: {
                  R1: r1,
                  R2: r2,
                  R3: r3,
                  R4: r4,
                  R5: r5,
                },
              };
            }
          }
        }
      }
    }

    if (!best) {
      setSolverResult(null);
      setSolverError('当前约束下无法求解出可行配置');
      return;
    }

    setSolverResult(best);
    setSolverError(null);
    setAllocationDraft(Object.fromEntries(Object.entries(best.allocation).map(([key, value]) => [key, String(value)])));
  };

  if (loading) {
    return (
      <AppPage>
        <div className="flex h-64 items-center justify-center">
          <p className="text-secondary-text">加载中...</p>
        </div>
      </AppPage>
    );
  }

  if (error && definitions.length === 0) {
    return (
      <AppPage>
        <EmptyState
          title="加载失败"
          description={error}
          action={<Button onClick={loadDefinitions}>重试</Button>}
        />
      </AppPage>
    );
  }

  return (
    <AppPage className="max-w-[1600px] space-y-3">
      <PageHeader
        title="资产配置"
        description="管理资产风险等级定义与配置模拟"
      />

      <div className="space-y-6">
        <div className="grid gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <Card>
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h3 className={CARD_TITLE_CLASS}>资产配置求解器</h3>
                <p className={CARD_DESC_CLASS}>设置约束条件后测算最优配置。</p>
              </div>
            </div>

            <div className="space-y-4">
              <div className="grid grid-cols-[96px_1fr_18px_1fr_20px] items-center gap-2 text-sm">
                <label className="text-secondary-text">目标收益</label>
                <input
                  type="number"
                  value={solverInput.targetReturnMin}
                  onChange={(e) => updateSolverInput('targetReturnMin', e.target.value)}
                  className={INPUT_CLASS}
                  placeholder="下限"
                />
                <span className="text-center text-secondary-text">-</span>
                <input
                  type="number"
                  value={solverInput.targetReturnMax}
                  onChange={(e) => updateSolverInput('targetReturnMax', e.target.value)}
                  className={INPUT_CLASS}
                  placeholder="上限"
                />
                <span className="text-secondary-text">%</span>
              </div>

              <div className="grid grid-cols-[96px_20px_1fr_20px] items-center gap-2 text-sm">
                <label className="text-secondary-text">最高回撤容忍度</label>
                <span className="text-secondary-text">&lt;</span>
                <input
                  type="number"
                  value={solverInput.maxDrawdownTolerance}
                  onChange={(e) => updateSolverInput('maxDrawdownTolerance', e.target.value)}
                  className={INPUT_CLASS}
                  placeholder="最大回撤"
                />
                <span className="text-secondary-text">%</span>
              </div>

              <div className="grid grid-cols-[96px_1fr_18px_1fr_20px] items-center gap-2 text-sm">
                <label className="text-secondary-text">基座比例</label>
                <input
                  type="number"
                  value={solverInput.baseRatioMin}
                  onChange={(e) => updateSolverInput('baseRatioMin', e.target.value)}
                  className={INPUT_CLASS}
                  placeholder="下限"
                />
                <span className="text-center text-secondary-text">-</span>
                <input
                  type="number"
                  value={solverInput.baseRatioMax}
                  onChange={(e) => updateSolverInput('baseRatioMax', e.target.value)}
                  className={INPUT_CLASS}
                  placeholder="上限"
                />
                <span className="text-secondary-text">%</span>
              </div>
              <p className="pl-24 text-xs text-secondary-text">R1 + R2 最低要求</p>

              <div className="rounded-lg border border-border/60 p-4">
                <div className={`${CARD_TITLE_CLASS} mb-3`}>最优方案</div>
                <div className="flex items-center justify-between gap-8 text-sm">
                  <div className="flex items-baseline gap-3">
                    <span className="font-semibold text-foreground">预期收益率</span>
                    <span className="text-2xl font-bold text-foreground">
                      {solverResult ? `${(solverResult.expectedReturn * 100).toFixed(1)}%` : '--%'}
                    </span>
                  </div>
                  <div className="flex items-baseline gap-3">
                    <span className="font-semibold text-foreground">最高回撤</span>
                    <span className="text-2xl font-bold text-foreground">
                      {solverResult ? `${(solverResult.maxDrawdown * 100).toFixed(1)}%` : '--%'}
                    </span>
                  </div>
                </div>
              </div>

              {solverError ? (
                <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400">
                  {solverError}
                </div>
              ) : null}

              <div className="flex items-center justify-between gap-2">
                <Button type="button" onClick={handleSolveAllocation}>开始测算</Button>
                <Button type="button" variant="outline" onClick={handleActualPortfolioSolve}>
                  实仓测算
                </Button>
              </div>
            </div>
          </Card>

          <Card>
            <div className="mb-4">
              <h3 className={CARD_TITLE_CLASS}>配置比例</h3>
              <p className={CARD_DESC_CLASS}>按 R1-R5 输入目标资产配置比例。</p>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="w-20 py-2 text-left font-medium text-secondary-text">分类</th>
                    <th className="py-2 text-left font-medium text-secondary-text">名称</th>
                    <th className="w-32 py-2 text-left font-medium text-secondary-text">配置比例</th>
                  </tr>
                </thead>
                <tbody>
                  {definitions.map((item) => (
                    <tr key={item.assetRiskClass} className="border-b border-border/50">
                      <td className="py-2">
                        <Badge variant={getRiskBadgeVariant(item.assetRiskClass)} className="!px-1.5 !py-0 text-[11px]">
                          {item.assetRiskClass}
                        </Badge>
                      </td>
                      <td className="py-2 text-foreground">{item.name}</td>
                      <td className="py-2">
                        <div className="flex items-center gap-2">
                          <input
                            type="number"
                            min="0"
                            max="100"
                            value={allocationDraft[item.assetRiskClass] ?? ''}
                            onChange={(e) => updateAllocationDraft(item.assetRiskClass, e.target.value)}
                            className={INPUT_CLASS}
                            placeholder="0"
                          />
                          <span className="text-secondary-text">%</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-4 flex justify-end">
              <Button type="button" variant="outline" onClick={handleCreatePlan} disabled={planSaving}>
                {planSaving ? '生成中...' : '生成计划'}
              </Button>
            </div>
          </Card>
        </div>

        <Card>
          <div className="mb-4">
            <div>
              <h3 className={CARD_TITLE_CLASS}>配置计划管理</h3>
              <p className={CARD_DESC_CLASS}>点击圆形按钮切换生效状态；同一时间只允许一个计划生效。</p>
            </div>
          </div>

          {planError ? (
            <div className="mb-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400">
              {planError}
            </div>
          ) : null}
          {planMessage ? (
            <div className="mb-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-400">
              {planMessage}
            </div>
          ) : null}

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="w-24 py-2 text-left font-medium text-secondary-text">状态</th>
                  <th className="w-44 py-2 text-left font-medium text-secondary-text">生成日期</th>
                  <th className="py-2 text-right font-medium text-secondary-text">R1</th>
                  <th className="py-2 text-right font-medium text-secondary-text">R2</th>
                  <th className="py-2 text-right font-medium text-secondary-text">R3</th>
                  <th className="py-2 text-right font-medium text-secondary-text">R4</th>
                  <th className="py-2 text-right font-medium text-secondary-text">R5</th>
                  <th className="w-28 py-2 text-right font-medium text-secondary-text">操作</th>
                </tr>
              </thead>
              <tbody>
                {plans.length > 0 ? plans.map((plan) => (
                  <tr key={plan.id} className="border-b border-border/50">
                    <td className="py-2">
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${plan.isActive ? 'bg-emerald-500/10 text-emerald-400' : 'bg-slate-500/10 text-secondary-text'}`}>
                        {plan.isActive ? '生效中' : '未生效'}
                      </span>
                    </td>
                    <td className="py-2 text-foreground">{formatPlanDate(plan.generatedAt)}</td>
                    <td className="py-2 text-right text-foreground">{plan.r1Ratio.toFixed(2)}%</td>
                    <td className="py-2 text-right text-foreground">{plan.r2Ratio.toFixed(2)}%</td>
                    <td className="py-2 text-right text-foreground">{plan.r3Ratio.toFixed(2)}%</td>
                    <td className="py-2 text-right text-foreground">{plan.r4Ratio.toFixed(2)}%</td>
                    <td className="py-2 text-right text-foreground">{plan.r5Ratio.toFixed(2)}%</td>
                    <td className="py-2">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          type="button"
                          aria-label={plan.isActive ? '取消生效' : '设为生效'}
                          title={plan.isActive ? '取消生效' : '设为生效'}
                          onClick={() => void handleTogglePlanActive(plan)}
                          disabled={planActionId === plan.id}
                          className={`h-7 w-7 rounded-full border transition disabled:opacity-50 ${plan.isActive ? 'border-emerald-400 bg-emerald-500 text-white shadow-sm shadow-emerald-500/30' : 'border-border bg-transparent hover:border-emerald-400 hover:bg-emerald-500/10'}`}
                        >
                          {plan.isActive ? '●' : ''}
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleDeletePlan(plan)}
                          disabled={planActionId === plan.id}
                          className="rounded border border-red-500/30 px-2 py-1 text-xs text-red-400 hover:bg-red-500/10 disabled:opacity-50"
                        >
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={8} className="py-6 text-center text-sm text-secondary-text">暂无配置计划</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        {/* 卡片 1: 资产分类定义 */}
        <Card>
          <div className="mb-4 flex items-center justify-between gap-3">
            <h3 className={CARD_TITLE_CLASS}>资产分类定义</h3>
            <div className="flex gap-2">
              {editing ? (
                <>
                  <Button onClick={handleSave} disabled={saving}>
                    {saving ? '保存中...' : '保存'}
                  </Button>
                  <Button variant="outline" onClick={handleCancel} disabled={saving}>
                    取消
                  </Button>
                </>
              ) : (
                <Button variant="outline" onClick={handleEdit}>
                  修改
                </Button>
              )}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="w-20 py-2 text-left font-medium text-secondary-text">风险等级</th>
                  <th className="w-32 py-2 text-left font-medium text-secondary-text">名称</th>
                  <th className="w-28 py-2 text-left font-medium text-secondary-text">预期回报率</th>
                  <th className="w-28 py-2 text-left font-medium text-secondary-text">波动率</th>
                  <th className="w-28 py-2 text-left font-medium text-secondary-text">最大回撤</th>
                  <th className="w-28 py-2 text-left font-medium text-secondary-text">权益权重</th>
                  <th className="py-2 text-left font-medium text-secondary-text">描述</th>
                </tr>
              </thead>
              <tbody>
                {formData.map((item) => (
                  <tr key={item.assetRiskClass} className="border-b border-border/50">
                    <td className="py-2">
                      <Badge variant={getRiskBadgeVariant(item.assetRiskClass)} className="!px-1.5 !py-0 text-[11px]">
                        {item.assetRiskClass}
                      </Badge>
                    </td>
                    <td className="py-2">
                      {editing ? (
                        <input
                          type="text"
                          value={item.name}
                          onChange={(e) => updateField(item.assetRiskClass, 'name', e.target.value)}
                          className={INPUT_CLASS}
                        />
                      ) : (
                        <span className="text-foreground">{item.name}</span>
                      )}
                    </td>
                    <td className="py-2">
                      {editing ? (
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          max="1"
                          value={item.expectedReturn ?? ''}
                          onChange={(e) => updateField(item.assetRiskClass, 'expectedReturn', e.target.value === '' ? null : parseFloat(e.target.value))}
                          className={INPUT_CLASS}
                        />
                      ) : (
                        <span className="text-foreground">{item.expectedReturn ? `${(item.expectedReturn * 100).toFixed(0)}%` : '-'}</span>
                      )}
                    </td>
                    <td className="py-2">
                      {editing ? (
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          max="1"
                          value={item.volatility ?? ''}
                          onChange={(e) => updateField(item.assetRiskClass, 'volatility', e.target.value === '' ? null : parseFloat(e.target.value))}
                          className={INPUT_CLASS}
                        />
                      ) : (
                        <span className="text-foreground">{item.volatility ? `${(item.volatility * 100).toFixed(0)}%` : '-'}</span>
                      )}
                    </td>
                    <td className="py-2">
                      {editing ? (
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          max="1"
                          value={item.maxDrawdown ?? ''}
                          onChange={(e) => updateField(item.assetRiskClass, 'maxDrawdown', e.target.value === '' ? null : parseFloat(e.target.value))}
                          className={INPUT_CLASS}
                        />
                      ) : (
                        <span className="text-foreground">{item.maxDrawdown ? `${(item.maxDrawdown * 100).toFixed(0)}%` : '-'}</span>
                      )}
                    </td>
                    <td className="py-2">
                      {editing ? (
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          max="1"
                          value={item.equityWeight}
                          onChange={(e) => updateField(item.assetRiskClass, 'equityWeight', e.target.value === '' ? 0 : parseFloat(e.target.value))}
                          className={INPUT_CLASS}
                        />
                      ) : (
                        <span className="text-foreground">{(item.equityWeight * 100).toFixed(0)}%</span>
                      )}
                    </td>
                    <td className="py-2">
                      {editing ? (
                        <input
                          type="text"
                          value={item.description ?? ''}
                          onChange={(e) => updateField(item.assetRiskClass, 'description', e.target.value)}
                          className={INPUT_CLASS}
                        />
                      ) : (
                        <span className="text-secondary-text">{item.description || '-'}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

      </div>
    </AppPage>
  );
};

const getRiskBadgeVariant = (riskClass: string): BadgeVariant => {
  if (riskClass === 'R5' || riskClass === 'R4') return 'danger';
  if (riskClass === 'R3' || riskClass === 'R2') return 'warning';
  return 'success';
};

export default AssetAllocationPage;
