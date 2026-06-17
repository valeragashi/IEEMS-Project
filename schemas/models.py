"""Shared data models for the IEEMS pipeline.

Trimmed to the fields the project brief (slides) actually calls for. Frozen
after team sign-off — adding an optional field is fine, renaming/removing one
needs agreement.

Conventions:
- Money is Decimal (build from strings: Decimal("12.50")) so totals never drift.
- Dates are ISO strings "YYYY-MM-DD".
- IDs are assigned in sorted order so re-runs are reproducible.

Pipeline order (follows the data, not the alphabet):
    A -> B -> D -> C -> E -> H
  A intake | B extract | D normalize | C policy | E duplicates | H decide
Agent D wraps each extracted expense with clean currency/date values, and Agents C
and E read the NORMALIZED expenses, not the raw ones.

Reference string values (validated by the agents, kept as plain str):
- severity:       INFO | WARN | HIGH | BLOCK
- decision:       AUTO_APPROVE | MANAGER_APPROVAL | MANUAL_REVIEW | BLOCK
- category:       lodging | meals | transport | airfare | alcohol | office | other
- payment_method: corporate_card | personal | cash | unknown
"""

from decimal import Decimal
from pydantic import BaseModel


# --- Agent A: context_packet.json ---

class FileEntry(BaseModel):
    file_id: str             # F001, F002... assigned in sorted order
    filename: str            # path inside the bundle (the evidence link)
    file_type: str           # receipt_pdf | card_export | policy | ...
    sha256: str              # Used for exact duplicate   

class ContextPacket(BaseModel):
    bundle_id: str
    employee_id: str         # employee metadata -> approval routing + posting
    trip_purpose: str
    submission_date: str
    employee_name: str
    cost_center: str         # needed by the ERP posting payload
    files: list[FileEntry]   # classified documents + evidence index


# --- Agent B: extracted_expenses.json ---

class LineItem(BaseModel):
    description: str
    quantity: Decimal = Decimal("1")
    unit_price: Decimal
    line_total: Decimal


class ExtractedExpense(BaseModel):
    expense_id: str
    source_file_id: str          # links back to the receipt (evidence)
    vendor: str                  # duplicate detection
    expense_date: str            # duplicate detection + weekend rule
    currency: str                # Agent D converts from this
    total_amount: Decimal
    category: str                # per-diem limit + alcohol rule
    payment_method: str          # duplicate detection
    country: str                 # per-diem table + alcohol-by-country rule
    line_items: list[LineItem] = []
    overall_confidence: float    # confidence scoring -> metrics
    needs_manual_review: bool    # low-confidence flag for manual review


class ExtractionOutput(BaseModel):
    bundle_id: str
    expenses: list[ExtractedExpense]
    skipped_files: list[str] = []   # unprocessable files that could not be read


# --- Agents C, D, E: findings (one shared shape) ---

class Finding(BaseModel):
    finding_id: str          # C-001, D-001, E-001 (prefix = source agent)
    agent: str
    expense_id: str          # the expense this is about, or "NONE" for card-only findings
    rule_id: str             # PER_DIEM_MEALS, EXACT_DUPLICATE, ...
    severity: str            # INFO | WARN | HIGH | BLOCK
    message: str
    evidence: list[str]      # file / field pointers (mandatory, non-empty)
    suggested_action: str

class FindingsOutput(BaseModel):
    agent: str
    bundle_id: str
    findings: list[Finding] = []


# --- Agent D: normalization_results.json ---
# D wraps each extracted expense with clean values. C and E read `normalized`.

class NormalizedExpense(BaseModel):
    expense: ExtractedExpense    # the original, unchanged
    amount_base: Decimal          # total converted at the fixed FX rate
    date_iso: str                # standardized "YYYY-MM-DD"
    vat_eligible: bool = False   # VAT reclaim tag


class NormalizationOutput(BaseModel):
    bundle_id: str
    normalized: list[NormalizedExpense]   # the input Agents C and E consume
    findings: list[Finding] = []          # missing receipt, total mismatch


# --- Agent H: final_decision.json ---

class ExpenseDecision(BaseModel):
    expense_id: str
    decision: str                                # the verdict
    approver: str                                # routing for the approval packet | Use standardized values "SYSTEM", "LINE_MANAGER", "FINANCE_REVIEW"
    reasons: list[str] = []                      # finding_ids behind the decision
    reimbursable_amount_base: Decimal = Decimal("0.00")


class FinalDecision(BaseModel):
    bundle_id: str
    decisions: list[ExpenseDecision]
    totals: dict[str, Decimal] = {}
