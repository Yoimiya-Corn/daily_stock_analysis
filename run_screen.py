"""全市场筛选脚本 - 独立运行"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(__file__))
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUNBUFFERED'] = '1'

import logging

log_file = os.path.join(os.path.dirname(__file__), 'logs', 'screen_result.log')
os.makedirs(os.path.dirname(log_file), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
    ]
)

logger = logging.getLogger('screen')
logger.info("=== 开始全市场筛选 ===")

from src.core.pipeline import StockAnalysisPipeline

pipeline = StockAnalysisPipeline()
results = pipeline.screen_market_stocks()

# results 是 {'buy': [...], 'watch': [...]}
buy_list = results.get('buy', []) if isinstance(results, dict) else []
watch_list = results.get('watch', []) if isinstance(results, dict) else []

logger.info(f"=== 筛选完成，买入推荐 {len(buy_list)} 只，观察 {len(watch_list)} 只 ===")

print("\n" + "="*60)
print(f"全市场筛选完成 | 买入推荐{len(buy_list)}只 | 观察{len(watch_list)}只")
print("="*60)

def get_one_line(r):
    try:
        if isinstance(r, dict):
            dash = r.get('dashboard', {})
            if isinstance(dash, dict):
                return dash.get('core_conclusion', {}).get('one_sentence', '')
        result_obj = getattr(r, 'analysis_result', None)
        if result_obj and isinstance(result_obj, dict):
            return result_obj.get('dashboard', {}).get('core_conclusion', {}).get('one_sentence', '')
    except:
        pass
    return ''

def get_field(r, *keys):
    for k in keys:
        if isinstance(r, dict):
            v = r.get(k)
        else:
            v = getattr(r, k, None)
        if v is not None:
            return v
    return ''

print("\n【买入推荐】")
for i, r in enumerate(buy_list[:5], 1):
    code = get_field(r, 'stock_code', 'code')
    name = get_field(r, 'stock_name', 'name')
    score = get_field(r, 'total_score', 'sentiment_score', 'score')
    trend = get_field(r, 'trend_prediction', 'trend')
    advice = get_field(r, 'operation_advice', 'advice')
    one_line = get_one_line(r)
    print(f"#{i} [{code}] {name} | 评分:{score} | 趋势:{trend} | 建议:{advice}")
    if one_line:
        print(f"   {one_line}")

if watch_list:
    print("\n【观察名单】")
    for i, r in enumerate(watch_list[:5], 1):
        code = get_field(r, 'stock_code', 'code')
        name = get_field(r, 'stock_name', 'name')
        score = get_field(r, 'total_score', 'sentiment_score', 'score')
        trend = get_field(r, 'trend_prediction', 'trend')
        print(f"#{i} [{code}] {name} | 评分:{score} | 趋势:{trend}")
