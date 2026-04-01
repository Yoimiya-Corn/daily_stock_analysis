
import sys
import os
import logging
from datetime import datetime

# Adjust path to find src
sys.path.append(os.getcwd())

from src.storage import DatabaseManager, AnalysisHistory
from sqlalchemy import select, desc

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    db = DatabaseManager.get_instance()
    
    with db.get_session() as session:
        # Check last 10 records
        stmt = select(AnalysisHistory).order_by(desc(AnalysisHistory.created_at)).limit(10)
        results = session.execute(stmt).scalars().all()
        
        print(f"\n当前系统时间: {datetime.now()}")
        print("-" * 50)
        print("【最新 10 条分析记录】")
        for r in results:
            print(f"ID: {r.id}, Code: {r.code}, Name: {r.name}, CreatedAt: {r.created_at}, QueryID: {r.query_id}")
            
        # Check specific stock 600101
        print("-" * 50)
        print("【明星电力 (600101) 分析记录】")
        stmt = select(AnalysisHistory).where(AnalysisHistory.code == '600101').order_by(desc(AnalysisHistory.created_at)).limit(5)
        results = session.execute(stmt).scalars().all()
        for r in results:
            print(f"ID: {r.id}, Code: {r.code}, CreatedAt: {r.created_at}, QueryID: {r.query_id}")

if __name__ == "__main__":
    main()
