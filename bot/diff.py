"""Cost comparison and difference calculations."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from .store import CostStore


@dataclass
class ServiceDiff:
    """Cost difference for a single service."""
    service: str
    current_cost: float
    previous_cost: float
    absolute_change: float
    percentage_change: float


@dataclass
class CostComparison:
    """Complete cost comparison between two periods."""
    total_current: float
    total_previous: float
    total_change: float
    total_percentage_change: float
    service_diffs: List[ServiceDiff]
    top_movers: List[ServiceDiff]


class CostDiffer:
    """Calculate cost differences between time periods."""
    
    def __init__(self, store: CostStore):
        """Initialize the cost differ.
        
        Args:
            store: CostStore instance for retrieving historical data
        """
        self.store = store
    
    def compare_week_over_week(self, current_date: date) -> Optional[CostComparison]:
        """Compare costs with the same day last week.
        
        Args:
            current_date: Current date to compare
            
        Returns:
            CostComparison with week-over-week differences, or None if no data
        """
        previous_date = current_date - timedelta(days=7)
        
        current_costs = self.store.get_daily_costs(current_date)
        previous_costs = self.store.get_daily_costs(previous_date)
        
        if current_costs is None or previous_costs is None:
            return None
        
        return self._compare_costs(current_costs, previous_costs)
    
    def compare_day_over_day(self, current_date: date) -> Optional[CostComparison]:
        """Compare costs with the previous day.
        
        Args:
            current_date: Current date to compare
            
        Returns:
            CostComparison with day-over-day differences, or None if no data
        """
        previous_date = current_date - timedelta(days=1)
        
        current_costs = self.store.get_daily_costs(current_date)
        previous_costs = self.store.get_daily_costs(previous_date)
        
        if current_costs is None or previous_costs is None:
            return None
        
        return self._compare_costs(current_costs, previous_costs)
    
    def _compare_costs(self, current: Dict[str, float], previous: Dict[str, float]) -> CostComparison:
        """Compare two cost dictionaries.
        
        Args:
            current: Current period costs by service
            previous: Previous period costs by service
            
        Returns:
            CostComparison with detailed differences
        """
        total_current = sum(current.values())
        total_previous = sum(previous.values())
        
        total_change = total_current - total_previous
        total_percentage_change = self._calculate_percentage_change(total_previous, total_change)
        
        service_diffs = []
        all_services = set(current.keys()) | set(previous.keys())
        
        for service in all_services:
            current_cost = current.get(service, 0.0)
            previous_cost = previous.get(service, 0.0)
            
            absolute_change = current_cost - previous_cost
            percentage_change = self._calculate_percentage_change(previous_cost, absolute_change)
            
            service_diffs.append(ServiceDiff(
                service=service,
                current_cost=current_cost,
                previous_cost=previous_cost,
                absolute_change=absolute_change,
                percentage_change=percentage_change
            ))
        
        # Sort by absolute change (descending) for top movers
        top_movers = sorted(
            [d for d in service_diffs if d.absolute_change != 0],
            key=lambda x: abs(x.absolute_change),
            reverse=True
        )
        
        return CostComparison(
            total_current=total_current,
            total_previous=total_previous,
            total_change=total_change,
            total_percentage_change=total_percentage_change,
            service_diffs=service_diffs,
            top_movers=top_movers
        )
    
    def _calculate_percentage_change(self, previous: float, change: float) -> float:
        """Calculate percentage change.
        
        Args:
            previous: Previous value
            change: Absolute change
            
        Returns:
            Percentage change (positive for increase, negative for decrease)
        """
        if previous == 0:
            return 100.0 if change > 0 else 0.0
        return (change / previous) * 100
    
    def get_month_to_date_progress(self, year: int, month: int, budget: Optional[float] = None) -> Dict[str, float]:
        """Get month-to-date spending progress.
        
        Args:
            year: Year
            month: Month (1-12)
            budget: Optional monthly budget in USD
            
        Returns:
            Dictionary with MTD metrics
        """
        mtd_total = self.store.get_month_to_date_total(year, month)
        
        result = {
            'mtd_total': mtd_total,
            'days_in_month': self._days_in_month(year, month),
            'current_day': date.today().day if date.today().year == year and date.today().month == month else self._days_in_month(year, month)
        }
        
        if budget:
            result['budget'] = budget
            result['budget_remaining'] = budget - mtd_total
            result['budget_used_pct'] = (mtd_total / budget) * 100
            
            # Project end-of-month total based on current spending rate
            days_passed = result['current_day']
            if days_passed > 0:
                daily_avg = mtd_total / days_passed
                days_remaining = result['days_in_month'] - days_passed
                projected_total = mtd_total + (daily_avg * days_remaining)
                result['projected_total'] = projected_total
                result['projected_vs_budget'] = projected_total - budget
        
        return result
    
    def _days_in_month(self, year: int, month: int) -> int:
        """Get the number of days in a month.
        
        Args:
            year: Year
            month: Month (1-12)
            
        Returns:
            Number of days in the month
        """
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        
        return (next_month - date(year, month, 1)).days
