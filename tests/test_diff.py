"""Tests for cost difference calculations."""

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from bot.diff import CostDiffer, CostComparison, ServiceDiff
from bot.store import CostStore


@pytest.fixture
def temp_store():
    """Create a temporary cost store for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    store = CostStore(db_path)
    
    # Load sample data
    fixtures_dir = Path(__file__).parent / 'fixtures'
    with open(fixtures_dir / 'sample_costs.json') as f:
        sample_costs = json.load(f)
    
    # Store sample data
    for date_str, costs in sample_costs.items():
        dt = date.fromisoformat(date_str)
        store.store_daily_costs(dt, costs)
    
    yield store
    
    # Cleanup
    Path(db_path).unlink()


@pytest.fixture
def differ(temp_store):
    """Create a cost differ with the temp store."""
    return CostDiffer(temp_store)


class TestCostDiffer:
    """Test cases for CostDiffer."""
    
    def test_compare_week_over_week(self, differ):
        """Test week-over-week comparison."""
        # Compare April 3 with March 27 (would be week over week)
        # Since we only have April data, let's test with what we have
        current_date = date(2026, 4, 3)
        previous_date = current_date - timedelta(days=7)
        
        # Store some data for the previous date
        previous_costs = {
            'EC2': 500.0,
            'RDS': 200.0,
            'S3': 50.0,
            'Lambda': 10.0
        }
        differ.store.store_daily_costs(previous_date, previous_costs)
        
        comparison = differ.compare_week_over_week(current_date)
        
        assert comparison is not None
        assert comparison.total_current > 0
        assert comparison.total_previous > 0
        assert len(comparison.service_diffs) > 0
    
    def test_compare_day_over_day(self, differ):
        """Test day-over-day comparison."""
        current_date = date(2026, 4, 3)
        previous_date = date(2026, 4, 2)
        
        comparison = differ.compare_day_over_day(current_date)
        
        assert comparison is not None
        assert comparison.total_current > 0
        assert comparison.total_previous > 0
        
        # Check that we have data for both dates
        assert len(comparison.service_diffs) > 0
        
        # Check specific services
        ec2_diff = next((d for d in comparison.service_diffs if d.service == 'EC2'), None)
        assert ec2_diff is not None
        assert ec2_diff.current_cost > ec2_diff.previous_cost  # EC2 increased
    
    def test_month_to_date_progress(self, differ):
        """Test month-to-date progress calculation."""
        year, month = 2026, 4
        budget = 25000.0
        
        progress = differ.get_month_to_date_progress(year, month, budget)
        
        assert 'mtd_total' in progress
        assert 'budget' in progress
        assert 'budget_remaining' in progress
        assert 'budget_used_pct' in progress
        assert 'days_in_month' in progress
        assert 'current_day' in progress
        
        assert progress['mtd_total'] > 0
        assert progress['budget'] == budget
        assert progress['budget_remaining'] < budget
        assert 0 < progress['budget_used_pct'] < 100
    
    def test_percentage_change_calculation(self, differ):
        """Test percentage change calculation."""
        # Test normal case
        pct = differ._calculate_percentage_change(100.0, 25.0)
        assert pct == 25.0
        
        # Test decrease
        pct = differ._calculate_percentage_change(100.0, -25.0)
        assert pct == -25.0
        
        # Test zero previous value
        pct = differ._calculate_percentage_change(0.0, 50.0)
        assert pct == 100.0
        
        # Test zero previous and zero change
        pct = differ._calculate_percentage_change(0.0, 0.0)
        assert pct == 0.0
    
    def test_top_movers_sorting(self, differ):
        """Test that top movers are sorted correctly."""
        current_date = date(2026, 4, 3)
        previous_date = date(2026, 4, 2)
        
        comparison = differ.compare_day_over_day(current_date)
        
        assert comparison is not None
        assert len(comparison.top_movers) > 0
        
        # Check that top movers are sorted by absolute change (descending)
        for i in range(len(comparison.top_movers) - 1):
            current_abs = abs(comparison.top_movers[i].absolute_change)
            next_abs = abs(comparison.top_movers[i + 1].absolute_change)
            assert current_abs >= next_abs


class TestServiceDiff:
    """Test cases for ServiceDiff dataclass."""
    
    def test_service_diff_creation(self):
        """Test ServiceDiff creation."""
        diff = ServiceDiff(
            service="EC2",
            current_cost=100.0,
            previous_cost=80.0,
            absolute_change=20.0,
            percentage_change=25.0
        )
        
        assert diff.service == "EC2"
        assert diff.current_cost == 100.0
        assert diff.previous_cost == 80.0
        assert diff.absolute_change == 20.0
        assert diff.percentage_change == 25.0


class TestCostComparison:
    """Test cases for CostComparison dataclass."""
    
    def test_cost_comparison_creation(self):
        """Test CostComparison creation."""
        service_diffs = [
            ServiceDiff("EC2", 100.0, 80.0, 20.0, 25.0),
            ServiceDiff("RDS", 50.0, 60.0, -10.0, -16.67)
        ]
        
        comparison = CostComparison(
            total_current=150.0,
            total_previous=140.0,
            total_change=10.0,
            total_percentage_change=7.14,
            service_diffs=service_diffs,
            top_movers=service_diffs
        )
        
        assert comparison.total_current == 150.0
        assert comparison.total_previous == 140.0
        assert comparison.total_change == 10.0
        assert len(comparison.service_diffs) == 2
        assert len(comparison.top_movers) == 2
