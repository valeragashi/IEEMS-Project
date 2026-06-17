from pathlib import Path
import yaml
from make_receipts import make_receipt_pdf

ROOT = Path(__file__).resolve().parent.parent # Root path
BUNDLES = ROOT / "input_bundles" # Bundles folder path

def _manifest(folder, **fields):
    (folder / "manifest.yaml").write_text(
        yaml.safe_dump(fields, sort_keys=False, allow_unicode=True)
    )

def _bundle(name):
    folder = BUNDLES / name
    (folder / "receipts").mkdir(parents=True, exist_ok=True)
    return folder

def _rno(scenario, i):
    return f"R-{scenario}-{i:03d}"

# s01 Clean hotel + flight within per diem limits — auto-approve and post.
def s01_clean():
    f = _bundle("s01_clean")

    make_receipt_pdf(
        path = str(f / "receipts" / "r1_hotel.pdf"), #path
        vendor = "Hotel Adlon Berlin",
        date = "2026-06-10",
        currency="EUR",
        items=[{"description": "Room (per night)", "quantity": 2, "unit_price": "160.00"}],
        country="DE",
        payment="corporate_card",
        vendor_address="Unter den Linden 77, Berlin",
        receipt_no=_rno("s01", 1)
    )

    make_receipt_pdf(
        path = str(f / "receipts" / "r2_airfare.pdf"),
        vendor="Lufthansa",
        date="2026-06-09",
        currency="USD",
        items=[{"description": "FRA-LHR economy", "quantity": 1, "unit_price": "420.00"}],
        country="DE",
        payment="corporate_card",
        vendor_address="Flughafen Frankfurt, Frankfurt",
        receipt_no=_rno("s01", 2)
    )
    
    (f / "card_export.csv").write_text(
        "date,vendor,amount,currency\n"
        "2026-06-10,Hotel Adlon Berlin,320.00,EUR\n"
        "2026-06-09,Lufthansa,420.00,USD\n"
    )

    _manifest(f, bundle_id="s01_clean", employee_id="EMP-0001", employee_name="Jane Doe",
              cost_center="CC-1100", submission_date="2026-06-10", trip_purpose="Client visit Berlin",
              expected={"decisions": [
                          {"expense_id": "E001", "decision": "AUTO_APPROVE"},
                          {"expense_id": "E002", "decision": "AUTO_APPROVE"},
                        ],
                        "must_contain_rule_ids": [],
                        "reimbursable": {"E001": "0.00", "E002": "0.00"}})

# s02 Dinner expense over per diem limit — flag for manager approval routing.
def s02_over_per_diem():
    f = _bundle("s02_over_per_diem")

    make_receipt_pdf(
        path= str(f / "receipts" / "r1_dinner.pdf"),
        vendor="Restaurant Vau",
        date="2026-06-10",
        currency="EUR",
        items=[
            {"description": "Starter",        "quantity": 1, "unit_price": "22.00"},
            {"description": "Main course",    "quantity": 1, "unit_price": "48.00"},
            {"description": "Glass of wine",  "quantity": 1, "unit_price": "25.00"},
        ],
        country="DE",
        payment="personal",
        vendor_address="Jaegerstrasse 54, Berlin",
        receipt_no=_rno("s02", 1)
    )
    
    _manifest(f, bundle_id="s02_over_per_diem", employee_id="EMP-0002", employee_name="Jane Doe",
        cost_center="CC-1100", submission_date="2026-06-10", trip_purpose="Client dinner Berlin",
        expected={"decisions": [
                    {"expense_id": "E001", "decision": "MANAGER_APPROVAL"},
                  ],
                  "must_contain_rule_ids": ["PER_DIEM_MEALS"]})

    
# s03 Same receipt submitted in two separate expense reports (exact duplicate).
def s03_duplicate():
    f = _bundle("s03_duplicate")

    make_receipt_pdf(
        path=str(f / "receipts" / "r1_lunch.pdf"),
        vendor="Cafe Roma", 
        date="2026-06-09", 
        currency="EUR",
        items=[{"description": "Team lunch", "quantity": 1, "unit_price": "38.00"}],
        country="IT", 
        payment="personal",
        vendor_address="Piazza Navona 5, Rome", 
        receipt_no=_rno("s03", 1)
    )
    
    r2 = f / "receipts" / "r2_dinner.pdf"
    make_receipt_pdf(str(r2), # We use a variable to re-use path to create a duplicate
        vendor="Trattoria Roma",
        date="2026-06-10",
        currency="EUR",
        items=[{"description": "Dinner", "quantity": 1, "unit_price": "48.00"}],
        country="IT",
        payment="personal",
        vendor_address="Via del Corso 14, Rome", 
        receipt_no=_rno("s03", 2)
    )
    # exact copy -> identical bytes, identical sha256: the planted duplicate
    (f / "receipts" / "r3_dinner_copy.pdf").write_bytes(r2.read_bytes())
    _manifest(f, bundle_id="s03_duplicate", employee_id="EMP-0003", employee_name="Jane Doe",
        cost_center="CC-1100", submission_date="2026-06-10", trip_purpose="Client visit Rome",
        expected={"decisions": [
                    {"expense_id": "E001", "decision": "AUTO_APPROVE"},
                    {"expense_id": "E002", "decision": "AUTO_APPROVE"},
                    {"expense_id": "E003", "decision": "BLOCK"},
                  ],
                  "must_contain_rule_ids": ["EXACT_DUPLICATE"],
                  "reimbursable": {"E001": "38.00", "E002": "48.00", "E003": "0.00"}})


# s04 Alcohol purchase in a country where it is non-reimbursable — policy block.

def s04_alcohol_block():
    f = _bundle("s04_alcohol_block")
    make_receipt_pdf(str(f / "receipts" / "r1_wine.pdf"),
        vendor="Riyadh Hotel Bar", date="2026-06-10", currency="USD",
        items=[{"description": "Bottle of wine", "quantity": 1, "unit_price": "60.00"}],
        country="SA", payment="corporate_card",
        vendor_address="King Fahd Rd, Riyadh", receipt_no=_rno("s04", 1))
    (f / "card_export.csv").write_text(
        "date,vendor,amount,currency\n"
        "2026-06-10,Riyadh Hotel Bar,60.00,USD\n"
    )
    _manifest(f, bundle_id="s04_alcohol_block", employee_id="EMP-0004", employee_name="Jane Doe",
        cost_center="CC-1100", submission_date="2026-06-10", trip_purpose="Conference Riyadh",
        expected={"decisions": [
                    {"expense_id": "E001", "decision": "BLOCK"},
                  ],
                  "must_contain_rule_ids": ["ALCOHOL_BLOCKED_COUNTRY"],
                  "reimbursable": {"E001": "0.00"}})

# s05 Missing receipt for high-value item above $50 threshold — exception raised.
def s05_missing_receipt():
    f = _bundle("s05_missing_receipt")
    make_receipt_pdf(str(f / "receipts" / "r1_taxi.pdf"),
        vendor="Berlin Taxi", date="2026-06-10", currency="EUR",
        items=[{"description": "Airport transfer", "quantity": 1, "unit_price": "32.00"}],
        country="DE", payment="personal",
        vendor_address="Hauptbahnhof, Berlin", receipt_no=_rno("s05", 1))
    (f / "card_export.csv").write_text(
        "date,vendor,amount,currency\n"
        "2026-06-10,Steakhouse Mitte,80.00,EUR\n"
    )
    _manifest(f, bundle_id="s05_missing_receipt", employee_id="EMP-0005", employee_name="Jane Doe",
        cost_center="CC-1100", submission_date="2026-06-11", trip_purpose="Client visit Berlin",
        expected={"decisions": [
                    {"expense_id": "E001", "decision": "AUTO_APPROVE"},
                  ],
                  "must_contain_rule_ids": ["MISSING_RECEIPT"],
                  "reimbursable": {"E001": "32.00"}})
# s06 VAT-eligible receipt — auto-tag for tax team reclaim processing.
def s06_vat():
    f = _bundle("s06_vat")
    make_receipt_pdf(
        path= str(f / "receipts" / "r1_hotel.pdf"),
        vendor="Hotel Bayerischer Hof", 
        date="2026-06-10", 
        currency="EUR",
        items=[{"description": "Room (per night)", "quantity": 1, "unit_price": "150.00"}],
        country="DE", 
        payment="corporate_card",
        vendor_address="Promenadeplatz 2, Munich", 
        receipt_no=_rno("s06", 1)
    )
    (f / "card_export.csv").write_text(
        "date,vendor,amount,currency\n"
        "2026-06-10,Hotel Bayerischer Hof,150.00,EUR\n"
    )
    _manifest(f, bundle_id="s06_vat", employee_id="EMP-0006", employee_name="Jane Doe",
        cost_center="CC-1100", submission_date="2026-06-10", trip_purpose="Conference Munich",
        expected={"decisions": [
                    {"expense_id": "E001", "decision": "AUTO_APPROVE"},
                  ],
                  "must_contain_rule_ids": ["VAT_RECLAIM_ELIGIBLE"],
                  "reimbursable": {"E001": "0.00"}})
# s07 Multi-currency trip requiring FX normalization and conversion.
def s07_multi_currency():
    f = _bundle("s07_multi_currency")
    make_receipt_pdf(
        path= str(f / "receipts" / "r1_eur.pdf"),
        vendor="Cafe Central", 
        date="2026-06-08", 
        currency="EUR",
        items=[{"description": "Working lunch", "quantity": 1, "unit_price": "120.00"}],
        country="AT", 
        payment="corporate_card",
        vendor_address="Herrengasse 14, Vienna", 
        receipt_no=_rno("s07", 1))
    
    make_receipt_pdf(
        path= str(f / "receipts" / "r2_gbp.pdf"),
        vendor="The Ledbury", 
        date="2026-06-09", 
        currency="GBP",
        items=[{"description": "Client dinner", "quantity": 1, "unit_price": "200.00"}],
        country="GB", 
        payment="corporate_card",
        vendor_address="127 Ledbury Rd, London", 
        receipt_no=_rno("s07", 2))
    
    make_receipt_pdf(str(f / "receipts" / "r3_usd.pdf"),
        vendor="WeWork NYC", 
        date="2026-06-10", 
        currency="USD",
        items=[{"description": "Desk day pass", "quantity": 1, "unit_price": "300.00"}],
        country="US", 
        payment="corporate_card",
        vendor_address="115 Broadway, New York", 
        receipt_no=_rno("s07", 3))
    
    (f / "card_export.csv").write_text(
        "date,vendor,amount,currency\n"
        "2026-06-08,Cafe Central,120.00,EUR\n"
        "2026-06-09,The Ledbury,200.00,GBP\n"
        "2026-06-10,WeWork NYC,300.00,USD\n"
    )

    _manifest(f, bundle_id="s07_multi_currency", employee_id="EMP-0007", employee_name="Jane Doe",
        cost_center="CC-1100", submission_date="2026-06-10", trip_purpose="Multi-city office tour",
        expected={"decisions": [
                    {"expense_id": "E001", "decision": "AUTO_APPROVE"},
                    {"expense_id": "E002", "decision": "AUTO_APPROVE"},
                    {"expense_id": "E003", "decision": "AUTO_APPROVE"},
                  ],
                  "must_contain_rule_ids": [],
                  "reimbursable": {"E001": "0.00", "E002": "0.00", "E003": "0.00"}})
    

# s08 Receipt with low OCR confidence on amount field — manual review route.
def s08_low_confidence():
    f = _bundle("s08_low_confidence")

    make_receipt_pdf(
        path= str(f / "receipts" / "r1_smudged.pdf"),
        vendor="Corner Bistro", 
        date="2026-06-10", 
        currency="EUR",
        items=[{"description": "Lunch", "quantity": 1, "unit_price": "44.00"}],
        country="FR", 
        payment="cash", 
        font="Helvetica",
        vendor_address="12 Rue de Rivoli, Paris", 
        receipt_no="",
        obscure_total=True)
    
    _manifest(f, bundle_id="s08_low_confidence", employee_id="EMP-0008", employee_name="Jane Doe",
        cost_center="CC-1100", submission_date="2026-06-10", trip_purpose="Client visit Paris",
        expected={"decisions": [
                    {"expense_id": "E001", "decision": "MANUAL_REVIEW"},
                  ],
                  "must_contain_rule_ids": []})
# s09 Clean small expense under threshold — minimal noise, fast-track approval.
def s09_fast_track():
    f = _bundle("s09_fast_track")

    make_receipt_pdf(
        path= str(f / "receipts" / "r1_taxi.pdf"),
        vendor="City Cab", 
        date="2026-06-10", 
        currency="EUR",
        items=[{"description": "Short ride", "quantity": 1, "unit_price": "12.00"}],
        country="DE", 
        payment="cash",
        vendor_address="Alexanderplatz, Berlin", 
        receipt_no=_rno("s09", 1))
    
    _manifest(f, bundle_id="s09_fast_track", employee_id="EMP-0009", employee_name="Jane Doe",
        cost_center="CC-1100", submission_date="2026-06-10", trip_purpose="Local travel Berlin",
        expected={"decisions": [
                    {"expense_id": "E001", "decision": "AUTO_APPROVE"},
                  ],
                  "must_contain_rule_ids": ["FAST_TRACK"],
                  "reimbursable": {"E001": "12.00"}})

def generate_receipts():
    s01_clean()
    s02_over_per_diem()
    s03_duplicate()
    s04_alcohol_block()
    s05_missing_receipt()
    s06_vat()
    s07_multi_currency()
    s08_low_confidence()
    s09_fast_track()

if __name__ == "__main__":
    generate_receipts()