from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import re
from typing import Optional
from datetime import datetime

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- REQUEST/RESPONSE MODELS ---
class InvoiceRequest(BaseModel):
    invoice_text: str

class InvoiceResponse(BaseModel):
    invoice_no: Optional[str] = None
    date: Optional[str] = None
    vendor: Optional[str] = None
    amount: Optional[float] = None
    tax: Optional[float] = None
    currency: Optional[str] = None

# --- HELPER FUNCTIONS ---

def extract_invoice_number(text: str) -> Optional[str]:
    """Extract invoice number"""
    patterns = [
        r'Invoice\s*(?:No|Number|#)[:.\s]+([A-Za-z0-9\-_/]+)',
        r'Ref[:\s]+([A-Za-z0-9\-_/]+)',
        r'INV[-:\s]+([A-Za-z0-9\-_/]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None

def extract_date(text: str) -> Optional[str]:
    """Extract date and convert to YYYY-MM-DD"""
    date_patterns = [
        (r'(\d{4}-\d{2}-\d{2})', '%Y-%m-%d'),
        (r'(\d{2}/\d{2}/\d{4})', '%m/%d/%Y'),
        (r'(\d{2}-\d{2}-\d{4})', '%m-%d-%Y'),
        (r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})', None),
        (r'(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})', None),
        (r'(\d{1,2})(?:st|nd|rd|th)?\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})', None),
    ]
    
    for pattern, date_format in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                if date_format:
                    dt = datetime.strptime(match.group(1), date_format)
                    return dt.strftime('%Y-%m-%d')
                else:
                    # Handle "15 March 2026" format
                    day = int(match.group(1))
                    month_str = match.group(2)
                    year = int(match.group(3))
                    
                    month_map = {
                        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
                        'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
                        'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12,
                        'January': 1, 'February': 2, 'March': 3, 'April': 4,
                        'May': 5, 'June': 6, 'July': 7, 'August': 8,
                        'September': 9, 'October': 10, 'November': 11, 'December': 12
                    }
                    month = month_map.get(month_str)
                    if month:
                        dt = datetime(year, month, day)
                        return dt.strftime('%Y-%m-%d')
            except:
                continue
    return None

def extract_vendor(text: str) -> Optional[str]:
    """Extract vendor name"""
    patterns = [
        r'(?:Vendor|Seller|Supplier|From|Company)[:.\s]+([^\n,]+)',
        r'(?:Bill to|Sold by)[:.\s]+([^\n,]+)',
        r'^([A-Za-z][A-Za-z\s]+)(?:\s*—|\s*-\s*Tax)',  # First line pattern
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            vendor = match.group(1).strip()
            if len(vendor) > 2:
                return vendor
    return None

def extract_amount(text: str) -> Optional[float]:
    """Extract subtotal amount (before tax)"""
    patterns = [
        r'(?:Subtotal|Sub total)[:.\s]+(?:Rs\.?|INR)?\s*([\d,]+\.?\d*)',
        r'(?:Subtotal|Sub total)[:.\s]+([\d,]+\.?\d*)',
        r'Amount[:.\s]+(?:Rs\.?|INR)?\s*([\d,]+\.?\d*)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                amount_str = match.group(1).replace(',', '')
                return float(amount_str)
            except:
                continue
    return None

def extract_tax(text: str) -> Optional[float]:
    """Extract tax amount"""
    patterns = [
        r'(?:GST|IGST|Tax|VAT)[:\s]*(?:\([^)]*\))?[:.\s]+(?:Rs\.?|INR)?\s*([\d,]+\.?\d*)',
        r'(?:GST|IGST|Tax|VAT)[:\s]*(?:\([^)]*\))?[:.\s]+([\d,]+\.?\d*)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                tax_str = match.group(1).replace(',', '')
                return float(tax_str)
            except:
                continue
    return None

def extract_currency(text: str) -> Optional[str]:
    """Extract currency code"""
    currency_patterns = {
        'INR': ['INR', 'Rs', '₹'],
        'USD': ['USD', '$', 'dollar'],
        'EUR': ['EUR', '€', 'euro'],
        'GBP': ['GBP', '£', 'pound'],
    }
    
    for code, symbols in currency_patterns.items():
        for symbol in symbols:
            if symbol in text:
                return code
    
    return None

# --- MAIN ENDPOINT ---
@app.post("/extract")
async def extract_invoice(request: InvoiceRequest):
    text = request.invoice_text
    
    if not text or len(text.strip()) < 5:
        return InvoiceResponse()
    
    try:
        # Extract all fields
        invoice_no = extract_invoice_number(text)
        date = extract_date(text)
        vendor = extract_vendor(text)
        amount = extract_amount(text)
        tax = extract_tax(text)
        currency = extract_currency(text)
        
        return InvoiceResponse(
            invoice_no=invoice_no,
            date=date,
            vendor=vendor,
            amount=amount,
            tax=tax,
            currency=currency
        )
        
    except Exception as e:
        # Always return valid JSON, even on error
        return InvoiceResponse()

# --- HOMEPAGE ---
@app.get("/")
async def root():
    return {
        "message": "Invoice Extraction API",
        "endpoint": "POST /extract",
        "fields": ["invoice_no", "date", "vendor", "amount", "tax", "currency"]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)