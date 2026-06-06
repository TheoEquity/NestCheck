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

const formatPlanMetric = (value?: number | null) => (
  value == null ? '--' : `${(value * 100).toFixed(1)}%`
);

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
    opportunityRatioMin: '',
    opportunityRatioMax: '',
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

      applyAllocationDraft(allocation);
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

  const roundAllocationForDraft = (allocation: Record<string, number>, opportunityMax?: number) => {
    const orderedClasses = ['R1', 'R2', 'R3', 'R4', 'R5'];
    const roundedEntries = orderedClasses.map(code => [code, Math.round(allocation[code] ?? 0)] as [string, number]);
    const total = roundedEntries.reduce((sum, [, value]) => sum + value, 0);

    if (roundedEntries.length > 0 && total !== 100) {
      const adjustIndex = roundedEntries.reduce((bestIndex, [code], index) => {
        const value = allocation[code] ?? 0;
        const currentFraction = Math.abs(value - Math.round(value));
        const bestCode = roundedEntries[bestIndex][0];
        const bestValue = allocation[bestCode] ?? 0;
        const bestFraction = Math.abs(bestValue - Math.round(bestValue));
        return currentFraction > bestFraction ? index : bestIndex;
      }, 0);
      roundedEntries[adjustIndex] = [roundedEntries[adjustIndex][0], Math.max(0, roundedEntries[adjustIndex][1] + 100 - total)];
    }

    if (opportunityMax != null) {
      const opportunityLimit = Math.floor(opportunityMax * 100);
      const r4Index = orderedClasses.indexOf('R4');
      const r5Index = orderedClasses.indexOf('R5');
      const opportunityTotal = roundedEntries[r4Index][1] + roundedEntries[r5Index][1];
      let overflow = Math.max(0, opportunityTotal - opportunityLimit);

      if (overflow > 0) {
        const r5Reduction = Math.min(roundedEntries[r5Index][1], overflow);
        roundedEntries[r5Index][1] -= r5Reduction;
        overflow -= r5Reduction;
        const r4Reduction = Math.min(roundedEntries[r4Index][1], overflow);
        roundedEntries[r4Index][1] -= r4Reduction;

        const reduced = r5Reduction + r4Reduction;
        const receiverIndex = ['R1', 'R2', 'R3'].reduce((bestIndex, code) => {
          const index = orderedClasses.indexOf(code);
          return roundedEntries[index][1] >= roundedEntries[bestIndex][1] ? index : bestIndex;
        }, 0);
        roundedEntries[receiverIndex][1] += reduced;
      }
    }

    return Object.fromEntries(roundedEntries);
  };

  const applyAllocationDraft = (allocation: Record<string, number>, opportunityMax?: number) => {
    const roundedAllocation = roundAllocationForDraft(allocation, opportunityMax);
    setAllocationDraft(Object.fromEntries(Object.entries(roundedAllocation).map(([key, value]) => [key, String(value)])));
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

  const handleManualAllocationEvaluate = () => {
    const allocation = Object.fromEntries(
      definitions.map(item => [item.assetRiskClass, getDraftRatio(item.assetRiskClass)]),
    );
    const totalRatio = Object.values(allocation).reduce((sum, value) => sum + value, 0);
    if (Math.abs(totalRatio - 100) > 0.05) {
      setSolverError('R1-R5 配置比例合计需为 100%');
      return;
    }

    calculatePortfolioResult(allocation);
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
        opportunityRatioMin: parseOptionalPercentInput(solverInput.opportunityRatioMin),
        opportunityRatioMax: parseOptionalPercentInput(solverInput.opportunityRatioMax),
      });
      await fetchLatestDefinitions();
      setSolverResult({
        expectedReturn: result.expectedReturn,
        maxDrawdown: result.maxDrawdown,
        allocation: result.allocation,
      });
      setSolverError(null);
      applyAllocationDraft(result.allocation, parseOptionalPercentInput(solverInput.opportunityRatioMax));
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
    const rawOpportunityMin = parsePercentInput(solverInput.opportunityRatioMin, 0);
    const rawOpportunityMax = parsePercentInput(solverInput.opportunityRatioMax, 1);
    const opportunityMin = Math.min(rawOpportunityMin, rawOpportunityMax);
    const opportunityMax = Math.max(rawOpportunityMin, rawOpportunityMax);
    const target = targetMax || targetMin;
    const alpha = 1000;
    const beta = 1;

    const searchState: { best: SolverResult | null; bestScore: number } = {
      best: null,
      bestScore: Number.POSITIVE_INFINITY,
    };

    const evaluateAllocation = (r1: number, r2: number, r3: number, r4: number) => {
      const rounded = [r1, r2, r3, r4].map(value => Number(value.toFixed(2)));
      const r5 = Number((100 - rounded[0] - rounded[1] - rounded[2] - rounded[3]).toFixed(2));
      if (r5 < -0.001) return;

      const baseRatio = rounded[0] / 100;
      if (baseRatio < baseMin || baseRatio > baseMax) return;
      const opportunityRatio = (rounded[3] + r5) / 100;
      if (opportunityRatio < opportunityMin || opportunityRatio > opportunityMax) return;

      const weights = [...rounded, r5].map(value => value / 100);
      const expectedReturn = weights.reduce((sum, weight, idx) => sum + weight * profiles[idx].expectedReturn, 0);
      const maxDrawdown = weights.reduce((sum, weight, idx) => sum + weight * profiles[idx].maxDrawdown, 0);
      if (maxDrawdown > maxDrawdownTolerance) return;

      const targetDistance = expectedReturn < targetMin
        ? targetMin - expectedReturn
        : expectedReturn > targetMax
          ? expectedReturn - targetMax
          : Math.abs(expectedReturn - target);
      const score = alpha * targetDistance ** 2 + beta * (maxDrawdown ** 2);
      if (score < searchState.bestScore) {
        searchState.bestScore = score;
        searchState.best = {
          expectedReturn,
          maxDrawdown,
          allocation: {
            R1: rounded[0],
            R2: rounded[1],
            R3: rounded[2],
            R4: rounded[3],
            R5: r5,
          },
        };
      }
    };

    const searchRange = (step: number, ranges?: Record<'R1' | 'R2' | 'R3' | 'R4', [number, number]>) => {
      const r1Start = ranges ? ranges.R1[0] : 0;
      const r1End = ranges ? ranges.R1[1] : 100;
      const r2Start = ranges ? ranges.R2[0] : 0;
      const r2End = ranges ? ranges.R2[1] : 100;
      const r3Start = ranges ? ranges.R3[0] : 0;
      const r3End = ranges ? ranges.R3[1] : 100;
      const r4Start = ranges ? ranges.R4[0] : 0;
      const r4End = ranges ? ranges.R4[1] : 100;

      for (let r1 = r1Start; r1 <= r1End; r1 += step) {
        for (let r2 = r2Start; r2 <= Math.min(r2End, 100 - r1); r2 += step) {
          for (let r3 = r3Start; r3 <= Math.min(r3End, 100 - r1 - r2); r3 += step) {
            for (let r4 = r4Start; r4 <= Math.min(r4End, 100 - r1 - r2 - r3); r4 += step) {
              evaluateAllocation(r1, r2, r3, r4);
            }
          }
        }
      }
    };

    searchRange(1);
    if (searchState.best) {
      const allocation = searchState.best.allocation;
      const refineRanges: Record<'R1' | 'R2' | 'R3' | 'R4', [number, number]> = {
        R1: [Math.max(0, allocation.R1 - 1), Math.min(100, allocation.R1 + 1)],
        R2: [Math.max(0, allocation.R2 - 1), Math.min(100, allocation.R2 + 1)],
        R3: [Math.max(0, allocation.R3 - 1), Math.min(100, allocation.R3 + 1)],
        R4: [Math.max(0, allocation.R4 - 1), Math.min(100, allocation.R4 + 1)],
      };
      searchRange(0.25, refineRanges);
    }

    if (!searchState.best) {
      setSolverResult(null);
      setSolverError('当前约束下无法求解出可行配置');
      return;
    }

    setSolverResult(searchState.best);
    setSolverError(null);
    applyAllocationDraft(searchState.best.allocation, opportunityMax);
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
                <label className="text-secondary-text">最大回撤</label>
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
              <p className="pl-24 text-xs text-secondary-text">R1 范围约束；主题仓为 R2 + R3</p>

              <div className="grid grid-cols-[96px_1fr_18px_1fr_20px] items-center gap-2 text-sm">
                <label className="text-secondary-text">机会仓比例</label>
                <input
                  type="number"
                  value={solverInput.opportunityRatioMin}
                  onChange={(e) => updateSolverInput('opportunityRatioMin', e.target.value)}
                  className={INPUT_CLASS}
                  placeholder="下限"
                />
                <span className="text-center text-secondary-text">-</span>
                <input
                  type="number"
                  value={solverInput.opportunityRatioMax}
                  onChange={(e) => updateSolverInput('opportunityRatioMax', e.target.value)}
                  className={INPUT_CLASS}
                  placeholder="上限"
                />
                <span className="text-secondary-text">%</span>
              </div>
              <p className="pl-24 text-xs text-secondary-text">R4 + R5 范围约束</p>

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

          <Card className="flex h-full flex-col">
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

            <div className="mt-auto flex justify-between gap-2 pt-4">
              <Button type="button" onClick={handleManualAllocationEvaluate}>
                倒算回撤收益
              </Button>
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
                  <th className="py-2 text-right font-medium text-secondary-text">预期收益</th>
                  <th className="py-2 text-right font-medium text-secondary-text">最高回撤</th>
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
                    <td className="py-2 text-right text-foreground">{Math.round(plan.r1Ratio)}%</td>
                    <td className="py-2 text-right text-foreground">{Math.round(plan.r2Ratio)}%</td>
                    <td className="py-2 text-right text-foreground">{Math.round(plan.r3Ratio)}%</td>
                    <td className="py-2 text-right text-foreground">{Math.round(plan.r4Ratio)}%</td>
                    <td className="py-2 text-right text-foreground">{Math.round(plan.r5Ratio)}%</td>
                    <td className="py-2 text-right text-foreground">{formatPlanMetric(plan.expectedReturn)}</td>
                    <td className="py-2 text-right text-foreground">{formatPlanMetric(plan.maxDrawdown)}</td>
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
                    <td colSpan={10} className="py-6 text-center text-sm text-secondary-text">暂无配置计划</td>
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
