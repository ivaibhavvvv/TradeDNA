"""TradeDNA Phase 6 - Single Authoritative Reconciliation Severity & Tolerance Policy
Defines versioned policies for discrepancy classification, tolerance evaluation,
precision rules, and penalty scoring.
"""

from decimal import Decimal
from typing import Optional


class ReconciliationSeverityPolicy:
    """Single Authoritative Policy for evaluating discrepancy severity boundaries."""

    def __init__(
        self,
        policy_version: str = "1.0.0",
        low_max: Decimal = Decimal("0.0500"),
        medium_max: Decimal = Decimal("5.0000"),
        high_max: Decimal = Decimal("50.0000"),
    ):
        self.policy_version = policy_version
        self.low_max = low_max
        self.medium_max = medium_max
        self.high_max = high_max

    def classify_financial_delta(self, delta: Decimal) -> str:
        """Classifies monetary difference based on strict boundary semantics:
        - 0 delta                   -> INFO
        - 0 < delta <= 0.05         -> LOW
        - 0.05 < delta < 5.00       -> MEDIUM
        - 5.00 <= delta <= 50.00    -> HIGH
        - delta > 50.00             -> CRITICAL
        """
        abs_d = abs(delta)
        if abs_d == Decimal("0.0000"):
            return "INFO"
        elif abs_d <= self.low_max:  # <= 0.05
            return "LOW"
        elif abs_d < self.medium_max:  # < 5.00
            return "MEDIUM"
        elif abs_d <= self.high_max:  # <= 50.00
            return "HIGH"
        else:  # > 50.00
            return "CRITICAL"

    def classify_structural_category(self, category: str) -> str:
        """Classifies non-financial or structural discrepancies."""
        critical_categories = {
            "LEDGER_IMBALANCE",
            "MISSING_CANONICAL_TRADE",
            "GHOST_CANONICAL_TRADE",
            "UNEXPLAINED_BALANCE_DIVERGENCE",
        }
        high_categories = {
            "MISSING_CANONICAL_EXECUTION",
            "ORPHAN_CANONICAL_EXECUTION",
            "POSITION_VOLUME_MISMATCH",
            "DEAL_VOLUME_MISMATCH",
            "UNMATCHED_EXIT_EVENT",
        }
        medium_categories = {
            "POSITION_PRICE_MISMATCH",
            "DEAL_PRICE_MISMATCH",
            "COMMISSION_MISMATCH",
            "SWAP_MISMATCH",
            "NON_TRADING_EVENT_MISMATCH",
            "TIMING_SKEW_EXCEEDED",
        }
        low_categories = {
            "SUB_CENT_ROUNDING_VARIANCE",
            "POSITION_SWAP_MISMATCH",
            "ACCOUNTING_PERIOD_SKEW",
        }

        if category in critical_categories:
            return "CRITICAL"
        elif category in high_categories:
            return "HIGH"
        elif category in medium_categories:
            return "MEDIUM"
        elif category in low_categories:
            return "LOW"
        return "INFO"


class ReconciliationToleranceProfile:
    """Configurable and versioned tolerance profile for multi-currency reconciliation."""

    def __init__(
        self,
        profile_version: str = "1.0.0",
        financial_penny_tolerance: Decimal = Decimal("0.0100"),
        volume_tolerance: Decimal = Decimal("0.0001"),
        fx_price_tolerance: Decimal = Decimal("0.000010"),
        metal_price_tolerance: Decimal = Decimal("0.010000"),
        timing_skew_window_ms: int = 2000,
        floating_pnl_tolerance_pct: Decimal = Decimal("0.005"),
    ):
        self.profile_version = profile_version
        self.financial_penny_tolerance = financial_penny_tolerance
        self.volume_tolerance = volume_tolerance
        self.fx_price_tolerance = fx_price_tolerance
        self.metal_price_tolerance = metal_price_tolerance
        self.timing_skew_window_ms = timing_skew_window_ms
        self.floating_pnl_tolerance_pct = floating_pnl_tolerance_pct

    def is_within_financial_tolerance(self, delta: Decimal) -> bool:
        return abs(delta) <= self.financial_penny_tolerance

    def is_within_volume_tolerance(self, delta: Decimal) -> bool:
        return abs(delta) <= self.volume_tolerance


# Authoritative Default Instances
DEFAULT_SEVERITY_POLICY = ReconciliationSeverityPolicy(policy_version="1.0.0")
DEFAULT_TOLERANCE_PROFILE = ReconciliationToleranceProfile(profile_version="1.0.0")
