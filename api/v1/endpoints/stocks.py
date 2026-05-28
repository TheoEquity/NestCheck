# -*- coding: utf-8 -*-
"""
===================================
股票数据接口
===================================

职责：
1. POST /api/v1/stocks/extract-from-image 从图片提取股票代码
2. POST /api/v1/stocks/parse-import 解析 CSV/Excel/剪贴板
3. GET /api/v1/stocks/{code}/quote 实时行情接口
4. GET /api/v1/stocks/{code}/history 历史行情接口
5. GET /api/v1/stocks/{code}/intraday 分时图数据接口
"""

import logging
from typing import Optional, List, Any

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile

from api.v1.schemas.stocks import (
    ExtractFromImageResponse,
    ExtractItem,
    KLineData,
    StockHistoryResponse,
    StockQuote,
)
from api.v1.schemas.common import ErrorResponse
from src.services.image_stock_extractor import (
    ALLOWED_MIME,
    MAX_SIZE_BYTES,
    extract_stock_codes_from_image,
)
from src.services.import_parser import (
    MAX_FILE_BYTES,
    parse_import_from_bytes,
    parse_import_from_text,
)
from src.services.stock_service import StockService

logger = logging.getLogger(__name__)

router = APIRouter()

# 须在 /{stock_code} 路由之前定义
ALLOWED_MIME_STR = ", ".join(ALLOWED_MIME)


@router.post(
    "/extract-from-image",
    response_model=ExtractFromImageResponse,
    responses={
        200: {"description": "提取的股票代码"},
        400: {"description": "图片无效", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="从图片提取股票代码",
    description="上传截图/图片，通过 Vision LLM 提取股票代码。支持 JPEG、PNG、WebP、GIF，最大 5MB。",
)
def extract_from_image(
    file: Optional[UploadFile] = File(None, description="图片文件（表单字段名 file）"),
    include_raw: bool = Query(False, description="是否在结果中包含原始 LLM 响应"),
) -> ExtractFromImageResponse:
    """
    从上传的图片中提取股票代码（使用 Vision LLM）。

    表单字段请使用 file 上传图片。优先级：Gemini / Anthropic / OpenAI（首个可用）。
    """
    if not file or not file.filename:
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_request", "message": "未提供文件，请使用表单字段 file 上传图片"},
        )

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_type",
                "message": f"不支持的类型：{content_type}。允许：{ALLOWED_MIME_STR}",
            },
        )

    try:
        file_size = 0
        content = b""
        for chunk in file.file:
            content += chunk
            file_size += len(chunk)
            if file_size > MAX_SIZE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail={
                        "error": "file_too_large",
                        "message": f"文件过大，最大 {MAX_SIZE_BYTES // 1024 // 1024}MB",
                    },
                )

        items = extract_stock_codes_from_image(content=content)
        return ExtractFromImageResponse(
            success=len(items) > 0,
            items=items,
            raw_text=None if not include_raw else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"图片提取失败：{e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "extraction_failed",
                "message": f"提取失败：{str(e)}",
            },
        )


@router.post(
    "/parse-import",
    response_model=ExtractFromImageResponse,
    summary="解析导入数据",
    description="解析 CSV/Excel/剪贴板文本，提取股票代码和数量。",
)
def parse_import_endpoint(
    file: Optional[UploadFile] = File(None, description="CSV/Excel 文件"),
    text: Optional[str] = Query(None, description="剪贴板文本"),
) -> ExtractFromImageResponse:
    """
    解析导入数据（CSV/Excel/剪贴板）。

    优先使用 file，若未提供则使用 text 参数。
    """
    try:
        if file:
            content = file.file.read()
            if len(content) > MAX_FILE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail={"error": "file_too_large", "message": "文件过大"},
                )
            items, raw_text = parse_import_from_bytes(content, file.content_type)
        elif text:
            items, raw_text = parse_import_from_text(text)
        else:
            raise HTTPException(
                status_code=400,
                detail={"error": "bad_request", "message": "请提供 file 或 text 参数"},
            )

        return ExtractFromImageResponse(
            success=len(items) > 0,
            items=items,
            raw_text=raw_text,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "parse_failed", "message": str(e)})
    except Exception as e:
        logger.error(f"解析导入失败：{e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"解析失败：{str(e)}"},
        )


@router.get(
    "/{stock_code}/quote",
    response_model=StockQuote,
    responses={
        200: {"description": "实时行情"},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取实时行情",
    description="获取指定股票的实时行情数据",
)
def get_stock_quote(stock_code: str) -> StockQuote:
    """
    获取股票实时行情

    Args:
        stock_code: 股票代码

    Returns:
        StockQuote: 实时行情数据
    """
    try:
        service = StockService()
        result = service.get_realtime_quote(stock_code)

        if not result:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": f"无法获取 {stock_code} 的行情数据",
                },
            )

        return StockQuote(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取实时行情失败：{e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取行情失败：{str(e)}",
            },
        )


@router.get(
    "/{stock_code}/history",
    response_model=StockHistoryResponse,
    responses={
        200: {"description": "历史行情"},
        422: {"description": "不支持的周期", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取历史行情",
    description="获取指定股票的历史 K 线数据",
)
def get_stock_history(
    stock_code: str,
    period: str = Query("daily", description="K 线周期", pattern="^(daily|weekly|monthly)$"),
    days: int = Query(30, ge=1, le=365, description="获取天数")
) -> StockHistoryResponse:
    """
    获取股票历史行情

    获取指定股票的历史 K 线数据

    Args:
        stock_code: 股票代码
        period: K 线周期 (daily/weekly/monthly)
        days: 获取天数

    Returns:
        StockHistoryResponse: 历史行情数据
    """
    try:
        service = StockService()

        # 使用 def 而非 async def，FastAPI 自动在线程池中执行
        result = service.get_history_data(
            stock_code=stock_code,
            period=period,
            days=days
        )

        # 转换为响应模型
        data = [
            KLineData(
                date=item.get("date"),
                open=item.get("open"),
                high=item.get("high"),
                low=item.get("low"),
                close=item.get("close"),
                volume=item.get("volume"),
                amount=item.get("amount"),
                change_percent=item.get("change_percent")
            )
            for item in result.get("data", [])
        ]

        return StockHistoryResponse(
            stock_code=stock_code,
            stock_name=result.get("stock_name"),
            period=period,
            data=data
        )

    except ValueError as e:
        # period 参数不支持的错误（如 weekly/monthly）
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unsupported_period",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error(f"获取历史行情失败：{e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取历史行情失败：{str(e)}"
            }
        )


@router.get(
    "/{stock_code}/intraday",
    response_model=StockHistoryResponse,
    responses={
        200: {"description": "分时图数据"},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取分时图数据",
    description="获取指定股票的分时图（分钟线）数据，缓存 60 秒",
)
def get_stock_intraday(
    stock_code: str,
    days: int = Query(1, ge=1, le=5, description="获取天数（1-5 天）")
) -> StockHistoryResponse:
    """
    获取股票分时图数据（分钟线）

    获取指定股票的分时图数据，包含分钟级别的开盘、收盘、最高、最低价。
    数据缓存 60 秒，减少重复请求。

    Args:
        stock_code: 股票代码
        days: 获取天数（1-5 天）

    Returns:
        StockHistoryResponse: 分时图数据
    """
    try:
        service = StockService()

        result = service.get_intraday_data(
            stock_code=stock_code,
            days=days
        )

        if not result or 'data' not in result:
            return StockHistoryResponse(
                stock_code=stock_code,
                stock_name=None,
                period="1m",
                data=[]
            )

        # 转换为响应模型
        data = [
            KLineData(
                date=item.get("date"),
                open=item.get("open"),
                high=item.get("high"),
                low=item.get("low"),
                close=item.get("close"),
                volume=item.get("volume"),
                amount=item.get("amount"),
                change_percent=item.get("change_percent")
            )
            for item in result.get("data", [])
        ]

        return StockHistoryResponse(
            stock_code=stock_code,
            stock_name=result.get("stock_name"),
            period="1m",
            data=data
        )

    except Exception as e:
        logger.error(f"获取分时图失败：{e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取分时图失败：{str(e)}"
            }
        )
