# -*- coding: utf-8 -*-
"""
===================================
股票数据服务层
===================================

职责：
1. 封装股票数据获取逻辑
2. 提供实时行情和历史数据接口
3. 本地缓存行情数据，减少频繁 API 调用
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path
import json

from src.repositories.stock_repo import StockRepository

logger = logging.getLogger(__name__)

# 行情缓存配置
QUOTE_CACHE_DIR = Path("/tmp/nestcheck_quote")
QUOTE_CACHE_DIR.mkdir(exist_ok=True)
QUOTE_CACHE_EXPIRY_SECONDS = 60  # 行情缓存过期时间（秒）

# 分时图缓存配置
INTRADAY_CACHE_DIR = Path("/tmp/nestcheck_intraday")
INTRADAY_CACHE_DIR.mkdir(exist_ok=True)
INTRADAY_CACHE_EXPIRY_SECONDS = 60  # 分时图缓存过期时间（秒）


class StockService:
    """
    股票数据服务
    
    封装股票数据获取的业务逻辑，含本地缓存机制
    """
    
    def __init__(self):
        """初始化股票数据服务"""
        self.repo = StockRepository()
    
    def _load_quote_cache(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """加载行情缓存"""
        cache_file = QUOTE_CACHE_DIR / f"{stock_code}.json"
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 检查缓存是否过期
            cached_at = datetime.fromisoformat(data.get("_cached_at", "1970-01-01"))
            if datetime.now() - cached_at > timedelta(seconds=QUOTE_CACHE_EXPIRY_SECONDS):
                logger.debug(f"行情缓存已过期 {stock_code}")
                return None
            
            return data
        except Exception as e:
            logger.warning(f"读取行情缓存失败 {stock_code}: {e}")
            return None
    
    def _save_quote_cache(self, stock_code: str, data: Dict[str, Any]):
        """保存行情缓存"""
        cache_file = QUOTE_CACHE_DIR / f"{stock_code}.json"
        data_with_timestamp = {
            **data,
            "_cached_at": datetime.now().isoformat()
        }
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data_with_timestamp, f, ensure_ascii=False, indent=2)
            logger.debug(f"行情缓存已保存 {stock_code}")
        except Exception as e:
            logger.error(f"保存行情缓存失败 {stock_code}: {e}")
    
    def get_intraday_data(self, stock_code: str, days: int = 1) -> Optional[Dict[str, Any]]:
        """
        获取分时图数据（分钟线）
        
        优先从缓存读取，缓存过期后再调用数据源
        
        Args:
            stock_code: 股票代码
            days: 获取天数（默认 1 天）
            
        Returns:
            分时图数据字典，包含 data 列表
        """
        # 先查缓存
        cache = self._load_intraday_cache(stock_code, days)
        if cache:
            logger.debug(f"分时图缓存命中：{stock_code}")
            return cache
        
        try:
            # 调用数据获取器获取分钟线数据
            from data_provider.base import DataFetcherManager
            
            manager = DataFetcherManager()
            minute_data = manager.get_minute_data(stock_code, days=days)
            
            if not minute_data:
                logger.warning(f"获取 {stock_code} 分时图数据失败")
                return None
            
            result = {
                "stock_code": stock_code,
                "data": minute_data,
                "_cached_at": datetime.now().isoformat()
            }
            
            # 保存到缓存
            self._save_intraday_cache(stock_code, days, result)
            return result
            
        except Exception as e:
            logger.error(f"获取分时图失败：{e}", exc_info=True)
            return None
    
    def _load_intraday_cache(self, stock_code: str, days: int) -> Optional[Dict[str, Any]]:
        """加载分时图缓存"""
        cache_file = INTRADAY_CACHE_DIR / f"{stock_code}_{days}d.json"
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 检查缓存是否过期
            cached_at = datetime.fromisoformat(data.get("_cached_at", "1970-01-01"))
            if datetime.now() - cached_at > timedelta(seconds=INTRADAY_CACHE_EXPIRY_SECONDS):
                logger.debug(f"分时图缓存已过期 {stock_code}")
                return None
            
            return data
        except Exception as e:
            logger.warning(f"读取分时图缓存失败 {stock_code}: {e}")
            return None
    
    def _save_intraday_cache(self, stock_code: str, days: int, data: Dict[str, Any]):
        """保存分时图缓存"""
        cache_file = INTRADAY_CACHE_DIR / f"{stock_code}_{days}d.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"分时图缓存已保存 {stock_code}")
        except Exception as e:
            logger.error(f"保存分时图缓存失败 {stock_code}: {e}")
    
    def get_realtime_quote(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        获取股票实时行情
        
        优先从缓存读取，缓存过期后再调用数据源
        
        Args:
            stock_code: 股票代码
            
        Returns:
            实时行情数据字典
        """
        # 先查缓存
        cache = self._load_quote_cache(stock_code)
        if cache:
            logger.debug(f"缓存命中：{stock_code}")
            return cache
        
        try:
            # 调用数据获取器获取实时行情
            from data_provider.base import DataFetcherManager
            
            manager = DataFetcherManager()
            quote = manager.get_realtime_quote(stock_code)
            
            if quote is None:
                logger.warning(f"获取 {stock_code} 实时行情失败")
                return None
            
            # UnifiedRealtimeQuote 是 dataclass，使用 getattr 安全访问字段
            # 字段映射：UnifiedRealtimeQuote -> API 响应
            # - code -> stock_code
            # - name -> stock_name
            # - price -> current_price
            # - change_amount -> change
            # - change_pct -> change_percent
            # - open_price -> open
            # - high -> high
            # - low -> low
            # - pre_close -> prev_close
            # - volume -> volume
            # - amount -> amount
            result = {
                "stock_code": getattr(quote, "code", stock_code),
                "stock_name": getattr(quote, "name", None),
                "current_price": getattr(quote, "price", 0.0) or 0.0,
                "change": getattr(quote, "change_amount", None),
                "change_percent": getattr(quote, "change_pct", None),
                "open": getattr(quote, "open_price", None),
                "high": getattr(quote, "high", None),
                "low": getattr(quote, "low", None),
                "prev_close": getattr(quote, "pre_close", None),
                "volume": getattr(quote, "volume", None),
                "amount": getattr(quote, "amount", None),
                "update_time": datetime.now().isoformat(),
            }
            
            # 保存到缓存
            self._save_quote_cache(stock_code, result)
            return result
            
        except ImportError:
            logger.warning("DataFetcherManager 未找到，使用占位数据")
            return self._get_placeholder_quote(stock_code)
        except Exception as e:
            logger.error(f"获取实时行情失败：{e}", exc_info=True)
            return None
            
            # UnifiedRealtimeQuote 是 dataclass，使用 getattr 安全访问字段
            # 字段映射: UnifiedRealtimeQuote -> API 响应
            # - code -> stock_code
            # - name -> stock_name
            # - price -> current_price
            # - change_amount -> change
            # - change_pct -> change_percent
            # - open_price -> open
            # - high -> high
            # - low -> low
            # - pre_close -> prev_close
            # - volume -> volume
            # - amount -> amount
            return {
                "stock_code": getattr(quote, "code", stock_code),
                "stock_name": getattr(quote, "name", None),
                "current_price": getattr(quote, "price", 0.0) or 0.0,
                "change": getattr(quote, "change_amount", None),
                "change_percent": getattr(quote, "change_pct", None),
                "open": getattr(quote, "open_price", None),
                "high": getattr(quote, "high", None),
                "low": getattr(quote, "low", None),
                "prev_close": getattr(quote, "pre_close", None),
                "volume": getattr(quote, "volume", None),
                "amount": getattr(quote, "amount", None),
                "update_time": datetime.now().isoformat(),
            }
            
        except ImportError:
            logger.warning("DataFetcherManager 未找到，使用占位数据")
            return self._get_placeholder_quote(stock_code)
        except Exception as e:
            logger.error(f"获取实时行情失败: {e}", exc_info=True)
            return None
    
    def get_history_data(
        self,
        stock_code: str,
        period: str = "daily",
        days: int = 30
    ) -> Dict[str, Any]:
        """
        获取股票历史行情
        
        Args:
            stock_code: 股票代码
            period: K 线周期 (daily/weekly/monthly)
            days: 获取天数
            
        Returns:
            历史行情数据字典
            
        Raises:
            ValueError: 当 period 不是 daily 时抛出（weekly/monthly 暂未实现）
        """
        # 验证 period 参数，只支持 daily
        if period != "daily":
            raise ValueError(
                f"暂不支持 '{period}' 周期，目前仅支持 'daily'。"
                "weekly/monthly 聚合功能将在后续版本实现。"
            )
        
        try:
            # 调用数据获取器获取历史数据
            from data_provider.base import DataFetcherManager
            
            manager = DataFetcherManager()
            df, source = manager.get_daily_data(stock_code, days=days)
            
            if df is None or df.empty:
                logger.warning(f"获取 {stock_code} 历史数据失败")
                return {"stock_code": stock_code, "period": period, "data": []}
            
            # 获取股票名称
            stock_name = manager.get_stock_name(stock_code)
            
            # 转换为响应格式
            data = []
            for _, row in df.iterrows():
                date_val = row.get("date")
                if hasattr(date_val, "strftime"):
                    date_str = date_val.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_val)
                
                data.append({
                    "date": date_str,
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "close": float(row.get("close", 0)),
                    "volume": float(row.get("volume", 0)) if row.get("volume") else None,
                    "amount": float(row.get("amount", 0)) if row.get("amount") else None,
                    "change_percent": float(row.get("pct_chg", 0)) if row.get("pct_chg") else None,
                })
            
            return {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "period": period,
                "data": data,
            }
            
        except ImportError:
            logger.warning("DataFetcherManager 未找到，返回空数据")
            return {"stock_code": stock_code, "period": period, "data": []}
        except Exception as e:
            logger.error(f"获取历史数据失败: {e}", exc_info=True)
            return {"stock_code": stock_code, "period": period, "data": []}
    
    def _get_placeholder_quote(self, stock_code: str) -> Dict[str, Any]:
        """
        获取占位行情数据（用于测试）
        
        Args:
            stock_code: 股票代码
            
        Returns:
            占位行情数据
        """
        return {
            "stock_code": stock_code,
            "stock_name": f"股票{stock_code}",
            "current_price": 0.0,
            "change": None,
            "change_percent": None,
            "open": None,
            "high": None,
            "low": None,
            "prev_close": None,
            "volume": None,
            "amount": None,
            "update_time": datetime.now().isoformat(),
        }
