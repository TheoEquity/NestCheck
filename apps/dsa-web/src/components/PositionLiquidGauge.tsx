import React, { useMemo } from 'react';
import { type RiskRadarResponse } from '../api/market';

interface PositionLiquidGaugeProps {
  data: RiskRadarResponse | null;
  /** Current actual portfolio equity ratio (0.0–1.0), rendered as dotted line */
  currentRatio?: number | null;
}

/** 根据 6 项雷达指标计算建议权益仓位 (加权 + 门限机制) */
function calculateEquityPosition(scores: Record<string, number>): { percent: number; status: string; finalRisk: number } {
  // 核心三要素 (0-1)
  const S_market = Math.max(scores.volatility, scores.drawdown) / 100;
  const S_corr = scores.correlation / 100;
  const S_spread = scores.spread / 100;

  // 调节器 (0-1)
  const R_fx = scores.fx / 100;
  const R_val = scores.valuation / 100;

  // 加权合成
  const core_risk = 0.40 * S_market + 0.35 * S_corr + 0.25 * S_spread;
  const adjusted_risk = core_risk * (1 + 0.15 * R_fx) + 0.10 * R_val;
  const final_risk = Math.min(adjusted_risk, 1.0);

  // 硬性门限（保命逻辑）
  const FORCE_DEFENSE = (
    scores.correlation >= 75 ||
    scores.spread >= 80 ||
    (scores.volatility >= 80 && scores.drawdown >= 60)
  );

  let target_ratio: number;
  if (FORCE_DEFENSE) {
    target_ratio = 0.30;
  } else if (final_risk < 0.25) {
    target_ratio = 0.90;
  } else if (final_risk < 0.45) {
    target_ratio = 0.80;
  } else if (final_risk < 0.65) {
    target_ratio = 0.60;
  } else if (final_risk < 0.85) {
    target_ratio = 0.40;
  } else {
    target_ratio = 0.20;
  }

  const percent = Math.round(target_ratio * 100);
  let status = '计算中';
  if (FORCE_DEFENSE) status = '强制防御';
  else if (percent >= 90) status = '高确信进攻';
  else if (percent >= 80) status = '中性偏多';
  else if (percent >= 60) status = '中性保守';
  else if (percent >= 40) status = '谨慎防御';
  else status = '极度保守';

  return { percent, status, finalRisk: Math.round(final_risk * 100) };
}

export const PositionLiquidGauge: React.FC<PositionLiquidGaugeProps> = ({ data, currentRatio }) => {
  const gaugeData = useMemo(() => {
    if (!data || data.error) {
      return { ratio: 0.5, percent: 50, color: '#a3a3a3', status: '计算中...', rawScore: 0, isValid: false };
    }

    const scores = {
      volatility: data.volatility ?? 50,
      drawdown: data.drawdown ?? 50,
      correlation: data.correlation ?? 50,
      spread: data.spread ?? 50,
      fx: data.fx ?? 50,
      valuation: data.valuation ?? 50,
    };

    const info = calculateEquityPosition(scores);
    const ratio = info.percent / 100;

    // 颜色映射基于建议仓位 (水位越低越危险/颜色越红)
    let color = '#eab308';
    if (info.percent >= 80) color = '#22c55e';
    else if (info.percent >= 60) color = '#eab308';
    else if (info.percent >= 40) color = '#f97316';
    else color = '#ef4444';

    return {
      ratio,
      percent: info.percent,
      status: info.status,
      rawScore: info.finalRisk,
      color,
      isValid: true,
    };
  }, [data]);

  // Current portfolio equity ratio (0-1) as percentage
  const currentPercent = currentRatio != null ? Math.round(currentRatio * 100) : null;

  if (!data) return null;

  return (
    <>
      {/* 水球主区域 */}
      <div className="flex items-center justify-center" style={{ height: 220 }}>
        <div className="relative w-44 h-44 rounded-full border-2 border-border overflow-hidden shadow-xl shrink-0"
          style={{ background: 'linear-gradient(180deg, #1d4ed8 0%, #1e3a5f 60%, #0c1929 100%)' }}
        >
          {/* 水位 */}
          <div
            className="absolute bottom-0 left-0 right-0 transition-all duration-1000 ease-out"
            style={{ height: `${gaugeData.ratio * 100}%`, backgroundColor: gaugeData.color, opacity: 0.85 }}
          />
          {/* 水面高光 */}
          <div
            className="absolute left-0 right-0 h-[2px] z-5 transition-all duration-1000 ease-out"
            style={{ bottom: `${gaugeData.ratio * 100}%`, backgroundColor: 'rgba(255,255,255,0.35)' }}
          />
          {/* 上方淡蓝色水雾 */}
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              background: 'linear-gradient(180deg, rgba(59,130,246,0.12) 0%, transparent 50%)',
            }}
          />
          {/* 当前持仓水位虚线 */}
          {currentPercent != null && (
            <div
              className="absolute left-0 right-0 z-20 border-t-[3px] border-dashed border-white/70"
              style={{ bottom: `${currentPercent}%` }}
              title={`当前持仓水位 ${currentPercent}%`}
            />
          )}
          {/* 当前持仓水位百分比标签 */}
          {currentPercent != null && (
            <div
              className="absolute right-3 z-20 text-[10px] font-bold text-white/80 bg-black/50 px-1 rounded"
              style={{ bottom: `${Math.min(currentPercent + 1, 95)}%` }}
            >
              {currentPercent}%
            </div>
          )}
          {/* 内部文字 */}
          <div className="absolute inset-0 flex flex-col items-center justify-center z-10">
            <span className="text-4xl font-bold text-white drop-shadow-md">{gaugeData.percent}%</span>
            <span className="text-[10px] text-white/90 mt-1 bg-black/40 px-2 py-0.5 rounded-full font-medium">
              {gaugeData.status}
            </span>
          </div>
        </div>
      </div>
      
      {/* 底部统一解读 */}
      <div className="mt-1 border-t border-border/30 px-1 pt-1.5 text-[11px] leading-snug text-secondary-text">
        <div>
          水位建议：雷达分 <span className="text-foreground font-medium">{gaugeData.rawScore}</span> 分。
          {gaugeData.isValid ? (
            <>建议 <span className="text-foreground font-medium">{gaugeData.percent}%</span> 仓位（{gaugeData.status}）
            {currentPercent != null ? <>，当前持仓 <span className="text-foreground font-medium">{currentPercent}%</span></> : null}。</>
          ) : (
            <>数据待完善...</>
          )}
        </div>
      </div>
    </>
  );
};
