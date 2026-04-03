"""Tests for anomaly detection."""

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from bot.anomaly import AnomalyDetector, Anomaly
from bot.diff import CostDiffer
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
def detector(temp_store):
    """Create an anomaly detector with test data."""
    differ = CostDiffer(temp_store)
    return AnomalyDetector(differ, threshold_pct=100.0)


class TestAnomalyDetector:
    """Test cases for AnomalyDetector."""
    
    def test_detect_day_over_day_anomalies(self, detector):
        """Test day-over-day anomaly detection."""
        current_date = date(2026, 4, 3)
        
        anomalies = detector.detect_day_over_day_anomalies(current_date)
        
        # Lambda spiked from 15.23 to 38.45, which is >100% increase
        lambda_anomalies = [a for a in anomalies if a.service == 'Lambda']
        assert len(lambda_anomalies) > 0
        
        lambda_anomaly = lambda_anomalies[0]
        assert lambda_anomaly.current_cost > lambda_anomaly.previous_cost
        assert lambda_anomaly.percentage_change > 100.0
        assert lambda_anomaly.severity in ['low', 'medium', 'high', 'critical']
    
    def test_detect_week_over_week_anomalies(self, detector):
        """Test week-over-week anomaly detection."""
        current_date = date(2026, 4, 3)
        
        # Add data from a week ago
        week_ago = current_date - timedelta(days=7)
        week_ago_costs = {
            'EC2': 400.0,
            'RDS': 180.0,
            'S3': 45.0,
            'Lambda': 8.0  # Much lower to trigger anomaly
        }
        detector.differ.store.store_daily_costs(week_ago, week_ago_costs)
        
        anomalies = detector.detect_week_over_week_anomalies(current_date)
        
        # Should detect anomalies for services that changed significantly
        assert len(anomalies) > 0
    
    def test_detect_unusual_spikes(self, detector):
        """Test unusual spike detection against historical average."""
        current_date = date(2026, 4, 3)
        
        # Add some historical data with lower Lambda costs
        for days_ago in range(1, 8):
            hist_date = current_date - timedelta(days=days_ago)
            hist_costs = {
                'EC2': 500.0,
                'RDS': 190.0,
                'S3': 50.0,
                'Lambda': 12.0  # Consistent lower cost
            }
            detector.differ.store.store_daily_costs(hist_date, hist_costs)
        
        anomalies = detector.detect_unusual_spikes(current_date, lookback_days=7)
        
        # Lambda should be detected as an anomaly
        lambda_anomalies = [a for a in anomalies if a.service == 'Lambda']
        assert len(lambda_anomalies) > 0
    
    def test_anomaly_severity_calculation(self, detector):
        """Test anomaly severity calculation."""
        from bot.diff import ServiceDiff
        
        # Test different severity levels
        test_cases = [
            (50.0, 'low'),
            (150.0, 'medium'),
            (250.0, 'high'),
            (600.0, 'critical')
        ]
        
        for pct_change, expected_severity in test_cases:
            service_diff = ServiceDiff(
                service='Test',
                current_cost=100.0,
                previous_cost=50.0,
                absolute_change=50.0,
                percentage_change=pct_change
            )
            
            severity = detector._calculate_severity(service_diff)
            assert severity == expected_severity
    
    def test_anomaly_description_generation(self, detector):
        """Test anomaly description generation."""
        from bot.diff import ServiceDiff
        
        service_diff = ServiceDiff(
            service='EC2',
            current_cost=150.0,
            previous_cost=100.0,
            absolute_change=50.0,
            percentage_change=50.0
        )
        
        description = detector._generate_description(service_diff, "day over day")
        
        assert 'EC2' in description
        assert 'increased' in description
        assert 'day over day' in description
        assert '100.0' in description
        assert '150.0' in description
        assert '50%' in description
    
    def test_is_anomaly_filtering(self, detector):
        """Test anomaly filtering logic."""
        from bot.diff import ServiceDiff
        
        # Test small absolute change (should be filtered out)
        small_change = ServiceDiff(
            service='Test',
            current_cost=102.0,
            previous_cost=100.0,
            absolute_change=2.0,  # Less than 5.0 threshold
            percentage_change=2.0
        )
        
        assert not detector._is_anomaly(small_change)
        
        # Test large percentage change
        large_change = ServiceDiff(
            service='Test',
            current_cost=200.0,
            previous_cost=100.0,
            absolute_change=100.0,
            percentage_change=100.0
        )
        
        assert detector._is_anomaly(large_change)
        
        # Test zero previous cost with small current cost
        zero_prev_small = ServiceDiff(
            service='Test',
            current_cost=5.0,
            previous_cost=0.0,
            absolute_change=5.0,
            percentage_change=100.0
        )
        
        assert not detector._is_anomaly(zero_prev_small)
    
    def test_get_anomaly_summary(self, detector):
        """Test anomaly summary generation."""
        anomalies = [
            Anomaly('EC2', 100.0, 50.0, 50.0, 100.0, 100.0, 'medium', 'test'),
            Anomaly('RDS', 200.0, 100.0, 100.0, 100.0, 100.0, 'high', 'test'),
            Anomaly('Lambda', 300.0, 75.0, 225.0, 300.0, 100.0, 'critical', 'test'),
            Anomaly('S3', 60.0, 30.0, 30.0, 100.0, 100.0, 'medium', 'test')
        ]
        
        summary = detector.get_anomaly_summary(anomalies)
        
        assert summary['low'] == 0
        assert summary['medium'] == 2
        assert summary['high'] == 1
        assert summary['critical'] == 1


class TestAnomaly:
    """Test cases for Anomaly dataclass."""
    
    def test_anomaly_creation(self):
        """Test Anomaly creation."""
        anomaly = Anomaly(
            service='EC2',
            current_cost=100.0,
            previous_cost=50.0,
            absolute_change=50.0,
            percentage_change=100.0,
            threshold_pct=100.0,
            severity='medium',
            description='EC2 spend increased day over day'
        )
        
        assert anomaly.service == 'EC2'
        assert anomaly.current_cost == 100.0
        assert anomaly.previous_cost == 50.0
        assert anomaly.absolute_change == 50.0
        assert anomaly.percentage_change == 100.0
        assert anomaly.threshold_pct == 100.0
        assert anomaly.severity == 'medium'
        assert 'EC2' in anomaly.description
