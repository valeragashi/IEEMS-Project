from decimal import Decimal
from pathlib import Path
import yaml


class PolicyService:
    """
    Loads and exposes the expense policy configuration used by
    Agents C, D, E and H.
    """

    def __init__(self, policy_path: str = "policy/expense_policy.yaml"):
        self.policy_path = Path(policy_path)
        self.policy = self._load_policy()

    def _load_policy(self) -> dict:
        if not self.policy_path.exists():
            raise FileNotFoundError(
                f"Policy file not found: {self.policy_path}"
            )

        with open(self.policy_path, "r", encoding="utf-8") as file:
            return yaml.safe_load(file)

    # ---------------------------------------------------------
    # General
    # ---------------------------------------------------------

    def get_policy_name(self) -> str:
        return self.policy["policy_name"]

    def get_version(self) -> str:
        return self.policy["version"]

    # ---------------------------------------------------------
    # Currency
    # ---------------------------------------------------------

    def get_base_currency(self) -> str:
        return self.policy["currency"]["base_currency"]

    def get_exchange_rate(self, currency: str) -> Decimal:
        rates = self.policy["currency"]["exchange_rates"]

        if currency not in rates:
            raise ValueError(f"Unsupported currency: {currency}")

        return Decimal(rates[currency])

    # ---------------------------------------------------------
    # Per Diem
    # ---------------------------------------------------------

    def get_per_diem_limit(
        self,
        country: str,
        category: str,
    ) -> Decimal | None:

        per_diem = self.policy["per_diem"]

        country_rules = per_diem.get(
            country,
            per_diem["DEFAULT"]
        )

        if category not in country_rules:
            return None

        return Decimal(country_rules[category])

    # ---------------------------------------------------------
    # Categories
    # ---------------------------------------------------------

    def is_allowed_category(self, category: str) -> bool:
        return category in self.policy["categories"]["allowed"]

    def is_restricted_category(self, category: str) -> bool:
        return category in self.policy["categories"].get(
            "restricted",
            []
        )

    def is_blocked_category(self, category: str) -> bool:
        return category in self.policy["categories"].get(
            "blocked",
            []
        )

    # ---------------------------------------------------------
    # Receipts
    # ---------------------------------------------------------

    def receipt_required_above(self) -> Decimal:
        return Decimal(
            self.policy["receipts"]["required_above"]
        )

    def get_missing_receipt_rule(self) -> dict:
        return self.policy["receipts"]["missing_receipt"]

    # ---------------------------------------------------------
    # Approval
    # ---------------------------------------------------------

    def get_approval_threshold(self, key: str) -> Decimal:
        return Decimal(self.policy["approval"][key])

    def get_approver(self, key: str) -> str:
        return self.policy["approval"]["approvers"][key]

    # ---------------------------------------------------------
    # Confidence
    # ---------------------------------------------------------

    def get_confidence_threshold(self) -> float:
        return float(
            self.policy["confidence"]["manual_review_below"]
        )

    # ---------------------------------------------------------
    # Policy Rules
    # ---------------------------------------------------------

    def get_rule(self, rule_name: str) -> dict:
        return self.policy["policy_rules"][rule_name]

    # ---------------------------------------------------------
    # Weekend
    # ---------------------------------------------------------

    def meals_require_weekend_approval(self) -> bool:
        return bool(
            self.policy["weekend"]["meals_require_approval"]
        )

    def get_weekend_meal_rule(self) -> dict:
        return self.policy["weekend"]["weekend_meal"]

    # ---------------------------------------------------------
    # VAT
    # ---------------------------------------------------------

    def get_vat_countries(self) -> list[str]:
        return self.policy["vat"]["eligible_countries"]

    def is_vat_eligible_country(
        self,
        country: str,
    ) -> bool:

        return country in self.get_vat_countries()

    # ---------------------------------------------------------
    # Duplicate Detection
    # ---------------------------------------------------------

    def get_duplicate_settings(self) -> dict:
        return self.policy["duplicate_detection"]

    # ---------------------------------------------------------
    # Fast Track
    # ---------------------------------------------------------

    def is_fast_track_enabled(self) -> bool:
        return bool(
            self.policy["fast_track"]["enabled"]
        )

    def get_fast_track_limit(self) -> Decimal:
        return Decimal(
            self.policy["fast_track"]["below"]
        )

    def get_fast_track_rule(self) -> dict:
        return self.policy["fast_track"]["fast_track_finding"]

    # ---------------------------------------------------------
    # Decision Rules
    # ---------------------------------------------------------

    def get_decision_rules(self) -> dict:
        return self.policy["decision_rules"]

    # ---------------------------------------------------------
    # Output
    # ---------------------------------------------------------

    def get_output_settings(self) -> dict:
        return self.policy["output"]