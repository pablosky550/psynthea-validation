"""Cross-run campaign analysis for the Psynthea validation framework."""

from validation.campaigns.models import CampaignResult, MetricSummary, RunMetric, RunRecord
from validation.campaigns.module_aggregation import (
    ModuleCampaignAggregationError,
    ModuleCampaignResult,
    ModuleResult,
    aggregate_module_campaign,
    discover_campaign_reports,
    persist_module_campaign,
)

__all__ = [
    "CampaignResult",
    "MetricSummary",
    "ModuleCampaignAggregationError",
    "ModuleCampaignResult",
    "ModuleResult",
    "RunMetric",
    "RunRecord",
    "aggregate_module_campaign",
    "discover_campaign_reports",
    "persist_module_campaign",
]
