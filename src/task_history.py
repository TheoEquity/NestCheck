# -*- coding: utf-8 -*-
"""
定时任务执行历史记录模块

使用 SQLite 存储任务执行记录，支持查询、统计等功能。
"""

import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TaskHistory:
    """任务执行历史管理器"""

    def __init__(self, db_path: str = "data/task_history.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """初始化数据库表"""
        conn = self._get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_ms INTEGER DEFAULT 0,
                    error TEXT,
                    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_name
                ON task_executions(task_name)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_executed_at
                ON task_executions(executed_at)
            """)
            conn.commit()
            logger.debug("任务历史数据库初始化成功: %s", self.db_path)
        except Exception as e:
            logger.error("任务历史数据库初始化失败: %s", e)
        finally:
            conn.close()

    def record(self, task_name: str, status: str, duration_ms: int = 0, error: str = None):
        """记录任务执行结果

        Args:
            task_name: 任务名称
            status: 执行状态 (success/failed/skipped)
            duration_ms: 执行耗时（毫秒）
            error: 错误信息（如果有）
        """
        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT INTO task_executions (task_name, status, duration_ms, error, executed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_name, status, duration_ms, error, datetime.now().isoformat())
            )
            conn.commit()
        except Exception as e:
            logger.error("记录任务历史失败: %s", e)
        finally:
            conn.close()

    def get_history(self, task_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取任务执行历史

        Args:
            task_name: 任务名称
            limit: 返回记录数限制

        Returns:
            执行历史列表（按时间倒序）
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT id, task_name, status, duration_ms, error, executed_at
                FROM task_executions
                WHERE task_name = ?
                ORDER BY executed_at DESC
                LIMIT ?
                """,
                (task_name, limit)
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "task_name": row["task_name"],
                    "status": row["status"],
                    "duration_ms": row["duration_ms"],
                    "error": row["error"],
                    "executed_at": row["executed_at"],
                }
                for row in rows
            ]
        except Exception as e:
            logger.error("查询任务历史失败: %s", e)
            return []
        finally:
            conn.close()

    def get_all_tasks(self) -> List[str]:
        """获取所有有历史记录的任务名称"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT DISTINCT task_name FROM task_executions ORDER BY task_name"
            )
            return [row["task_name"] for row in cursor.fetchall()]
        except Exception as e:
            logger.error("查询任务列表失败: %s", e)
            return []
        finally:
            conn.close()

    def get_stats(self, task_name: str, days: int = 7) -> Dict[str, Any]:
        """获取任务执行统计信息

        Args:
            task_name: 任务名称
            days: 统计天数

        Returns:
            统计信息字典
        """
        days = max(1, min(int(days), 365))
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT
                    COUNT(*) as total_runs,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_count,
                    AVG(duration_ms) as avg_duration_ms,
                    MAX(duration_ms) as max_duration_ms,
                    MIN(duration_ms) as min_duration_ms
                FROM task_executions
                WHERE task_name = ?
                AND executed_at >= datetime('now', ?)
                """,
                (task_name, f"-{days} days")
            )
            row = cursor.fetchone()
            if row:
                return {
                    "task_name": task_name,
                    "total_runs": row["total_runs"] or 0,
                    "success_count": row["success_count"] or 0,
                    "failed_count": row["failed_count"] or 0,
                    "avg_duration_ms": round(row["avg_duration_ms"] or 0, 2),
                    "max_duration_ms": row["max_duration_ms"] or 0,
                    "min_duration_ms": row["min_duration_ms"] or 0,
                    "success_rate": round(
                        (row["success_count"] or 0) / max(row["total_runs"] or 1, 1) * 100, 2
                    ),
                }
            return {
                "task_name": task_name,
                "total_runs": 0,
                "success_count": 0,
                "failed_count": 0,
                "avg_duration_ms": 0,
                "max_duration_ms": 0,
                "min_duration_ms": 0,
                "success_rate": 0,
            }
        except Exception as e:
            logger.error("查询任务统计失败: %s", e)
            return {"task_name": task_name, "total_runs": 0, "success_count": 0, "failed_count": 0}
        finally:
            conn.close()

    def cleanup(self, days: int = 30):
        """清理过期历史记录

        Args:
            days: 保留天数
        """
        days = max(1, min(int(days), 3650))
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM task_executions WHERE executed_at < datetime('now', ?)",
                (f"-{days} days",)
            )
            deleted = cursor.rowcount
            conn.commit()
            if deleted > 0:
                logger.info("已清理 %d 条过期任务历史记录", deleted)
        except Exception as e:
            logger.error("清理任务历史失败: %s", e)
        finally:
            conn.close()


# 全局实例
task_history = TaskHistory()
