from datetime import datetime
from decimal import Decimal
from difflib import SequenceMatcher


class DuplicateService:
    def __init__(self, settings: dict):
        self.settings = settings

    def same_hash(self, sha1: str, sha2: str) -> bool:
        return bool(sha1 and sha2 and sha1 == sha2)

    def vendor_similarity(self, vendor_a: str, vendor_b: str) -> int:
        a = vendor_a.strip().lower()
        b = vendor_b.strip().lower()
        return int(SequenceMatcher(None, a, b).ratio() * 100)

    def amount_within_tolerance(
        self,
        amount_a: Decimal,
        amount_b: Decimal,
    ) -> bool:
        tolerance_pct = Decimal(str(self.settings["amount_tolerance_percent"]))

        if amount_a == amount_b:
            return True

        base = max(abs(amount_a), abs(amount_b))

        if base == 0:
            return False

        difference_pct = (abs(amount_a - amount_b) / base) * Decimal("100")

        return difference_pct <= tolerance_pct

    def dates_within_window(self, date_a: str, date_b: str) -> bool:
        window_days = int(self.settings["date_window_days"])

        parsed_a = datetime.strptime(date_a, "%Y-%m-%d")
        parsed_b = datetime.strptime(date_b, "%Y-%m-%d")

        return abs((parsed_a - parsed_b).days) <= window_days

    def is_strong_duplicate(self, expense_a, expense_b) -> bool:
        return (
            expense_a.vendor.strip().lower() == expense_b.vendor.strip().lower()
            and expense_a.expense_date == expense_b.expense_date
            and expense_a.currency == expense_b.currency
            and expense_a.total_amount == expense_b.total_amount
        )

    def is_fuzzy_duplicate(self, normalized_a, normalized_b) -> bool:
        expense_a = normalized_a.expense
        expense_b = normalized_b.expense

        vendor_score = self.vendor_similarity(expense_a.vendor, expense_b.vendor)
        min_vendor_score = int(self.settings["vendor_similarity_min"])

        return (
            vendor_score >= min_vendor_score
            and self.amount_within_tolerance(
                normalized_a.amount_base,
                normalized_b.amount_base,
            )
            and self.dates_within_window(
                normalized_a.date_iso,
                normalized_b.date_iso,
            )
        )