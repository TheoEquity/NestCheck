import { useEffect, useState } from "react";
import {
  AppPage,
  Badge,
  Button,
  Card,
  EmptyState,
  PageHeader,
} from "../components/common";
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  RefreshCw,
  BarChart3,
} from "lucide-react";

interface TaskStats {
  task_name: string;
  total_runs: number;
  success_count: number;
  failed_count: number;
  avg_duration_ms: number;
  max_duration_ms: number;
  min_duration_ms: number;
  success_rate: number;
}

interface TaskRecord {
  task_name: string;
  status: string;
  last_run: string | null;
  last_status: string | null;
  stats: TaskStats;
  recent_history: Array<{
    id: number;
    task_name: string;
    status: string;
    duration_ms: number;
    error: string | null;
    executed_at: string;
  }>;
}

interface HistoryRecord {
  id: number;
  task_name: string;
  status: string;
  duration_ms: number;
  error: string | null;
  executed_at: string;
}

export default function SchedulerPage() {
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [history, setHistory] = useState<HistoryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [tasksRes, historyRes] = await Promise.all([
        fetch("/api/v1/scheduler/tasks"),
        fetch("/api/v1/scheduler/history?limit=50"),
      ]);

      if (!tasksRes.ok || !historyRes.ok) {
        throw new Error("获取任务数据失败");
      }

      const tasksData = await tasksRes.json();
      const historyData = await historyRes.json();

      setTasks(tasksData);
      setHistory(historyData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "未知错误");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "success":
        return (
          <Badge variant="success">
            <CheckCircle className="w-3 h-3 mr-1" />
            成功
          </Badge>
        );
      case "failed":
        return (
          <Badge variant="danger">
            <XCircle className="w-3 h-3 mr-1" />
            失败
          </Badge>
        );
      case "skipped":
        return (
          <Badge variant="warning">
            <AlertTriangle className="w-3 h-3 mr-1" />
            跳过
          </Badge>
        );
      default:
        return <Badge variant="info">{status}</Badge>;
    }
  };

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  const formatTime = (iso: string) => {
    const date = new Date(iso);
    return date.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  };

  if (loading) {
    return (
      <AppPage>
        <div className="flex items-center justify-center h-64">
          <RefreshCw className="w-8 h-8 animate-spin text-gray-400" />
        </div>
      </AppPage>
    );
  }

  if (error) {
    return (
      <AppPage>
        <Card>
          <div className="pt-6 text-center">
            <p className="text-red-500 mb-4">{error}</p>
            <Button onClick={fetchData}>
              重试
            </Button>
          </div>
        </Card>
      </AppPage>
    );
  }

  return (
    <AppPage>
      <PageHeader
        title="定时任务管理"
        description="查看任务执行历史、统计信息和运行状态"
        actions={
          <Button onClick={fetchData} variant="outline">
            <RefreshCw className="w-4 h-4 mr-2" />
            刷新
          </Button>
        }
      />

      <div className="space-y-6">
        {tasks.length === 0 ? (
          <Card>
            <EmptyState
              title="暂无任务记录"
              description="定时任务执行后会在此显示历史记录和统计信息"
            />
          </Card>
        ) : (
          tasks.map((task) => (
            <Card key={task.task_name}>
              <div className="p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold">{task.task_name}</h3>
                  <Badge variant="info">{task.status}</Badge>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <p className="text-sm text-gray-500">总执行次数</p>
                    <p className="text-2xl font-bold">
                      {task.stats.total_runs}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">成功率</p>
                    <p
                      className={`text-2xl font-bold ${
                        task.stats.success_rate >= 90
                          ? "text-green-500"
                          : task.stats.success_rate >= 70
                          ? "text-yellow-500"
                          : "text-red-500"
                      }`}
                    >
                      {task.stats.success_rate}%
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">平均耗时</p>
                    <p className="text-2xl font-bold">
                      {formatDuration(task.stats.avg_duration_ms)}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">最近执行</p>
                    <p className="text-sm">
                      {task.last_run ? formatTime(task.last_run) : "未执行"}
                    </p>
                  </div>
                </div>

                {task.recent_history.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium mb-2">最近执行记录</h4>
                    <div className="space-y-2">
                      {task.recent_history.slice(0, 5).map((record) => (
                        <div
                          key={record.id}
                          className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700"
                        >
                          <div className="flex items-center gap-2">
                            {getStatusBadge(record.status)}
                            <span className="text-sm">
                              {formatDuration(record.duration_ms)}
                            </span>
                          </div>
                          <span className="text-sm text-gray-500">
                            {formatTime(record.executed_at)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </Card>
          ))
        )}

        {history.length > 0 && (
          <Card>
            <div className="p-6">
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <BarChart3 className="w-5 h-5" />
                全局执行历史
              </h3>
              <div className="space-y-2">
                {history.slice(0, 20).map((record) => (
                  <div
                    key={record.id}
                    className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700"
                  >
                    <div className="flex items-center gap-3">
                      <span className="font-medium text-sm">
                        {record.task_name}
                      </span>
                      {getStatusBadge(record.status)}
                      <span className="text-sm text-gray-500">
                        {formatDuration(record.duration_ms)}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      {record.error && (
                        <span
                          className="text-xs text-red-500 max-w-xs truncate"
                          title={record.error}
                        >
                          {record.error}
                        </span>
                      )}
                      <span className="text-sm text-gray-500">
                        {formatTime(record.executed_at)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </Card>
        )}
      </div>
    </AppPage>
  );
}
