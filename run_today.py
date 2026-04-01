# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
sys.path.insert(0, r'd:\vscode\gu\daily_stock_analysis')

from src.core.pipeline import StockAnalysisPipeline
from src.enums import ReportType

STOCKS = [
    '600519','300750','002594','002009',
    '601398','601288','601988','601939',
    'hk01810','000400','600101','000564'
]

from src.storage import DatabaseManager
from datetime import date

pipeline = StockAnalysisPipeline()

for code in STOCKS:
    print(f'[分析] {code} ...', flush=True)
    try:
        r = pipeline.analyze_stock(code, ReportType.SIMPLE)
        if r and r.success:
            print(f'  OK: {r.name} {r.sentiment_score}分 {r.operation_advice}', flush=True)
        else:
            print(f'  FAIL: {code}', flush=True)
    except Exception as e:
        print(f'  ERROR: {code} {e}', flush=True)

# 从数据库读取完整结果
import datetime
today = datetime.date.today()
db = DatabaseManager()
records, total = db.get_analysis_history_paginated(None, today, today, 0, 50)
print(f'\n========== 今日自选股分析结果 {today} ({total}条) ==========')
for r in sorted(records, key=lambda x: x.sentiment_score or 0, reverse=True):
    print(f'\n{r.sentiment_score}分 | {r.name}({r.code}) | {r.operation_advice} | {r.trend_prediction}')
    print(f'  买:{r.ideal_buy}  次买:{r.secondary_buy}  损:{r.stop_loss}  盈:{r.take_profit}')
    print(f'  {(r.analysis_summary or "")[:120]}')
print('\n分析完成')
