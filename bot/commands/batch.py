# -*- coding: utf-8 -*-
"""
===================================
批量分析命令
===================================

批量分析显式传入的股票列表。
"""

import logging
import threading
import uuid
from typing import List

from bot.commands.base import BotCommand
from bot.models import BotMessage, BotResponse

logger = logging.getLogger(__name__)


class BatchCommand(BotCommand):
    """
    批量分析命令
    
    批量分析显式传入的股票列表，生成汇总报告。
    
    用法：
        /batch      - 提示传入股票列表
        /batch 600519 000001 - 分析指定股票
    """
    
    @property
    def name(self) -> str:
        return "batch"
    
    @property
    def aliases(self) -> List[str]:
        return ["b", "批量", "全部"]
    
    @property
    def description(self) -> str:
        return "批量分析股票"
    
    @property
    def usage(self) -> str:
        return "/batch [数量]"
    
    @property
    def admin_only(self) -> bool:
        """批量分析需要管理员权限（防止滥用）"""
        return False  # 可以根据需要设为 True
    
    def execute(self, message: BotMessage, args: List[str]) -> BotResponse:
        """执行批量分析命令"""
        from data_provider.base import normalize_stock_code
        
        stock_list = [normalize_stock_code(item) for item in args if item.strip()]
        
        if not stock_list:
            return BotResponse.error_response(
                "请在 /batch 后传入股票代码，例如：/batch 600519 000001"
            )
        
        logger.info(f"[BatchCommand] 开始批量分析 {len(stock_list)} 只股票")
        
        # 在后台线程中执行分析
        thread = threading.Thread(
            target=self._run_batch_analysis,
            args=(stock_list, message),
            daemon=True
        )
        thread.start()
        
        return BotResponse.markdown_response(
            f"✅ **批量分析任务已启动**\n\n"
            f"• 分析数量: {len(stock_list)} 只\n"
            f"• 股票列表: {', '.join(stock_list[:5])}"
            f"{'...' if len(stock_list) > 5 else ''}\n\n"
            f"分析完成后将自动推送汇总报告。"
        )
    
    def _run_batch_analysis(self, stock_list: List[str], message: BotMessage) -> None:
        """后台执行批量分析"""
        try:
            from src.config import get_config
            from main import StockAnalysisPipeline
            
            config = get_config()
            
            # 创建分析管道
            pipeline = StockAnalysisPipeline(
                config=config,
                source_message=message,
                query_id=uuid.uuid4().hex,
                query_source="bot"
            )
            
            # 执行分析
            results = pipeline.run(
                stock_codes=stock_list,
                dry_run=False
            )
            
            logger.info(f"[BatchCommand] 批量分析完成，成功 {len(results)} 只")
            
        except Exception as e:
            logger.error(f"[BatchCommand] 批量分析失败: {e}")
            logger.exception(e)
