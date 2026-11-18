"""客户信息只读接口：管理员页面调用并展示政策使用者对应的模拟客户数据。

数据来自 seed/synthetic_customers.json，均为合成演示数据，非真实客户信息。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import require_api_key, require_roles
from app.db.session import get_db
from app.domain.exposure import load_customers

router = APIRouter(prefix="/customers", tags=["customers"], dependencies=[Depends(require_api_key)])


@router.get("")
def list_customers(
    _: str = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    """返回模拟客户列表（合成数据，非真实客户）。"""
    customers = load_customers()
    items = [
        {
            "customer_id": c.get("customer_id"),
            "name_masked": c.get("name_masked"),
            "business_line": c.get("business_line"),
            "segment": c.get("segment"),
            "region": c.get("region"),
            "loan_balance_cny_yi": c.get("loan_balance_cny_yi", 0),
            "other_bank_loans_cny_yi": c.get("other_bank_loans_cny_yi", 0),
            "overseas_business": c.get("overseas_business", []),
            "products": c.get("products", []),
            "relationship_manager": c.get("relationship_manager", ""),
        }
        for c in customers
    ]
    return {"items": items, "total": len(items), "is_synthetic": True}
