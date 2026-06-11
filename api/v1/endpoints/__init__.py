# -*- coding: utf-8 -*-
"""
===================================
API v1 Endpoints 模块初始化
===================================

职责：
1. 声明所有 endpoint 路由模块
"""

from api.v1.endpoints import (
    health,
    history,
    stocks,
    backtest,
    system_config,
    auth,
    agent,
    agent_management,
    portfolio,
    funds,
    watchlist,
)
__all__ = [
    "health",
    "history",
    "stocks",
    "backtest",
    "system_config",
    "auth",
    "agent",
    "agent_management",
    "portfolio",
    "funds",
    "watchlist",
]
