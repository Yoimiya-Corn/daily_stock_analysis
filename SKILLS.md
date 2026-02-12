# A股智能分析系统 - 技术文档

> 本文档用于快速理解项目架构、核心功能和操作指南，降低上下文理解成本

## 1. 项目概览

### 1.1 核心功能
- **自选股智能分析**：AI驱动的多维度股票分析（技术面、基本面、舆情）
- **全市场选股推荐**：基于"趋势突破+资金共振"策略的每日推荐
- **Web界面**：React前端 + FastAPI后端，实时查看分析报告
- **定时任务**：每日09:30、15:00自动运行分析
- **多渠道推送**：邮件、企业微信、飞书、Telegram

### 1.2 技术栈

**后端**：
- Python 3.14 + FastAPI + Uvicorn
- 数据源：akshare、baostock、pytdx、tushare、yfinance
- AI分析：DeepSeek API（OpenAI兼容）
- 数据库：SQLite

**前端**：
- React 19 + TypeScript + Vite 7
- UI：Tailwind CSS v4（终端暗色风格）
- 状态管理：Zustand
- 数据转换：snake_case（后端）→ camelCase（前端）

## 2. 项目结构

```
daily_stock_analysis/
├── api/                          # FastAPI 后端
│   ├── v1/
│   │   ├── endpoints/           # API 端点
│   │   │   ├── analysis.py      # 分析触发
│   │   │   ├── market.py        # 全市场推荐 ★
│   │   │   ├── history.py       # 历史报告
│   │   │   └── ...
│   │   ├── schemas/             # Pydantic 模型
│   │   └── router.py            # 路由注册
│   ├── app.py                   # FastAPI 应用工厂
│   └── middlewares/             # 中间件
├── apps/
│   └── dsa-web/                 # React 前端
│       ├── src/
│       │   ├── components/      # UI 组件
│       │   │   └── report/
│       │   │       └── MarketRecommendations.tsx  # 推荐组件 ★
│       │   ├── pages/           # 页面
│       │   │   └── HomePage.tsx # 首页（含推荐） ★
│       │   ├── api/             # API 调用
│       │   │   └── market.ts    # 市场推荐 API ★
│       │   └── types/           # TypeScript 类型
│       └── vite.config.ts       # Vite 配置
├── src/                         # 核心业务逻辑
│   ├── core/
│   │   └── pipeline.py          # 分析流水线 ★★★
│   │       └── screen_market_stocks()  # 选股核心逻辑 ★★★
│   ├── analyzer.py              # AI 分析器
│   ├── storage.py               # 数据持久化
│   ├── notification.py          # 通知服务
│   ├── config.py                # 配置管理
│   └── ...
├── data_provider/               # 数据源抽象层
│   ├── base.py                  # 数据源基类
│   ├── akshare_fetcher.py       # AKShare（东财）
│   ├── baostock_fetcher.py      # Baostock（TCP）
│   ├── pytdx_fetcher.py         # pytdx（通达信）
│   └── ...
├── .env                         # 环境配置 ★
├── main.py                      # 入口（CLI）
├── server.py                    # 入口（FastAPI）
└── webui.py                     # 入口（Web UI）
```

## 3. 核心选股策略（重点）

### 3.1 策略名称
**"趋势突破+资金共振"策略**

由 DeepSeek AI 设计，针对 A股 T+1 交易特性优化。

### 3.2 买入推荐逻辑

**核心思想**：买在启动初期，不追高

```python
# 筛选条件（硬性门槛）
涨幅：0.5-5%          # 温和启动，避免追涨停
量比：≥ 1.8           # 明显放量
成交额：> 2亿         # 流动性充足
市值：> 50亿          # 大中盘为主
PE：0-60             # 估值合理
振幅：< 8%            # 排除妖股
排除：ST、涨停、停牌

# 综合评分（总分 ~80分）
得分 = 量比×20 + 涨幅×3 + 成交额/2亿 + PE安全边际 + 市值稳定性

# 关键点
1. 涨幅权重降低（×3 vs 旧策略×10）：不鼓励追高
2. 量比权重提高（×20）：资金驱动为主
3. 估值安全边际：PE越低分越高
4. 市值稳定性：100-500亿最优
```

**代码位置**：`src/core/pipeline.py:930-990`

### 3.3 观察推荐逻辑

```python
涨幅：0-3%            # 稳健上涨
换手率：≥ 0.5%        # 量能不萎缩
市值：> 50亿
PE：0-80
量比：≥ 0.8
60日涨跌幅：> 10%     # 中期趋势强
排除：买入列表中的股票
```

### 3.4 数据源降级链

```
东财 (ak.stock_zh_a_spot_em)
  ↓ 失败（经常被封）
baostock + pytdx (TCP直连，最可靠) ★
  ↓ 失败
efinance (东财备用接口)
  ↓ 失败
新浪 (ak.stock_zh_a_spot)
  ↓ 失败
返回空列表
```

**优先使用 baostock+pytdx**：因为HTTP接口经常被IP封禁。

## 4. 配置说明

### 4.1 环境变量（.env）

```bash
# === 自选股配置 ===
STOCK_LIST=600519,300750,002594,601398,601288,601988,601939,hk01810

# === 定时任务 ===
SCHEDULE_ENABLED=true
SCHEDULE_TIME=09:30,15:00   # 开盘前、收盘后
MARKET_REVIEW_ENABLED=true  # 启用大盘复盘

# === AI 配置（DeepSeek）===
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
OPENAI_TEMPERATURE=0.7

# === 通知配置 ===
# 邮件
SMTP_HOST=smtp.gmail.com
SMTP_USER=your@email.com
SMTP_PASS=your_password
EMAIL_TO=receiver@email.com

# 企业微信
WECHAT_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx

# 飞书
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxx

# Telegram
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx

# === 数据源配置 ===
TUSHARE_TOKEN=your_token  # 可选，有token则优先级最高

# === 其他 ===
MAX_WORKERS=3              # 并发线程数（低并发防封禁）
WEBUI_ENABLED=true         # 启用Web界面
BACKTEST_ENABLED=true      # 启用自动回测
```

### 4.2 前端配置

**API Base URL**：`apps/dsa-web/src/utils/constants.ts`
```typescript
export const API_BASE_URL = import.meta.env.VITE_API_URL
  || (import.meta.env.PROD ? '' : 'http://127.0.0.1:8000');
```

开发环境：指向 `localhost:8000`
生产环境：使用相对路径（同源）

## 5. 常见操作

### 5.1 启动服务

```bash
# 方式1：启动后端（含前端静态文件托管）
cd daily_stock_analysis
python webui.py
# 访问：http://localhost:8000

# 方式2：仅启动 API 服务
python server.py

# 方式3：前端开发模式
cd apps/dsa-web
npx vite --host 0.0.0.0 --port 5173
# 访问：http://localhost:5173
```

### 5.2 运行分析

```bash
# 单次分析
python main.py

# 指定股票
python main.py --stocks 600519,000001

# 调试模式
python main.py --debug

# 仅获取数据，不AI分析
python main.py --dry-run

# 单股推送（分析完立即推送）
python main.py --single-notify

# 仅大盘复盘
python main.py --market-review

# 启用定时任务（09:30, 15:00）
python main.py --schedule
```

### 5.3 前端构建

```bash
cd apps/dsa-web

# 开发模式
npx vite

# 类型检查
npx tsc --noEmit

# 生产构建（输出到 ../../static/）
npx vite build
```

### 5.4 测试全市场推荐

```python
# 快速测试
python -c "
from src.core.pipeline import StockAnalysisPipeline
result = StockAnalysisPipeline().screen_market_stocks()
print(f'Buy: {len(result[\"buy\"])}, Watch: {len(result[\"watch\"])}')
"
```

## 6. API 端点

### 6.1 核心端点

```
GET  /api/v1/health                    # 健康检查
GET  /api/v1/analysis/history          # 历史报告列表
GET  /api/v1/analysis/report/{id}      # 获取单个报告
POST /api/v1/analysis/analyze          # 触发分析
GET  /api/v1/market/recommendations    # 全市场推荐 ★
GET  /api/v1/stocks/list               # 自选股列表
```

### 6.2 市场推荐 API（重点）

**端点**：`GET /api/v1/market/recommendations`

**响应**：
```json
{
  "buy": [
    {
      "name": "特变电工",
      "code": "600089",
      "price": 28.72,
      "change_pct": 3.5,
      "volume_ratio": 0.0,
      "turnover_rate": 0.0,
      "pe": 0.0,
      "market_cap": "N/A",
      "reason": "今日涨3.5%，成交额71.4亿"
    }
  ],
  "watch": [...],
  "updated_at": "2026-02-12 10:32:38"
}
```

**缓存**：5分钟（防止频繁调用）

**代码位置**：
- 后端：`api/v1/endpoints/market.py`
- 前端：`apps/dsa-web/src/api/market.ts`

## 7. 数据流

### 7.1 全市场推荐数据流

```
1. 前端发起请求
   └─ HomePage.tsx (useEffect)
      └─ marketApi.getRecommendations()

2. 后端处理
   └─ GET /api/v1/market/recommendations
      └─ market.py: 检查缓存（5分钟）
         └─ StockAnalysisPipeline.screen_market_stocks()
            ├─ 获取全市场数据（东财/baostock+pytdx/efinance/新浪）
            ├─ 基础过滤（去除ST、涨停、停牌）
            ├─ 买入条件筛选（涨幅0.5-5%、量比≥1.8等）
            ├─ 综合评分排序
            └─ 返回 Top 5

3. 前端渲染
   └─ MarketRecommendations.tsx
      ├─ 买入推荐卡片（绿色标签）
      └─ 观察推荐卡片（橙色标签）
```

### 7.2 自选股分析数据流

```
1. 触发方式
   ├─ 手动：Web界面输入股票代码
   ├─ 定时：scheduler 09:30/15:00
   └─ CLI：python main.py

2. 分析流程
   └─ StockAnalysisPipeline.run()
      ├─ 获取历史K线（60天）
      ├─ 获取实时行情
      ├─ 获取筹码分布
      ├─ 搜索舆情新闻（Tavily/SerpAPI）
      ├─ AI分析（DeepSeek）
      │   ├─ 技术面分析（均线、趋势、支撑位）
      │   ├─ 基本面分析（PE、市值、业绩）
      │   ├─ 舆情分析（新闻情绪）
      │   └─ 综合决策（买入/持有/观察/风险警示）
      ├─ 保存到数据库
      └─ 推送通知
```

## 8. 运维指南

### 8.1 数据源故障处理

**问题**：东财接口被封（push2.eastmoney.com RemoteDisconnected）

**解决**：
1. 系统自动降级到 baostock+pytdx（TCP直连，最可靠）
2. 如仍失败，检查网络或等待1小时后重试

**日志位置**：`logs/stock_analysis_YYYYMMDD.log`

### 8.2 前端不显示推荐

**排查步骤**：
1. 检查后端API：`curl http://localhost:8000/api/v1/market/recommendations`
2. 检查浏览器控制台是否有CORS错误
3. 强制刷新：`Ctrl+Shift+R`
4. 重新构建前端：`cd apps/dsa-web && npx vite build`

### 8.3 AI 分析失败

**可能原因**：
- DeepSeek API Key 过期/余额不足
- API 调用超时（网络问题）

**解决**：
- 检查 `.env` 中 `OPENAI_API_KEY`
- 查看日志：`logs/stock_analysis_debug_YYYYMMDD.log`

### 8.4 临时文件清理

```bash
# 清理所有临时文件
cd daily_stock_analysis
rm -rf .tmp/*
rm -f tmpclaude-*
find . -type d -name "__pycache__" -delete
find . -type f -name "*.pyc" -delete
```

## 9. 性能优化

### 9.1 全市场推荐优化

- **缓存**：实时数据缓存5分钟（`_realtime_cache`）
- **并发控制**：`MAX_WORKERS=3`（避免被封）
- **降级策略**：优先使用TCP源（baostock+pytdx）

### 9.2 前端优化

- **生产构建**：`vite build` 自动tree-shaking、code splitting
- **资源压缩**：gzip压缩（静态文件 117KB → 不压缩时更大）
- **懒加载**：路由级代码分割

## 10. 常见问题

### Q1: 为什么推荐的股票涨幅都很温和（2-5%）？

A: 这是新策略的核心设计。旧策略推荐2-7%容易追高，新策略改为0.5-5%，买在启动初期，降低次日冲高回落风险。

### Q2: pytdx 获取的数据为什么没有量比、PE等字段？

A: pytdx（通达信）只提供基础行情（价格、成交量），没有量比、PE、换手率。需要结合 baostock 获取股票列表，再用 pytdx 批量获取价格。这就是为什么代码里是 `baostock+pytdx` 组合。

### Q3: 为什么数据源这么多层降级？

A: A股数据接口极不稳定：
- 东财：最全但经常被IP封
- baostock：稳定但更新慢
- pytdx：TCP直连，最可靠但字段少
- 新浪：慢且返回HTML概率高

多层降级保证系统可用性。

### Q4: 前端 snake_case 和 camelCase 如何转换？

A: 后端返回 snake_case，前端用 `toCamelCase()` 工具函数（基于 `camelcase-keys`）自动转换。

```typescript
// api/utils.ts
export function toCamelCase<T>(data: unknown): T {
  return camelcaseKeys(data, { deep: true }) as T;
}
```

### Q5: 如何增加新的选股条件？

A: 修改 `src/core/pipeline.py` 的 `screen_market_stocks()` 方法：

```python
# 1. 在 buy_mask 中添加条件
if '新字段' in df_filtered.columns:
    buy_mask = buy_mask & (df_filtered['新字段'] > 阈值)

# 2. 在评分公式中添加权重
new_score = df['新字段'] * 权重
buy_df['_score'] = vr * 20 + momentum_score + new_score
```

## 11. 扩展指南

### 11.1 添加新的数据源

1. 创建 `data_provider/new_fetcher.py`，继承 `BaseFetcher`
2. 实现 `fetch_daily()` 和 `fetch_realtime()` 方法
3. 在 `data_provider/base.py` 的 `_init_default_fetchers()` 中注册

### 11.2 添加新的 API 端点

1. 创建 schema：`api/v1/schemas/new.py`
2. 创建 endpoint：`api/v1/endpoints/new.py`
3. 注册路由：`api/v1/router.py` 添加 `router.include_router()`

### 11.3 添加新的前端组件

1. 创建组件：`apps/dsa-web/src/components/new/NewComponent.tsx`
2. 添加类型：`apps/dsa-web/src/types/analysis.ts`
3. 集成到页面：`apps/dsa-web/src/pages/HomePage.tsx`

## 12. 快速参考

```bash
# === 常用命令 ===
python webui.py                    # 启动Web服务
python main.py                     # 运行一次分析
python main.py --schedule          # 启动定时任务
cd apps/dsa-web && npx vite build  # 前端构建

# === 关键文件 ===
.env                              # 配置文件
src/core/pipeline.py              # 核心业务逻辑（选股、分析）
api/v1/endpoints/market.py        # 市场推荐API
apps/dsa-web/src/components/report/MarketRecommendations.tsx  # 推荐组件

# === 日志位置 ===
logs/stock_analysis_YYYYMMDD.log       # 分析日志
logs/web_server_YYYYMMDD.log           # API日志
.tmp/                                  # 临时文件

# === 数据库 ===
data/stock_analysis.db             # SQLite 数据库
```

---

**文档版本**：2026-02-12
**维护者**：AI Assistant + User
**最后更新**：实现"趋势突破+资金共振"选股策略
