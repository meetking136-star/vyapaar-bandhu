from fastapi import APIRouter, Request, Form
from fastapi.responses import PlainTextResponse
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os
import threading

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])

PENDING_CONFIRMATIONS = {}

FIELD_ALIASES = {
    "gstin":    "seller_gstin",
    "gst":      "seller_gstin",
    "invoice":  "invoice_no",
    "number":   "invoice_no",
    "date":     "invoice_date",
    "taxable":  "taxable_amount",
    "cgst":     "cgst",
    "sgst":     "sgst",
    "igst":     "igst",
    "total":    "total_amount",
    "amount":   "total_amount",
}

FIELD_LABELS = {
    "seller_gstin":   "GSTIN",
    "invoice_no":     "Invoice No",
    "invoice_date":   "Date (DD-MM-YYYY)",
    "taxable_amount": "Taxable Amount (Rs.)",
    "cgst":           "CGST (Rs.)",
    "sgst":           "SGST (Rs.)",
    "igst":           "IGST (Rs.)",
    "total_amount":   "Grand Total (Rs.)",
}


def send_whatsapp_message(to: str, body: str):
    client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
    client.messages.create(
        from_="whatsapp:+14155238886",
        to=to,
        body=body
    )
    print(f"📤 Sent to {to}: {body[:80]}...")


def build_confirmation_message(fields: dict, gstin_status: str) -> str:
    msg = "Invoice details mili! Confirm karein:\n"
    msg += "--------------------\n"
    if fields["seller_gstin"]["value"]:
        msg += f"GSTIN: {fields['seller_gstin']['value']}\n"
        if gstin_status:
            msg += f"  {gstin_status}\n"
    if fields["invoice_no"]["value"]:
        msg += f"Invoice No: {fields['invoice_no']['value']}\n"
    if fields["invoice_date"]["value"]:
        msg += f"Date: {fields['invoice_date']['value']}\n"
    if fields["taxable_amount"]["value"]:
        msg += f"Taxable: Rs.{fields['taxable_amount']['value']}\n"
    if fields["cgst"]["value"]:
        msg += f"CGST: Rs.{fields['cgst']['value']}\n"
    if fields["sgst"]["value"]:
        msg += f"SGST: Rs.{fields['sgst']['value']}\n"
    if fields["igst"]["value"]:
        msg += f"IGST: Rs.{fields['igst']['value']}\n"
    if fields["total_amount"]["value"]:
        msg += f"Total: Rs.{fields['total_amount']['value']}\n"
    msg += "--------------------\n"
    msg += "Reply karein:\n"
    msg += "'yes' -> Save karein\n"
    msg += "'no' -> Cancel karein\n"
    msg += "'edit date' -> Date badlein\n"
    msg += "'edit gstin' -> GSTIN badlein\n"
    msg += "'edit total' -> Total badlein"
    return msg


@router.post("/webhook")
async def whatsapp_webhook(
    request: Request,
    Body: str = Form(default=""),
    From: str = Form(default=""),
    NumMedia: str = Form(default="0"),
    MediaUrl0: str = Form(default=""),
    MediaContentType0: str = Form(default=""),
):
    print(f"📱 Message from: {From}")
    print(f"📝 Body: '{Body}'")
    print(f"🖼️  Media count: {NumMedia}")

    if int(NumMedia) > 0 and "image" in MediaContentType0:
        threading.Thread(
            target=process_image_background,
            args=(MediaUrl0, From),
            daemon=True
        ).start()
        response = MessagingResponse()
        response.message("Photo mil gayi! Processing kar raha hoon... (10-20 seconds)")
        return PlainTextResponse(str(response), media_type="application/xml")

    elif int(NumMedia) > 0 and "pdf" in MediaContentType0.lower():
        threading.Thread(
            target=process_pdf_background,
            args=(MediaUrl0, From),
            daemon=True
        ).start()
        response = MessagingResponse()
        response.message("Bank statement mil gaya! Parse kar raha hoon... (15-20 seconds) 🏦")
        return PlainTextResponse(str(response), media_type="application/xml")

    elif Body:
        reply = handle_text(Body, From)
    else:
        reply = "Kripya ek message ya photo bhejiye."

    response = MessagingResponse()
    response.message(reply)
    return PlainTextResponse(str(response), media_type="application/xml")


def process_image_background(media_url: str, sender: str):
    try:
        from app.services.ocr_service import extract_text_from_image_url
        from app.services.gstin_validator import validate_gstin

        TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID")
        TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

        result = extract_text_from_image_url(media_url, TWILIO_SID, TWILIO_TOKEN)

        if not result["success"]:
            send_whatsapp_message(sender, "Photo padh nahi paya. Achhi roshni mein dobara photo lein.")
            return

        fields = result["fields"]
        filled = [k for k, v in fields.items() if v["value"] is not None]

        if len(filled) == 0:
            send_whatsapp_message(sender, "Invoice mein koi data nahi mila. Seedha, achhi roshni mein photo lein.")
            return

        gstin_status = ""
        if fields["seller_gstin"]["value"]:
            validation = validate_gstin(fields["seller_gstin"]["value"])
            gstin_status = f"Valid ({validation['state_name']})" if validation["is_valid"] else "Invalid GSTIN - ITC risk!"

        PENDING_CONFIRMATIONS[sender] = {
            "fields": fields,
            "awaiting_edit": None
        }

        msg = build_confirmation_message(fields, gstin_status)
        send_whatsapp_message(sender, msg)

    except Exception as e:
        print(f"❌ Background processing error: {e}")
        send_whatsapp_message(sender, "Error aaya. Dobara photo bhejiye.")


def process_pdf_background(media_url: str, sender: str):
    try:
        import requests as req
        from app.services.bank_pdf_parser import parse_bank_statement_from_bytes

        TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID")
        TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

        print(f"📥 Downloading PDF from Twilio...")
        response = req.get(media_url, auth=(TWILIO_SID, TWILIO_TOKEN), timeout=30)

        if response.status_code != 200:
            send_whatsapp_message(sender, "PDF download nahi hua. Dobara bhejiye.")
            return

        pdf_bytes = response.content
        print(f"✅ PDF downloaded: {len(pdf_bytes)} bytes")

        result = parse_bank_statement_from_bytes(pdf_bytes)

        if not result["success"]:
            send_whatsapp_message(sender, f"PDF parse nahi hua: {result['error']}")
            return

        txns = result["transactions"]
        bank = result["bank"]

        msg  = f"🏦 {bank} Bank Statement Parse Ho Gayi!\n\n"
        msg += f"📊 Total Transactions: {result['total_transactions']}\n"
        msg += f"💸 Total Debit: Rs.{result['total_debit']:,.2f}\n"
        msg += f"💰 Total Credit: Rs.{result['total_credit']:,.2f}\n"
        msg += f"📋 ITC Possible: {result['itc_possible_count']} transactions\n\n"

        itc_txns = [t for t in txns if t.get("itc_possible")][:5]
        if itc_txns:
            msg += "✅ ITC Eligible Transactions:\n"
            for t in itc_txns:
                msg += f"• {t['date']} — {t['description'][:30]} — Rs.{t['amount']:,.0f}\n"

        msg += f"\n💡 Tip: In {result['itc_possible_count']} transactions pe ITC claim ho sakta hai!"
        msg += "\nInvoices upload karke exact ITC calculate karein 📄"

        send_whatsapp_message(sender, msg)

    except Exception as e:
        print(f"❌ PDF processing error: {e}")
        send_whatsapp_message(sender, "PDF process karne mein error aaya. Dobara bhejiye.")


def handle_text(body: str, sender: str) -> str:
    body_lower = body.lower().strip()
    session = PENDING_CONFIRMATIONS.get(sender)

    if session and session.get("awaiting_edit"):
        field_name = session["awaiting_edit"]
        return apply_field_edit(sender, field_name, body.strip())

    if session:
        if any(w in body_lower for w in ["yes", "haan", "ha", "correct", "sahi", "ok", "okay"]):
            return process_confirmed_invoice(sender)

        if any(w in body_lower for w in ["nahi", "cancel", "galat", "wrong", "no"]):
            del PENDING_CONFIRMATIONS[sender]
            return "Invoice cancel kar diya. Dobara photo bhejein."

        if body_lower.startswith("edit "):
            keyword = body_lower.replace("edit ", "").strip()
            field_name = FIELD_ALIASES.get(keyword)
            if field_name:
                session["awaiting_edit"] = field_name
                label = FIELD_LABELS[field_name]
                return f"Sahi {label} enter karein:"
            else:
                return (
                    "Kaunsa field badalna hai? Example:\n"
                    "'edit date'\n'edit gstin'\n'edit total'\n'edit cgst'"
                )

        return (
            "Pending invoice hai. Reply karein:\n"
            "'yes' -> Save\n'no' -> Cancel\n'edit date' -> Field badlein"
        )

    if any(w in body_lower for w in ["hello", "hi", "namaste", "helo"]):
        return (
            "Namaste! VyapaarBandhu mein swagat hai!\n\n"
            "1. Invoice ki photo bhejiye -> ITC calculate karunga\n"
            "2. Bank statement PDF bhejiye -> transactions parse karunga\n"
            "3. 'tax' likhiye -> GST liability\n"
            "4. 'deadline' likhiye -> filing dates"
        )
    elif any(w in body_lower for w in ["tax", "gst", "kitna", "liability"]):
        return "Is mahine abhi tak koi invoice upload nahi hua.\nInvoice ki photo bhejiye!"
    elif any(w in body_lower for w in ["deadline", "date", "last date", "due"]):
        from app.services.compliance_engine import get_filing_deadlines
        from datetime import datetime
        period = datetime.now().strftime("%Y-%m")
        deadlines = get_filing_deadlines(period)
        return (
            f"Filing Deadlines:\n"
            f"GSTR-1: {deadlines['gstr1_deadline']} ({deadlines['days_to_gstr1']} din baaki)\n"
            f"GSTR-3B: {deadlines['gstr3b_deadline']} ({deadlines['days_to_gstr3b']} din baaki)"
        )
    else:
        return "'hello' likhiye shuru karne ke liye\nYa invoice ki photo bhejiye!"


def apply_field_edit(sender: str, field_name: str, new_value: str) -> str:
    session = PENDING_CONFIRMATIONS[sender]
    fields  = session["fields"]
    session["awaiting_edit"] = None

    amount_fields = ["taxable_amount", "cgst", "sgst", "igst", "total_amount"]
    if field_name in amount_fields:
        try:
            cleaned = new_value.replace("rs", "").replace("Rs", "").replace(",", "").strip()
            new_value = float(cleaned)
        except ValueError:
            return f"'{new_value}' valid amount nahi hai. Sirf number enter karein, jaise: 700"

    fields[field_name] = {"value": new_value, "confidence": 1.0}
    print(f"✏️  Field edited: {field_name} = {new_value}")

    gstin_status = ""
    if fields["seller_gstin"]["value"]:
        from app.services.gstin_validator import validate_gstin
        validation = validate_gstin(fields["seller_gstin"]["value"])
        gstin_status = f"Valid ({validation['state_name']})" if validation["is_valid"] else "Invalid GSTIN - ITC risk!"

    label = FIELD_LABELS[field_name]
    msg  = f"{label} update ho gaya: {new_value}\n\n"
    msg += build_confirmation_message(fields, gstin_status)
    return msg


def process_confirmed_invoice(sender: str) -> str:
    if sender not in PENDING_CONFIRMATIONS:
        return "Koi pending invoice nahi hai. Photo bhejiye!"

    data   = PENDING_CONFIRMATIONS.pop(sender)
    fields = data["fields"]

    # Fix: inter-state (IGST only) vs intra-state (CGST + SGST)
    igst = fields["igst"]["value"] or 0
    cgst = fields["cgst"]["value"] or 0
    sgst = fields["sgst"]["value"] or 0

    if igst > 0:
        total_tax = igst           # inter-state transaction — IGST only
        tax_type  = f"IGST: Rs.{igst}"
    else:
        total_tax = cgst + sgst    # intra-state transaction
        tax_type  = f"CGST: Rs.{cgst} + SGST: Rs.{sgst}"

    from app.services.invoice_service import save_invoice
    from app.services.classification_service import classify_invoice

    classification = classify_invoice(fields)
    db_result = save_invoice(sender, fields)

    msg = "Invoice save ho gayi! ✅\n\n"
    if fields["invoice_no"]["value"]:
        msg += f"Invoice: {fields['invoice_no']['value']}\n"
    if fields["invoice_date"]["value"]:
        msg += f"Date: {fields['invoice_date']['value']}\n"
    if fields["total_amount"]["value"]:
        msg += f"Total: Rs.{fields['total_amount']['value']}\n"
    if total_tax > 0:
        msg += f"\n💰 ITC Mila: Rs.{round(total_tax, 2)} ({tax_type})\n"
    if db_result.get("success"):
        msg += f"📊 Is Mahine Ka Total ITC: Rs.{db_result['itc_total']}\n"
        msg += f"📄 Invoice ID: #{db_result['invoice_id']}\n"
    else:
        msg += f"\n⚠️ DB save mein error: {db_result.get('error', 'unknown')}\n"

    msg += f"\n🧠 AI Analysis:\n"
    msg += f"Category: {classification['category']}\n"
    if classification.get('itc_blocked') and classification.get('itc_blocked') > 0:
        msg += f"⚠️ ITC BLOCKED: Rs.{classification['itc_blocked']}\n"
        msg += f"Reason: {classification['reason']}\n"
    else:
        msg += f"✅ ITC Eligible: Rs.{classification['itc_eligible']}\n"

    msg += "\nAur invoices bhejte rahein! 📄"
    return msg