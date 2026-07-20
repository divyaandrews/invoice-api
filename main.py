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

class InvoiceRequest(BaseModel):
    invoice_text: str

class InvoiceResponse(BaseModel):
    invoice_no: Optional[str] = None
    date: Optional[str] = None
    vendor: Optional[str] = None
    amount: Optional[float] = None
    tax: Optional[float] = None
    currency: Optional[str] = None

def extract_invoice_number(text: str) -> Optional[str]:
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
    """Extract date and convert to YYYY-MM-DD (Indian format: DD/MM/YYYY)"""
    
    # Look for "Date:" label
    date_label_match = re.search(r'Date[:.\s]+([^\n]+)', text, re.IGNORECASE)
    if date_label_match:
        date_str = date_label_match.group(1).strip()
        
        # Try DD/MM/YYYY
        match = re.search(r'(\d{2})/(\d{2})/(\d{4})', date_str)
        if match:
            day = int(match.group(1))
            month = int(match.group(2))
            year = int(match.group(3))
            if 1 <= day <= 31 and 1 <= month <= 12:
                return f"{year}-{month:02d}-{day:02d}"
        
        # Try DD-MM-YYYY
        match = re.search(r'(\d{2})-(\d{2})-(\d{4})', date_str)
        if match:
            day = int(match.group(1))
            month = int(match.group(2))
            year = int(match.group(3))
            if 1 <= day <= 31 and 1 <= month <= 12:
                return f"{year}-{month:02d}-{day:02d}"
        
        # Try DD Month YYYY
        match = re.search(r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})', date_str, re.IGNORECASE)
        if match:
            day = int(match.group(1))
            month_str = match.group(2)
            year = int(match.group(3))
            month_map = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                        'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
            month = month_map.get(month_str)
            if month and 1 <= day <= 31:
                return f"{year}-{month:02d}-{day:02d}"
    
    # Fallback: look for any date pattern in DD/MM/YYYY format
    match = re.search(r'(\d{2})/(\d{2})/(\d{4})', text)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))
        if 1 <= day <= 31 and 1 <= month <= 12:
            return f"{year}-{month:02d}-{day:02d}"
    
    return None

def extract_vendor(text: str) -> Optional[str]:
    patterns = [
        r'(?:Vendor|Seller|Supplier|From|Company)[:.\s]+([^\n,]+)',
        r'(?:Bill to|Sold by)[:.\s]+([^\n,]+)',
        r'^([A-Za-z][A-Za-z\s]+)(?:\s*—|\s*-\s*Tax)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            vendor = match.group(1).strip()
            if len(vendor) > 2:
                return vendor
    return None

def extract_amount(text: str) -> Optional[float]:
    """Extract subtotal amount intelligently"""
    
    # First, try to find subtotal explicitly
    subtotal_match = re.search(r'(?:Subtotal|Sub total)[:.\s]+(?:Rs\.?|INR)?\s*([\d,]+\.?\d*)', text, re.IGNORECASE)
    if subtotal_match:
        try:
            return float(subtotal_match.group(1).replace(',', ''))
        except:
            pass
    
    # If we can't find subtotal, try to find tax and total
    tax_amount = None
    total_amount = None
    
    # Find tax
    tax_match = re.search(r'(?:GST|IGST|Tax|VAT)[:\s]*(?:\([^)]*\))?[:.\s]+(?:Rs\.?|INR)?\s*([\d,]+\.?\d*)', text, re.IGNORECASE)
    if tax_match:
        try:
            tax_amount = float(tax_match.group(1).replace(',', ''))
        except:
            pass
    
    # Find total
    total_match = re.search(r'(?:Total Due|Grand Total|Total)[:.\s]+(?:Rs\.?|INR)?\s*([\d,]+\.?\d*)', text, re.IGNORECASE)
    if total_match:
        try:
            total_amount = float(total_match.group(1).replace(',', ''))
        except:
            pass
    
    # If we have both tax and total, subtract tax from total to get subtotal
    if tax_amount is not None and total_amount is not None:
        subtotal = total_amount - tax_amount
        return round(subtotal, 2)
    
    # If we found total but not tax, return total (assuming no tax)
    if total_amount is not None:
        return total_amount
    
    return None

def extract_tax(text: str) -> Optional[float]:
    patterns = [
        r'(?:GST|IGST|Tax|VAT)[:\s]*(?:\([^)]*\))?[:.\s]+(?:Rs\.?|INR)?\s*([\d,]+\.?\d*)',
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
    if 'INR' in text or 'Rs' in text or '₹' in text:
        return 'INR'
    if 'USD' in text or '$' in text:
        return 'USD'
    if 'EUR' in text or '€' in text:
        return 'EUR'
    if 'GBP' in text or '£' in text:
        return 'GBP'
    return None

@app.post("/extract")
async def extract_invoice(request: InvoiceRequest):
    text = request.invoice_text
    
    if not text or len(text.strip()) < 5:
        return InvoiceResponse()
    
    try:
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
        return InvoiceResponse()

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