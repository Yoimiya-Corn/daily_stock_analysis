
import logging
import sys
import os

# Add project root to sys.path
sys.path.append(os.getcwd())

from src.config import get_config, setup_env
from src.core.pipeline import StockAnalysisPipeline
from src.logging_config import setup_logging

def main():
    # Setup environment and logging
    setup_env()
    config = get_config()
    setup_logging(log_prefix="my_stocks", debug=config.debug, log_dir=config.log_dir)
    
    logger = logging.getLogger(__name__)
    
    try:
        print(f"当前配置的自选股列表: {config.stock_list}", flush=True)
        
        if not config.stock_list:
            print("自选股列表为空，请检查 .env 配置", flush=True)
            return

        logger.info("=" * 60)
        logger.info("开始分析自选股...")
        logger.info("=" * 60)
        
        # Initialize pipeline
        pipeline = StockAnalysisPipeline(config=config)
        
        # Run analysis
        results = pipeline.run(
            stock_codes=config.stock_list,
            dry_run=False,
            send_notification=False
        )
        
        print("\n" + "="*30 + " 自选股分析结果 " + "="*30, flush=True)
        for r in results:
            emoji = r.get_emoji()
            print(f"\n{emoji} {r.name}({r.code})", flush=True)
            print(f"   评分: {r.sentiment_score} | 趋势: {r.trend_prediction}", flush=True)
            print(f"   建议: {r.operation_advice}", flush=True)
            print(f"   核心结论: {r.get_core_conclusion()}", flush=True)
            if r.current_price:
                print(f"   当前价格: {r.current_price} (涨跌: {r.change_pct}%)", flush=True)
            
            # 资金流向和财务数据展示 (如果有)
            if hasattr(r, 'context_snapshot') and r.context_snapshot:
                ctx = r.context_snapshot
                if 'money_flow_raw' in ctx and ctx['money_flow_raw']:
                    mf = ctx['money_flow_raw']
                    inflow = mf.get('主力净流入净额', 'N/A')
                    print(f"   💸 主力净流入: {inflow}", flush=True)
                if 'financial_raw' in ctx and ctx['financial_raw']:
                    fin = ctx['financial_raw']
                    roe = fin.get('净资产收益率', 'N/A')
                    print(f"   🏢 ROE: {roe}%", flush=True)

        print("\n" + "="*60, flush=True)
        print("分析完成！", flush=True)
        
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        print(f"FATAL ERROR: {e}", file=sys.stderr, flush=True)

if __name__ == "__main__":
    main()
