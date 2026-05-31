# -*- coding: utf-8 -*-
"""Calculate current portfolio equity ratio vs total assets (in CNY).

Equity weight by risk_class (from asset_risk_definitions table):
  R1 * 0%  (cash, R1)
  R2 * 5%  (bonds, R2)
  R3 * 20% (mixed, R3)
  R4 *100% (equity, R4)
  R5 *100% (equity, R5)

Formula: equity = R1*0 + R2*0.05 + R3*0.20 + R4 + R5
         ratio  = equity / total (all already converted to CNY)
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def calculate_equity_ratio() -> Dict[str, Any]:
    """Read current asset positions from DB and compute equity ratio.

    Reads equity weights from asset_risk_definitions table.
    Falls back to hardcoded defaults if definitions not found.

    Returns:
        {
            "equity_ratio": 0.72,
            "total_cny": 2000000.0,
            "equity_cny": 1440000.0,
            "detail": {
                "R1": {"total": 370000, "equity": 0, "weight": 0.0, "name": "现金/货基"},
                "R2": {"total": 500000, "equity": 25000, "weight": 0.05, "name": "纯债/短久期"},
                "R3": {"total": 800000, "equity": 160000, "weight": 0.20, "name": "固收+"},
                "R4": {"total": 100000, "equity": 100000, "weight": 1.0, "name": "宽基/价值"},
                "R5": {"total": 230000, "equity": 230000, "weight": 1.0, "name": "行业/个股"},
            }
        }
    """
    from src.storage import get_db

    db = get_db()

    equity_weight_map = {
        "R1": 0.0,
        "R2": 0.05,
        "R3": 0.20,
        "R4": 1.0,
        "R5": 1.0,
    }
    risk_names = {
        "R1": "现金/货基",
        "R2": "纯债/短久期",
        "R3": "固收+",
        "R4": "宽基/价值",
        "R5": "行业/个股",
    }

    try:
        with db.get_session() as session:
            from src.storage import AssetRiskDefinition
            definitions = session.query(AssetRiskDefinition).filter(
                AssetRiskDefinition.is_active == True
            ).all()
            for definition in definitions:
                equity_weight_map[definition.asset_risk_class] = definition.equity_weight
                risk_names[definition.asset_risk_class] = definition.name
    except Exception as exc:
        logger.warning("读取资产风险等级定义失败，使用默认权重：%s", exc)

    rows = []
    with db.get_session() as session:
        from src.storage import PortfolioPosition
        result = session.query(PortfolioPosition).filter(
            PortfolioPosition.quantity > 0
        ).all()
        rows = list(result)

    # FX rates in DB (latest known rates)
    fx_rates = {}
    try:
        conn = db._engine.connect()
        from sqlalchemy import text
        rate_rows = conn.execute(text(
            "SELECT currency, rate FROM fx_rates ORDER BY as_of_date DESC LIMIT 10"
        )).fetchall()
        # Take latest per currency
        seen = set()
        for r in rate_rows:
            if r[0] not in seen:
                fx_rates[r[0]] = float(r[1])
                seen.add(r[0])
        conn.close()
    except Exception:
        pass

    # Fallback FX rates
    if "USD" not in fx_rates: fx_rates["USD"] = 7.20
    if "HKD" not in fx_rates: fx_rates["HKD"] = 0.92
    if "CNY" not in fx_rates: fx_rates["CNY"] = 1.0

    group_by_risk = {}
    for pos in rows:
        risk = pos.asset_risk_class or "R5"
        mv = float(pos.market_value_base or 0.0)
        # If market_value_base not populated, use quantity * price * fx rate
        if mv <= 0:
            local_mv = float(pos.quantity or 0.0) * float(pos.last_price or 0.0)
            rate = fx_rates.get(pos.currency, 1.0)
            mv = local_mv * rate

        if risk not in group_by_risk:
            group_by_risk[risk] = 0.0
        group_by_risk[risk] += mv

    detail = {}
    total_cny = 0.0
    equity_cny = 0.0
    for risk_class in ["R1", "R2", "R3", "R4", "R5"]:
        total = group_by_risk.get(risk_class, 0.0)
        total_cny += total
        weight = equity_weight_map.get(risk_class, 1.0)
        eq = total * weight
        equity_cny += eq
        detail[risk_class] = {
            "total": round(total, 2),
            "equity": round(eq, 2),
            "weight": weight,
            "name": risk_names.get(risk_class, risk_class),
        }

    ratio = equity_cny / total_cny if total_cny > 0 else 0.0

    return {
        "equity_ratio": round(ratio, 4),
        "total_cny": round(total_cny, 2),
        "equity_cny": round(equity_cny, 2),
        "detail": detail,
    }
