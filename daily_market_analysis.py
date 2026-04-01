
import sys
import os
import logging
import time

# Add project root to sys.path
sys.path.append(os.getcwd())

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8')

from src.config import get_config, setup_env
from src.core.pipeline import StockAnalysisPipeline
from src.logging_config import setup_logging

def print_separator(title=""):
    width = 60
    if title:
        print(f"\n{'=' * 20} {title} {'=' * 20}")
    else:
        print(f"{'=' * width}")

def main():
    # Setup environment and logging
    setup_env()
    config = get_config()
    setup_logging(log_prefix="daily_analysis", debug=config.debug, log_dir=config.log_dir)
    
    logger = logging.getLogger(__name__)
    
    try:
        pipeline = StockAnalysisPipeline(config=config)
        
        # --- Stage 1: Analyze My Stocks ---
        print_separator("第一阶段：分析自选股")
        
        my_stocks = config.stock_list
        if not my_stocks:
            print("❌ 自选股列表为空，请检查 .env 配置")
        else:
            print(f"📋 自选股列表 ({len(my_stocks)}只): {', '.join(my_stocks)}")
            print("🚀 开始分析...")
            
            results = pipeline.run(
                stock_codes=my_stocks,
                dry_run=False,
                send_notification=False  # Don't send notification here, we print to console
            )
            
            print_separator("自选股分析报告")
            for r in results:
                # Basic Info
                code = r.code
                name = r.name
                emoji = "📈" if r.sentiment_score >= 60 else "📉"
                
                print(f"\n{emoji} 【{name}】({code})")
                print(f"   📊 综合评分: {r.sentiment_score}/100")
                print(f"   🔮 趋势预测: {r.trend_prediction}")
                print(f"   💡 操作建议: {r.operation_advice}")
                
                # Context Info (Money Flow & Financials)
                if r.dashboard and 'data_perspective' in r.dashboard:
                    dp = r.dashboard['data_perspective']
                    extras = []
                    
                    if 'money_flow' in dp:
                        mf = dp['money_flow']
                        inflow = mf.get('main_net_inflow', 'N/A')
                        if inflow != 'N/A':
                            extras.append(f"主力净流入: {inflow}")
                            
                    if 'financial_health' in dp:
                        fin = dp['financial_health']
                        roe = fin.get('roe', 'N/A')
                        if roe != 'N/A':
                            extras.append(f"ROE: {roe}%")
                            
                    if extras:
                        print(f"   💰 {' | '.join(extras)}")
                
                # Core Conclusion
                conclusion = r.get_core_conclusion()
                if conclusion:
                    print(f"   📝 核心观点: {conclusion}")
        
        # --- Stage 2: Screen Market Stocks ---
        print("\n\n")
        print_separator("第二阶段：全市场精选推荐")
        print("🔍 正在扫描全市场股票（基于技术形态和基本面筛选）...")
        
        # Note: screen_market_stocks returns a dict {'buy': [], 'watch': []}
        screen_results = pipeline.screen_market_stocks()
        
        buy_list = screen_results.get('buy', [])
        
        if not buy_list:
            print("⚠️ 未筛选到强力买入信号的股票。")
        else:
            print(f"🎉 筛选出 {len(buy_list)} 只推荐买入股票：")
            for i, stock in enumerate(buy_list[:5], 1):
                code = stock.get('code')
                name = stock.get('name')
                score = stock.get('score', 'N/A')
                reason = stock.get('reason', '技术形态突破')
                
                print(f"\n🏆 推荐 #{i}: {name} ({code})")
                print(f"   评分: {score}")
                print(f"   推荐理由: {reason}")
                
        print("\n")
        print_separator("分析完成")
        
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        print(f"❌ 发生错误: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
