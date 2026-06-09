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
        "task_key": "market_cache_refresh",
        "name": "市场数据刷新",
        "description": "Web 服务后台托管的市场数据刷新入口：每日 08:30 和 20:30 刷新组合价格、基金净值、风险指标、板块 ETF、自选信号和首页市场缓存；交易时段另有 5 分钟市场缓存刷新循环。",
        "schedule_type": "daily",
        "schedule_time": "08:30,20:30",
        "interval_seconds": None,
        "enabled": True,
    },
    {
        "task_key": "seasonality_cache_refresh",
        "name": "全年择时缓存刷新",
        "description": "全年择时缓存维护入口，当前随市场缓存刷新链路维护，无独立手动触发操作。",
        "schedule_type": "daily",
        "schedule_time": "20:30",
        "interval_seconds": None,
        "enabled": True,
    },
    {
        "task_key": "agent_event_monitor",
        "name": "Agent 事件监控",
        "description": "告警 worker 展示项；实际开关和间隔由系统配置 AGENT_EVENT_MONITOR_ENABLED / AGENT_EVENT_MONITOR_INTERVAL_MINUTES 控制。",
        "schedule_type": "interval",
        "schedule_time": None,
        "interval_seconds": 300,
        "enabled": True,
    },
]
SUPPORTED_TASK_KEYS = tuple(task["task_key"] for task in SEED_TASKS)


def ensure_seed_tasks() -> None:
    """确保种子任务记录存在，并同步内置任务的展示元数据。"""
    db = DatabaseManager.get_instance()
    with db.session_scope() as session:
        existing_rows = {
            row[0].task_key: row[0]
            for row in session.execute(select(ScheduledTask)).fetchall()
        }
        existing = set(existing_rows.keys())
        to_create = [s for s in SEED_TASKS if s["task_key"] not in existing]
        if to_create:
            session.add_all([ScheduledTask(**kwargs) for kwargs in to_create])
            for s in to_create:
                logger.info("已注册定时任务定义: %s", s["task_key"])
        for seed in SEED_TASKS:
            task = existing_rows.get(seed["task_key"])
            if task is None:
                continue
            for key in ("name", "description", "schedule_type", "schedule_time", "interval_seconds"):
                setattr(task, key, seed[key])
        session.commit()


def list_tasks() -> List[Dict]:
    """列出所有任务定义"""
    db = DatabaseManager.get_instance()
    with db.session_scope() as session:
        rows = session.execute(
            select(ScheduledTask).where(ScheduledTask.task_key.in_(SUPPORTED_TASK_KEYS))
        ).fetchall()
        task_by_key = {r[0].task_key: r[0] for r in rows}
        return [
            _task_to_dict(task_by_key[key])
            for key in SUPPORTED_TASK_KEYS
            if key in task_by_key
        ]


def get_task(task_key: str) -> Optional[Dict]:
    """获取单个任务定义"""
    if task_key not in SUPPORTED_TASK_KEYS:
        return None
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
    if task_key not in SUPPORTED_TASK_KEYS:
        return None
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
