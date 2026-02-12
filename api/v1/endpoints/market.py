# -*- coding: utf-8 -*-
"""
===================================
全市场选股推荐接口
===================================

职责：
1. 提供 GET /api/v1/market/recommendations 全市场推荐接口
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException

from api.v1.schemas.market import MarketRecommendationsResponse, RecommendationItem
from api.v1.schemas.common import ErrorResponse
from src.core.pipeline import StockAnalysisPipeline

logger = logging.getLogger(__name__)

router = APIRouter()

# 模块级缓存：避免短时间内重复筛选
_cache = {
    'data': None,
    'timestamp': 0,
    'ttl': 300,  # 5分钟缓存
}


@router.get(
    "/recommendations",
    response_model=MarketRecommendationsResponse,
    responses={
        200: {"description": "全市场选股推荐"},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取全市场选股推荐",
    description="基于全A股实时行情数据，按量价、估值、趋势等指标自动筛选买入和观察推荐",
)
def get_market_recommendations() -> MarketRecommendationsResponse:
    """
    获取全市场选股推荐

    Returns:
        MarketRecommendationsResponse: 买入推荐 + 观察推荐列表
    """
    import time

    now = time.time()

    # 检查缓存
    if (_cache['data'] is not None
            and now - _cache['timestamp'] < _cache['ttl']):
        logger.info("[API] 全市场推荐命中缓存")
        return _cache['data']

    try:
        pipeline = StockAnalysisPipeline()
        raw = pipeline.screen_market_stocks()

        buy_items = [RecommendationItem(**item) for item in raw.get('buy', [])]
        watch_items = [RecommendationItem(**item) for item in raw.get('watch', [])]

        response = MarketRecommendationsResponse(
            buy=buy_items,
            watch=watch_items,
            updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )

        # 写入缓存
        _cache['data'] = response
        _cache['timestamp'] = now

        logger.info(f"[API] 全市场推荐: buy={len(buy_items)}, watch={len(watch_items)}")
        return response

    except Exception as e:
        logger.error(f"[API] 全市场推荐失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "screening_failed", "message": f"全市场筛选失败: {str(e)}"},
        )
