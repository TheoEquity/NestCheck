# -*- coding: utf-8 -*-
"""Runtime background scheduler tasks for the FastAPI app lifecycle."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI

logger = logging.getLogger(__name__)

PORTFOLIO_PRICE_REFRESH_TASK_KEY = "market_cache_refresh"
PORTFOLIO_PRICE_REFRESH_TIMES = ((8, 30), (20, 30))


async def start_runtime_scheduler_tasks(app: FastAPI) -> None:
    """Start app-lifecycle background tasks and store handles on app.state."""
    app.state._price_refresh_task = asyncio.create_task(_daily_portfolio_price_refresh())
    app.state._market_refresh_task = asyncio.create_task(_daily_market_cache_refresh_loop())
    app.state._startup_catch_up_task = asyncio.create_task(_startup_catch_up_check())


async def stop_runtime_scheduler_tasks(app: FastAPI) -> None:
    """Cancel app-lifecycle background tasks created by start_runtime_scheduler_tasks."""
    task_names = (
        "_price_refresh_task",
        "_market_refresh_task",
        "_startup_catch_up_task",
    )
    tasks = [getattr(app.state, name, None) for name in task_names]
    for task in tasks:
        if task is not None:
            task.cancel()
    for task in tasks:
        if task is None:
            continue
        try:
            await task
        except asyncio.CancelledError:
            pass
    for name in task_names:
        if hasattr(app.state, name):
            delattr(app.state, name)


async def _startup_catch_up_check() -> None:
    """Check whether today's full sync has run, and trigger it when stale."""
    from src.storage import MarketCache, get_db
    from src.task_history import task_history
    from src.services.scheduler_jobs import run_daily_market_cache_refresh

    beijing_tz = timezone(timedelta(hours=8))
    await asyncio.sleep(45)

    try:
        now = datetime.now(beijing_tz)
        today = now.date()

        is_fresh = False
        with get_db().get_session() as session:
            trend_row = session.query(MarketCache).filter_by(cache_key="trend").one_or_none()
            if trend_row and trend_row.created_at.date() == today:
                is_fresh = True

        if not is_fresh:
            for item in task_history.get_history("market_cache_refresh", limit=5):
                try:
                    executed_at = datetime.fromisoformat(item["executed_at"])
                    if executed_at.tzinfo is None:
                        executed_at = executed_at.replace(tzinfo=beijing_tz)
                    else:
                        executed_at = executed_at.astimezone(beijing_tz)
                    if executed_at.date() == today and item.get("status") == "success":
                        is_fresh = True
                        break
                except Exception:
                    continue

        if not is_fresh:
            logger.info("Startup catch-up: No fresh data for %s. Triggering full daily sync.", today)
            with ThreadPoolExecutor(max_workers=1) as executor:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(executor, run_daily_market_cache_refresh)
            task_history.record("market_cache_refresh", "success", duration_ms=0)
            logger.info("Startup catch-up: Full sync finished.")
        else:
            logger.info("Startup catch-up: Data for %s is up-to-date. Skipping.", today)
    except Exception as exc:
        logger.warning("Startup catch-up check failed: %s", exc)


async def _daily_portfolio_price_refresh() -> None:
    """Refresh portfolio position prices at 08:30 and 20:30 Beijing time."""
    beijing_tz = timezone(timedelta(hours=8))
    now = datetime.now(beijing_tz)
    today = now.date()
    last_refresh_slots = set()

    try:
        for slot in PORTFOLIO_PRICE_REFRESH_TIMES:
            if _is_refresh_slot_due(now, slot):
                last_refresh_slots.add((today, slot))
                logger.info("Startup: Slot %02d:%02d is past; marked as handled", slot[0], slot[1])
    except Exception as exc:
        logger.error("Startup check failed: %s", exc, exc_info=True)

    await asyncio.sleep(30)

    with ThreadPoolExecutor(max_workers=1) as executor:
        while True:
            try:
                now = datetime.now(beijing_tz)
                today = now.date()
                for slot in PORTFOLIO_PRICE_REFRESH_TIMES:
                    slot_key = (today, slot)
                    if _is_refresh_slot_due(now, slot) and slot_key not in last_refresh_slots:
                        logger.info("Daily portfolio price refresh started for %02d:%02d", slot[0], slot[1])
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(executor, _run_price_refresh_with_history)
                        last_refresh_slots.add(slot_key)
                        logger.info("Daily portfolio price refresh completed for %02d:%02d", slot[0], slot[1])
                        break

                if len(last_refresh_slots) > len(PORTFOLIO_PRICE_REFRESH_TIMES) * 2:
                    last_refresh_slots = {
                        item for item in last_refresh_slots
                        if item[0] >= today - timedelta(days=1)
                    }
            except Exception as exc:
                logger.error("Portfolio price refresh error: %s", exc)

            await asyncio.sleep(30)


def _is_refresh_slot_due(now: datetime, slot: tuple[int, int]) -> bool:
    hour, minute = slot
    return now.hour > hour or (now.hour == hour and now.minute >= minute)


def _run_price_refresh_with_history() -> None:
    """Run price refresh and record automatic scheduler history."""
    import time
    from src.task_history import task_history

    start = time.time()
    try:
        from src.services.scheduler_jobs import run_daily_market_cache_refresh

        run_daily_market_cache_refresh()
        task_history.record(
            PORTFOLIO_PRICE_REFRESH_TASK_KEY,
            "success",
            duration_ms=int((time.time() - start) * 1000),
        )
    except Exception as exc:
        task_history.record(
            PORTFOLIO_PRICE_REFRESH_TASK_KEY,
            "failed",
            duration_ms=int((time.time() - start) * 1000),
            error=str(exc),
        )
        raise


async def _daily_market_cache_refresh_loop() -> None:
    """Refresh market dashboard cache during A-share trading hours."""
    refresh_interval_seconds = 300

    with ThreadPoolExecutor(max_workers=1) as executor:
        await asyncio.sleep(30)
        while True:
            now = datetime.now(timezone.utc).replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8)))
            if now.weekday() < 5 and 9 <= now.hour < 15:
                try:
                    logger.info("Market cache refresh started")
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(executor, _run_market_cache_refresh)
                    logger.info("Market cache refresh completed")
                except Exception as exc:
                    logger.error("Market cache refresh error: %s", exc, exc_info=True)

            await asyncio.sleep(refresh_interval_seconds)


def _run_market_cache_refresh() -> None:
    """Synchronous wrapper for market cache refresh."""
    from src.services.market_cache_service import refresh_all_market_caches

    result = refresh_all_market_caches()
    items: dict[str, Any] = result.get("items", {})
    ok_count = sum(1 for item in items.values() if item.get("status") == "success")
    logger.info("Market cache refresh: success=%d/%d", ok_count, len(items))
