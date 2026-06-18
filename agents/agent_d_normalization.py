import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from schemas.models import ExtractedExpense, ExtractionOutput, Finding, NormalizationOutput, NormalizedExpense
from services.currency_service import to_base
from utils.constants import AGENT_D, FILENAME_EXTRACTED_EXPENSES, FILENAME_NORMALIZATION_RESULT, FILENAME_CARD_EXPORT



from utils.json_utils import model_to_dict, read_json, write_json

#These formats are tried in order
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%m/%d/%Y", "%Y/%m/%d")

_DEFAULT_RULE = {
    "unknown_currency": {"severity": "BLOCK", "suggested_action": "REJECT"},
    "invalid_date": {"severity": "HIGH", "suggested_action": "MANUAL_REVIEW"},
    "total_mismatch": {"severity": "WARN", "suggested_action": "MANUAL_REVIEW"}
}

#Helping funcs

def _normalize_date(raw: str) -> str | None:
    for format in _DATE_FORMATS:
        try:
            return datetime.strptime(raw.strip(), format).date().isoformat()
        except (ValueError, AttributeError):
            continue
    return None

def _reconcile_total(expense: ExtractedExpense) -> Decimal | None:
    #Returning none means there was no problems with the total
    if not expense.line_items:
        return None
    line_sum = sum((line.line_total for line in expense.line_items), Decimal("0.00"))
    return line_sum if line_sum != expense.total_amount else None

def _rates(policy: dict) -> dict:
    return policy.get("currency", {}).get("exchange_rates", {})

def _vat_countries(policy: dict) -> list[str]:
    vat = policy.get("vat", {})
    return vat.get("eligible_countries", []) if vat.get("enabled", False) else []

def _policy_rule(policy: dict, name: str) -> dict:
    return policy.get("policy_rules", {}).get(name, _DEFAULT_RULE[name])

def _load_card_rows(bundle_path: Path) -> list[dict]:
    path = bundle_path / FILENAME_CARD_EXPORT
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
    
def normalize(extraction: ExtractionOutput, policy: dict, bundle_path: Path) -> NormalizationOutput:
    rates = _rates(policy)
    vat_countries = _vat_countries(policy)

    findings: list[Finding] = []
    counter = 0

    def add(expense_id, rule_id, rule, message, evidence):
        nonlocal counter # modifies the counter outside this scope
        counter += 1
        findings.append(Finding(
            finding_id=f"D-{counter:03d}",
            agent=AGENT_D,
            expense_id=expense_id,
            rule_id=rule_id,
            severity=rule["severity"],
            message=message,
            evidence=evidence,
            suggested_action=rule["suggested_action"],
        ))
        
    normalized: list[NormalizedExpense] = []

    for expense in extraction.expenses:

        #Change currency format
        try:
            amount_base = to_base(expense.total_amount, expense.currency, rates)
        except (KeyError, InvalidOperation):
            amount_base = Decimal("0.00")
            add(expense.expense_id, "UNKNOWN_CURRENCY", _policy_rule(policy, "unknown_currency"),
                f"No exchange rate configured for currency '{expense.currency}'.",
                [expense.source_file_id, "currency"])
            
        # Normalize date format
        date_iso = _normalize_date(expense.expense_date)
        if date_iso is None:
            add(expense.expense_id, "INVALID_DATE", _policy_rule(policy, "invalid_date"),
                f"Could not parse expense date '{expense.expense_date}'.",
                [expense.source_file_id, "expense_date"])
            date_iso = expense.expense_date

        # Totals reconciliation
        line_sum = _reconcile_total(expense)
        if line_sum is not None:
            add(expense.expense_id, "TOTAL_MISMATCH", _policy_rule(policy, "total_mismatch"),
                f"Line items sum to {line_sum} but the printed total is {expense.total_amount}.",
                [expense.source_file_id, "total_amount", "line_items"])
            
        # VAT Eligibility
        vat_eligible = expense.country in vat_countries
        if vat_eligible:
            rule = policy.get("vat", {}).get("vat_reclaim", {"severity": "INFO", "suggested_action": "NONE"})
            add(expense.expense_id, "VAT_RECLAIM_ELIGIBLE", rule,
                f"Expense in {expense.country} is eligible for VAT reclaim.",
                [expense.source_file_id, "country"])
            
        normalized.append(NormalizedExpense(
            expense=expense,
            amount_base=amount_base,
            date_iso=date_iso,
            vat_eligible=vat_eligible,
        ))

    # check card charges with no receipt
    _check_missing_receipts(_load_card_rows(bundle_path), normalized, policy, add)
    
    return NormalizationOutput(
        bundle_id=extraction.bundle_id,
        normalized=normalized,
        findings=findings,
    )

def _check_missing_receipts(card_rows, normalized, policy, add) -> None:
    #If a card charge exists with no corresponding receipt is a MISSING_RECEIPT finding
    if not card_rows:
        return
    
    receipts = policy.get("receipts", {})
    threshold = Decimal(str(receipts.get("required_above", "50.00")))
    rule = receipts.get("missing_receipt", {"severity": "HIGH", "suggested_action": "MANUAL_REVIEW"})
    rates = _rates(policy)

    covered = {(n.date_iso, n.amount_base) for n in normalized}

    for row in card_rows:
        currency = (row.get("currency") or "").strip()
        try:
            amount_base = to_base(row.get("amount", "0"), currency, rates)
        except (KeyError, InvalidOperation):
            continue #If currency unknown, skip

        date_iso = _normalize_date(row.get("date", "")) or (row.get("date") or "").strip()
        if (date_iso, amount_base) in covered:
            continue
        if amount_base > threshold:
            vendor = (row.get("vendor") or "?").strip()
            add("NONE", "MISSING_RECEIPT", rule,
                f"Card charge '{vendor}' for {amount_base} has no matching receipt.",
                [FILENAME_CARD_EXPORT, vendor, str(amount_base)])
            

def run(bundle_path, run_dir, policy=None) -> int:
    policy = policy or {}
    run_dir = Path(run_dir)

    extraction = ExtractionOutput(**read_json(run_dir / FILENAME_EXTRACTED_EXPENSES))
    output = normalize(extraction, policy, Path(bundle_path))
    write_json(model_to_dict(output), run_dir / FILENAME_NORMALIZATION_RESULT)
    return 0