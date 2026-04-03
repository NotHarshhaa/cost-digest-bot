"""AWS Cost Explorer client for fetching cost data."""

import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError


class AWSCostClient:
    """Client for fetching AWS cost data via Cost Explorer API."""
    
    def __init__(self, region: Optional[str] = None):
        """Initialize the AWS Cost Explorer client.
        
        Args:
            region: AWS region. Defaults to AWS_DEFAULT_REGION env var or us-east-1.
        """
        self.region = region or os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        self.client = boto3.client('ce', region_name=self.region)
    
    def get_daily_costs(self, start_date: datetime, end_date: datetime) -> Dict[str, float]:
        """Fetch daily costs by service for a given date range.
        
        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            
        Returns:
            Dictionary mapping service names to total costs in USD
            
        Raises:
            ClientError: If AWS API call fails
        """
        try:
            response = self.client.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Granularity='DAILY',
                Metrics=['BlendedCost'],
                GroupBy=[
                    {
                        'Type': 'DIMENSION',
                        'Key': 'SERVICE'
                    }
                ]
            )
            
            costs = {}
            for result in response.get('ResultsByTime', []):
                for group in result.get('Groups', []):
                    service = group['Keys'][0]
                    amount = float(group['Metrics']['BlendedCost']['Amount'])
                    costs[service] = costs.get(service, 0) + amount
            
            return costs
            
        except ClientError as e:
            raise RuntimeError(f"Failed to fetch AWS costs: {e}")
    
    def get_month_to_date_costs(self, year: int, month: int) -> Dict[str, float]:
        """Fetch month-to-date costs by service.
        
        Args:
            year: Year (e.g., 2026)
            month: Month (1-12)
            
        Returns:
            Dictionary mapping service names to total costs in USD
        """
        start_date = datetime(year, month, 1)
        today = datetime.now()
        end_date = min(today, datetime(year, month + 1, 1) - timedelta(days=1))
        
        return self.get_daily_costs(start_date, end_date)
    
    def get_cost_forecast(self, days: int = 7) -> float:
        """Get cost forecast for the next N days.
        
        Args:
            days: Number of days to forecast
            
        Returns:
            Forecasted cost in USD
        """
        try:
            end_date = datetime.now() + timedelta(days=days)
            response = self.client.get_cost_forecast(
                TimePeriod={
                    'Start': datetime.now().strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Metric='BLENDED_COST',
                Granularity='DAILY'
            )
            
            return float(response['Total']['Amount'])
            
        except ClientError as e:
            raise RuntimeError(f"Failed to fetch cost forecast: {e}")
