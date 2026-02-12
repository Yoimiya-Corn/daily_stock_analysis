# -*- coding: utf-8 -*-
"""
===================================
全市场选股推荐 - 响应模型
===================================
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class RecommendationItem(BaseModel):
    """单只推荐股票"""

    name: str = Field(..., description="股票名称")
    code: str = Field(..., description="股票代码")
    price: float = Field(..., description="最新价")
    change_pct: float = Field(..., description="涨跌幅(%)")
    volume_ratio: float = Field(0, description="量比")
    turnover_rate: float = Field(0, description="换手率(%)")
    pe: float = Field(0, description="市盈率")
    market_cap: str = Field("N/A", description="总市值(亿)")
    reason: str = Field("", description="推荐理由")
    change_60d: Optional[float] = Field(None, description="60日涨跌幅(%)")


class MarketRecommendationsResponse(BaseModel):
    """全市场推荐响应"""

    buy: List[RecommendationItem] = Field(default_factory=list, description="买入推荐")
    watch: List[RecommendationItem] = Field(default_factory=list, description="观察推荐")
    updated_at: str = Field(..., description="数据更新时间")

    class Config:
        json_schema_extra = {
            "example": {
                "buy": [
                    {
                        "name": "示例股票",
                        "code": "600519",
                        "price": 1800.0,
                        "change_pct": 3.5,
                        "volume_ratio": 2.1,
                        "turnover_rate": 1.2,
                        "pe": 35,
                        "market_cap": "22625亿",
                        "reason": "今日涨3.5%，量比2.1（放量），换手1.2%",
                    }
                ],
                "watch": [],
                "updated_at": "2025-02-11 15:00:00",
            }
        }
