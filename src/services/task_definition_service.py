# -*- coding: utf-8 -*-
"""
定时任务定义服务 — CRUD 和初始化种子数据
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import select

from src.storage import ScheduledTask, DatabaseManager

logger = logging.getLogger(__name__)

# ─── 种子任务列表 ───
SEED_TASKS: List[Dict] = [
    {
        "task_key": "scheduled_task",
        "name": "大盘复盘",
        "description": "每日定时执行大盘分析，包括个股技术面、新闻面、资金面综合研判，生成研报并通过通知渠道推送。",
        "schedule_type": "daily",
        "schedule_time": None,  # 跟随 .env SCHEDULE_TIME
        "interval_seconds": None,
        "enabled": False,
    },
    {
        "task_key": "market_cache_refresh",
        "name": "市场缓存刷新",
        "description": "刷新市场大盘数据缓存（指数、估值分位、涨跌幅分布、趋势雷达等），供首页仪表盘使用。",
        "schedule_type": "daily",
        "schedule_time": "20:30",
        "interval_seconds": None,
        "enabled": False,
    },
    {
        "task_key": "agent_event_monitor",
        "name": "Agent 事件监控",
        "description": "后台常驻任务，周期性轮询 Agent 运行状态和事件队列，处理异步任务进度更新与结果回调。",
        "schedule_type": "interval",
        "schedule_time": None,
        "interval_seconds": 300,
        "enabled": True,
    },
]


def ensure_seed_tasks() -> None:
    """确保种子任务记录存在（不会覆盖已有配置）"""
    db = DatabaseManager.get_instance()
    with db.session_scope() as session:
        existing = set(
            row[0]
            for row in session.execute(
                select(ScheduledTask.task_key)
            ).fetchall()
        )
        to_create = [s for s in SEED_TASKS if s["task_key"] not in existing]
        if to_create:
            session.add_all([ScheduledTask(**kwargs) for kwargs in to_create])
            session.commit()
            for s in to_create:
                logger.info("已注册定时任务定义: %s", s["task_key"])


def list_tasks() -> List[Dict]:
    """列出所有任务定义"""
    db = DatabaseManager.get_instance()
    with db.session_scope() as session:
        rows = session.execute(select(ScheduledTask).order_by(ScheduledTask.id)).fetchall()
        return [_task_to_dict(r[0]) for r in rows]


def get_task(task_key: str) -> Optional[Dict]:
    """获取单个任务定义"""
    db = DatabaseManager.get_instance()
    with db.session_scope() as session:
        row = session.execute(
            select(ScheduledTask).where(ScheduledTask.task_key == task_key)
        ).fetchone()
        if row:
            return _task_to_dict(row[0])
        return None


def update_task(task_key: str, **kwargs) -> Optional[Dict]:
    """更新任务定义，返回更新后的记录；任务不存在时返回 None"""
    allowed = {"name", "description", "schedule_type", "schedule_time",
               "interval_seconds", "enabled"}
    filtered = {k: v for k, v in kwargs.items() if k in allowed}
    if not filtered:
        return get_task(task_key)

    db = DatabaseManager.get_instance()
    with db.session_scope() as session:
        row = session.execute(
            select(ScheduledTask).where(ScheduledTask.task_key == task_key)
        ).fetchone()
        if not row:
            return None
        task = row[0]
        for k, v in filtered.items():
            setattr(task, k, v)
        task.updated_at = datetime.now()
        session.commit()
        session.refresh(task)
        logger.info("定时任务 %s 已更新: %s", task_key, list(filtered.keys()))
        return _task_to_dict(task)


def toggle_task(task_key: str, enabled: bool) -> Optional[Dict]:
    """启用/禁用任务"""
    return update_task(task_key, enabled=enabled)


def _task_to_dict(task: ScheduledTask) -> Dict:
    return {
        "id": task.id,
        "task_key": task.task_key,
        "name": task.name,
        "description": task.description,
        "schedule_type": task.schedule_type,
        "schedule_time": task.schedule_time,
        "interval_seconds": task.interval_seconds,
        "enabled": task.enabled,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }
