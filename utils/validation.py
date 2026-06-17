"""
utils/validation.py
===================
Schema and constraint helpers for the IEEMS pipeline.

These functions are intentionally pure (no I/O, no side-effects) so they
can be called freely inside agents, unit tests, and CI checks alike.

Design principles
-----------------
* Raise ``ValueError`` with a precise, human-readable message — never
  return ``bool`` silently.  Agents can catch and turn these into FINDINGs
  if needed, or let them propagate as hard errors.
* All allowed-value sets are imported from ``utils.constants`` — never
  duplicated here.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

from utils.constants import (
    ALLOWED_APPROVERS,
    ALLOWED_CATEGORIES,
    ALLOWED_DECISIONS,
    ALLOWED_PAYMENT_METHODS,
    ALLOWED_SEVERITIES,
    SEVERITY_RANK,
)


# ---------------------------------------------------------------------------
# Generic constrained-string validator
# ---------------------------------------------------------------------------

def validate_allowed(value: str, allowed: frozenset[str], field_name: str) -> str:
    """Assert that *value* belongs to *allowed*; return it if so.

    Parameters
    ----------
    value:
        The string to check.
    allowed:
        The set of permitted values (from ``utils.constants``).
    field_name:
        Name used in the error message, e.g. ``"severity"``.

    Returns
    -------
    str
        *value* unchanged (allows use in assignment chains).

    Raises
    ------
    ValueError
        If *value* is not in *allowed*.

    Example
    -------
    >>> validate_allowed("WARN", ALLOWED_SEVERITIES, "severity")
    'WARN'
    >>> validate_allowed("CRITICAL", ALLOWED_SEVERITIES, "severity")
    # ValueError: Invalid severity 'CRITICAL'. Allowed: {BLOCK, HIGH, INFO, WARN}
    """
    if value not in allowed:
        sorted_allowed = ", ".join(sorted(allowed))
        raise ValueError(
            f"Invalid {field_name} {value!r}. "
            f"Allowed values: {{{sorted_allowed}}}"
        )
    return value


# ---------------------------------------------------------------------------
# Domain-specific validators (thin wrappers for readability in agents)
# ---------------------------------------------------------------------------

def validate_severity(value: str) -> str:
    """Validate a finding severity string."""
    return validate_allowed(value, ALLOWED_SEVERITIES, "severity")


def validate_decision(value: str) -> str:
    """Validate a final decision string."""
    return validate_allowed(value, ALLOWED_DECISIONS, "decision")


def validate_category(value: str) -> str:
    """Validate an expense category string."""
    return validate_allowed(value, ALLOWED_CATEGORIES, "category")


def validate_payment_method(value: str) -> str:
    """Validate a payment method string."""
    return validate_allowed(value, ALLOWED_PAYMENT_METHODS, "payment_method")


def validate_approver(value: str) -> str:
    """Validate an approver routing string."""
    return validate_allowed(value, ALLOWED_APPROVERS, "approver")


# ---------------------------------------------------------------------------
# Decimal validators
# ---------------------------------------------------------------------------

def validate_decimal_string(value: Any, field_name: str = "amount") -> Decimal:
    """Parse *value* into a ``Decimal``, rejecting floats and bad strings.

    Parameters
    ----------
    value:
        Accepted types: ``str`` (e.g. ``"12.50"``), ``int``, or
        ``Decimal``.  ``float`` is explicitly rejected to prevent drift.
    field_name:
        Used in error messages.

    Returns
    -------
    Decimal

    Raises
    ------
    TypeError
        If *value* is a ``float`` (use strings instead).
    ValueError
        If *value* cannot be parsed as a valid decimal number.
    """
    if isinstance(value, float):
        raise TypeError(
            f"Field '{field_name}' must not be a float — "
            f"use a string (e.g. '12.50') or Decimal to avoid drift."
        )
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise ValueError(
            f"Field '{field_name}' value {value!r} is not a valid decimal number."
        )


def validate_non_negative(value: Decimal, field_name: str = "amount") -> Decimal:
    """Assert *value* is zero or positive.

    Raises
    ------
    ValueError
        If *value* is negative.
    """
    if value < Decimal("0"):
        raise ValueError(
            f"Field '{field_name}' must be non-negative; got {value!r}."
        )
    return value


# ---------------------------------------------------------------------------
# Date validator
# ---------------------------------------------------------------------------

def validate_iso_date(value: str, field_name: str = "date") -> str:
    """Assert *value* is a valid ISO-8601 date string (``YYYY-MM-DD``).

    Returns
    -------
    str
        *value* unchanged.

    Raises
    ------
    ValueError
        If *value* does not match the expected format.
    """
    import datetime  # local import to keep module-level imports minimal

    try:
        datetime.date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError(
            f"Field '{field_name}' must be an ISO date 'YYYY-MM-DD'; "
            f"got {value!r}."
        )
    return value


# ---------------------------------------------------------------------------
# Severity comparison helper
# ---------------------------------------------------------------------------

def is_severity_at_least(actual: str, minimum: str) -> bool:
    """Return ``True`` if *actual* severity is >= *minimum* severity.

    Useful for filtering: ``is_severity_at_least(finding.severity, "HIGH")``.

    Raises
    ------
    ValueError
        If either argument is not a known severity.
    """
    validate_severity(actual)
    validate_severity(minimum)
    return SEVERITY_RANK[actual] >= SEVERITY_RANK[minimum]


# ---------------------------------------------------------------------------
# Composite model validators
# ---------------------------------------------------------------------------

def validate_finding_fields(
    *,
    finding_id: str,
    agent: str,
    expense_id: str,
    rule_id: str,
    severity: str,
    message: str,
    evidence: list[str],
    suggested_action: str,
) -> None:
    """Cross-check all required fields of a ``Finding`` before construction.

    Raises ``ValueError`` on the first constraint that fails.  Pass the
    same keyword arguments you would pass to ``Finding(**kwargs)``.
    """
    if not finding_id or not finding_id.strip():
        raise ValueError("finding_id must be a non-empty string.")

    if not agent or not agent.strip():
        raise ValueError("agent must be a non-empty string.")

    if not expense_id or not expense_id.strip():
        raise ValueError(
            "expense_id must be a non-empty string ('NONE' is valid for "
            "card-only findings)."
        )

    if not rule_id or not rule_id.strip():
        raise ValueError("rule_id must be a non-empty string.")

    validate_severity(severity)

    if not message or not message.strip():
        raise ValueError("message must be a non-empty string.")

    if not evidence:
        raise ValueError(
            "evidence must be a non-empty list — at least one file or "
            "field pointer is required."
        )

    if not suggested_action or not suggested_action.strip():
        raise ValueError("suggested_action must be a non-empty string.")


def validate_expense_decision_fields(
    *,
    expense_id: str,
    decision: str,
    approver: str,
    reimbursable_amount_usd: Any,
) -> Decimal:
    """Validate and return the ``reimbursable_amount_usd`` as a ``Decimal``.

    Raises ``ValueError`` / ``TypeError`` on the first failure.
    """
    if not expense_id or not expense_id.strip():
        raise ValueError("expense_id must be a non-empty string.")

    validate_decision(decision)
    validate_approver(approver)

    amount = validate_decimal_string(reimbursable_amount_usd, "reimbursable_amount_usd")
    validate_non_negative(amount, "reimbursable_amount_usd")
    return amount