# -*- coding: utf-8 -*-
"""
新闻数据获取器
"""
import logging
from typing import List, Dict, Optional
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)

class NewsFetcher:
    """
    新闻数据获取器
    
    主要通过 AkShare 获取个股新闻、公告等免费数据源
    作为 SearchService 的免费替代或补充
    """
    
    def fetch_stock_news(self, stock_code: str, top_n: int = 5) -> List[Dict[str, str]]:
        """
        获取个股新闻 (东方财富)
        
        Args:
            stock_code: 股票代码
            top_n: 返回最新的 N 条新闻
            
        Returns:
            新闻列表 [{'title': '...', 'publish_time': '...', 'url': '...'}, ...]
        """
        import akshare as ak
        
        try:
            logger.info(f"[{stock_code}] 正在获取个股新闻(AkShare)...")
            # ak.stock_news_em(symbol="600519")
            df = ak.stock_news_em(symbol=stock_code)
            
            if df is None or df.empty:
                return []
                
            # 按发布时间排序（如果有）
            if '发布时间' in df.columns:
                df['发布时间'] = pd.to_datetime(df['发布时间'])
                df = df.sort_values('发布时间', ascending=False)
            
            news_list = []
            for _, row in df.head(top_n).iterrows():
                item = {
                    'title': str(row.get('新闻标题', '')),
                    'publish_time': str(row.get('发布时间', '')),
                    'content': str(row.get('新闻内容', ''))[:200] + '...', # 截取部分内容
                    'url': str(row.get('新闻链接', '')),
                    'source': '东方财富'
                }
                news_list.append(item)
                
            logger.info(f"[{stock_code}] 获取到 {len(news_list)} 条新闻")
            return news_list
            
        except Exception as e:
            logger.warning(f"[{stock_code}] 获取个股新闻失败: {e}")
            return []

    def fetch_stock_research_reports(self, stock_code: str, top_n: int = 3) -> List[Dict[str, str]]:
        """
        获取个股研报 (东方财富)
        """
        import akshare as ak
        
        try:
            logger.info(f"[{stock_code}] 正在获取个股研报(AkShare)...")
            # ak.stock_research_report_em(symbol="600519")
            df = ak.stock_research_report_em(symbol=stock_code)
            
            if df is None or df.empty:
                return []
                
            # 按日期排序
            if '日期' in df.columns:
                df['日期'] = pd.to_datetime(df['日期'])
                df = df.sort_values('日期', ascending=False)
                
            reports = []
            for _, row in df.head(top_n).iterrows():
                item = {
                    'title': str(row.get('报告名称', '')),
                    'publish_time': str(row.get('日期', '')),
                    'rating': str(row.get('东财评级', '')),
                    'org': str(row.get('机构', '')),
                    'url': str(row.get('报告PDF链接', '')),
                    'source': '东方财富研报'
                }
                reports.append(item)
                
            logger.info(f"[{stock_code}] 获取到 {len(reports)} 条研报")
            return reports
            
        except Exception as e:
            logger.warning(f"[{stock_code}] 获取个股研报失败: {e}")
            return []

    def format_news_context(self, news_list: List[Dict], reports_list: List[Dict]) -> str:
        """
        格式化新闻和研报为文本上下文
        """
        context_parts = []
        
        if news_list:
            context_parts.append("### 📰 最新个股新闻 (来源: 东方财富)")
            for news in news_list:
                context_parts.append(f"- [{news['publish_time']}] {news['title']}")
        
        if reports_list:
            context_parts.append("\n### 📑 最新机构研报")
            for report in reports_list:
                rating = f"[{report['rating']}]" if report['rating'] else ""
                context_parts.append(f"- [{report['publish_time']}] {report['org']}{rating}: {report['title']}")
                
        return "\n".join(context_parts)
