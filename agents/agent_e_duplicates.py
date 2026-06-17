import json
from pathlib import Path

from schemas.models import ContextPacket, Finding, FindingsOutput, NormalizationOutput
from services.duplicate_service import DuplicateService
from services.policy_service import PolicyService


class DuplicateDetectionAgent:
    def __init__(
        self,
        duplicate_service: DuplicateService,
        policy_service: PolicyService,
    ):
        self.duplicate_service = duplicate_service
        self.policy = policy_service
        self.findings: list[Finding] = []
        self.counter = 1

    def _next_id(self) -> str:
        finding_id = f"E-{self.counter:03d}"
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
                agent="E",
                expense_id=expense_id,
                rule_id=rule_id,
                severity=severity,
                message=message,
                evidence=evidence,
                suggested_action=suggested_action,
            )
        )

    def check_exact_duplicates(
        self,
        normalized_expenses,
        context_packet: ContextPacket,
    ) -> None:
        file_hashes = {
            file.file_id: file.sha256
            for file in context_packet.files
        }

        seen_hashes = {}

        for normalized in normalized_expenses:
            expense = normalized.expense
            file_id = expense.source_file_id
            file_hash = file_hashes.get(file_id)

            if not file_hash:
                continue

            if file_hash in seen_hashes:
                original_expense_id, original_file_id = seen_hashes[file_hash]
                rule = self.policy.get_duplicate_settings()["exact_duplicate"]

                self._add_finding(
                    expense_id=expense.expense_id,
                    rule_id="EXACT_DUPLICATE",
                    severity=rule["severity"],
                    message=(
                        f"Expense {expense.expense_id} has the same file hash "
                        f"as {original_expense_id}."
                    ),
                    evidence=[
                        original_file_id,
                        file_id,
                        file_hash,
                    ],
                    suggested_action=rule["suggested_action"],
                )
            else:
                seen_hashes[file_hash] = (
                    expense.expense_id,
                    file_id,
                )

    def check_pairwise_duplicates(self, normalized_expenses) -> None:
        for i in range(len(normalized_expenses)):
            for j in range(i + 1, len(normalized_expenses)):
                first = normalized_expenses[i]
                second = normalized_expenses[j]

                first_expense = first.expense
                second_expense = second.expense

                if self.duplicate_service.is_strong_duplicate(
                    first_expense,
                    second_expense,
                ):
                    rule = self.policy.get_duplicate_settings()["strong_duplicate"]

                    self._add_finding(
                        expense_id=second_expense.expense_id,
                        rule_id="STRONG_DUPLICATE",
                        severity=rule["severity"],
                        message=(
                            f"Expense {second_expense.expense_id} matches "
                            f"{first_expense.expense_id} by vendor, date, "
                            f"amount and currency."
                        ),
                        evidence=[
                            first_expense.source_file_id,
                            second_expense.source_file_id,
                            first_expense.expense_id,
                            second_expense.expense_id,
                        ],
                        suggested_action=rule["suggested_action"],
                    )
                    continue

                if self.duplicate_service.is_fuzzy_duplicate(first, second):
                    rule = self.policy.get_duplicate_settings()["fuzzy_duplicate"]

                    self._add_finding(
                        expense_id=second_expense.expense_id,
                        rule_id="FUZZY_DUPLICATE",
                        severity=rule["severity"],
                        message=(
                            f"Expense {second_expense.expense_id} is similar "
                            f"to {first_expense.expense_id} by vendor, amount "
                            f"and date."
                        ),
                        evidence=[
                            first_expense.source_file_id,
                            second_expense.source_file_id,
                            first_expense.expense_id,
                            second_expense.expense_id,
                        ],
                        suggested_action=rule["suggested_action"],
                    )

    def detect(
        self,
        normalization_output: NormalizationOutput,
        context_packet: ContextPacket,
    ) -> FindingsOutput:
        normalized_expenses = normalization_output.normalized

        self.check_exact_duplicates(normalized_expenses, context_packet)
        self.check_pairwise_duplicates(normalized_expenses)

        return FindingsOutput(
            agent="E",
            bundle_id=normalization_output.bundle_id,
            findings=self.findings,
        )


def run(
    bundle_path: str,
    run_dir: str,
    policy_path: str = "policy/expense_policy.yaml",
) -> int:
    run_path = Path(run_dir)

    normalization_file = run_path / "normalization_results.json"
    context_file = run_path / "context_packet.json"
    output_file = run_path / "duplicates.json"

    if not normalization_file.exists():
        raise FileNotFoundError(
            f"Missing normalization results: {normalization_file}"
        )

    if not context_file.exists():
        raise FileNotFoundError(
            f"Missing context packet: {context_file}"
        )

    with open(normalization_file, "r", encoding="utf-8") as file:
        normalization_data = json.load(file)

    with open(context_file, "r", encoding="utf-8") as file:
        context_data = json.load(file)

    normalization_output = NormalizationOutput.model_validate(
        normalization_data
    )
    context_packet = ContextPacket.model_validate(context_data)

    policy_service = PolicyService(policy_path)
    duplicate_service = DuplicateService(
        policy_service.get_duplicate_settings()
    )

    agent = DuplicateDetectionAgent(
        duplicate_service=duplicate_service,
        policy_service=policy_service,
    )

    result = agent.detect(
        normalization_output=normalization_output,
        context_packet=context_packet,
    )

    with open(output_file, "w", encoding="utf-8") as file:
        file.write(result.model_dump_json(indent=2))

    return 0