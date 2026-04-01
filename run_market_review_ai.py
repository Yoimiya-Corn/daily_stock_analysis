
import sys
import os
import logging

# Add project root to sys.path
sys.path.append(os.getcwd())

from src.config import get_config, setup_env
from src.market_analyzer import MarketAnalyzer
from src.analyzer import GeminiAnalyzer
from src.search_service import SearchService

def main():
    setup_env()
    config = get_config()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    
    logger = logging.getLogger(__name__)
    
    print("🚀 初始化 AI 分析器...")
    analyzer = GeminiAnalyzer()
    
    print("🚀 初始化搜索服务...")
    search_service = SearchService(
        bocha_keys=config.bocha_api_keys,
        tavily_keys=config.tavily_api_keys,
        brave_keys=config.brave_api_keys,
        serpapi_keys=config.serpapi_keys,
    )
    
    market_analyzer = MarketAnalyzer(
        search_service=search_service,
        analyzer=analyzer
    )
    
    print("📊 开始大盘复盘分析...")
    report = market_analyzer.run_daily_review()
    
    print("\n" + "="*20 + " 大盘复盘报告 " + "="*20)
    print(report)
    print("="*54)

if __name__ == "__main__":
    main()
