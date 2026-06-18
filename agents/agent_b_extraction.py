from typing import Literal
from pydantic import BaseModel, Field
from openai import OpenAI
from decimal import Decimal, InvalidOperation

from schemas.models import ExtractedExpense, ExtractionOutput, LineItem, ContextPacket
from services.pdf_service import extract_text
from services.openai_service import extract_structured

from utils.json_utils import read_json, write_json, model_to_dict
from utils.constants import FILENAME_CONTEXT_PACKET, FILENAME_EXTRACTED_EXPENSES

from pathlib import Path

class LLMLineItem(BaseModel):
    description: str = Field(description="Line item text exactly as printed.")
    quantity: str = Field(description="Quantity as printed, e.g. '2'. A number written as a string.")
    unit_price: str = Field(description="Unit price as printed, digits only, no currency symbol, e.g. '11.50'.")
    line_total: str = Field(description="Line total AS PRINTED. Do NOT recompute it from quantity x unit_price.")

class LLMReceipt(BaseModel):
    vendor: str = Field(description="Merchant name as printed at the top of the receipt.")
    expense_date: str = Field(description="Receipt date in YYYY-MM-DD format.")
    currency: str = Field(description="3-letter ISO currency code, e.g. 'EUR', 'USD', 'GBP'. Convert any symbol to its code.")
    country: str = Field(description="2-letter ISO country code, e.g. 'DE', 'FR', 'SA'. Infer from the address if not explicit.")
    payment_method: Literal["corporate_card", "personal", "cash", "unknown"] = Field(
        description="How the receipt says it was paid. Use 'unknown' if not stated.")
    category: Literal["lodging", "meals", "transport", "airfare", "alcohol", "office", "other"] = Field(
        description="Best-fit expense category based on vendor and items.")
    total_amount: str = Field(description="Grand total AS PRINTED, digits only, no symbol, e.g. '95.00'. If unreadable, give your best guess and LOWER overall_confidence.")
    line_items: list[LLMLineItem] = Field(description="Every line item on the receipt. Empty list if none are itemized.")
    overall_confidence: float = Field(description="Confidence in this extraction, 0.0-1.0. Lower it when text is missing, ambiguous, or unreadable (e.g. a smudged total).")

EXTRACTION_SYSTEM_PROMPT = """
You extract structured data from a single expense receipt.
Report only what is actually printed on the receipt. Do not invent, infer, or "correct" values. If a field is missing, ambiguous, or unreadable, fill in your best reading and lower overall_confidence rather than guessing a clean value.
Transcribe amounts exactly as printed — never recompute a total or line total yourself, even if the arithmetic looks wrong. A mismatch is real information for a later step.
"""

_client = OpenAI()

def _to_decimal(text):
    try:
        return Decimal(str(text)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None

def map_to_expense(llm, expense_id, source_file_id, confidence_threshold=0.80):
    # Turn an LLMReceipt DTO into an ExtractedExpense from the frozenschema
    bad_parse = False

    total = _to_decimal(llm.total_amount)
    if total is None:
        total, bad_parse = Decimal("0.00"), True
    
    line_items = []
    for li in llm.line_items:
        unit, line, qty = _to_decimal(li.unit_price), _to_decimal(li.line_total), _to_decimal(li.quantity)
        if None in (unit, line, qty):
            bad_parse = True
            unit, line, qty = unit or Decimal("0.00"), line or Decimal("0.00"), qty or Decimal("0.00")
        line_items.append(
            LineItem(
                description=li.description,
                quantity = qty,
                unit_price=unit,
                line_total= line))
        
    needs_review = (llm.overall_confidence <= confidence_threshold) or bad_parse

    return ExtractedExpense(
        expense_id=expense_id,
        source_file_id=source_file_id,
        vendor=llm.vendor,
        expense_date=llm.expense_date,
        currency=llm.currency,
        total_amount=total,
        category=llm.category,
        payment_method=llm.payment_method,
        country=llm.country,
        line_items=line_items,
        overall_confidence=llm.overall_confidence,
        needs_manual_review=needs_review,     
    )


def run_extraction(context, bundle_dir, confidence_threshold: float = 0.80) -> ExtractionOutput:
    #Agent B creates one structured expense per receipt
    #EXXX IDs are assigned by sorted filenames
    bundle_dir = Path(bundle_dir)
    receipts = sorted(
        (f for f in context.files if f.file_type == "receipt_pdf"),
        key=lambda f: f.filename, # Sort by filenme
    )

    expenses, skipped = [], []
    for i, entry in enumerate(receipts, start=1):
        expense_id = f"E{i:03d}"
        path = bundle_dir / "receipts" / entry.filename
        try:
            text = extract_text(str(path))
            if not text:
                skipped.append(f"{entry.filename}: no extractable text")
                continue
            llm = extract_structured(EXTRACTION_SYSTEM_PROMPT, text, LLMReceipt)
            expenses.append(map_to_expense(llm, expense_id, entry.file_id, confidence_threshold))
        except Exception as e:
            skipped.append(f"{entry.filename}: {e}")

    return ExtractionOutput(bundle_id=context.bundle_id, expenses=expenses, skipped_files=skipped)

def run(bundle_path, run_dir, policy):
    ctx = ContextPacket(**read_json(run_dir / FILENAME_CONTEXT_PACKET))
    out = run_extraction(ctx, bundle_dir=bundle_path)
    write_json(model_to_dict(out), run_dir / FILENAME_EXTRACTED_EXPENSES)   # data first, path second
    return 0