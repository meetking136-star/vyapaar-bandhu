from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.models.base import Invoice, GSTLedger, User
from datetime import datetime
from pydantic import BaseModel
import io

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    REPORTLAB = True
except ImportError:
    REPORTLAB = False

router = APIRouter(prefix="/api", tags=["Dashboard API"])

class ClientCreate(BaseModel):
    name: str
    phone: str
    gstin: str = ""
    state: str = ""

@router.get("/dashboard/stats")
def get_dashboard_stats(db: Session = Depends(get_db)):
    try:
        period = datetime.now().strftime("%Y-%m")
        itc_row = db.query(func.sum(GSTLedger.itc_available)).filter(GSTLedger.period == period).scalar() or 0
        total_invoices = db.query(func.count(Invoice.id)).scalar() or 0
        pending_invoices = db.query(func.count(Invoice.id)).filter(Invoice.status == "pending").scalar() or 0
        total_users = db.query(func.count(User.id)).scalar() or 0
        return {
            "total_itc": round(float(itc_row), 2),
            "total_invoices": total_invoices,
            "pending_invoices": pending_invoices,
            "total_clients": total_users,
            "period": period
        }
    except Exception as e:
        return {"error": str(e)}

@router.get("/clients")
def get_clients(db: Session = Depends(get_db)):
    try:
        period = datetime.now().strftime("%Y-%m")
        users = db.query(User).all()
        result = []
        for user in users:
            ledger = db.query(GSTLedger).filter(GSTLedger.user_id == user.id, GSTLedger.period == period).first()
            invoice_count = db.query(func.count(Invoice.id)).filter(Invoice.user_id == user.id).scalar() or 0
            itc = float(ledger.itc_available) if ledger else 0
            if itc > 1000:
                status = "compliant"
            elif itc > 0:
                status = "attention"
            else:
                status = "at-risk"
            risk_score = min(100, int((itc / 500) * 10 + invoice_count * 5))
            result.append({
                "id": str(user.id),
                "name": user.business_name or user.phone or "Unknown",
                "gstin": user.gstin or "",
                "state": user.state_code or "",
                "whatsapp": user.phone or "",
                "itcThisMonth": itc,
                "invoiceCount": invoice_count,
                "complianceStatus": status,
                "riskScore": min(risk_score, 100)
            })
        return result
    except Exception as e:
        return {"error": str(e)}

@router.post("/clients")
def create_client(client: ClientCreate, db: Session = Depends(get_db)):
    try:
        user = User(
            business_name=client.name,
            phone=client.phone,
            gstin=client.gstin,
            state_code=client.state
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return {"success": True, "id": str(user.id)}
    except Exception as e:
        return {"error": str(e)}

@router.get("/clients/{client_id}/filing-pdf")
def get_filing_pdf(client_id: int, db: Session = Depends(get_db)):
    if not REPORTLAB:
        return {"error": "reportlab not installed"}
    user = db.query(User).filter(User.id == client_id).first()
    if not user:
        return {"error": "Client not found"}
    invoices = db.query(Invoice).filter(Invoice.user_id == client_id).all()
    buf = io.BytesIO()
    p = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, h-50, "VyapaarBandhu — Filing Summary")
    p.setFont("Helvetica", 11)
    p.drawString(50, h-80, f"Client: {user.business_name or user.phone or 'Unknown'}")
    p.drawString(50, h-100, f"GSTIN: {user.gstin or 'Not set'}")
    p.drawString(50, h-120, f"Period: {datetime.now().strftime('%B %Y')}")
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, h-160, "Invoice No")
    p.drawString(200, h-160, "Date")
    p.drawString(320, h-160, "Total")
    p.drawString(420, h-160, "ITC")
    p.drawString(490, h-160, "Status")
    y = h - 180
    total_itc = 0
    p.setFont("Helvetica", 10)
    for inv in invoices:
        itc = float((inv.cgst or 0) + (inv.sgst or 0) + (inv.igst or 0))
        total = float((inv.taxable_amt or 0) + itc)
        total_itc += itc
        p.drawString(50, y, inv.invoice_no or "—")
        p.drawString(200, y, str(inv.date or "")[:10])
        p.drawString(320, y, f"Rs {total:.2f}")
        p.drawString(420, y, f"Rs {itc:.2f}")
        p.drawString(490, y, inv.status or "confirmed")
        y -= 20
        if y < 100:
            p.showPage()
            y = h - 50
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, y - 20, f"Total ITC Eligible: Rs {total_itc:.2f}")
    p.save()
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=filing_{client_id}_{datetime.now().strftime('%Y%m')}.pdf"})

@router.get("/clients/{client_id}")
def get_client_detail(client_id: int, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.id == client_id).first()
        if not user:
            return {"error": "Client not found"}
        invoices = db.query(Invoice).filter(Invoice.user_id == client_id).all()
        period = datetime.now().strftime("%Y-%m")
        ledger = db.query(GSTLedger).filter(GSTLedger.user_id == client_id, GSTLedger.period == period).first()
        invoice_list = []
        for inv in invoices:
            itc = float((inv.cgst or 0) + (inv.sgst or 0) + (inv.igst or 0))
            total = float((inv.taxable_amt or 0) + itc)
            invoice_list.append({
                "id": str(inv.id),
                "invoiceNo": inv.invoice_no or "",
                "date": str(inv.date or ""),
                "supplierGstin": inv.seller_gstin or "",
                "taxableAmt": float(inv.taxable_amt or 0),
                "total": total,
                "cgst": float(inv.cgst or 0),
                "sgst": float(inv.sgst or 0),
                "igst": float(inv.igst or 0),
                "itc": itc,
                "status": inv.status or "confirmed",
                "aiCategory": "General"
            })
        return {
            "id": str(user.id),
            "name": user.business_name or user.phone or "Unknown",
            "gstin": user.gstin or "",
            "state": user.state_code or "",
            "whatsapp": user.phone or "",
            "itcThisMonth": float(ledger.itc_available) if ledger else 0,
            "invoiceCount": len(invoice_list),
            "invoices": invoice_list
        }
    except Exception as e:
        return {"error": str(e)}

@router.get("/invoices")
def get_invoices(db: Session = Depends(get_db)):
    try:
        invoices = db.query(Invoice).order_by(Invoice.id.desc()).all()
        result = []
        for inv in invoices:
            user = db.query(User).filter(User.id == inv.user_id).first()
            itc = float((inv.cgst or 0) + (inv.sgst or 0) + (inv.igst or 0))
            total = float((inv.taxable_amt or 0) + itc)
            result.append({
                "id": str(inv.id),
                "clientId": str(inv.user_id),
                "clientName": user.business_name or user.phone or "Unknown" if user else "Unknown",
                "invoiceNo": inv.invoice_no or "",
                "date": str(inv.date or ""),
                "supplierGstin": inv.seller_gstin or "",
                "taxableAmt": float(inv.taxable_amt or 0),
                "total": total,
                "cgst": float(inv.cgst or 0),
                "sgst": float(inv.sgst or 0),
                "igst": float(inv.igst or 0),
                "itc": itc,
                "status": inv.status or "confirmed",
                "aiCategory": "General"
            })
        return result
    except Exception as e:
        return {"error": str(e)}

@router.post("/invoices/{invoice_id}/approve")
def approve_invoice(invoice_id: int, db: Session = Depends(get_db)):
    try:
        inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not inv:
            return {"error": "Invoice not found"}
        inv.status = "confirmed"
        db.commit()
        return {"success": True, "invoice_id": invoice_id, "status": "confirmed"}
    except Exception as e:
        return {"error": str(e)}

@router.post("/invoices/{invoice_id}/reject")
def reject_invoice(invoice_id: int, db: Session = Depends(get_db)):
    try:
        inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not inv:
            return {"error": "Invoice not found"}
        inv.status = "rejected"
        db.commit()
        return {"success": True, "invoice_id": invoice_id, "status": "rejected"}
    except Exception as e:
        return {"error": str(e)}

@router.get("/alerts")
def get_alerts(db: Session = Depends(get_db)):
    try:
        users = db.query(User).all()
        alerts = []
        period = datetime.now().strftime("%Y-%m")
        for user in users:
            invoice_count = db.query(func.count(Invoice.id)).filter(Invoice.user_id == user.id).scalar() or 0
            if invoice_count == 0:
                alerts.append({
                    "id": f"alert-{user.id}",
                    "clientName": user.business_name or user.phone or "Unknown",
                    "type": "No Invoices",
                    "message": "No invoices uploaded this month. ITC at risk.",
                    "priority": "high",
                    "dueDate": f"{period}-20",
                    "daysRemaining": 11,
                    "resolved": False
                })
            elif invoice_count < 3:
                alerts.append({
                    "id": f"alert-low-{user.id}",
                    "clientName": user.business_name or user.phone or "Unknown",
                    "type": "Low Invoice Count",
                    "message": f"Only {invoice_count} invoice(s) uploaded. More expected.",
                    "priority": "medium",
                    "dueDate": f"{period}-25",
                    "daysRemaining": 16,
                    "resolved": False
                })
        return alerts
    except Exception as e:
        return {"error": str(e)}