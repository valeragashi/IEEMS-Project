import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from schemas.models import (
    ContextPacket,
    ExpenseDecision,
    FinalDecision,
    Finding,
    FindingsOutput,
    NormalizationOutput,
)
from services.policy_service import PolicyService
from utils.json_utils import model_to_dict, read_json, write_json


class OrchestratorAgent:
    def __init__(self, policy_service: PolicyService):
        self.policy = policy_service

    def _load_inputs(self, run_dir: Path):
        context = ContextPacket.model_validate(
            read_json(run_dir / "context_packet.json")
        )

        normalization = NormalizationOutput.model_validate(
            read_json(run_dir / "normalization_results.json")
        )

        policy_findings = FindingsOutput.model_validate(
            read_json(run_dir / "policy_results.json")
        )

        duplicate_findings = FindingsOutput.model_validate(
            read_json(run_dir / "duplicates.json")
        )

        all_findings = []
        all_findings.extend(normalization.findings)      # D findings
        all_findings.extend(policy_findings.findings)    # C findings
        all_findings.extend(duplicate_findings.findings) # E findings

        return context, normalization, all_findings

    def _group_findings_by_expense(
        self,
        findings: list[Finding],
    ) -> dict[str, list[Finding]]:
        grouped = defaultdict(list)

        for finding in findings:
            grouped[finding.expense_id].append(finding)

        return grouped

    def _has_severity(
        self,
        findings: list[Finding],
        severity: str,
    ) -> bool:
        return any(f.severity == severity for f in findings)

    def _get_reasons(self, findings: list[Finding]) -> list[str]:
        return [finding.finding_id for finding in findings]

    
    def _get_reimbursable_amount(
        self,
        normalized_expense,
        decision: str,
    ) -> Decimal:
        expense = normalized_expense.expense

        if decision == "BLOCK":
            return Decimal("0.00")

        if expense.payment_method == "corporate_card":
            return Decimal("0.00")

        return normalized_expense.amount_base

    def _decide_expense(
        self,
        normalized_expense,
        findings: list[Finding],
    ) -> ExpenseDecision:
        expense = normalized_expense.expense

    

        if self._has_severity(findings, "BLOCK"):
         decision, approver = "BLOCK", "SYSTEM"

        elif self._has_severity(findings, "HIGH"):
            decision, approver = "MANAGER_APPROVAL", "LINE_MANAGER"

        elif expense.needs_manual_review:
            decision, approver = "MANUAL_REVIEW", "LINE_MANAGER"

        else:
            decision, approver = "AUTO_APPROVE", "SYSTEM"

        reimbursable_amount = self._get_reimbursable_amount(
            normalized_expense,
            decision,
        )

        return ExpenseDecision(
            expense_id=expense.expense_id,
            decision=decision,
            approver=approver,
            reasons=self._get_reasons(findings),
            reimbursable_amount_base=reimbursable_amount,
        )

    def _build_final_decision(
        self,
        normalization: NormalizationOutput,
        findings_by_expense: dict[str, list[Finding]],
    ) -> FinalDecision:
        decisions = []

        for normalized_expense in normalization.normalized:
            expense_id = normalized_expense.expense.expense_id
            expense_findings = findings_by_expense.get(expense_id, [])

            decisions.append(
                self._decide_expense(
                    normalized_expense,
                    expense_findings,
                )
            )

        totals = self._calculate_totals(normalization, decisions)

        return FinalDecision(
            bundle_id=normalization.bundle_id,
            decisions=decisions,
            totals=totals,
        )

    def _calculate_totals(
        self,
        normalization: NormalizationOutput,
        decisions: list[ExpenseDecision],
    ) -> dict[str, Decimal]:
        amount_by_expense = {
            item.expense.expense_id: item.amount_base
            for item in normalization.normalized
        }

        totals = {
            "approved_base": Decimal("0.00"),
            "held_base": Decimal("0.00"),
            "blocked_base": Decimal("0.00"),
            "approved_base": Decimal("0.00"),  # kept for demo.py compatibility
            "blocked_base": Decimal("0.00"),   # kept for demo.py compatibility
        }

        for decision in decisions:
            amount = amount_by_expense.get(
                decision.expense_id,
                Decimal("0.00"),
            )

            if decision.decision == "AUTO_APPROVE":
                totals["approved_base"] += decision.reimbursable_amount_base
                totals["approved_base"] += decision.reimbursable_amount_base

            elif decision.decision == "BLOCK":
                totals["blocked_base"] += amount
                totals["blocked_base"] += amount

            else:
                totals["held_base"] += amount

        return totals

    def _finding_to_dict(self, finding: Finding) -> dict:
        return {
            "finding_id": finding.finding_id,
            "agent": finding.agent,
            "expense_id": finding.expense_id,
            "rule_id": finding.rule_id,
            "severity": finding.severity,
            "message": finding.message,
            "evidence": finding.evidence,
            "suggested_action": finding.suggested_action,
        }

    def _build_approval_packet(
        self,
        context: ContextPacket,
        normalization: NormalizationOutput,
        final_decision: FinalDecision,
        findings_by_expense: dict[str, list[Finding]],
    ) -> dict:
        normalized_by_id = {
            item.expense.expense_id: item
            for item in normalization.normalized
        }

        items = []

        for decision in final_decision.decisions:
            if decision.decision == "AUTO_APPROVE":
                continue

            normalized = normalized_by_id[decision.expense_id]
            expense = normalized.expense
            findings = findings_by_expense.get(decision.expense_id, [])

            items.append(
                {
                    "expense_id": expense.expense_id,
                    "vendor": expense.vendor,
                    "category": expense.category,
                    "amount_base": str(normalized.amount_base),
                    "currency": self.policy.get_base_currency(),
                    "decision": decision.decision,
                    "approver": decision.approver,
                    "reasons": [
                        self._finding_to_dict(finding)
                        for finding in findings
                    ],
                }
            )

        return {
            "bundle_id": context.bundle_id,
            "employee_id": context.employee_id,
            "employee_name": context.employee_name,
            "cost_center": context.cost_center,
            "items_requiring_approval": items,
        }

    def _build_posting_payload(
        self,
        context: ContextPacket,
        normalization: NormalizationOutput,
        final_decision: FinalDecision,
    ) -> dict:
        normalized_by_id = {
            item.expense.expense_id: item
            for item in normalization.normalized
        }

        postings = []

        for decision in final_decision.decisions:
            if decision.decision != "AUTO_APPROVE":
                continue

            normalized = normalized_by_id[decision.expense_id]
            expense = normalized.expense

            postings.append(
                {
                    "expense_id": expense.expense_id,
                    "employee_id": context.employee_id,
                    "vendor": expense.vendor,
                    "category": expense.category,
                    "gross_amount_base": str(normalized.amount_base),
                    "reimbursable_amount_base": str(
                        decision.reimbursable_amount_base
                    ),
                    "currency": self.policy.get_base_currency(),
                    "cost_center": context.cost_center,
                    "vat_eligible": normalized.vat_eligible,
                }
            )

        return {
            "bundle_id": context.bundle_id,
            "employee_id": context.employee_id,
            "employee_name": context.employee_name,
            "cost_center": context.cost_center,
            "trip_purpose": context.trip_purpose,
            "submission_date": context.submission_date,
            "currency": self.policy.get_base_currency(),
            "postings": postings,
        }
            

    def _build_metrics(
        self,
        normalization: NormalizationOutput,
        final_decision: FinalDecision,
        all_findings: list[Finding],
    ) -> dict:
        total = len(normalization.normalized)

        auto = sum(
            1 for d in final_decision.decisions
            if d.decision == "AUTO_APPROVE"
        )
        manager = sum(
            1 for d in final_decision.decisions
            if d.decision == "MANAGER_APPROVAL"
        )
        manual = sum(
            1 for d in final_decision.decisions
            if d.decision == "MANUAL_REVIEW"
        )
        blocked = sum(
            1 for d in final_decision.decisions
            if d.decision == "BLOCK"
        )

        if total:
            avg_confidence = sum(
                item.expense.overall_confidence
                for item in normalization.normalized
            ) / total
            exception_rate = (total - auto) / total
        else:
            avg_confidence = 0
            exception_rate = 0


        findings_by_severity = {
        "INFO": 0,
        "WARN": 0,
        "HIGH": 0,
         "BLOCK": 0,
}

        for finding in all_findings:
             if finding.severity in findings_by_severity:
                findings_by_severity[finding.severity] += 1

        return {
            "bundle_id": normalization.bundle_id,
            "total_expenses": total,
            "auto_approved_count": auto,
            "manager_approval_count": manager,
            "manual_review_count": manual,
            "blocked_count": blocked,
            "finding_count": len(all_findings),
            "avg_overall_confidence": round(avg_confidence, 4),
            "exception_rate": round(exception_rate, 4),
            "findings_by_severity": findings_by_severity,
            "totals": {
                key: str(value)
                for key, value in final_decision.totals.items()
            },
        }

    def _build_audit_log(
        self,
        context: ContextPacket,
        normalization: NormalizationOutput,
        final_decision: FinalDecision,
        findings_by_expense: dict[str, list[Finding]],
    ) -> str:
        normalized_by_id = {
            item.expense.expense_id: item
            for item in normalization.normalized
        }

        lines = [
            "# IEEMS Audit Log",
            "",
            f"Bundle: {context.bundle_id}",
            f"Employee: {context.employee_name} ({context.employee_id})",
            f"Cost Center: {context.cost_center}",
            f"Trip Purpose: {context.trip_purpose}",
            f"Submission Date: {context.submission_date}",
            "",
        ]

        for decision in final_decision.decisions:
            normalized = normalized_by_id[decision.expense_id]
            expense = normalized.expense
            findings = findings_by_expense.get(expense.expense_id, [])

            lines.extend(
                [
                    f"## Expense {expense.expense_id}",
                    f"Vendor: {expense.vendor}",
                    f"Category: {expense.category}",
                    f"Amount Base: {normalized.amount_base}",
                    f"Currency: {self.policy.get_base_currency()}",
                    f"Decision: {decision.decision}",
                    f"Approver: {decision.approver}",
                    "",
                    "Findings:",
                ]
            )

            if findings:
                for finding in findings:
                    lines.extend(
                        [
                            (
                                f"- {finding.finding_id} | "
                                f"{finding.rule_id} | "
                                f"{finding.severity} | "
                                f"{finding.message}"
                            ),
                            f"  Evidence: {', '.join(finding.evidence)}",
                            f"  Suggested Action: {finding.suggested_action}",
                        ]
                    )
            else:
                lines.append("- None")

            lines.append("")

            lines.extend(
            [
                "",
                "=" * 40,
                "SUMMARY",
                "=" * 40,
                "",
                f"Auto Approved: {sum(1 for d in final_decision.decisions if d.decision == 'AUTO_APPROVE')}",
                f"Manager Approval: {sum(1 for d in final_decision.decisions if d.decision == 'MANAGER_APPROVAL')}",
                f"Manual Review: {sum(1 for d in final_decision.decisions if d.decision == 'MANUAL_REVIEW')}",
                f"Blocked: {sum(1 for d in final_decision.decisions if d.decision == 'BLOCK')}",
                "",
            ]
)

        return "\n".join(lines)

    def _build_exceptions_md(self, all_findings: list[Finding]) -> str:
        exception_findings = [
            finding
            for finding in all_findings
            if finding.severity in {"WARN", "HIGH", "BLOCK"}
        ]

        lines = [
            "# IEEMS Exceptions",
            "",
            "All WARN, HIGH and BLOCK findings are listed here.",
            "",
        ]

        if not exception_findings:
            lines.append("No exceptions found.")
            return "\n".join(lines)

        for finding in exception_findings:
            lines.extend(
                [
                    f"## {finding.finding_id} — {finding.rule_id}",
                    f"- Agent: {finding.agent}",
                    f"- Expense ID: {finding.expense_id}",
                    f"- Severity: {finding.severity}",
                    f"- Suggested Action: {finding.suggested_action}",
                    f"- Message: {finding.message}",
                    f"- Evidence: {', '.join(finding.evidence)}",
                    "",
                ]
            )

        return "\n".join(lines)

    def orchestrate(self, run_dir: Path) -> None:
        context, normalization, all_findings = self._load_inputs(run_dir)

        findings_by_expense = self._group_findings_by_expense(all_findings)

        final_decision = self._build_final_decision(
            normalization,
            findings_by_expense,
        )

        approval_packet = self._build_approval_packet(
            context,
            normalization,
            final_decision,
            findings_by_expense,
        )

        posting_payload = self._build_posting_payload(
            context,
            normalization,
            final_decision,
        )

        metrics = self._build_metrics(
            normalization,
            final_decision,
            all_findings,
        )

        audit_log = self._build_audit_log(
            context,
            normalization,
            final_decision,
            findings_by_expense,
        )

        exceptions_md = self._build_exceptions_md(all_findings)

        write_json(model_to_dict(final_decision), run_dir / "final_decision.json")
        write_json(approval_packet, run_dir / "approval_packet.json")
        write_json(posting_payload, run_dir / "posting_payload.json")
        write_json(metrics, run_dir / "metrics.json")

        (run_dir / "audit_log.md").write_text(
            audit_log,
            encoding="utf-8",
        )

        (run_dir / "exceptions.md").write_text(
            exceptions_md,
            encoding="utf-8",
        )


def run(bundle_path, run_dir, policy=None) -> int:
    try:
        agent = OrchestratorAgent(PolicyService())
        agent.orchestrate(Path(run_dir))
        return 0
    except Exception as exc:
        print(f"[Agent H ERROR] {exc}")
        return 1