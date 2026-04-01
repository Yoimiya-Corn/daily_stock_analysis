import efinance as ef
import pandas as pd

# 设置显示格式，防止输出错位
pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)
pd.set_option('display.unicode.ambiguous_as_wide', True)
pd.set_option('display.unicode.east_asian_width', True)

fund_code = "001467"
print(f"🔍 正在深度分析: 华富永鑫灵活配置混合C ({fund_code})...\n")

try:
    # 1. 查业绩：看看最近赚钱没
    df_history = ef.fund.get_quote_history(fund_code)
    if df_history is not None and not df_history.empty:
        latest = df_history.iloc[-1]
        print(f"📅 最新净值日期: {latest['日期']}")
        print(f"💰 单位净值: {latest['单位净值']}")
        # 修正：efinance 返回的列名是 '涨跌幅' 而不是 '日增长率'
        pct_change = latest.get('涨跌幅', 'N/A')
        print(f"📈 日涨跌幅: {pct_change}%\n")
        
        # 简单计算近1月收益
        if len(df_history) >= 20:
            month_ago = df_history.iloc[-20]
            month_return = (latest['单位净值'] - month_ago['单位净值']) / month_ago['单位净值'] * 100
            print(f"📊 近1月收益率: {month_return:.2f}% (跑赢理财了吗？)")
    
    # 2. 查持仓：使用 akshare 替代 efinance (efinance 接口不稳定)
    print(f"\n📦 [核心持仓揭秘]")
    import akshare as ak
    try:
        # 使用 akshare 获取基金持仓
        positions = ak.fund_portfolio_hold_em(symbol=fund_code)
        
        if positions is not None and not positions.empty:
            latest_date = positions['季度'].iloc[0]
            latest_pos = positions[positions['季度'] == latest_date]
            
            print(f"报告期: {latest_date}")
            print("-" * 40)
            # 打印股票代码、名称和占比
            print(latest_pos[['股票代码', '股票名称', '占净值比例']].to_string(index=False))
                
            print("-" * 40)
            print("💡 决策辅助：")
            print("   - 如果重仓股是【贵州茅台、宁德时代】等大白马 -> 偏向核心资产，稳健持有。")
            print("   - 如果重仓股是【中际旭创、工业富联】等科技股 -> 偏向AI成长，波动大，适合定投。")
        else:
            print("⚠️ 暂未获取到持仓数据，可能是新基金或数据源未更新。")
            
    except Exception as e:
        print(f"❌ akshare 获取持仓失败: {e}")
        # 继续尝试 efinance 旧逻辑作为 fallback（虽然大概率也失败）
        pass

    # 原有逻辑（已失效，保留结构）
    positions = None

except Exception as e:
    print(f"❌ 分析中断: {e}")
    print("提示: 请确保已安装 efinance (pip install efinance)")