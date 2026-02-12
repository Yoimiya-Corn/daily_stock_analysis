# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 核心分析流水线
===================================

职责：
1. 管理整个分析流程
2. 协调数据获取、存储、搜索、分析、通知等模块
3. 实现并发控制和异常处理
4. 提供股票分析的核心功能
"""

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import List, Dict, Any, Optional, Tuple

from src.config import get_config, Config
from src.storage import get_db
from data_provider import DataFetcherManager
from data_provider.realtime_types import ChipDistribution
from src.analyzer import GeminiAnalyzer, AnalysisResult, STOCK_NAME_MAP
from src.notification import NotificationService, NotificationChannel
from src.search_service import SearchService
from src.enums import ReportType
from src.stock_analyzer import StockTrendAnalyzer, TrendAnalysisResult
from bot.models import BotMessage


logger = logging.getLogger(__name__)


class StockAnalysisPipeline:
    """
    股票分析主流程调度器
    
    职责：
    1. 管理整个分析流程
    2. 协调数据获取、存储、搜索、分析、通知等模块
    3. 实现并发控制和异常处理
    """
    
    def __init__(
        self,
        config: Optional[Config] = None,
        max_workers: Optional[int] = None,
        source_message: Optional[BotMessage] = None,
        query_id: Optional[str] = None,
        query_source: Optional[str] = None,
        save_context_snapshot: Optional[bool] = None
    ):
        """
        初始化调度器
        
        Args:
            config: 配置对象（可选，默认使用全局配置）
            max_workers: 最大并发线程数（可选，默认从配置读取）
        """
        self.config = config or get_config()
        self.max_workers = max_workers or self.config.max_workers
        self.source_message = source_message
        self.query_id = query_id
        self.query_source = self._resolve_query_source(query_source)
        self.save_context_snapshot = (
            self.config.save_context_snapshot if save_context_snapshot is None else save_context_snapshot
        )
        
        # 初始化各模块
        self.db = get_db()
        self.fetcher_manager = DataFetcherManager()
        # 不再单独创建 akshare_fetcher，统一使用 fetcher_manager 获取增强数据
        self.trend_analyzer = StockTrendAnalyzer()  # 趋势分析器
        self.analyzer = GeminiAnalyzer()
        self.notifier = NotificationService(source_message=source_message)
        
        # 初始化搜索服务
        self.search_service = SearchService(
            bocha_keys=self.config.bocha_api_keys,
            tavily_keys=self.config.tavily_api_keys,
            brave_keys=self.config.brave_api_keys,
            serpapi_keys=self.config.serpapi_keys,
        )
        
        logger.info(f"调度器初始化完成，最大并发数: {self.max_workers}")
        logger.info("已启用趋势分析器 (MA5>MA10>MA20 多头判断)")
        # 打印实时行情/筹码配置状态
        if self.config.enable_realtime_quote:
            logger.info(f"实时行情已启用 (优先级: {self.config.realtime_source_priority})")
        else:
            logger.info("实时行情已禁用，将使用历史收盘价")
        if self.config.enable_chip_distribution:
            logger.info("筹码分布分析已启用")
        else:
            logger.info("筹码分布分析已禁用")
        if self.search_service.is_available:
            logger.info("搜索服务已启用 (Tavily/SerpAPI)")
        else:
            logger.warning("搜索服务未启用（未配置 API Key）")
    
    def fetch_and_save_stock_data(
        self, 
        code: str,
        force_refresh: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        获取并保存单只股票数据
        
        断点续传逻辑：
        1. 检查数据库是否已有今日数据
        2. 如果有且不强制刷新，则跳过网络请求
        3. 否则从数据源获取并保存
        
        Args:
            code: 股票代码
            force_refresh: 是否强制刷新（忽略本地缓存）
            
        Returns:
            Tuple[是否成功, 错误信息]
        """
        try:
            today = date.today()
            
            # 断点续传检查：如果今日数据已存在，跳过
            if not force_refresh and self.db.has_today_data(code, today):
                logger.info(f"[{code}] 今日数据已存在，跳过获取（断点续传）")
                return True, None
            
            # 从数据源获取数据
            logger.info(f"[{code}] 开始从数据源获取数据...")
            df, source_name = self.fetcher_manager.get_daily_data(code, days=30)
            
            if df is None or df.empty:
                return False, "获取数据为空"
            
            # 保存到数据库
            saved_count = self.db.save_daily_data(df, code, source_name)
            logger.info(f"[{code}] 数据保存成功（来源: {source_name}，新增 {saved_count} 条）")
            
            return True, None
            
        except Exception as e:
            error_msg = f"获取/保存数据失败: {str(e)}"
            logger.error(f"[{code}] {error_msg}")
            return False, error_msg
    
    def analyze_stock(self, code: str, report_type: ReportType) -> Optional[AnalysisResult]:
        """
        分析单只股票（增强版：含量比、换手率、筹码分析、多维度情报）
        
        流程：
        1. 获取实时行情（量比、换手率）- 通过 DataFetcherManager 自动故障切换
        2. 获取筹码分布 - 通过 DataFetcherManager 带熔断保护
        3. 进行趋势分析（基于交易理念）
        4. 多维度情报搜索（最新消息+风险排查+业绩预期）
        5. 从数据库获取分析上下文
        6. 调用 AI 进行综合分析
        
        Args:
            code: 股票代码
            report_type: 报告类型
            
        Returns:
            AnalysisResult 或 None（如果分析失败）
        """
        try:
            # 获取股票名称（优先从实时行情获取真实名称）
            stock_name = STOCK_NAME_MAP.get(code, '')
            
            # Step 1: 获取实时行情（量比、换手率等）- 使用统一入口，自动故障切换
            realtime_quote = None
            try:
                realtime_quote = self.fetcher_manager.get_realtime_quote(code)
                if realtime_quote:
                    # 使用实时行情返回的真实股票名称
                    if realtime_quote.name:
                        stock_name = realtime_quote.name
                    # 兼容不同数据源的字段（有些数据源可能没有 volume_ratio）
                    volume_ratio = getattr(realtime_quote, 'volume_ratio', None)
                    turnover_rate = getattr(realtime_quote, 'turnover_rate', None)
                    logger.info(f"[{code}] {stock_name} 实时行情: 价格={realtime_quote.price}, "
                              f"量比={volume_ratio}, 换手率={turnover_rate}% "
                              f"(来源: {realtime_quote.source.value if hasattr(realtime_quote, 'source') else 'unknown'})")
                else:
                    logger.info(f"[{code}] 实时行情获取失败或已禁用，将使用历史数据进行分析")
            except Exception as e:
                logger.warning(f"[{code}] 获取实时行情失败: {e}")
            
            # 如果还是没有名称，使用代码作为名称
            if not stock_name:
                stock_name = f'股票{code}'
            
            # Step 2: 获取筹码分布 - 使用统一入口，带熔断保护
            chip_data = None
            try:
                chip_data = self.fetcher_manager.get_chip_distribution(code)
                if chip_data:
                    logger.info(f"[{code}] 筹码分布: 获利比例={chip_data.profit_ratio:.1%}, "
                              f"90%集中度={chip_data.concentration_90:.2%}")
                else:
                    logger.debug(f"[{code}] 筹码分布获取失败或已禁用")
            except Exception as e:
                logger.warning(f"[{code}] 获取筹码分布失败: {e}")
            
            # Step 3: 趋势分析（基于交易理念）
            trend_result: Optional[TrendAnalysisResult] = None
            try:
                # 获取历史数据进行趋势分析
                context = self.db.get_analysis_context(code)
                if context and 'raw_data' in context:
                    import pandas as pd
                    raw_data = context['raw_data']
                    if isinstance(raw_data, list) and len(raw_data) > 0:
                        df = pd.DataFrame(raw_data)
                        trend_result = self.trend_analyzer.analyze(df, code)
                        logger.info(f"[{code}] 趋势分析: {trend_result.trend_status.value}, "
                                  f"买入信号={trend_result.buy_signal.value}, 评分={trend_result.signal_score}")
            except Exception as e:
                logger.warning(f"[{code}] 趋势分析失败: {e}")
            
            # Step 4: 多维度情报搜索（最新消息+风险排查+业绩预期）
            news_context = None
            if self.search_service.is_available:
                logger.info(f"[{code}] 开始多维度情报搜索...")
                
                # 使用多维度搜索（最多5次搜索）
                intel_results = self.search_service.search_comprehensive_intel(
                    stock_code=code,
                    stock_name=stock_name,
                    max_searches=5
                )
                
                # 格式化情报报告
                if intel_results:
                    news_context = self.search_service.format_intel_report(intel_results, stock_name)
                    total_results = sum(
                        len(r.results) for r in intel_results.values() if r.success
                    )
                    logger.info(f"[{code}] 情报搜索完成: 共 {total_results} 条结果")
                    logger.debug(f"[{code}] 情报搜索结果:\n{news_context}")

                    # 保存新闻情报到数据库（用于后续复盘与查询）
                    try:
                        query_context = self._build_query_context()
                        for dim_name, response in intel_results.items():
                            if response and response.success and response.results:
                                self.db.save_news_intel(
                                    code=code,
                                    name=stock_name,
                                    dimension=dim_name,
                                    query=response.query,
                                    response=response,
                                    query_context=query_context
                                )
                    except Exception as e:
                        logger.warning(f"[{code}] 保存新闻情报失败: {e}")
            else:
                logger.info(f"[{code}] 搜索服务不可用，跳过情报搜索")
            
            # Step 5: 获取分析上下文（技术面数据）
            context = self.db.get_analysis_context(code)
            
            if context is None:
                logger.warning(f"[{code}] 无法获取历史行情数据，将仅基于新闻和实时行情分析")
                from datetime import date
                context = {
                    'code': code,
                    'stock_name': stock_name,
                    'date': date.today().isoformat(),
                    'data_missing': True,
                    'today': {},
                    'yesterday': {}
                }
            
            # Step 6: 增强上下文数据（添加实时行情、筹码、趋势分析结果、股票名称）
            enhanced_context = self._enhance_context(
                context, 
                realtime_quote, 
                chip_data, 
                trend_result,
                stock_name  # 传入股票名称
            )
            
            # Step 7: 调用 AI 分析（传入增强的上下文和新闻）
            result = self.analyzer.analyze(enhanced_context, news_context=news_context)

            # Step 7.5: 填充分析时的价格信息到 result
            if result:
                realtime_data = enhanced_context.get('realtime', {})
                result.current_price = realtime_data.get('price')
                result.change_pct = realtime_data.get('change_pct')

            # Step 8: 保存分析历史记录
            if result:
                try:
                    context_snapshot = self._build_context_snapshot(
                        enhanced_context=enhanced_context,
                        news_content=news_context,
                        realtime_quote=realtime_quote,
                        chip_data=chip_data
                    )
                    # 为每只股票生成唯一的 query_id（如果批次级 query_id 存在则作为前缀）
                    stock_query_id = f"{self.query_id}_{code}" if self.query_id else uuid.uuid4().hex

                    self.db.save_analysis_history(
                        result=result,
                        query_id=stock_query_id,
                        report_type=report_type.value,
                        news_content=news_context,
                        context_snapshot=context_snapshot,
                        save_snapshot=self.save_context_snapshot
                    )
                    logger.debug(f"[{code}] 分析历史已保存，query_id: {stock_query_id}")
                except Exception as e:
                    logger.warning(f"[{code}] 保存分析历史失败: {e}")

            return result
            
        except Exception as e:
            logger.error(f"[{code}] 分析失败: {e}")
            logger.exception(f"[{code}] 详细错误信息:")
            return None
    
    def _enhance_context(
        self,
        context: Dict[str, Any],
        realtime_quote,
        chip_data: Optional[ChipDistribution],
        trend_result: Optional[TrendAnalysisResult],
        stock_name: str = ""
    ) -> Dict[str, Any]:
        """
        增强分析上下文
        
        将实时行情、筹码分布、趋势分析结果、股票名称添加到上下文中
        
        Args:
            context: 原始上下文
            realtime_quote: 实时行情数据（UnifiedRealtimeQuote 或 None）
            chip_data: 筹码分布数据
            trend_result: 趋势分析结果
            stock_name: 股票名称
            
        Returns:
            增强后的上下文
        """
        enhanced = context.copy()
        
        # 添加股票名称
        if stock_name:
            enhanced['stock_name'] = stock_name
        elif realtime_quote and getattr(realtime_quote, 'name', None):
            enhanced['stock_name'] = realtime_quote.name
        
        # 添加实时行情（兼容不同数据源的字段差异）
        if realtime_quote:
            # 使用 getattr 安全获取字段，缺失字段返回 None 或默认值
            volume_ratio = getattr(realtime_quote, 'volume_ratio', None)
            enhanced['realtime'] = {
                'name': getattr(realtime_quote, 'name', ''),
                'price': getattr(realtime_quote, 'price', None),
                'change_pct': getattr(realtime_quote, 'change_pct', None),
                'volume_ratio': volume_ratio,
                'volume_ratio_desc': self._describe_volume_ratio(volume_ratio) if volume_ratio else '无数据',
                'turnover_rate': getattr(realtime_quote, 'turnover_rate', None),
                'pe_ratio': getattr(realtime_quote, 'pe_ratio', None),
                'pb_ratio': getattr(realtime_quote, 'pb_ratio', None),
                'total_mv': getattr(realtime_quote, 'total_mv', None),
                'circ_mv': getattr(realtime_quote, 'circ_mv', None),
                'change_60d': getattr(realtime_quote, 'change_60d', None),
                'source': getattr(realtime_quote, 'source', None),
            }
            # 移除 None 值以减少上下文大小
            enhanced['realtime'] = {k: v for k, v in enhanced['realtime'].items() if v is not None}
        
        # 添加筹码分布
        if chip_data:
            current_price = getattr(realtime_quote, 'price', 0) if realtime_quote else 0
            enhanced['chip'] = {
                'profit_ratio': chip_data.profit_ratio,
                'avg_cost': chip_data.avg_cost,
                'concentration_90': chip_data.concentration_90,
                'concentration_70': chip_data.concentration_70,
                'chip_status': chip_data.get_chip_status(current_price or 0),
            }
        
        # 添加趋势分析结果
        if trend_result:
            enhanced['trend_analysis'] = {
                'trend_status': trend_result.trend_status.value,
                'ma_alignment': trend_result.ma_alignment,
                'trend_strength': trend_result.trend_strength,
                'bias_ma5': trend_result.bias_ma5,
                'bias_ma10': trend_result.bias_ma10,
                'volume_status': trend_result.volume_status.value,
                'volume_trend': trend_result.volume_trend,
                'buy_signal': trend_result.buy_signal.value,
                'signal_score': trend_result.signal_score,
                'signal_reasons': trend_result.signal_reasons,
                'risk_factors': trend_result.risk_factors,
            }
        
        return enhanced
    
    def _describe_volume_ratio(self, volume_ratio: float) -> str:
        """
        量比描述
        
        量比 = 当前成交量 / 过去5日平均成交量
        """
        if volume_ratio < 0.5:
            return "极度萎缩"
        elif volume_ratio < 0.8:
            return "明显萎缩"
        elif volume_ratio < 1.2:
            return "正常"
        elif volume_ratio < 2.0:
            return "温和放量"
        elif volume_ratio < 3.0:
            return "明显放量"
        else:
            return "巨量"

    def _build_context_snapshot(
        self,
        enhanced_context: Dict[str, Any],
        news_content: Optional[str],
        realtime_quote: Any,
        chip_data: Optional[ChipDistribution]
    ) -> Dict[str, Any]:
        """
        构建分析上下文快照
        """
        return {
            "enhanced_context": enhanced_context,
            "news_content": news_content,
            "realtime_quote_raw": self._safe_to_dict(realtime_quote),
            "chip_distribution_raw": self._safe_to_dict(chip_data),
        }

    @staticmethod
    def _safe_to_dict(value: Any) -> Optional[Dict[str, Any]]:
        """
        安全转换为字典
        """
        if value is None:
            return None
        if hasattr(value, "to_dict"):
            try:
                return value.to_dict()
            except Exception:
                return None
        if hasattr(value, "__dict__"):
            try:
                return dict(value.__dict__)
            except Exception:
                return None
        return None

    def _resolve_query_source(self, query_source: Optional[str]) -> str:
        """
        解析请求来源。

        优先级（从高到低）：
        1. 显式传入的 query_source：调用方明确指定时优先使用，便于覆盖推断结果或兼容未来 source_message 来自非 bot 的场景
        2. 存在 source_message 时推断为 "bot"：当前约定为机器人会话上下文
        3. 存在 query_id 时推断为 "web"：Web 触发的请求会带上 query_id
        4. 默认 "system"：定时任务或 CLI 等无上述上下文时

        Args:
            query_source: 调用方显式指定的来源，如 "bot" / "web" / "cli" / "system"

        Returns:
            归一化后的来源标识字符串，如 "bot" / "web" / "cli" / "system"
        """
        if query_source:
            return query_source
        if self.source_message:
            return "bot"
        if self.query_id:
            return "web"
        return "system"

    def _build_query_context(self) -> Dict[str, str]:
        """
        生成用户查询关联信息
        """
        context: Dict[str, str] = {
            "query_id": self.query_id or "",
            "query_source": self.query_source or "",
        }

        if self.source_message:
            context.update({
                "requester_platform": self.source_message.platform or "",
                "requester_user_id": self.source_message.user_id or "",
                "requester_user_name": self.source_message.user_name or "",
                "requester_chat_id": self.source_message.chat_id or "",
                "requester_message_id": self.source_message.message_id or "",
                "requester_query": self.source_message.content or "",
            })

        return context
    
    def process_single_stock(
        self,
        code: str,
        skip_analysis: bool = False,
        single_stock_notify: bool = False,
        report_type: ReportType = ReportType.SIMPLE
    ) -> Optional[AnalysisResult]:
        """
        处理单只股票的完整流程

        包括：
        1. 获取数据
        2. 保存数据
        3. AI 分析
        4. 单股推送（可选，#55）

        此方法会被线程池调用，需要处理好异常

        Args:
            code: 股票代码
            skip_analysis: 是否跳过 AI 分析
            single_stock_notify: 是否启用单股推送模式（每分析完一只立即推送）
            report_type: 报告类型枚举（从配置读取，Issue #119）

        Returns:
            AnalysisResult 或 None
        """
        logger.info(f"========== 开始处理 {code} ==========")
        
        try:
            # Step 1: 获取并保存数据
            success, error = self.fetch_and_save_stock_data(code)
            
            if not success:
                logger.warning(f"[{code}] 数据获取失败: {error}")
                # 即使获取失败，也尝试用已有数据分析
            
            # Step 2: AI 分析
            if skip_analysis:
                logger.info(f"[{code}] 跳过 AI 分析（dry-run 模式）")
                return None
            
            result = self.analyze_stock(code, report_type)
            
            if result:
                logger.info(
                    f"[{code}] 分析完成: {result.operation_advice}, "
                    f"评分 {result.sentiment_score}"
                )
                
                # 单股推送模式（#55）：每分析完一只股票立即推送
                if single_stock_notify and self.notifier.is_available():
                    try:
                        # 根据报告类型选择生成方法
                        if report_type == ReportType.FULL:
                            # 完整报告：使用决策仪表盘格式
                            report_content = self.notifier.generate_dashboard_report([result])
                            logger.info(f"[{code}] 使用完整报告格式")
                        else:
                            # 精简报告：使用单股报告格式（默认）
                            report_content = self.notifier.generate_single_stock_report(result)
                            logger.info(f"[{code}] 使用精简报告格式")
                        
                        if self.notifier.send(report_content):
                            logger.info(f"[{code}] 单股推送成功")
                        else:
                            logger.warning(f"[{code}] 单股推送失败")
                    except Exception as e:
                        logger.error(f"[{code}] 单股推送异常: {e}")
            
            return result
            
        except Exception as e:
            # 捕获所有异常，确保单股失败不影响整体
            logger.exception(f"[{code}] 处理过程发生未知异常: {e}")
            return None
    
    def run(
        self, 
        stock_codes: Optional[List[str]] = None,
        dry_run: bool = False,
        send_notification: bool = True
    ) -> List[AnalysisResult]:
        """
        运行完整的分析流程
        
        流程：
        1. 获取待分析的股票列表
        2. 使用线程池并发处理
        3. 收集分析结果
        4. 发送通知
        
        Args:
            stock_codes: 股票代码列表（可选，默认使用配置中的自选股）
            dry_run: 是否仅获取数据不分析
            send_notification: 是否发送推送通知
            
        Returns:
            分析结果列表
        """
        start_time = time.time()
        
        # 使用配置中的股票列表
        if stock_codes is None:
            self.config.refresh_stock_list()
            stock_codes = self.config.stock_list
        
        if not stock_codes:
            logger.error("未配置自选股列表，请在 .env 文件中设置 STOCK_LIST")
            return []
        
        logger.info(f"===== 开始分析 {len(stock_codes)} 只股票 =====")
        logger.info(f"股票列表: {', '.join(stock_codes)}")
        logger.info(f"并发数: {self.max_workers}, 模式: {'仅获取数据' if dry_run else '完整分析'}")
        
        # === 批量预取实时行情（优化：避免每只股票都触发全量拉取）===
        # 只有股票数量 >= 5 时才进行预取，少量股票直接逐个查询更高效
        if len(stock_codes) >= 5:
            prefetch_count = self.fetcher_manager.prefetch_realtime_quotes(stock_codes)
            if prefetch_count > 0:
                logger.info(f"已启用批量预取架构：一次拉取全市场数据，{len(stock_codes)} 只股票共享缓存")
        
        # 单股推送模式（#55）：从配置读取
        single_stock_notify = getattr(self.config, 'single_stock_notify', False)
        # Issue #119: 从配置读取报告类型
        report_type_str = getattr(self.config, 'report_type', 'simple').lower()
        report_type = ReportType.FULL if report_type_str == 'full' else ReportType.SIMPLE
        # Issue #128: 从配置读取分析间隔
        analysis_delay = getattr(self.config, 'analysis_delay', 0)

        if single_stock_notify:
            logger.info(f"已启用单股推送模式：每分析完一只股票立即推送（报告类型: {report_type_str}）")
        
        results: List[AnalysisResult] = []
        
        # 使用线程池并发处理
        # 注意：max_workers 设置较低（默认3）以避免触发反爬
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交任务
            future_to_code = {
                executor.submit(
                    self.process_single_stock,
                    code,
                    skip_analysis=dry_run,
                    single_stock_notify=single_stock_notify and send_notification,
                    report_type=report_type  # Issue #119: 传递报告类型
                ): code
                for code in stock_codes
            }
            
            # 收集结果
            for idx, future in enumerate(as_completed(future_to_code)):
                code = future_to_code[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)

                    # Issue #128: 分析间隔 - 在个股分析和大盘分析之间添加延迟
                    if idx < len(stock_codes) - 1 and analysis_delay > 0:
                        logger.debug(f"等待 {analysis_delay} 秒后继续下一只股票...")
                        time.sleep(analysis_delay)

                except Exception as e:
                    logger.error(f"[{code}] 任务执行失败: {e}")
        
        # 统计
        elapsed_time = time.time() - start_time
        
        # dry-run 模式下，数据获取成功即视为成功
        if dry_run:
            # 检查哪些股票的数据今天已存在
            success_count = sum(1 for code in stock_codes if self.db.has_today_data(code))
            fail_count = len(stock_codes) - success_count
        else:
            success_count = len(results)
            fail_count = len(stock_codes) - success_count
        
        logger.info("===== 分析完成 =====")
        logger.info(f"成功: {success_count}, 失败: {fail_count}, 耗时: {elapsed_time:.2f} 秒")
        
        # 发送通知（单股推送模式下跳过汇总推送，避免重复）
        if results and send_notification and not dry_run:
            # 运行全市场选股
            market_recs = self.screen_market_stocks()
            if single_stock_notify:
                # 单股推送模式：只保存汇总报告，不再重复推送
                logger.info("单股推送模式：跳过汇总推送，仅保存报告到本地")
                self._send_notifications(results, skip_push=True, market_recommendations=market_recs)
            else:
                self._send_notifications(results, market_recommendations=market_recs)

        return results
    
    def _calculate_technical_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        计算技术指标

        Args:
            df: K线数据（标准化格式，包含 close, high, low, volume 列）

        Returns:
            技术指标字典
        """
        import pandas as pd
        import numpy as np

        if df is None or df.empty or len(df) < 20:
            return None

        # 确保按日期排序（从旧到新）
        df = df.sort_values('date').reset_index(drop=True)

        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        volume = df['volume'].values

        # 计算移动平均线
        ma5 = pd.Series(close).rolling(5).mean().iloc[-1] if len(close) >= 5 else np.nan
        ma10 = pd.Series(close).rolling(10).mean().iloc[-1] if len(close) >= 10 else np.nan
        ma20 = pd.Series(close).rolling(20).mean().iloc[-1] if len(close) >= 20 else np.nan
        ma60 = pd.Series(close).rolling(60).mean().iloc[-1] if len(close) >= 60 else np.nan

        # 均线多头排列检查
        ma_bullish = False
        if not np.isnan(ma5) and not np.isnan(ma10) and not np.isnan(ma20):
            ma_bullish = (ma5 > ma10 > ma20)

        # 创20日新高检查
        is_20day_high = False
        if len(high) >= 20:
            is_20day_high = (close[-1] >= np.max(high[-20:-1]))

        # 前3日缩量整理检查（量能整理）
        is_volume_consolidated = False
        if len(volume) >= 5:
            recent_3d_avg = np.mean(volume[-3:])
            prev_2d_avg = np.mean(volume[-5:-3])
            is_volume_consolidated = (recent_3d_avg < prev_2d_avg * 0.7) if prev_2d_avg > 0 else False

        # 计算RSI(14)
        rsi = np.nan
        if len(close) >= 15:
            delta = pd.Series(close).diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = (100 - (100 / (1 + rs))).iloc[-1]

        # 计算MACD
        macd_golden_cross = False
        macd_histogram = 0
        if len(close) >= 26:
            ema12 = pd.Series(close).ewm(span=12, adjust=False).mean()
            ema26 = pd.Series(close).ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            macd_hist = macd_line - signal_line

            macd_histogram = macd_hist.iloc[-1]
            # 金叉：MACD线上穿信号线
            if len(macd_hist) >= 2:
                macd_golden_cross = (macd_hist.iloc[-2] < 0 and macd_hist.iloc[-1] > 0)

        # 计算20日涨幅
        gain_20d = 0
        if len(close) >= 20:
            gain_20d = (close[-1] / close[-20] - 1) * 100

        # 计算波动率（20日标准差/均值）
        volatility = 0
        if len(close) >= 20:
            volatility = pd.Series(close[-20:]).std() / pd.Series(close[-20:]).mean()

        return {
            'ma5': ma5,
            'ma10': ma10,
            'ma20': ma20,
            'ma60': ma60,
            'ma_bullish': ma_bullish,
            'is_20day_high': is_20day_high,
            'is_volume_consolidated': is_volume_consolidated,
            'rsi': rsi,
            'macd_golden_cross': macd_golden_cross,
            'macd_histogram': macd_histogram,
            'gain_20d': gain_20d,
            'volatility': volatility,
        }

    def _calculate_full_score(
        self,
        indicators: Dict[str, Any],
        volume_ratio: float,
        pe: float,
        market_cap: float,
        change_pct: float
    ) -> float:
        """
        计算完整评分（趋势突破+资金共振策略）

        评分体系（总分100）：
        - 趋势强度分(40): 20日涨幅(15) + 均线多头(10) + RSI(8) + MACD(7)
        - 量价配合分(35): 量比(16) + 突破强度(10) + 涨幅动能(9)
        - 安全边际分(25): 估值(10) + 市值(8) + 波动率(7)

        Args:
            indicators: 技术指标字典
            volume_ratio: 量比
            pe: 市盈率
            market_cap: 总市值（亿）
            change_pct: 今日涨幅

        Returns:
            综合评分
        """
        score = 0

        # === 趋势强度分(40分) ===
        # 1. 20日涨幅排名分(0-15分)：涨幅越高分越高
        gain_20d = indicators.get('gain_20d', 0)
        if gain_20d > 30:
            score += 15
        elif gain_20d > 20:
            score += 12
        elif gain_20d > 10:
            score += 8
        elif gain_20d > 5:
            score += 5
        elif gain_20d > 0:
            score += 2

        # 2. 均线多头质量(0-10分)
        if indicators.get('ma_bullish', False):
            score += 10
        elif indicators.get('ma5', 0) > indicators.get('ma10', 0):
            score += 5

        # 3. RSI(14) 在50-70区间(0-8分)：强势但不超买
        rsi = indicators.get('rsi', 0)
        if 50 <= rsi <= 70:
            score += 8
        elif 45 <= rsi < 50 or 70 < rsi <= 75:
            score += 5
        elif 40 <= rsi < 45:
            score += 3

        # 4. MACD金叉/红柱(0-7分)
        if indicators.get('macd_golden_cross', False):
            score += 7
        elif indicators.get('macd_histogram', 0) > 0:
            score += 4

        # === 量价配合分(35分) ===
        # 5. 量比×8 (0-16分)：量比2.0得16分
        score += min(volume_ratio * 8, 16)

        # 6. 突破强度(0-10分)
        if indicators.get('is_20day_high', False):
            score += 10
        elif change_pct > 3:
            score += 6
        elif change_pct > 1:
            score += 3

        # 7. 涨幅动能(0-9分)：今日涨幅适中得分
        if 0.5 <= change_pct <= 5:
            score += 9
        elif 0 <= change_pct < 0.5 or 5 < change_pct <= 7:
            score += 5

        # === 安全边际分(25分) ===
        # 8. 估值分位(0-10分)：PE越低分越高
        if 0 < pe <= 20:
            score += 10
        elif 20 < pe <= 30:
            score += 8
        elif 30 < pe <= 40:
            score += 5
        elif 40 < pe <= 60:
            score += 3

        # 9. 市值稳定性(0-8分)：100-500亿最优
        mv_yi = market_cap / 100_000_000 if market_cap > 0 else 0
        if 100 <= mv_yi <= 500:
            score += 8
        elif 50 <= mv_yi < 100 or 500 < mv_yi <= 1000:
            score += 5
        elif mv_yi > 1000:
            score += 3

        # 10. 波动率控制(0-7分)：低波动加分
        volatility = indicators.get('volatility', 0)
        if volatility < 0.02:
            score += 7
        elif volatility < 0.03:
            score += 5
        elif volatility < 0.05:
            score += 3

        return score

    def screen_market_stocks(self) -> Dict[str, list]:
        """
        从全市场A股中筛选推荐股票（完整版：趋势突破+资金共振策略）

        策略核心：两阶段筛选
        - 第一阶段：实时数据快速过滤，获取候选池（~100-200只）
        - 第二阶段：获取历史K线，计算技术指标，综合评分

        技术指标：
        - 均线多头排列：MA5 > MA10 > MA20 > MA60
        - 创20日新高：突破前期高点
        - 前3日缩量整理：量能整理，蓄势待发
        - MACD金叉：趋势确认
        - RSI 50-70：强势但不超买

        Returns:
            {'buy': [...], 'watch': [...]} 各最多5只
        """
        try:
            import pandas as pd
            from data_provider.akshare_fetcher import _realtime_cache
            import time as _time

            logger.info("开始全市场A股筛选（完整版：趋势突破+资金共振策略）...")
            logger.info("采用两阶段筛选：第一阶段实时数据快速过滤 → 第二阶段历史K线技术分析")

            # ========== 第一阶段：获取全市场实时数据 ==========
            current_time = _time.time()
            df = None
            if (_realtime_cache['data'] is not None and
                not _realtime_cache['data'].empty and
                current_time - _realtime_cache['timestamp'] < _realtime_cache['ttl']):
                df = _realtime_cache['data']
                logger.info(f"[第一阶段] 使用缓存数据，共 {len(df)} 只股票")
            else:
                # 缓存过期，重新拉取（带重试和降级）
                import akshare as ak
                logger.info("[全市场筛选] 缓存过期，重新拉取全市场数据...")
                for attempt in range(3):
                    try:
                        if attempt > 0:
                            _time.sleep(5 * attempt)
                            logger.info(f"[全市场筛选] 第 {attempt + 1} 次重试...")
                        df = ak.stock_zh_a_spot_em()
                        if df is not None and not df.empty:
                            _realtime_cache['data'] = df
                            _realtime_cache['timestamp'] = current_time
                            logger.info(f"[全市场筛选] 东财接口拉取成功，共 {len(df)} 只股票")
                            break
                    except Exception as fetch_err:
                        logger.warning(f"[全市场筛选] 东财接口第 {attempt + 1} 次失败: {fetch_err}")
                        df = None

                # 东财接口全部失败，优先尝试 baostock+pytdx（TCP直连）
                if df is None or df.empty:
                    logger.info("[全市场筛选] 东财接口不可用，尝试 baostock+pytdx TCP直连...")
                    try:
                        import baostock as _bs
                        from pytdx.hq import TdxHq_API as _TdxHqAPI

                        # baostock 获取完整A股列表
                        import time as _time
                        _lg = _bs.login()
                        _stock_list = []
                        for _day_offset in range(0, 10):
                            _query_date = _time.strftime('%Y-%m-%d', _time.localtime(_time.time() - _day_offset * 86400))
                            _rs = _bs.query_all_stock(day=_query_date)
                            _temp_list = []
                            while _rs.error_code == '0' and _rs.next():
                                _temp_list.append(_rs.get_row_data())
                            if len(_temp_list) > 100:
                                _stock_list = _temp_list
                                logger.info(f"[全市场筛选] baostock 使用日期 {_query_date}, 获取 {len(_stock_list)} 只股票")
                                break
                        _bs.logout()

                        _a_shares = []
                        for _row in _stock_list:
                            _code_full, _trade_status, _name = _row[0], _row[1], _row[2]
                            if _trade_status != '1':
                                continue
                            _parts = _code_full.split('.')
                            if len(_parts) != 2:
                                continue
                            _mkt, _num = _parts
                            if _mkt == 'sh' and (_num.startswith('60') or _num.startswith('68')):
                                _a_shares.append((1, _num, _name))
                            elif _mkt == 'sz' and (_num.startswith('00') or _num.startswith('30')):
                                _a_shares.append((0, _num, _name))

                        logger.info(f"[全市场筛选] baostock 获取A股列表: {len(_a_shares)} 只")

                        # pytdx 批量获取行情
                        _tdx = _TdxHqAPI()
                        _connected = False
                        for _host in ['218.75.126.9', '115.238.56.198', '124.160.88.183',
                                      '60.12.136.250', '218.108.98.244', '180.153.18.170']:
                            try:
                                if _tdx.connect(_host, 7709, time_out=10):
                                    _connected = True
                                    break
                            except Exception:
                                continue

                        if _connected and _a_shares:
                            _names_map = {(_m, _c): _n for _m, _c, _n in _a_shares}
                            _all_quotes = []
                            for _i in range(0, len(_a_shares), 80):
                                _batch = _a_shares[_i:_i+80]
                                _codes = [(_m, _c) for _m, _c, _ in _batch]
                                try:
                                    _data = _tdx.get_security_quotes(_codes)
                                    if _data:
                                        _all_quotes.extend(_data)
                                except Exception:
                                    continue
                            _tdx.disconnect()

                            # 转为 DataFrame
                            _rows = []
                            for _idx, _q in enumerate(_all_quotes):
                                _lc = _q['last_close']
                                _pr = _q['price']
                                # 打印前 5 条原始数据用于调试
                                if _idx < 5:
                                    logger.info(f"[全市场筛选] 样本数据 {_idx+1}: code={_q.get('code')}, price={_pr}, last_close={_lc}")
                                if _lc <= 0 or _pr <= 0:
                                    continue
                                _pct = (_pr - _lc) / _lc * 100
                                _rows.append({
                                    '代码': _q['code'],
                                    '名称': _names_map.get((_q['market'], _q['code']), ''),
                                    '最新价': _pr,
                                    '涨跌幅': round(_pct, 2),
                                    '成交量': _q['vol'],
                                    '成交额': _q['amount'],
                                })

                            logger.info(f"[全市场筛选] pytdx获取 {len(_all_quotes)} 条行情, 有效 {len(_rows)} 条")
                            if _rows:
                                df = pd.DataFrame(_rows)
                                _realtime_cache['data'] = df
                                _realtime_cache['timestamp'] = current_time
                                logger.info(f"[全市场筛选] baostock+pytdx 降级成功，共 {len(df)} 只股票")
                        else:
                            if not _connected:
                                logger.warning("[全市场筛选] pytdx 无法连接任何服务器")
                    except Exception as tcp_err:
                        logger.warning(f"[全市场筛选] baostock+pytdx 降级失败: {tcp_err}")

                # baostock+pytdx 也失败，尝试 efinance
                if df is None or df.empty:
                    logger.info("[全市场筛选] 尝试 efinance 降级...")
                    try:
                        import efinance as ef
                        df = ef.stock.get_realtime_quotes()
                        if df is not None and not df.empty:
                            logger.info(f"[全市场筛选] efinance 原始列: {list(df.columns)}")
                            ef_col_map = {
                                '股票代码': '代码', '股票名称': '名称',
                                '市盈率': '市盈率-动态',
                            }
                            existing_map = {k: v for k, v in ef_col_map.items() if k in df.columns}
                            df = df.rename(columns=existing_map)
                            if '60日涨跌幅' not in df.columns:
                                df['60日涨跌幅'] = 0.0
                            _realtime_cache['data'] = df
                            _realtime_cache['timestamp'] = current_time
                            logger.info(f"[全市场筛选] efinance 降级成功，共 {len(df)} 只股票")
                    except Exception as ef_err:
                        logger.warning(f"[全市场筛选] efinance 也失败: {ef_err}")

                # 最后尝试新浪接口
                if df is None or df.empty:
                    logger.info("[全市场筛选] 尝试新浪接口降级...")
                    try:
                        df = ak.stock_zh_a_spot()
                        if df is not None and not df.empty:
                            logger.info(f"[全市场筛选] 新浪原始列: {list(df.columns)}")
                            col_map = {
                                'symbol': '代码', 'code': '代码',
                                'name': '名称',
                                'trade': '最新价', 'close': '最新价',
                                'changepercent': '涨跌幅',
                                'volume': '成交量', 'amount': '成交额',
                                'turnoverratio': '换手率',
                                'per': '市盈率-动态', 'pb': '市净率',
                                'mktcap': '总市值', 'nmc': '流通市值',
                            }
                            existing_map = {k: v for k, v in col_map.items() if k in df.columns}
                            df = df.rename(columns=existing_map)
                            if '量比' not in df.columns:
                                df['量比'] = 1.0
                            if '60日涨跌幅' not in df.columns:
                                df['60日涨跌幅'] = 0.0
                            if '总市值' in df.columns:
                                df['总市值'] = pd.to_numeric(df['总市值'], errors='coerce') * 10000
                            if '流通市值' in df.columns:
                                df['流通市值'] = pd.to_numeric(df['流通市值'], errors='coerce') * 10000
                            _realtime_cache['data'] = df
                            _realtime_cache['timestamp'] = current_time
                            logger.info(f"[全市场筛选] 新浪接口降级成功，共 {len(df)} 只股票")
                    except Exception as sina_err:
                        logger.warning(f"[全市场筛选] 新浪接口也失败: {sina_err}")

            if df is None or df.empty:
                logger.warning("[第一阶段] 无法获取A股行情数据")
                return {'buy': [], 'watch': []}

            # 数值列转换（处理可能的百分号字符串如 "2.50%"）
            numeric_cols = ['涨跌幅', '量比', '换手率', '市盈率-动态', '市净率',
                           '总市值', '流通市值', '60日涨跌幅', '最新价', '成交额']
            for col in numeric_cols:
                if col in df.columns:
                    if df[col].dtype == object:
                        df[col] = df[col].astype(str).str.replace('%', '', regex=False).str.replace(',', '', regex=False)
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            logger.info(f"[第一阶段] 数据列: {list(df.columns)}")

            # 基础过滤：去除ST、退市、停牌、低价股、涨停
            base_mask = (
                ~df['名称'].str.contains('ST|退|停|N ', na=False) &
                (df['最新价'] > 5) &
                (df['成交额'] > 0) &
                (df['涨跌幅'] < 9.5)
            )
            df_filtered = df[base_mask].copy()
            logger.info(f"[第一阶段] 基础过滤后剩余 {len(df_filtered)} 只")

            # 一阶段快速过滤：筛选候选池（目标约100-200只）
            candidate_mask = (
                (df_filtered['涨跌幅'] >= -2) &  # 近期走势不太差
                (df_filtered['涨跌幅'] <= 7) &   # 不追涨幅过大
                (df_filtered['成交额'] > 100_000_000)  # 基本流动性
            )

            # 量比条件（有一定资金关注）
            if '量比' in df_filtered.columns and df_filtered['量比'].sum() > 0:
                candidate_mask = candidate_mask & (df_filtered['量比'] >= 1.2)

            # 市值条件（大中盘为主）
            if '总市值' in df_filtered.columns:
                candidate_mask = candidate_mask & (df_filtered['总市值'] > 5_000_000_000)

            # 估值条件（合理估值）
            if '市盈率-动态' in df_filtered.columns:
                candidate_mask = candidate_mask & (df_filtered['市盈率-动态'] > 0) & (df_filtered['市盈率-动态'] < 80)

            candidates_df = df_filtered[candidate_mask].copy()
            logger.info(f"[第一阶段] 候选池筛选完成：{len(candidates_df)} 只股票")

            if candidates_df.empty:
                logger.warning("[第一阶段] 候选池为空，无法进入第二阶段")
                return {'buy': [], 'watch': []}

            # 限制候选池大小（避免第二阶段耗时过长）
            max_candidates = 150
            if len(candidates_df) > max_candidates:
                # 按量比×涨跌幅排序，取前150
                candidates_df['_quick_score'] = candidates_df.get('量比', 1.5) * (candidates_df['涨跌幅'] + 5)
                candidates_df = candidates_df.sort_values('_quick_score', ascending=False).head(max_candidates)
                logger.info(f"[第一阶段] 候选池过大，按快速评分取前 {max_candidates} 只")

            # ========== 第二阶段：历史K线技术分析 ==========
            logger.info(f"[第二阶段] 开始为 {len(candidates_df)} 只候选股票获取历史K线数据...")
            logger.info("[第二阶段] 该阶段将耗时1-2分钟，请耐心等待...")

            scored_stocks = []
            fetch_success_count = 0
            fetch_fail_count = 0

            for idx, (_, row) in enumerate(candidates_df.iterrows(), 1):
                code = str(row['代码'])
                name = str(row['名称'])

                # 每处理10只股票输出一次进度
                if idx % 10 == 0:
                    logger.info(f"[第二阶段] 进度: {idx}/{len(candidates_df)} ({idx*100//len(candidates_df)}%)")

                try:
                    # 获取60日K线数据
                    kline_df, source = self.fetcher_manager.get_daily_data(code, days=60)

                    if kline_df is None or kline_df.empty or len(kline_df) < 20:
                        logger.debug(f"[{code}] K线数据不足，跳过")
                        fetch_fail_count += 1
                        continue

                    # 计算技术指标
                    indicators = self._calculate_technical_indicators(kline_df)

                    if indicators is None:
                        logger.debug(f"[{code}] 技术指标计算失败，跳过")
                        fetch_fail_count += 1
                        continue

                    # 计算完整评分
                    score = self._calculate_full_score(
                        indicators=indicators,
                        volume_ratio=row.get('量比', 1.5),
                        pe=row.get('市盈率-动态', 50),
                        market_cap=row.get('总市值', 0),
                        change_pct=row.get('涨跌幅', 0)
                    )

                    scored_stocks.append({
                        'code': code,
                        'name': name,
                        'price': float(row.get('最新价', 0)),
                        'change_pct': float(row.get('涨跌幅', 0)),
                        'volume_ratio': float(row.get('量比', 0)),
                        'turnover_rate': float(row.get('换手率', 0)),
                        'pe': float(row.get('市盈率-动态', 0)),
                        'market_cap': row.get('总市值', 0),
                        'score': score,
                        'indicators': indicators,
                    })

                    fetch_success_count += 1

                except Exception as e:
                    logger.debug(f"[{code}] 获取K线数据失败: {e}")
                    fetch_fail_count += 1
                    continue

            logger.info(f"[第二阶段] K线数据获取完成：成功 {fetch_success_count} 只，失败 {fetch_fail_count} 只")

            if not scored_stocks:
                logger.warning("[第二阶段] 所有候选股票K线数据获取失败")
                return {'buy': [], 'watch': []}

            # 按评分排序
            scored_stocks.sort(key=lambda x: x['score'], reverse=True)
            logger.info(f"[第二阶段] 综合评分完成，最高分: {scored_stocks[0]['score']:.1f}，最低分: {scored_stocks[-1]['score']:.1f}")

            # === 买入推荐：高分股票 + 符合买入条件 ===
            buy_candidates = []
            for stock in scored_stocks:
                # 买入条件：涨幅0.5-5%（温和启动）+ 高评分
                if 0.5 <= stock['change_pct'] <= 5.0 and stock['score'] >= 40:
                    buy_candidates.append(stock)

            buy_candidates = buy_candidates[:5]  # 最多5只
            logger.info(f"[最终结果] 买入推荐: {len(buy_candidates)} 只")

            # === 观察推荐：次高分股票 或 稳健上涨 ===
            watch_candidates = []
            buy_codes = {s['code'] for s in buy_candidates}

            for stock in scored_stocks:
                # 排除已在买入列表中的
                if stock['code'] in buy_codes:
                    continue

                # 观察条件：评分不错（>30分） + 涨幅温和（-2% ~ 3%）
                if -2 <= stock['change_pct'] <= 3 and stock['score'] >= 30:
                    watch_candidates.append(stock)

            watch_candidates = watch_candidates[:5]  # 最多5只
            logger.info(f"[最终结果] 观察推荐: {len(watch_candidates)} 只")

            # === 格式化推荐理由 ===
            def format_reason(stock: Dict[str, Any]) -> str:
                """生成推荐理由"""
                indicators = stock['indicators']
                parts = []

                # 今日涨跌
                parts.append(f"今日{'涨' if stock['change_pct'] >= 0 else '跌'}{abs(stock['change_pct']):.1f}%")

                # 量价配合
                if stock['volume_ratio'] > 0:
                    vr_desc = "明显放量" if stock['volume_ratio'] >= 2.0 else "放量" if stock['volume_ratio'] >= 1.5 else "量比正常"
                    parts.append(f"量比{stock['volume_ratio']:.1f}（{vr_desc}）")

                # 趋势状态
                if indicators.get('ma_bullish', False):
                    parts.append("均线多头排列")
                elif indicators.get('ma5', 0) > indicators.get('ma10', 0):
                    parts.append("短期趋势向上")

                # 突破信号
                if indicators.get('is_20day_high', False):
                    parts.append("创20日新高")

                # MACD
                if indicators.get('macd_golden_cross', False):
                    parts.append("MACD金叉")

                # RSI
                rsi = indicators.get('rsi', 0)
                if 50 <= rsi <= 70:
                    parts.append(f"RSI {rsi:.0f}（强势）")

                # 20日涨幅
                gain_20d = indicators.get('gain_20d', 0)
                if gain_20d > 10:
                    parts.append(f"20日涨{gain_20d:.1f}%")

                # 估值
                if stock['pe'] > 0:
                    parts.append(f"PE {stock['pe']:.0f}")

                # 市值
                mv_yi = stock['market_cap'] / 100_000_000 if stock['market_cap'] > 0 else 0
                if mv_yi > 0:
                    parts.append(f"市值{mv_yi:.0f}亿")

                # 综合评分
                parts.append(f"综合评分{stock['score']:.0f}")

                return '，'.join(parts)

            # === 转换为API格式 ===
            buy_recs = []
            for stock in buy_candidates:
                mv_yi = stock['market_cap'] / 100_000_000 if stock['market_cap'] > 0 else 0
                buy_recs.append({
                    'name': stock['name'],
                    'code': stock['code'],
                    'price': stock['price'],
                    'change_pct': stock['change_pct'],
                    'volume_ratio': stock['volume_ratio'],
                    'turnover_rate': stock['turnover_rate'],
                    'pe': stock['pe'],
                    'market_cap': f"{mv_yi:.0f}亿" if mv_yi > 0 else "N/A",
                    'reason': format_reason(stock)
                })

            watch_recs = []
            for stock in watch_candidates:
                mv_yi = stock['market_cap'] / 100_000_000 if stock['market_cap'] > 0 else 0
                watch_recs.append({
                    'name': stock['name'],
                    'code': stock['code'],
                    'price': stock['price'],
                    'change_pct': stock['change_pct'],
                    'volume_ratio': stock['volume_ratio'],
                    'turnover_rate': stock['turnover_rate'],
                    'pe': stock['pe'],
                    'market_cap': f"{mv_yi:.0f}亿" if mv_yi > 0 else "N/A",
                    'reason': format_reason(stock)
                })

            logger.info(f"[全市场筛选完成] 买入推荐 {len(buy_recs)} 只，观察推荐 {len(watch_recs)} 只")
            return {'buy': buy_recs, 'watch': watch_recs}

        except Exception as e:
            logger.error(f"全市场选股失败: {e}", exc_info=True)
            return {'buy': [], 'watch': []}

    def _send_notifications(self, results: List[AnalysisResult], skip_push: bool = False, market_recommendations: Optional[Dict] = None) -> None:
        """
        发送分析结果通知

        生成决策仪表盘格式的报告

        Args:
            results: 分析结果列表
            skip_push: 是否跳过推送（仅保存到本地，用于单股推送模式）
            market_recommendations: 全市场选股推荐
        """
        try:
            logger.info("生成决策仪表盘日报...")

            # 生成决策仪表盘格式的详细日报
            report = self.notifier.generate_dashboard_report(results, market_recommendations=market_recommendations)
            
            # 保存到本地
            filepath = self.notifier.save_report_to_file(report)
            logger.info(f"决策仪表盘日报已保存: {filepath}")
            
            # 跳过推送（单股推送模式）
            if skip_push:
                return
            
            # 推送通知
            if self.notifier.is_available():
                channels = self.notifier.get_available_channels()
                context_success = self.notifier.send_to_context(report)

                # 企业微信：只发精简版（平台限制）
                wechat_success = False
                if NotificationChannel.WECHAT in channels:
                    dashboard_content = self.notifier.generate_wechat_dashboard(results)
                    logger.info(f"企业微信仪表盘长度: {len(dashboard_content)} 字符")
                    logger.debug(f"企业微信推送内容:\n{dashboard_content}")
                    wechat_success = self.notifier.send_to_wechat(dashboard_content)

                # 其他渠道：发完整报告（避免自定义 Webhook 被 wechat 截断逻辑污染）
                non_wechat_success = False
                for channel in channels:
                    if channel == NotificationChannel.WECHAT:
                        continue
                    if channel == NotificationChannel.FEISHU:
                        non_wechat_success = self.notifier.send_to_feishu(report) or non_wechat_success
                    elif channel == NotificationChannel.TELEGRAM:
                        non_wechat_success = self.notifier.send_to_telegram(report) or non_wechat_success
                    elif channel == NotificationChannel.EMAIL:
                        non_wechat_success = self.notifier.send_to_email(report) or non_wechat_success
                    elif channel == NotificationChannel.CUSTOM:
                        non_wechat_success = self.notifier.send_to_custom(report) or non_wechat_success
                    elif channel == NotificationChannel.PUSHPLUS:
                        non_wechat_success = self.notifier.send_to_pushplus(report) or non_wechat_success
                    elif channel == NotificationChannel.SERVERCHAN3:
                        non_wechat_success = self.notifier.send_to_serverchan3(report) or non_wechat_success
                    elif channel == NotificationChannel.DISCORD:
                        non_wechat_success = self.notifier.send_to_discord(report) or non_wechat_success
                    elif channel == NotificationChannel.PUSHOVER:
                        non_wechat_success = self.notifier.send_to_pushover(report) or non_wechat_success
                    elif channel == NotificationChannel.ASTRBOT:
                        non_wechat_success = self.notifier.send_to_astrbot(report) or non_wechat_success
                    else:
                        logger.warning(f"未知通知渠道: {channel}")

                success = wechat_success or non_wechat_success or context_success
                if success:
                    logger.info("决策仪表盘推送成功")
                else:
                    logger.warning("决策仪表盘推送失败")
            else:
                logger.info("通知渠道未配置，跳过推送")
                
        except Exception as e:
            logger.error(f"发送通知失败: {e}")
