import akshare as ak
import pandas as pd
from datetime import datetime, timedelta

# 设置显示格式
pd.set_option('display.max_rows', None)
pd.set_option('display.unicode.ambiguous_as_wide', True)
pd.set_option('display.unicode.east_asian_width', True)

def check_gold_stocks():
    # 基金前三大重仓股 (根据之前脚本查出的)
    gold_stocks = {
        "600489": "中金黄金",
        "600547": "山东黄金",
        "601899": "紫金矿业"
    }
    
    print("🔍 正在扫描黄金股三巨头近期走势...\n")
    
    start_date = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d")
    end_date = datetime.now().strftime("%Y%m%d")
    
    print(f"{'名称':<8} {'最新价':<8} {'涨跌幅':<8} {'趋势判断'}")
    print("-" * 45)
    
    for code, name in gold_stocks.items():
        try:
            # 获取日线数据
            # 优先尝试东方财富接口
            try:
                df = ak.stock_zh_a_hist(symbol=code, start_date=start_date, end_date=end_date, adjust="qfq")
            except:
                # 备用：腾讯接口（需要 sh/sz 前缀）
                prefix = 'sh' if code.startswith('6') else 'sz'
                # 腾讯接口返回的是英文列名，需要映射
                df = ak.stock_zh_a_hist_tx(symbol=f"{prefix}{code}", start_date=start_date, end_date=end_date, adjust="qfq")
                df.rename(columns={'date': '日期', 'close': '收盘', 'amount': '成交额'}, inplace=True)
                # 计算涨跌幅 (腾讯接口可能不直接返回涨跌幅，需手动计算)
                if '涨跌幅' not in df.columns and len(df) > 1:
                    df['涨跌幅'] = df['收盘'].pct_change() * 100
            
            if not df.empty:
                latest = df.iloc[-1]
                # 简单计算均线
                ma5 = df['收盘'].rolling(5).mean().iloc[-1]
                ma20 = df['收盘'].rolling(20).mean().iloc[-1]
                price = latest['收盘']
                pct = latest['涨跌幅']
                
                # 简单趋势判断
                trend = "🤔 震荡"
                if price > ma5 and ma5 > ma20:
                    trend = "🔥 强势上涨"
                elif price < ma5 and ma5 < ma20:
                    trend = "❄️ 下跌趋势"
                
                print(f"{name:<8} {price:<10} {pct:>6.2f}%   {trend}")
            else:
                print(f"{name:<8} 暂无数据")
                
        except Exception as e:
            print(f"{name} 获取失败")

    print("-" * 45)
    print("💡 决策参考：")
    print("   - 如果全是【强势上涨】：拿住！行情还在。")
    print("   - 如果出现【下跌趋势】：金价可能在回调，建议减仓。")

if __name__ == "__main__":
    check_gold_stocks()