import React, { useMemo } from 'react';
import { LineChart, Line, ResponsiveContainer } from 'recharts';
import type { KLineData } from '../types/stocks';

interface MiniSparklineProps {
  data: KLineData[];
  color?: string;
  height?: number;
}

export const MiniSparkline: React.FC<MiniSparklineProps> = ({
  data,
  color = '#22c55e',
  height = 40,
}) => {
  const chartData = useMemo(() => {
    if (!data || data.length === 0) return [];

    return data.map((item) => ({
      time: item.date,
      price: item.close,
    }));
  }, [data]);

  if (!chartData || chartData.length === 0) {
    return (
      <div
        style={{
          height: `${height}px`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#9ca3af',
          fontSize: '10px',
        }}
      >
        暂无数据
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData}>
        <Line
          type="monotone"
          dataKey="price"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
};
