"""Main entry point for the cost digest bot."""

import os
import sys
from datetime import date, datetime, timedelta
from typing import Optional

from dotenv import load_dotenv

from .aws_costs import AWSCostClient
from .anomaly import AnomalyDetector
from .diff import CostDiffer
from .slack_post import SlackPoster
from .store import CostStore


def load_config():
    """Load configuration from environment variables."""
    load_dotenv()
    
    return {
        'aws_region': os.getenv('AWS_DEFAULT_REGION', 'us-east-1'),
        'slack_token': os.getenv('SLACK_BOT_TOKEN'),
        'slack_channel': os.getenv('SLACK_CHANNEL', '#infra-costs'),
        'monthly_budget': os.getenv('MONTHLY_BUDGET_USD'),
        'anomaly_threshold': float(os.getenv('ANOMALY_THRESHOLD_PCT', '100')),
        'top_movers_count': int(os.getenv('TOP_MOVERS_COUNT', '5')),
        'lookback_days': int(os.getenv('LOOKBACK_DAYS', '7')),
        'dry_run': os.getenv('DRY_RUN', 'false').lower() == 'true'
    }


def fetch_and_store_costs(aws_client: AWSCostClient, store: CostStore, target_date: date) -> bool:
    """Fetch costs from AWS and store them locally.
    
    Args:
        aws_client: AWS Cost Explorer client
        store: Local cost store
        target_date: Date to fetch costs for
        
    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"Fetching AWS costs for {target_date}...")
        
        # Fetch costs for the target date
        costs = aws_client.get_daily_costs(target_date, target_date)
        
        if not costs:
            print("No cost data returned from AWS")
            return False
        
        # Store the costs
        store.store_daily_costs(target_date, costs)
        
        total_cost = sum(costs.values())
        print(f"Stored {len(costs)} services with total cost ${total_cost:.2f}")
        
        return True
        
    except Exception as e:
        print(f"Error fetching costs: {e}")
        return False


def generate_digest(
    store: CostStore,
    differ: CostDiffer,
    anomaly_detector: AnomalyDetector,
    slack_poster: SlackPoster,
    target_date: date,
    config: dict
) -> bool:
    """Generate and post the daily cost digest.
    
    Args:
        store: Cost store
        differ: Cost differ
        anomaly_detector: Anomaly detector
        slack_poster: Slack poster
        target_date: Target date
        config: Configuration dictionary
        
    Returns:
        True if successful, False otherwise
    """
    try:
        print("Generating cost digest...")
        
        # Get week-over-week comparison
        comparison = differ.compare_week_over_week(target_date)
        if comparison is None:
            print("No comparison data available (need at least 8 days of data)")
            return False
        
        print(f"Total cost: ${comparison.total_current:.2f} ({comparison.total_percentage_change:+.1f}% vs last week)")
        
        # Detect anomalies
        print("Detecting anomalies...")
        day_over_day_anomalies = anomaly_detector.detect_day_over_day_anomalies(target_date)
        week_over_week_anomalies = anomaly_detector.detect_week_over_week_anomalies(target_date)
        unusual_spikes = anomaly_detector.detect_unusual_spikes(target_date, config['lookback_days'])
        
        # Combine and deduplicate anomalies
        all_anomalies = list(set(day_over_day_anomalies + week_over_week_anomalies + unusual_spikes))
        
        if all_anomalies:
            print(f"Found {len(all_anomalies)} anomalies:")
            for anomaly in all_anomalies:
                print(f"  - {anomaly.severity}: {anomaly.description}")
        else:
            print("No anomalies detected")
        
        # Get month-to-date progress
        mtd_progress = None
        if config['monthly_budget']:
            try:
                budget = float(config['monthly_budget'])
                mtd_progress = differ.get_month_to_date_progress(
                    target_date.year, target_date.month, budget
                )
                print(f"Month-to-date: ${mtd_progress['mtd_total']:.2f} of ${budget:.2f} budget")
            except ValueError:
                print("Invalid monthly budget format")
        
        # Post to Slack (unless dry run)
        if config['dry_run']:
            print("DRY RUN: Would post to Slack")
            print(f"Channel: {config['slack_channel']}")
            return True
        
        print("Posting to Slack...")
        success = slack_poster.post_daily_digest(
            target_date,
            comparison,
            all_anomalies,
            mtd_progress,
            config['top_movers_count']
        )
        
        if success:
            print("Successfully posted to Slack")
        else:
            print("Failed to post to Slack")
        
        return success
        
    except Exception as e:
        print(f"Error generating digest: {e}")
        return False


def backfill_data(aws_client: AWSCostClient, store: CostStore, days: int) -> None:
    """Backfill historical data for the specified number of days.
    
    Args:
        aws_client: AWS Cost Explorer client
        store: Local cost store
        days: Number of days to backfill
    """
    print(f"Backfilling data for the last {days} days...")
    
    for days_ago in range(days, 0, -1):
        target_date = date.today() - timedelta(days=days_ago)
        
        # Check if we already have data for this date
        if store.get_daily_costs(target_date) is not None:
            print(f"Data already exists for {target_date}, skipping")
            continue
        
        success = fetch_and_store_costs(aws_client, store, target_date)
        if success:
            print(f"Backfilled data for {target_date}")
        else:
            print(f"Failed to backfill data for {target_date}")


def main(target_date: Optional[date] = None) -> int:
    """Main entry point.
    
    Args:
        target_date: Target date for the digest. Defaults to yesterday.
        
    Returns:
        Exit code (0 for success, 1 for error)
    """
    try:
        config = load_config()
        
        # Validate required configuration
        if not config['slack_token']:
            print("Error: SLACK_BOT_TOKEN is required")
            return 1
        
        # Use yesterday as default target date
        if target_date is None:
            target_date = date.today() - timedelta(days=1)
        
        print(f"Running cost digest for {target_date}")
        
        # Initialize components
        aws_client = AWSCostClient(config['aws_region'])
        store = CostStore()
        differ = CostDiffer(store)
        anomaly_detector = AnomalyDetector(differ, config['anomaly_threshold'])
        slack_poster = SlackPoster(config['slack_token'], config['slack_channel'])
        
        # Test Slack connection
        if not slack_poster.test_connection():
            print("Error: Failed to connect to Slack")
            return 1
        
        # Fetch and store costs
        if not fetch_and_store_costs(aws_client, store, target_date):
            return 1
        
        # Generate and post digest
        if not generate_digest(store, differ, anomaly_detector, slack_poster, target_date, config):
            return 1
        
        print("Cost digest completed successfully")
        return 0
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        return 130
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1


if __name__ == '__main__':
    # Parse command line arguments
    target_date = None
    
    if len(sys.argv) > 1:
        if sys.argv[1] == '--backfill':
            # Backfill mode
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
            config = load_config()
            aws_client = AWSCostClient(config['aws_region'])
            store = CostStore()
            backfill_data(aws_client, store, days)
            sys.exit(0)
        elif sys.argv[1] == '--date':
            # Specific date mode
            try:
                target_date = datetime.strptime(sys.argv[2], '%Y-%m-%d').date()
            except (IndexError, ValueError):
                print("Usage: python digest.py --date YYYY-MM-DD")
                sys.exit(1)
        elif sys.argv[1] in ['-h', '--help']:
            print("Usage: python digest.py [OPTIONS]")
            print("")
            print("Options:")
            print("  --backfill [DAYS]    Backfill historical data (default: 7 days)")
            print("  --date YYYY-MM-DD    Generate digest for specific date")
            print("  --help               Show this help message")
            print("")
            print("Environment variables:")
            print("  SLACK_BOT_TOKEN      Slack bot token (required)")
            print("  SLACK_CHANNEL        Slack channel (default: #infra-costs)")
            print("  AWS_DEFAULT_REGION   AWS region (default: us-east-1)")
            print("  MONTHLY_BUDGET_USD   Monthly budget in USD")
            print("  ANOMALY_THRESHOLD_PCT Anomaly threshold percentage (default: 100)")
            print("  TOP_MOVERS_COUNT     Number of top services to show (default: 5)")
            print("  LOOKBACK_DAYS        Days for historical comparison (default: 7)")
            print("  DRY_RUN              Set to 'true' to skip posting to Slack")
            sys.exit(0)
    
    exit_code = main(target_date)
    sys.exit(exit_code)
