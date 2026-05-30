"""
自选股历史数据回填服务 (方案C)
- 添加新股票时异步 Backfill 1-2 年历史数据
- 分析时如果库内数据不足，降级现拉
"""

import logging
from typing import Optional
from src.storage import StorageManager, DatabaseManager

logger = logging.getLogger(__name__)

def backfill_stock_history(code: str, days: int = 730) -> int:
    """
    回填单只股票的历史日线数据入库
    
    Args:
        code: 股票代码 (如 600519, AAPL)
        days: 回填天数，默认 730 天（约 2 年）
        
    Returns:
        入库成功的新增记录数
    """
    from data_provider.fetcher_manager import DataFetcherManager
    
    manager = StorageManager()
    fetcher = DataFetcherManager()
    
    logger.info(f"[Backfill] 开始回填 {code} 的 {days} 天历史数据...")
    
    df, source_name = fetcher.get_daily_data(code, days=days)
    
    if df is None or df.empty:
        logger.warning(f"[Backfill] {code} 未获取到数据，跳过")
        return 0
    
    saved_count = manager.save_daily_data(df, code, source_name)
    logger.info(f"[Backfill] {code} 回填成功，入库 {saved_count} 条记录 (来源: {source_name})")
    
    return saved_count


def get_historical_data_with_fallback(code: str, required_days: int = 90):
    """
    智能获取历史数据 (分析时降级策略)
    - 优先从数据库读取
    - 如果库内数据不足 required_days 天，降级到网络现拉补充
    
    Args:
        code: 股票代码
        required_days: 分析所需最小历史天数
        
    Returns:
        (DataFrame, source_name)
    """
    manager = StorageManager()
    
    # Step 1: 尝试从数据库读取
    db_df = manager.get_stock_history(code, days=required_days + 60)
    
    if db_df is not None and not db_df.empty and len(db_df) >= required_days:
        logger.info(f"[DataFallback] {code} 数据库有足够历史数据 ({len(db_df)} 条)，直接读取")
        return db_df, "database"
    
    # Step 2: 降级到网络现拉并补充入库
    logger.info(f"[DataFallback] {code} 库内数据不足 ({len(db_df) if db_df is not None else 0} 条)，降级现拉...")
    from data_provider.fetcher_manager import DataFetcherManager
    
    fetcher = DataFetcherManager()
    net_df, source_name = fetcher.get_daily_data(code, days=required_days + 60)
    
    if net_df is not None and not net_df.empty:
        # 补充入库供下次使用
        try:
            manager.save_daily_data(net_df, code, source_name)
        except Exception as e:
            logger.warning(f"[DataFallback] {code} 数据入库失败 (不影响分析): {e}")
    
    return net_df, source_name
