import { cn } from '../utils/cn';
import type { MarketEnvironment } from '../api/market';

const COLOR_MAP: Record<string, { bg: string; border: string; text: string; dot: string }> = {
  green: {
    bg: 'bg-green-50',
    border: 'border-green-200',
    text: 'text-green-700',
    dot: 'bg-green-500',
  },
  yellow: {
    bg: 'bg-yellow-50',
    border: 'border-yellow-200',
    text: 'text-yellow-700',
    dot: 'bg-yellow-500',
  },
  red: {
    bg: 'bg-red-50',
    border: 'border-red-200',
    text: 'text-red-700',
    dot: 'bg-red-500',
  },
  gray: {
    bg: 'bg-gray-50',
    border: 'border-gray-200',
    text: 'text-gray-500',
    dot: 'bg-gray-400',
  },
};

export const TrafficLightLabel: React.FC<{ env: MarketEnvironment; className?: string }> = ({ env, className }) => {
  const colors = COLOR_MAP[env.color] ?? COLOR_MAP.gray;

  return (
    <div
      className={cn(
        'flex flex-col items-center gap-1.5 px-1 py-3 rounded-lg border',
        colors.bg,
        colors.border,
        className
      )}
    >
      <div className="flex items-center gap-3">
        {/* 趋势位灯 */}
        <div className="flex flex-col items-center gap-1">
          <div
            className={cn(
              'w-3 h-3 rounded-full shadow-sm',
              env.trend === 'bullish' ? 'bg-green-500' : env.trend === 'bearish' ? 'bg-red-500' : 'bg-yellow-500'
            )}
          />
          <span className="text-[9px] text-gray-500">趋势</span>
        </div>
        {/* 波动态灯 */}
        <div className="flex flex-col items-center gap-1">
          <div
            className={cn(
              'w-3 h-3 rounded-full shadow-sm',
              env.volatility === 'controlled' ? 'bg-green-500' : 'bg-red-500'
            )}
          />
          <span className="text-[9px] text-gray-500">波动</span>
        </div>
        {/* 支撑距离灯 */}
        <div className="flex flex-col items-center gap-1">
          <div
            className={cn(
              'w-3 h-3 rounded-full shadow-sm',
              env.supportStatus === 'safe' ? 'bg-green-500' : 'bg-red-500'
            )}
          />
          <span className="text-[9px] text-gray-500">支撑</span>
        </div>
      </div>
      <div className={cn('text-xs font-semibold mt-1', colors.text)}>{env.label}</div>
    </div>
  );
};
