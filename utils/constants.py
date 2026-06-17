"""
utils/constants.py
==================
Global string constants and allowed values for the IEEMS pipeline.
All agents import from here — never hard-code these strings elsewhere.
"""

# ---------------------------------------------------------------------------
# Pipeline agent identifiers
# ---------------------------------------------------------------------------
AGENT_A = "A"   # Intake / context
AGENT_B = "B"   # Extraction
AGENT_C = "C"   # Policy
AGENT_D = "D"   # Normalization
AGENT_E = "E"   # Duplicates
AGENT_H = "H"   # Decision

# ---------------------------------------------------------------------------
# Finding severity levels (ordered lowest → highest)
# ---------------------------------------------------------------------------
SEVERITY_INFO  = "INFO"
SEVERITY_WARN  = "WARN"
SEVERITY_HIGH  = "HIGH"
SEVERITY_BLOCK = "BLOCK"

ALLOWED_SEVERITIES: frozenset[str] = frozenset({
    SEVERITY_INFO,
    SEVERITY_WARN,
    SEVERITY_HIGH,
    SEVERITY_BLOCK,
})

SEVERITY_RANK: dict[str, int] = {
    SEVERITY_INFO:  0,
    SEVERITY_WARN:  1,
    SEVERITY_HIGH:  2,
    SEVERITY_BLOCK: 3,
}

# ---------------------------------------------------------------------------
# Final decision values
# ---------------------------------------------------------------------------
DECISION_AUTO_APPROVE     = "AUTO_APPROVE"
DECISION_MANAGER_APPROVAL = "MANAGER_APPROVAL"
DECISION_MANUAL_REVIEW    = "MANUAL_REVIEW"
DECISION_BLOCK            = "BLOCK"

ALLOWED_DECISIONS: frozenset[str] = frozenset({
    DECISION_AUTO_APPROVE,
    DECISION_MANAGER_APPROVAL,
    DECISION_MANUAL_REVIEW,
    DECISION_BLOCK,
})

# ---------------------------------------------------------------------------
# Expense categories
# ---------------------------------------------------------------------------
CATEGORY_LODGING   = "lodging"
CATEGORY_MEALS     = "meals"
CATEGORY_TRANSPORT = "transport"
CATEGORY_AIRFARE   = "airfare"
CATEGORY_ALCOHOL   = "alcohol"
CATEGORY_OFFICE    = "office"
CATEGORY_OTHER     = "other"

ALLOWED_CATEGORIES: frozenset[str] = frozenset({
    CATEGORY_LODGING,
    CATEGORY_MEALS,
    CATEGORY_TRANSPORT,
    CATEGORY_AIRFARE,
    CATEGORY_ALCOHOL,
    CATEGORY_OFFICE,
    CATEGORY_OTHER,
})

# ---------------------------------------------------------------------------
# Payment methods
# ---------------------------------------------------------------------------
PAYMENT_CORPORATE_CARD = "corporate_card"
PAYMENT_PERSONAL       = "personal"
PAYMENT_CASH           = "cash"
PAYMENT_UNKNOWN        = "unknown"

ALLOWED_PAYMENT_METHODS: frozenset[str] = frozenset({
    PAYMENT_CORPORATE_CARD,
    PAYMENT_PERSONAL,
    PAYMENT_CASH,
    PAYMENT_UNKNOWN,
})

# ---------------------------------------------------------------------------
# Approver routing values
# ---------------------------------------------------------------------------
APPROVER_SYSTEM         = "SYSTEM"
APPROVER_LINE_MANAGER   = "LINE_MANAGER"
APPROVER_FINANCE_REVIEW = "FINANCE_REVIEW"

ALLOWED_APPROVERS: frozenset[str] = frozenset({
    APPROVER_SYSTEM,
    APPROVER_LINE_MANAGER,
    APPROVER_FINANCE_REVIEW,
})

# ---------------------------------------------------------------------------
# File types recognised by Agent A
# ---------------------------------------------------------------------------
FILE_TYPE_RECEIPT_PDF  = "receipt_pdf"
FILE_TYPE_CARD_EXPORT  = "card_export"
FILE_TYPE_POLICY       = "policy"

# ---------------------------------------------------------------------------
# Pipeline output filenames (agents write; downstream agents read)
# ---------------------------------------------------------------------------
FILENAME_CONTEXT_PACKET       = "context_packet.json"
FILENAME_EXTRACTED_EXPENSES   = "extracted_expenses.json"
FILENAME_NORMALIZATION_RESULT = "normalization_results.json"
FILENAME_POLICY_FINDINGS      = "policy_findings.json"
FILENAME_DUPLICATE_FINDINGS   = "duplicate_findings.json"
FILENAME_FINAL_DECISION       = "final_decision.json"
FILENAME_AUDIT_LOG            = "audit.log"

# ---------------------------------------------------------------------------
# Runs root directory (relative to project root)
# ---------------------------------------------------------------------------
RUNS_ROOT = "runs"