import type React from 'react';
import { useState, useEffect } from 'react';
import { Button, Loading } from '../../components/common';
import { schedulerApi, type SchedulerTask } from '../../api/scheduler';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { CheckCircle, XCircle, AlertTriangle, RefreshCw, PlayCircle, Database } from 'lucide-react';

/* ───── 内置只读任务列表（后台已托管，前端不允许改动） ───── */
const READONLY_TASK_KEYS = new Set(['scheduled_task', 'market_cache_refresh', 'seasonality_cache_refresh']);

/* ───── 类型定义 ───── */

interface TaskRecord {
  id: number;
  taskKey: string;
  name: string;
  description: string;
  scheduleType: string;
  scheduleTime: string | null;
  intervalSeconds: number | null;
  enabled: boolean;
  successRate: string | null;
  totalRuns: number;
  lastRun: string | null;
  lastStatus: string | null;
  nextRun: string;
}

/* ───── 工具函数 ───── */

const formatInterval = (secs: number | null): string => {
  if (!secs) return '-';
  if (secs < 60) return `每 ${secs} 秒`;
  if (secs < 3600) return `每 ${Math.floor(secs / 60)} 分钟`;
  return `每 ${(secs / 3600).toFixed(1)} 小时`;
};

const getStatusIcon = (status: string) => {
  switch (status) {
    case 'success':
      return <span className="text-success"><CheckCircle className="w-4 h-4" /></span>;
    case 'failed':
      return <span className="text-danger"><XCircle className="w-4 h-4" /></span>;
    case 'skipped':
      return <span className="text-warning"><AlertTriangle className="w-4 h-4" /></span>;
    default:
      return <span className="text-muted-text">-</span>;
  }
};

/* ───── 主组件 ───── */

export const SchedulerTasksPanel: React.FC = () => {
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggerLoading, setTriggerLoading] = useState<string | null>(null);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [triggerMessage, setTriggerMessage] = useState<string | null>(null);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editSchedule, setEditSchedule] = useState('');
  const [toggleLoading, setToggleLoading] = useState<string | null>(null);
  const [initMarketLoading, setInitMarketLoading] = useState(false);

  const loadData = async () => {
    try {
      const tasksRes = await schedulerApi.getTasks();
      setTasks(tasksRes.map((t: SchedulerTask) => ({
        id: t.id || 0,
        taskKey: t.taskName,
        name: t.taskName,
        description: '-',
        scheduleType: 'daily',
        scheduleTime: null,
        intervalSeconds: null,
        enabled: true,
        successRate: null,
        totalRuns: 0,
        lastRun: null,
        lastStatus: null,
        nextRun: '-',
        ...t,
      })));
      setError(null);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const handleTrigger = async (taskKey: string) => {
    setTriggerLoading(taskKey);
    setTriggerMessage(null);
    try {
      const result = await schedulerApi.triggerTask(taskKey);
      if (result.status === 'success') {
        setTriggerMessage(`任务执行成功，耗时 ${result.durationMs || 0}ms`);
      } else if (result.status === 'skipped') {
        setTriggerMessage(result.message || '任务已跳过');
      } else if (result.status === 'timeout') {
        setTriggerMessage(result.message || '任务执行超时');
      } else {
        setTriggerMessage(result.error || result.message || '任务执行失败');
      }
      setTimeout(() => void loadData(), 1500);
    } catch {
      setTriggerMessage('触发失败，请查看控制台错误信息');
    } finally {
      setTriggerLoading(null);
    }
  };

  const handleToggle = async (taskKey: string, currentEnabled: boolean) => {
    setToggleLoading(taskKey);
    try {
      await schedulerApi.updateTaskStatus(taskKey, { enabled: !currentEnabled });
      await loadData();
    } catch {
      // error already shown via loadData or can be handled separately
    } finally {
      setToggleLoading(null);
    }
  };

  const handleScheduleSave = async (taskKey: string) => {
    try {
      const timeVal = editSchedule.trim();
      if (timeVal && !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(timeVal)) {
        setTriggerMessage('时间格式无效，应为 HH:MM');
        return;
      }
      await schedulerApi.updateTaskSchedule(taskKey, { schedule_time: timeVal || null });
      setEditingKey(null);
      setEditSchedule('');
      setTriggerMessage('定时配置已更新（需重启服务生效）');
      setTimeout(() => void loadData(), 500);
    } catch {
      setTriggerMessage('更新失败');
    }
  };

  const handleInitMarketData = async () => {
    setInitMarketLoading(true);
    setTriggerMessage(null);
    try {
      const res = await schedulerApi.initMarketData();
      setTriggerMessage(res.message || '初始化任务已启动，正在同步 5 年历史数据...');
    } catch {
      setTriggerMessage('启动大盘初始化失败');
    } finally {
      setInitMarketLoading(false);
    }
  };

  if (loading) {
    return <div className="flex justify-center py-12"><Loading label="加载定时任务..." /></div>;
  }

  if (error) {
    return (
      <div className="rounded-lg border bg-card/50 p-6">
        <p className="text-danger">加载失败：{error.message}</p>
        <Button className="mt-3" size="sm" variant="outline" onClick={() => void loadData()}>重试</Button>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {triggerMessage && (
        <div className="rounded-lg border border-cyan/30 bg-cyan/5 p-3 text-xs text-cyan">
          {triggerMessage}
          <button className="ml-3 underline" onClick={() => setTriggerMessage(null)}>关闭</button>
        </div>
      )}

      {/* 快捷操作：大盘历史数据初始化 */}
      <div className="rounded-lg border border-border/40 bg-card/30 p-4 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-foreground">大盘与情绪数据初始化</h3>
          <p className="text-xs text-muted-text mt-1">
            首次部署或图表历史数据缺失时，手动触发全量拉取过去 5 年的大盘指数与风险指标数据。
          </p>
        </div>
        <Button 
          size="sm" 
          variant="outline" 
          onClick={handleInitMarketData} 
          disabled={initMarketLoading}
          className="flex items-center gap-1.5"
        >
          <Database className="w-4 h-4" />
          {initMarketLoading ? '同步中...' : '初始化大盘数据'}
        </Button>
      </div>

      {/* 表头 */}
      <div className="grid grid-cols-12 gap-4 px-4 py-2 text-xs font-semibold uppercase tracking-[0.08em] text-muted-text">
        <div className="col-span-1">ID</div>
        <div className="col-span-2">名称</div>
        <div className="col-span-2">作用说明</div>
        <div className="col-span-2">执行时间</div>
        <div className="col-span-1">频率</div>
        <div className="col-span-1">成功率</div>
        <div className="col-span-1 text-center">状态</div>
        <div className="col-span-1 text-center">操作</div>
        <div className="col-span-1 text-center">启用</div>
      </div>

      {/* 任务行 */}
      {tasks.map((task) => {
        const isEditing = editingKey === task.taskKey;
        const displayTime = task.scheduleTime
          ? task.scheduleTime
          : (task.nextRun !== '-' && task.nextRun.startsWith('每日') ? task.nextRun.replace('每日 ', '') : '-');

        return (
          <div
            key={task.taskKey}
            className={`grid grid-cols-12 gap-4 rounded-lg border bg-card/50 px-4 py-4 text-sm items-start transition-colors hover:bg-card/80 ${
              task.enabled ? '' : 'opacity-50'
            }`}
          >
            {/* ID */}
            <div className="col-span-1 truncate font-mono text-xs text-muted-text" title={task.taskKey}>
              {task.taskKey}
            </div>

            {/* 名称 */}
            <div className="col-span-2 font-semibold text-foreground">{task.name}</div>

            {/* 作用说明 */}
            <div className="col-span-2 text-xs leading-5 text-secondary-text" title={task.description}>
              {task.description}
            </div>

            {/* 执行时间（可编辑） */}
            <div className="col-span-2 text-xs text-foreground">
              {isEditing ? (
                <div className="flex gap-1 items-center">
                  <input
                    type="text"
                    className="w-20 rounded border border-border/60 bg-background px-2 py-1 text-xs font-mono"
                    placeholder="HH:MM"
                    value={editSchedule}
                    onChange={(e) => setEditSchedule(e.target.value)}
                  />
                  <Button size="sm" className="px-2 py-0.5 h-6 text-[10px]" onClick={() => void handleScheduleSave(task.taskKey)}>保存</Button>
                  <Button size="sm" variant="outline" className="px-2 py-0.5 h-6 text-[10px]" onClick={() => { setEditingKey(null); setEditSchedule(''); }}>取消</Button>
                </div>
              ) : (
                <div className="flex items-center gap-1">
                  <span>{displayTime}</span>
                  {task.scheduleType === 'daily' && !READONLY_TASK_KEYS.has(task.taskKey) && (
                    <button
                      className="text-muted-text hover:text-foreground transition-colors"
                      onClick={() => { setEditingKey(task.taskKey); setEditSchedule(task.scheduleTime || ''); }}
                    >
                      编辑
                    </button>
                  )}
                </div>
              )}
            </div>

            {/* 频率 */}
            <div className="col-span-1 text-xs text-foreground">
              {task.scheduleType === 'interval'
                ? formatInterval(task.intervalSeconds)
                : (task.scheduleType === 'daily' ? '每日一次' : '-')}
            </div>

            {/* 成功率 */}
            <div className="col-span-1">
              {task.successRate ? (
                <div>
                  <span className="font-semibold text-sm text-success">{task.successRate}</span>
                </div>
              ) : task.totalRuns === 0 ? (
                <span className="text-xs text-muted-text">-</span>
              ) : null}
            </div>

            {/* 状态 */}
            <div className="col-span-1 flex justify-center">
              {task.lastRun ? getStatusIcon(task.lastStatus || '') : <span className="text-xs text-muted-text">待运行</span>}
            </div>

            {/* 操作（触发按钮） */}
            <div className="col-span-1 flex justify-center">
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleTrigger(task.taskKey)}
                disabled={triggerLoading === task.taskKey || task.taskKey === 'agent_event_monitor' || READONLY_TASK_KEYS.has(task.taskKey)}
                className={`gap-1 text-xs ${READONLY_TASK_KEYS.has(task.taskKey) ? 'opacity-40 cursor-not-allowed' : ''}`}
              >
                <PlayCircle className="w-3.5 h-3.5" />
                {triggerLoading === task.taskKey ? '执行中' : '触发'}
              </Button>
            </div>

            {/* 启用/禁用开关 */}
            <div className="col-span-1 flex justify-center">
              <button
                onClick={() => handleToggle(task.taskKey, task.enabled)}
                disabled={toggleLoading === task.taskKey || READONLY_TASK_KEYS.has(task.taskKey)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  task.enabled ? 'bg-primary' : 'bg-muted'
                } ${READONLY_TASK_KEYS.has(task.taskKey) ? 'cursor-not-allowed opacity-40' : ''}`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    task.enabled ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>
          </div>
        );
      })}

      {/* 底部 */}
      <div className="flex items-center justify-between pt-2 border-t border-border/40">
        <p className="text-[11px] text-muted-text">
          共 {tasks.length} 个定时任务 · 修改定时配置后需重启服务生效
        </p>
        <Button size="sm" variant="outline" onClick={() => void loadData()}>
          <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
          刷新
        </Button>
      </div>
    </div>
  );
};
