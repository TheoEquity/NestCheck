# -*- coding: utf-8 -*-
"""
===================================
定时调度模块 - APScheduler 版本
===================================

职责：
1. 支持 CRON 表达式定时执行
2. 支持每日固定时间执行（向后兼容）
3. 支持后台周期性任务
4. 优雅处理信号，确保可靠退出
5. 支持任务执行历史记录

依赖：
- apscheduler: 高级 Python 调度库
"""

import logging
import signal
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

try:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.date import DateTrigger
    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False
    logger = logging.getLogger(__name__)
    logger.error("APScheduler 未安装，请执行: pip install apscheduler")

logger = logging.getLogger(__name__)


class GracefulShutdown:
    """
    优雅退出处理器

    捕获 SIGTERM/SIGINT 信号，确保任务完成后再退出
    """

    def __init__(self):
        self.shutdown_requested = False
        self._lock = threading.Lock()

        # 注册信号处理器
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """信号处理函数"""
        with self._lock:
            if not self.shutdown_requested:
                logger.info(f"收到退出信号 ({signum})，等待当前任务完成...")
                self.shutdown_requested = True

    @property
    def should_shutdown(self) -> bool:
        """检查是否应该退出"""
        with self._lock:
            return self.shutdown_requested


class Scheduler:
    """
    定时任务调度器（APScheduler 版本）

    支持：
    - CRON 表达式（如 "0 18 * * *" 每日 18 点）
    - 间隔定时（如每 5 分钟）
    - 启动时立即执行
    - 优雅退出
    """

    def __init__(
        self,
        schedule_time: str = "18:00",
        schedule_cron: str = "",
        schedule_time_provider: Optional[Callable[[], str]] = None,
    ):
        """
        初始化调度器

        Args:
            schedule_time: 每日执行时间，格式 "HH:MM"（向后兼容）
            schedule_cron: CRON 表达式（优先级高于 schedule_time）
        """
        if not HAS_APSCHEDULER:
            raise ImportError("请安装 APScheduler: pip install apscheduler")

        self.scheduler = BlockingScheduler()
        self.schedule_time = schedule_time
        self.schedule_cron = schedule_cron
        self._schedule_time_provider = schedule_time_provider
        self.shutdown_handler = GracefulShutdown()
        self._task_callback: Optional[Callable] = None
        self._daily_job_id: Optional[str] = None
        self._background_tasks: List[Dict[str, Any]] = []
        self._running = False

    def set_daily_task(self, task: Callable, run_immediately: bool = True):
        """
        设置每日定时任务

        Args:
            task: 要执行的任务函数（无参数）
            run_immediately: 是否在设置后立即执行一次
        """
        self._task_callback = task

        # 优先使用 CRON 表达式
        if self.schedule_cron:
            if not self._configure_cron_task(self.schedule_cron):
                raise ValueError(f"无效的 CRON 表达式: {self.schedule_cron!r}")
        else:
            if not self._configure_daily_task(self.schedule_time):
                raise ValueError(f"无效的定时执行时间: {self.schedule_time!r}")

        if run_immediately:
            logger.info("立即执行一次任务...")
            self._safe_run_task()

    def _is_valid_schedule_time(self, schedule_time: str) -> bool:
        """验证时间字符串格式 (HH:MM 24小时制)"""
        import re
        candidate = (schedule_time or "").strip()
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", candidate):
            return False
        return True

    def _is_valid_cron(self, cron_expr: str) -> bool:
        """验证 CRON 表达式"""
        try:
            parts = cron_expr.strip().split()
            if len(parts) != 5:
                return False
            # 尝试创建 CronTrigger 验证格式
            CronTrigger.from_crontab(cron_expr)
            return True
        except Exception:
            return False

    def _cancel_daily_job(self) -> None:
        """移除已注册的每日任务"""
        if self._daily_job_id and self.scheduler.get_job(self._daily_job_id):
            self.scheduler.remove_job(self._daily_job_id)
            self._daily_job_id = None

    def _configure_cron_task(self, cron_expr: str) -> bool:
        """注册 CRON 定时任务"""
        if not self._is_valid_cron(cron_expr):
            logger.warning(f"检测到无效的 CRON 表达式: {cron_expr}")
            return False

        self._cancel_daily_job()
        job = self.scheduler.add_job(
            self._safe_run_task,
            CronTrigger.from_crontab(cron_expr),
            id="daily_cron_task",
            name="每日定时任务",
            replace_existing=True,
        )
        self._daily_job_id = job.id
        self.schedule_cron = cron_expr
        logger.info(f"已设置 CRON 定时任务，表达式: {cron_expr}")
        return True

    def _configure_daily_task(self, schedule_time: str) -> bool:
        """注册每日固定时间任务"""
        candidate = (schedule_time or "").strip()
        if not self._is_valid_schedule_time(candidate):
            logger.warning(
                f"检测到无效的定时执行时间 {candidate!r}，继续使用当前时间 {self.schedule_time}"
            )
            return False

        self._cancel_daily_job()
        hour, minute = map(int, candidate.split(':'))
        job = self.scheduler.add_job(
            self._safe_run_task,
            CronTrigger(hour=hour, minute=minute),
            id="daily_task",
            name="每日定时任务",
            replace_existing=True,
        )
        self._daily_job_id = job.id
        self.schedule_time = candidate
        logger.info(f"已设置每日定时任务，执行时间: {candidate}")
        return True

    def _refresh_daily_schedule_if_needed(self) -> None:
        """检查并更新每日调度时间（如果配置发生变化）"""
        if self._task_callback is None or self._schedule_time_provider is None:
            return

        try:
            latest_schedule_time = (self._schedule_time_provider() or "").strip()
        except Exception as exc:
            logger.warning(f"读取最新 SCHEDULE_TIME 失败，继续沿用 {self.schedule_time}: {exc}")
            return

        if not latest_schedule_time or latest_schedule_time == self.schedule_time:
            return

        if self._configure_daily_task(latest_schedule_time):
            logger.info(f"更新后的下次执行时间: {self._get_next_run_time()}")

    def _safe_run_task(self):
        """安全执行任务（带异常捕获）"""
        if self._task_callback is None:
            return

        start_time = time.time()
        try:
            logger.info("=" * 50)
            logger.info(f"定时任务开始执行 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 50)

            self._task_callback()

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(f"定时任务执行完成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}，耗时 {duration_ms}ms")

            # 记录执行历史
            self._record_execution("scheduled_task", "success", duration_ms=duration_ms)

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.exception(f"定时任务执行失败: {e}")
            self._record_execution("scheduled_task", "failed", duration_ms=duration_ms, error=str(e))

    def add_background_task(
        self,
        task: Callable,
        interval_seconds: int,
        run_immediately: bool = False,
        name: Optional[str] = None,
    ) -> None:
        """注册周期性后台任务

        Args:
            task: 要执行的任务函数
            interval_seconds: 执行间隔（秒）
            run_immediately: 是否立即执行一次
            name: 任务名称
        """
        task_name = name or getattr(task, "__name__", "background_task")

        # 使用 APScheduler 的 IntervalTrigger
        job = self.scheduler.add_job(
            self._safe_run_background_task,
            IntervalTrigger(seconds=interval_seconds),
            id=f"background_{task_name}",
            name=task_name,
            args=[task],
            replace_existing=True,
        )

        entry = {
            "task": task,
            "interval_seconds": interval_seconds,
            "name": task_name,
            "job": job,
        }
        self._background_tasks.append(entry)
        logger.info(f"已注册后台任务: {task_name}（间隔 {interval_seconds} 秒，立即执行={run_immediately})")

        if run_immediately:
            self._safe_run_background_task(task)

    def _safe_run_background_task(self, task: Callable):
        """安全执行后台任务"""
        task_name = getattr(task, '__name__', 'unknown')
        start_time = time.time()
        try:
            logger.info(f"后台任务开始执行: {task_name}")
            task()
            duration_ms = int((time.time() - start_time) * 1000)
            self._record_execution(task_name, "success", duration_ms=duration_ms)
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.exception(f"后台任务执行失败: {e}")
            self._record_execution(task_name, "failed", duration_ms=duration_ms, error=str(e))

    def run(self):
        """
        运行调度器主循环

        阻塞运行，直到收到退出信号
        """
        self._running = True
        logger.info("调度器开始运行...")
        logger.info(f"下次执行时间: {self._get_next_run_time()}")

        # 注册退出事件
        self.scheduler.add_listener(
            self._on_scheduler_shutdown,
            signal=signal.SIGTERM | signal.SIGINT,
        )

        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("调度器收到退出信号")
        finally:
            self._running = False
            logger.info("调度器已停止")

    def _on_scheduler_shutdown(self, event):
        """调度器关闭事件处理"""
        self._running = False

    def _get_next_run_time(self) -> str:
        """获取下次执行时间"""
        jobs = self.scheduler.get_jobs()
        if jobs:
            next_job = min(jobs, key=lambda j: j.next_run_time or datetime.max)
            if next_job.next_run_time:
                return next_job.next_run_time.strftime('%Y-%m-%d %H:%M:%S')
        return "未设置"

    def stop(self):
        """停止调度器"""
        self._running = False
        self.scheduler.shutdown(wait=False)

    def _record_execution(self, task_name: str, status: str, duration_ms: int = 0, error: str = None):
        """记录任务执行历史（可选，需要 SQLite 支持）"""
        try:
            from src.task_history import task_history
            task_history.record(task_name, status, duration_ms=duration_ms, error=error)
        except ImportError:
            pass  # SQLite未初始化时忽略


def run_with_schedule(
    task: Callable,
    schedule_time: str = "18:00",
    schedule_cron: str = "",
    run_immediately: bool = True,
    background_tasks: Optional[List[Dict[str, Any]]] = None,
    schedule_time_provider: Optional[Callable[[], str]] = None,
):
    """
    便捷函数：使用定时调度运行任务

    Args:
        task: 要执行的任务函数
        schedule_time: 每日执行时间（向后兼容）
        schedule_cron: CRON 表达式（优先级更高）
        run_immediately: 是否立即执行一次
        background_tasks: 可选的后台任务定义列表
        schedule_time_provider: 可选的时间提供器
    """
    scheduler = Scheduler(
        schedule_time=schedule_time,
        schedule_cron=schedule_cron,
        schedule_time_provider=schedule_time_provider,
    )
    for entry in background_tasks or []:
        scheduler.add_background_task(
            task=entry["task"],
            interval_seconds=entry["interval_seconds"],
            run_immediately=entry.get("run_immediately", False),
            name=entry.get("name"),
        )
    scheduler.set_daily_task(task, run_immediately=run_immediately)
    scheduler.run()


if __name__ == "__main__":
    # 测试定时调度
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
    )

    def test_task():
        print(f"任务执行中... {datetime.now()}")
        time.sleep(2)
        print("任务完成!")

    print("启动测试调度器（按 Ctrl+C 退出）")
    # 支持 CRON 表达式或固定时间
    run_with_schedule(
        test_task,
        schedule_time="23:59",
        schedule_cron="",  # 可改为 "*/2 * * * *" 测试每 2 分钟执行
        run_immediately=True
    )
