"""Slack message builder and poster using Block Kit."""

import os
from datetime import date
from typing import Dict, List, Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from .anomaly import Anomaly
from .diff import CostComparison


class SlackPoster:
    """Posts cost digests to Slack using Block Kit."""
    
    def __init__(self, token: Optional[str] = None, channel: Optional[str] = None):
        """Initialize the Slack poster.
        
        Args:
            token: Slack bot token. Defaults to SLACK_BOT_TOKEN env var.
            channel: Slack channel. Defaults to SLACK_CHANNEL env var.
        """
        self.token = token or os.getenv('SLACK_BOT_TOKEN')
        self.channel = channel or os.getenv('SLACK_CHANNEL', '#infra-costs')
        
        if not self.token:
            raise ValueError("Slack token is required. Set SLACK_BOT_TOKEN environment variable.")
        
        self.client = WebClient(token=self.token)
    
    def post_daily_digest(
        self,
        current_date: date,
        comparison: CostComparison,
        anomalies: List[Anomaly],
        mtd_progress: Optional[Dict] = None,
        top_movers_count: int = 5
    ) -> bool:
        """Post daily cost digest to Slack.
        
        Args:
            current_date: Current date
            comparison: Week-over-week cost comparison
            anomalies: List of detected anomalies
            mtd_progress: Month-to-date progress metrics
            top_movers_count: Number of top services to show
            
        Returns:
            True if posted successfully, False otherwise
        """
        try:
            blocks = self._build_digest_blocks(
                current_date, comparison, anomalies, mtd_progress, top_movers_count
            )
            
            response = self.client.chat_postMessage(
                channel=self.channel,
                blocks=blocks,
                text=f"📊 Daily Cost Digest — {current_date.strftime('%b %d, %Y')}"
            )
            
            return response['ok']
            
        except SlackApiError as e:
            print(f"Error posting to Slack: {e}")
            return False
    
    def _build_digest_blocks(
        self,
        current_date: date,
        comparison: CostComparison,
        anomalies: List[Anomaly],
        mtd_progress: Optional[Dict],
        top_movers_count: int
    ) -> List[Dict]:
        """Build Slack Block Kit blocks for the digest.
        
        Args:
            current_date: Current date
            comparison: Cost comparison data
            anomalies: List of anomalies
            mtd_progress: Month-to-date progress
            top_movers_count: Number of top movers to show
            
        Returns:
            List of Slack Block Kit blocks
        """
        blocks = []
        
        # Header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📊 Daily Cost Digest — {current_date.strftime('%b %d, %Y')}"
            }
        })
        
        # Total spend summary
        change_emoji = "📈" if comparison.total_change > 0 else "📉" if comparison.total_change < 0 else "➡️"
        change_text = f"+{comparison.total_change:.0f}" if comparison.total_change > 0 else f"{comparison.total_change:.0f}"
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Total spend today:* ${comparison.total_current:,.0f}   ({change_emoji} {change_text} vs last week, {comparison.total_percentage_change:+.0f}%)"
            }
        })
        
        # Top movers
        if comparison.top_movers:
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Top movers:*"
                }
            })
            
            for i, mover in enumerate(comparison.top_movers[:top_movers_count]):
                if mover.absolute_change > 0:
                    emoji = "🔴"
                    change_text = f"+${mover.absolute_change:.0f}"
                else:
                    emoji = "🟢" if mover.previous_cost > 0 else "⚪"
                    change_text = f"-${abs(mover.absolute_change):.0f}"
                
                pct_change = f"+{mover.percentage_change:.0f}" if mover.percentage_change > 0 else f"{mover.percentage_change:.0f}"
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{emoji} {mover.service:<12} ${mover.current_cost:>6.0f}   {change_text:>8} ({pct_change:>5}%)"
                    }
                })
        
        # Anomalies
        if anomalies:
            blocks.append({"type": "divider"})
            
            # Critical anomalies first
            critical_anomalies = [a for a in anomalies if a.severity == 'critical']
            high_anomalies = [a for a in anomalies if a.severity == 'high']
            other_anomalies = [a for a in anomalies if a.severity in ['medium', 'low']]
            
            for anomaly_list, emoji in [(critical_anomalies, "🚨"), (high_anomalies, "⚠️")]:
                if anomaly_list:
                    for anomaly in anomaly_list[:2]:  # Limit to prevent too long messages
                        blocks.append({
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"{emoji} *{anomaly.severity.title()} anomaly:* {anomaly.description}"
                            }
                        })
            
            if len(other_anomalies) > 0:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"ℹ️ {len(other_anomalies)} other {'anomaly' if len(other_anomalies) == 1 else 'anomalies'} detected"
                    }
                })
        
        # Month-to-date progress
        if mtd_progress:
            blocks.append({"type": "divider"})
            
            mtd_text = f"📅 *Month-to-date:* ${mtd_progress['mtd_total']:,.0f}"
            
            if 'projected_total' in mtd_progress:
                projected_vs_budget = mtd_progress['projected_vs_budget']
                if projected_vs_budget > 0:
                    mtd_text += f" (⚠️ on track — projected ${mtd_progress['projected_total']:,.0f} vs ${mtd_progress['budget']:,.0f} budget)"
                else:
                    mtd_text += f" (✅ on track — projected ${mtd_progress['projected_total']:,.0f} vs ${mtd_progress['budget']:,.0f} budget)"
            else:
                mtd_text += " (📊 tracking)"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": mtd_text
                }
            })
        
        return blocks
    
    def post_anomaly_alert(self, anomalies: List[Anomaly], current_date: date) -> bool:
        """Post a focused anomaly alert.
        
        Args:
            anomalies: List of anomalies to alert about
            current_date: Current date
            
        Returns:
            True if posted successfully, False otherwise
        """
        if not anomalies:
            return True
        
        try:
            blocks = self._build_anomaly_blocks(anomalies, current_date)
            
            response = self.client.chat_postMessage(
                channel=self.channel,
                blocks=blocks,
                text=f"🚨 Cost Anomaly Alert — {current_date.strftime('%b %d, %Y')}"
            )
            
            return response['ok']
            
        except SlackApiError as e:
            print(f"Error posting anomaly alert to Slack: {e}")
            return False
    
    def _build_anomaly_blocks(self, anomalies: List[Anomaly], current_date: date) -> List[Dict]:
        """Build blocks for anomaly alert.
        
        Args:
            anomalies: List of anomalies
            current_date: Current date
            
        Returns:
            List of Slack Block Kit blocks
        """
        blocks = []
        
        # Header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🚨 Cost Anomaly Alert — {current_date.strftime('%b %d, %Y')}"
            }
        })
        
        # Group by severity
        critical = [a for a in anomalies if a.severity == 'critical']
        high = [a for a in anomalies if a.severity == 'high']
        medium = [a for a in anomalies if a.severity == 'medium']
        
        for severity_list, emoji, title in [(critical, "🚨", "Critical"), (high, "⚠️", "High"), (medium, "ℹ️", "Medium")]:
            if severity_list:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{emoji} {title} Severity:*"
                    }
                })
                
                for anomaly in severity_list[:3]:  # Limit to prevent spam
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"• {anomaly.description}"
                        }
                    })
                
                if len(severity_list) > 3:
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"• ... and {len(severity_list) - 3} more {title.lower()} anomalies"
                        }
                    })
        
        return blocks
    
    def test_connection(self) -> bool:
        """Test Slack connection.
        
        Returns:
            True if connection is successful, False otherwise
        """
        try:
            response = self.client.auth_test()
            return response['ok']
        except SlackApiError as e:
            print(f"Slack connection test failed: {e}")
            return False
