import json
from datetime import datetime
from pathlib import Path

from schemas.models import Finding, FindingsOutput, NormalizationOutput
from services.policy_service import PolicyService


class PolicyValidationAgent:
    def __init__(self, policy_service: PolicyService):
        self.policy = policy_service
        self.findings: list[Finding] = []
        self.counter = 1

    def _next_id(self) -> str:
        finding_id = f"C-{self.counter:03d}"
        self.counter += 1
        return finding_id

    def _add_finding(
        self,
        expense_id: str,
        rule_id: str,
        severity: str,
        message: str,
        evidence: list[str],
        suggested_action: str,
    ) -> None:
        self.findings.append(
            Finding(
                finding_id=self._next_id(),
                agent="C",
                expense_id=expense_id,
                rule_id=rule_id,
                severity=severity,
                message=message,
                evidence=evidence,
                suggested_action=suggested_action,
            )
        )

    def check_category(self, normalized_expense) -> None:
        expense = normalized_expense.expense

        if self.policy.is_blocked_category(expense.category):
            rule = self.policy.get_rule("blocked_category")
            self._add_finding(
                expense_id=expense.expense_id,
                rule_id="BLOCKED_CATEGORY",
                severity=rule["severity"],
                message=f"Category '{expense.category}' is blocked by policy.",
                evidence=[expense.source_file_id, "category"],
                suggested_action=rule["suggested_action"],
            )
            return

        if not self.policy.is_allowed_category(expense.category) and not self.policy.is_restricted_category(expense.category):
            rule = self.policy.get_rule("blocked_category")
            self._add_finding(
                expense_id=expense.expense_id,
                rule_id="UNSUPPORTED_CATEGORY",
                severity=rule["severity"],
                message=f"Category '{expense.category}' is not supported by policy.",
                evidence=[expense.source_file_id, "category"],
                suggested_action=rule["suggested_action"],
            )

    def check_per_diem(self, normalized_expense) -> None:
        expense = normalized_expense.expense

        limit = self.policy.get_per_diem_limit(expense.country, expense.category)

        if limit is None:
            return

        if normalized_expense.amount_base > limit:
            rule = self.policy.get_rule("per_diem_exceeded")
            self._add_finding(
                expense_id=expense.expense_id,
                rule_id=f"PER_DIEM_{expense.category.upper()}",
                severity=rule["severity"],
                message=(
                    f"{expense.category} expense exceeds per diem limit. "
                    f"Amount: {normalized_expense.amount_base}, Limit: {limit}, Country: {expense.country}."
                ),
                evidence=[expense.source_file_id, "amount_base", "category", "country"],
                suggested_action=rule["suggested_action"],
            )

    def check_alcohol(self, normalized_expense) -> None:
        expense = normalized_expense.expense

        if expense.category != "alcohol":
            return

        rule = self.policy.get_rule("alcohol_expense")
        self._add_finding(
            expense_id=expense.expense_id,
            rule_id="ALCOHOL_EXPENSE",
            severity=rule["severity"],
            message="Alcohol expense requires manager approval.",
            evidence=[expense.source_file_id, "category"],
            suggested_action=rule["suggested_action"],
        )

    def check_low_confidence(self, normalized_expense) -> None:
        expense = normalized_expense.expense
        threshold = self.policy.get_confidence_threshold()

        if expense.overall_confidence < threshold or expense.needs_manual_review:
            rule = self.policy.get_rule("low_confidence_extraction")
            self._add_finding(
                expense_id=expense.expense_id,
                rule_id="LOW_CONFIDENCE_EXTRACTION",
                severity=rule["severity"],
                message=(
                    f"Extraction confidence is below threshold. "
                    f"Confidence: {expense.overall_confidence}, Threshold: {threshold}."
                ),
                evidence=[expense.source_file_id, "overall_confidence"],
                suggested_action=rule["suggested_action"],
            )

    def check_weekend_meal(self, normalized_expense) -> None:
        expense = normalized_expense.expense

        if not self.policy.meals_require_weekend_approval():
            return

        if expense.category != "meals":
            return

        expense_date = datetime.strptime(normalized_expense.date_iso, "%Y-%m-%d")

        if expense_date.weekday() >= 5:
            rule = self.policy.get_weekend_meal_rule()
            self._add_finding(
                expense_id=expense.expense_id,
                rule_id="WEEKEND_MEAL",
                severity=rule["severity"],
                message="Meal expense submitted for a weekend date requires manager approval.",
                evidence=[expense.source_file_id, "date_iso", "category"],
                suggested_action=rule["suggested_action"],
            )

    def check_fast_track(self, normalized_expense) -> None:
        if not self.policy.is_fast_track_enabled():
            return

        expense = normalized_expense.expense
        limit = self.policy.get_fast_track_limit()

        if normalized_expense.amount_base < limit:
            rule = self.policy.get_fast_track_rule()
            self._add_finding(
                expense_id=expense.expense_id,
                rule_id="FAST_TRACK",
                severity=rule["severity"],
                message=f"Expense is below fast-track threshold of {limit}.",
                evidence=[expense.source_file_id, "amount_base"],
                suggested_action=rule["suggested_action"],
            )

    def validate(self, normalization_output: NormalizationOutput) -> FindingsOutput:
        for normalized_expense in normalization_output.normalized:
            self.check_category(normalized_expense)
            self.check_per_diem(normalized_expense)
            self.check_alcohol(normalized_expense)
            self.check_low_confidence(normalized_expense)
            self.check_weekend_meal(normalized_expense)
            self.check_fast_track(normalized_expense)

        return FindingsOutput(
            agent="C",
            bundle_id=normalization_output.bundle_id,
            findings=self.findings,
        )


def run(bundle_path: str, run_dir: str, policy_path: str = "policy/expense_policy.yaml") -> int:
    run_path = Path(run_dir)

    input_file = run_path / "normalization_results.json"
    output_file = run_path / "policy_results.json"

    if not input_file.exists():
        raise FileNotFoundError(f"Missing normalization results: {input_file}")

    with open(input_file, "r", encoding="utf-8") as file:
        data = json.load(file)

    normalization_output = NormalizationOutput.model_validate(data)

    policy_service = PolicyService(policy_path)
    agent = PolicyValidationAgent(policy_service)

    result = agent.validate(normalization_output)

    with open(output_file, "w", encoding="utf-8") as file:
        file.write(result.model_dump_json(indent=2))

    return 0