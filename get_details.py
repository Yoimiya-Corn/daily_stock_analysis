
import sys
import os
from datetime import datetime, date
from sqlalchemy import create_engine, desc, and_
from sqlalchemy.orm import sessionmaker

# Add project root to sys.path
sys.path.append(os.getcwd())
# Add daily_stock_analysis to path
sys.path.append(os.path.join(os.getcwd(), 'daily_stock_analysis'))

# Import from source code
# Since src is inside daily_stock_analysis, we need to import correctly
# If we run from daily_stock_analysis root:
try:
    from src.storage import AnalysisHistory
except ImportError:
    # If running from outside
    sys.path.append(os.path.abspath('daily_stock_analysis'))
    from src.storage import AnalysisHistory

def main():
    # Path to database relative to where we run or absolute
    db_path = "d:/vscode/gu/data/stock_analysis.db"
    
    db_url = f"sqlite:///{db_path}"
    print(f"Connecting to: {db_url}")
    
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Stocks of interest: 600101 (Star Power), 000400 (Xuji Electric), 600519 (Moutai)
    target_stocks = ['600101', '000400', '600519']
    
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    
    print(f"Querying for date >= {today_start}")
    
    results = session.query(AnalysisHistory).filter(
        and_(
            AnalysisHistory.code.in_(target_stocks),
            AnalysisHistory.created_at >= today_start
        )
    ).order_by(desc(AnalysisHistory.created_at)).all()
    
    if not results:
        print("No results found.")
    
    seen = set()
    for r in results:
        if r.code in seen:
            continue
        seen.add(r.code)
        print(f"\n=== {r.name} ({r.code}) ===")
        print(f"Summary: {r.analysis_summary}")
        print(f"Trend Prediction: {r.trend_prediction}")
        print(f"Operation Advice: {r.operation_advice}")
        print(f"Ideal Buy: {r.ideal_buy}")
        print(f"Stop Loss: {r.stop_loss}")
        print(f"Take Profit: {r.take_profit}")

    session.close()

if __name__ == "__main__":
    main()
