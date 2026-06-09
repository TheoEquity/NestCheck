import apiClient from './index';
import { getParsedApiError } from './error';
import { toCamelCase, toSnakeCase } from './utils';

export interface SchedulerTask {
  id?: number;
  taskKey?: string;
  taskName: string;
  name?: string;
  description?: string;
  scheduleType?: string;
  scheduleTime?: string | string[] | null;
  intervalSeconds?: number | null;
  enabled?: boolean;
  successRate?: string | null;
  totalRuns?: number;
  lastRun?: string;
  lastStatus?: 'success' | 'failed' | 'skipped';
  nextRun?: string;
  status?: 'configured' | 'running' | 'stopped' | 'failed';
  stats?: {
    taskName: string;
    totalRuns: number;
    successCount: number;
    failedCount: number;
    avgDurationMs: number;
    maxDurationMs: number;
    minDurationMs: number;
    successRate: number;
  };
  recentHistory?: Array<{
    id: number;
    taskName: string;
    status: 'success' | 'failed' | 'skipped';
    durationMs: number;
    error?: string;
    executedAt: string;
  }>;
  nextRunInfo?: {
    nextRun: string;
    scheduleTime?: string;
    interval?: number;
  };
}

export interface TaskNextRun {
  nextRun: string;
  scheduleTime?: string;
  interval?: number;
}

export interface TriggerTaskResponse {
  status: 'success' | 'failed' | 'skipped' | 'timeout' | 'running' | 'accepted';
  message?: string;
  durationMs?: number;
  error?: string;
}

export interface UpdateScheduleRequest {
  scheduleTime: string;
}

export interface UpdateScheduleResponse {
  success: boolean;
  message: string;
  scheduleTime: string;
  nextRun: string;
}

export interface UpdateTaskStatusRequest {
  enabled: boolean;
}

export const schedulerApi = {
  async getTasks(): Promise<SchedulerTask[]> {
    const response = await apiClient.get<Record<string, unknown>[]>('/api/v1/scheduler/tasks');
    return response.data.map(task => toCamelCase<SchedulerTask>(task));
  },

  async getTaskHistory(taskName: string, limit = 50): Promise<Array<{
    id: number;
    taskName: string;
    status: 'success' | 'failed' | 'skipped';
    durationMs: number;
    error?: string;
    executedAt: string;
  }>> {
    const response = await apiClient.get<Record<string, unknown>[]>(
      `/api/v1/scheduler/tasks/${taskName}/history`,
      { params: { limit } },
    );
    return response.data.map(item => toCamelCase(item));
  },

  async getTaskStats(taskName: string, days = 7): Promise<{
    taskName: string;
    totalRuns: number;
    successCount: number;
    failedCount: number;
    avgDurationMs: number;
    maxDurationMs: number;
    minDurationMs: number;
    successRate: number;
  }> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/scheduler/tasks/${taskName}/stats`,
      { params: { days } },
    );
    return toCamelCase(response.data);
  },

  async triggerTask(taskName: string): Promise<TriggerTaskResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/scheduler/tasks/${taskName}/trigger`,
    );
    return toCamelCase(response.data);
  },

  async updateTaskSchedule(taskName: string, payload: Record<string, unknown>): Promise<Record<string, unknown>> {
    const response = await apiClient.put<Record<string, unknown>>(
      `/api/v1/scheduler/tasks/${taskName}/schedule`,
      toSnakeCase(payload),
    );
    return toCamelCase(response.data);
  },

  async updateTaskStatus(taskName: string, payload: UpdateTaskStatusRequest): Promise<Record<string, unknown>> {
    const response = await apiClient.put<Record<string, unknown>>(
      `/api/v1/scheduler/tasks/${taskName}/status`,
      toSnakeCase(payload),
    );
    return toCamelCase(response.data);
  },

  async getNextRunTimes(): Promise<Record<string, TaskNextRun>> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/scheduler/next-run');
    const camelCase = toCamelCase(response.data);
    return camelCase as Record<string, TaskNextRun>;
  },

  async getGlobalHistory(limit = 100): Promise<Array<{
    id: number;
    taskName: string;
    status: 'success' | 'failed' | 'skipped';
    durationMs: number;
    error?: string;
    executedAt: string;
  }>> {
    const response = await apiClient.get<Record<string, unknown>[]>(
      '/api/v1/scheduler/history',
      { params: { limit } },
    );
    return response.data.map(item => toCamelCase(item));
  },

  async initMarketData(): Promise<{ status: string; message: string }> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/scheduler/tasks/init-market-data',
    );
    return toCamelCase(response.data);
  },
};

export { getParsedApiError };
