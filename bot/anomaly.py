"""Anomaly detection for cost spikes."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional

from .diff import CostDiffer, ServiceDiff


@dataclass
class Anomaly:
    """Detected cost anomaly."""
    service: str
    current_cost: float
    previous_cost: float
    absolute_change: float
    percentage_change: float
    threshold_pct: float
    severity: str  # 'low', 'medium', 'high', 'critical'
    description: str


class AnomalyDetector:
    """Detects cost anomalies based on configurable thresholds."""
    
    def __init__(self, differ: CostDiffer, threshold_pct: float = 100.0):
        """Initialize the anomaly detector.
        
        Args:
            differ: CostDiffer instance for comparisons
            threshold_pct: Percentage change threshold for anomaly detection
        """
        self.differ = differ
        self.threshold_pct = threshold_pct
    
    def detect_day_over_day_anomalies(self, current_date: date) -> List[Anomaly]:
        """Detect anomalies by comparing current costs with previous day.
        
        Args:
            current_date: Current date to analyze
            
        Returns:
            List of detected anomalies
        """
        comparison = self.differ.compare_day_over_day(current_date)
        
        if comparison is None:
            return []
        
        anomalies = []
        for service_diff in comparison.service_diffs:
            if self._is_anomaly(service_diff):
                severity = self._calculate_severity(service_diff)
                description = self._generate_description(service_diff, "day over day")
                
                anomalies.append(Anomaly(
                    service=service_diff.service,
                    current_cost=service_diff.current_cost,
                    previous_cost=service_diff.previous_cost,
                    absolute_change=service_diff.absolute_change,
                    percentage_change=service_diff.percentage_change,
                    threshold_pct=self.threshold_pct,
                    severity=severity,
                    description=description
                ))
        
        return anomalies
    
    def detect_week_over_week_anomalies(self, current_date: date) -> List[Anomaly]:
        """Detect anomalies by comparing current costs with same day last week.
        
        Args:
            current_date: Current date to analyze
            
        Returns:
            List of detected anomalies
        """
        comparison = self.differ.compare_week_over_week(current_date)
        
        if comparison is None:
            return []
        
        anomalies = []
        for service_diff in comparison.service_diffs:
            if self._is_anomaly(service_diff):
                severity = self._calculate_severity(service_diff)
                description = self._generate_description(service_diff, "week over week")
                
                anomalies.append(Anomaly(
                    service=service_diff.service,
                    current_cost=service_diff.current_cost,
                    previous_cost=service_diff.previous_cost,
                    absolute_change=service_diff.absolute_change,
                    percentage_change=service_diff.percentage_change,
                    threshold_pct=self.threshold_pct,
                    severity=severity,
                    description=description
                ))
        
        return anomalies
    
    def detect_unusual_spikes(self, current_date: date, lookback_days: int = 7) -> List[Anomaly]:
        """Detect unusual spikes by comparing against historical average.
        
        Args:
            current_date: Current date to analyze
            lookback_days: Number of days to look back for average calculation
            
        Returns:
            List of detected anomalies
        """
        current_costs = self.differ.store.get_daily_costs(current_date)
        if current_costs is None:
            return []
        
        anomalies = []
        
        for service, current_cost in current_costs.items():
            if current_cost < 1.0:  # Skip very small costs
                continue
            
            # Calculate historical average
            historical_costs = []
            for days_ago in range(1, lookback_days + 1):
                hist_date = current_date - timedelta(days=days_ago)
                hist_costs = self.differ.store.get_daily_costs(hist_date)
                if hist_costs and service in hist_costs:
                    historical_costs.append(hist_costs[service])
            
            if not historical_costs:
                continue
            
            avg_historical_cost = sum(historical_costs) / len(historical_costs)
            
            if avg_historical_cost == 0:
                percentage_change = 100.0 if current_cost > 0 else 0.0
            else:
                percentage_change = ((current_cost - avg_historical_cost) / avg_historical_cost) * 100
            
            if percentage_change >= self.threshold_pct:
                absolute_change = current_cost - avg_historical_cost
                severity = self._calculate_severity_from_percentage(percentage_change)
                
                description = (
                    f"{service} spend {percentage_change:.0f}% higher than {lookback_days}-day average "
                    f"(${avg_historical_cost:.2f} → ${current_cost:.2f})"
                )
                
                anomalies.append(Anomaly(
                    service=service,
                    current_cost=current_cost,
                    previous_cost=avg_historical_cost,
                    absolute_change=absolute_change,
                    percentage_change=percentage_change,
                    threshold_pct=self.threshold_pct,
                    severity=severity,
                    description=description
                ))
        
        return anomalies
    
    def _is_anomaly(self, service_diff: ServiceDiff) -> bool:
        """Check if a service diff qualifies as an anomaly.
        
        Args:
            service_diff: Service cost difference
            
        Returns:
            True if this is an anomaly
        """
        # Skip very small absolute changes
        if abs(service_diff.absolute_change) < 5.0:
            return False
        
        # Skip if previous cost was zero and current cost is small
        if service_diff.previous_cost == 0 and service_diff.current_cost < 10.0:
            return False
        
        return abs(service_diff.percentage_change) >= self.threshold_pct
    
    def _calculate_severity(self, service_diff: ServiceDiff) -> str:
        """Calculate anomaly severity based on percentage change.
        
        Args:
            service_diff: Service cost difference
            
        Returns:
            Severity level: 'low', 'medium', 'high', or 'critical'
        """
        pct_change = abs(service_diff.percentage_change)
        
        if pct_change >= 500:
            return 'critical'
        elif pct_change >= 300:
            return 'high'
        elif pct_change >= 200:
            return 'medium'
        else:
            return 'low'
    
    def _calculate_severity_from_percentage(self, percentage_change: float) -> str:
        """Calculate severity from percentage change.
        
        Args:
            percentage_change: Percentage change
            
        Returns:
            Severity level
        """
        pct_change = abs(percentage_change)
        
        if pct_change >= 500:
            return 'critical'
        elif pct_change >= 300:
            return 'high'
        elif pct_change >= 200:
            return 'medium'
        else:
            return 'low'
    
    def _generate_description(self, service_diff: ServiceDiff, comparison_type: str) -> str:
        """Generate human-readable anomaly description.
        
        Args:
            service_diff: Service cost difference
            comparison_type: Type of comparison (e.g., "day over day")
            
        Returns:
            Human-readable description
        """
        if service_diff.previous_cost == 0:
            if service_diff.current_cost > 0:
                return f"{service_diff.service} spend appeared from nowhere (${service_diff.current_cost:.2f})"
            else:
                return f"{service_diff.service} spend dropped to zero"
        
        direction = "increased" if service_diff.absolute_change > 0 else "decreased"
        
        return (
            f"{service_diff.service} spend {direction} {comparison_type} "
            f"(${service_diff.previous_cost:.2f} → ${service_diff.current_cost:.2f}, "
            f"{abs(service_diff.percentage_change):.0f}% change)"
        )
    
    def get_anomaly_summary(self, anomalies: List[Anomaly]) -> Dict[str, int]:
        """Get a summary of anomalies by severity.
        
        Args:
            anomalies: List of anomalies
            
        Returns:
            Dictionary mapping severity to count
        """
        summary = {'low': 0, 'medium': 0, 'high': 0, 'critical': 0}
        
        for anomaly in anomalies:
            summary[anomaly.severity] += 1
        
        return summary
