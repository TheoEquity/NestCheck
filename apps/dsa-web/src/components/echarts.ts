import * as echarts from 'echarts/core';
import { BarChart, GaugeChart, HeatmapChart, LineChart, RadarChart } from 'echarts/charts';
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  RadarComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { ECharts, EChartsCoreOption, EChartsType } from 'echarts/core';

echarts.use([
  BarChart,
  GaugeChart,
  HeatmapChart,
  LineChart,
  RadarChart,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  RadarComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
]);

export { echarts };
export type { ECharts, EChartsCoreOption, EChartsType };
