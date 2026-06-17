import pdfplumber

def extract_text(path: str) -> str:
    """Return the PDF's text, pages joined. Returns '' if there's no text
    layer (image-only receipt) — Agent B treats '' as low-confidence / fallback."""
    with pdfplumber.open(path) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages).strip()
    

if __name__ == "__main__":
    text = extract_text("input_bundles/s07_multi_currency/receipts/r1_eur.pdf")
    print(text)
    print("--- has text layer:", bool(text))