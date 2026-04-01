
import sys
import os
from datetime import datetime, date, timedelta
from sqlalchemy import create_engine, select, desc, and_
from sqlalchemy.orm import sessionmaker

# Add project root to sys.path
sys.path.append(os.getcwd())

from src.storage import AnalysisHistory, DatabaseManager

def main():
    db_path = "./data/stock_analysis.db"
    db_url = f"sqlite:///{os.path.abspath(db_path)}"
    
    print(f"Connecting to database: {db_url}")
    
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    watchlist = ['600519','300750','002594','002009','601398','601288','601988','601939','hk01810','000400','600101']
    
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    
    print(f"Checking analysis for date >= {today_start}")
    
    results = session.query(AnalysisHistory).filter(
        and_(
            AnalysisHistory.code.in_(watchlist),
            AnalysisHistory.created_at >= today_start
        )
    ).order_by(AnalysisHistory.code, desc(AnalysisHistory.created_at)).all()
    
    if not results:
        print("No analysis results found for today.")
        return

    # Deduplicate by code (take latest)
    latest_results = {}
    for r in results:
        if r.code not in latest_results:
            latest_results[r.code] = r
            
    print(f"\n{'Code':<10} {'Name':<10} {'Score':<6} {'Trend':<10} {'Advice':<10}")
    print("-" * 60)
    
    for code in watchlist:
        if code in latest_results:
            r = latest_results[code]
            print(f"{r.code:<10} {r.name[:10]:<10} {r.sentiment_score:<6} {r.trend_prediction[:10]:<10} {r.operation_advice:<10}")
        else:
            print(f"{code:<10} {'Pending...':<10} {'-':<6} {'-':<10} {'-':<10}")

    session.close()

if __name__ == "__main__":
    main()
