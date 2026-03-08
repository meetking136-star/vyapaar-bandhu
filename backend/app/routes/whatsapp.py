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
    """Send a WhatsApp message via Twilio REST API."""
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
        # Respond INSTANTLY to Twilio — then process in background thread
        threading.Thread(
            target=process_image_background,
            args=(MediaUrl0, From),
            daemon=True
        ).start()

        # Immediate reply so Twilio gets response in < 1 second
        response = MessagingResponse()
        response.message("Photo mil gayi! Processing kar raha hoon... (10-20 seconds)")
        return PlainTextResponse(str(response), media_type="application/xml")

    elif Body:
        reply = handle_text(Body, From)
    else:
        reply = "Kripya ek message ya photo bhejiye."

    response = MessagingResponse()
    response.message(reply)
    return PlainTextResponse(str(response), media_type="application/xml")


def process_image_background(media_url: str, sender: str):
    """Runs in background thread — does OCR then sends result via Twilio REST API."""
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
            "2. 'tax' likhiye -> GST liability\n"
            "3. 'deadline' likhiye -> filing dates"
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

    total_tax = (
        (fields["cgst"]["value"]  or 0) +
        (fields["sgst"]["value"]  or 0) +
        (fields["igst"]["value"]  or 0)
    )

    # TODO Week 5: save_invoice_to_db(sender, fields)

    msg = "Invoice save ho gayi!\n\n"
    if fields["invoice_no"]["value"]:
        msg += f"Invoice: {fields['invoice_no']['value']}\n"
    if fields["invoice_date"]["value"]:
        msg += f"Date: {fields['invoice_date']['value']}\n"
    if fields["total_amount"]["value"]:
        msg += f"Total: Rs.{fields['total_amount']['value']}\n"
    if total_tax > 0:
        msg += f"\nITC Add Hua: Rs.{total_tax}\nYeh amount aapke GST ledger mein add ho gaya!"
    else:
        msg += "\nNote: Is invoice mein koi ITC eligible tax nahi mila."
    msg += "\n\nAur invoices bhejte rahein!"
    return msg