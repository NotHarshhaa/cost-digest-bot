"""SQLite database for storing daily cost snapshots."""

import json
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional


class CostStore:
    """SQLite database for storing and retrieving daily cost data."""
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize the cost store.
        
        Args:
            db_path: Path to SQLite database file. Defaults to data/costs.db
        """
        if db_path is None:
            db_path = Path(__file__).parent.parent / "data" / "costs.db"
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_costs (
                    date TEXT PRIMARY KEY,
                    total_cost REAL NOT NULL,
                    service_costs TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
    
    def store_daily_costs(self, date: date, costs: Dict[str, float]) -> None:
        """Store daily costs by service.
        
        Args:
            date: Date of the costs
            costs: Dictionary mapping service names to costs in USD
        """
        total_cost = sum(costs.values())
        service_costs_json = json.dumps(costs)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO daily_costs (date, total_cost, service_costs)
                VALUES (?, ?, ?)
                """,
                (date.isoformat(), total_cost, service_costs_json)
            )
            conn.commit()
    
    def get_daily_costs(self, date: date) -> Optional[Dict[str, float]]:
        """Retrieve daily costs by service for a specific date.
        
        Args:
            date: Date to retrieve costs for
            
        Returns:
            Dictionary mapping service names to costs in USD, or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT service_costs FROM daily_costs WHERE date = ?",
                (date.isoformat(),)
            )
            row = cursor.fetchone()
            
            if row is None:
                return None
            
            return json.loads(row[0])
    
    def get_total_cost(self, date: date) -> Optional[float]:
        """Retrieve total cost for a specific date.
        
        Args:
            date: Date to retrieve total cost for
            
        Returns:
            Total cost in USD, or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT total_cost FROM daily_costs WHERE date = ?",
                (date.isoformat(),)
            )
            row = cursor.fetchone()
            return row[0] if row else None
    
    def get_costs_range(self, start_date: date, end_date: date) -> List[Dict]:
        """Retrieve costs for a date range.
        
        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            
        Returns:
            List of dictionaries with date, total_cost, and service_costs
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT date, total_cost, service_costs 
                FROM daily_costs 
                WHERE date BETWEEN ? AND ?
                ORDER BY date
                """,
                (start_date.isoformat(), end_date.isoformat())
            )
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'date': datetime.fromisoformat(row[0]).date(),
                    'total_cost': row[1],
                    'service_costs': json.loads(row[2])
                })
            
            return results
    
    def get_month_to_date_total(self, year: int, month: int) -> float:
        """Calculate month-to-date total cost.
        
        Args:
            year: Year
            month: Month (1-12)
            
        Returns:
            Month-to-date total cost in USD
        """
        start_date = date(year, month, 1)
        today = date.today()
        
        # If asking for current month, go up to today
        if year == today.year and month == today.month:
            end_date = today
        else:
            # For past months, go to end of month
            if month == 12:
                end_date = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(year, month + 1, 1) - timedelta(days=1)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT COALESCE(SUM(total_cost), 0)
                FROM daily_costs 
                WHERE date BETWEEN ? AND ?
                """,
                (start_date.isoformat(), end_date.isoformat())
            )
            return cursor.fetchone()[0]
    
    def get_latest_date(self) -> Optional[date]:
        """Get the most recent date with stored costs.
        
        Returns:
            Most recent date with data, or None if no data exists
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT date FROM daily_costs ORDER BY date DESC LIMIT 1"
            )
            row = cursor.fetchone()
            return datetime.fromisoformat(row[0]).date() if row else None
