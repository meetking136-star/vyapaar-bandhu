from fastapi import APIRouter, Request, Form
from fastapi.responses import PlainTextResponse
from twilio.twiml.messaging_response import MessagingResponse
import os

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])


@router.post("/webhook")
async def whatsapp_webhook(
    request: Request,
    Body: str = Form(default=""),
    From: str = Form(default=""),
    NumMedia: str = Form(default="0"),
    MediaUrl0: str = Form(default=""),
    MediaContentType0: str = Form(default=""),
):
    """
    This is the endpoint Twilio calls every time
    Rameshbhai sends a WhatsApp message.
    
    Twilio sends form data with:
    - Body: text message content
    - From: sender's WhatsApp number
    - NumMedia: number of images/files attached
    - MediaUrl0: URL of first attached image
    """
    
    print(f"📱 Message from: {From}")
    print(f"📝 Body: {Body}")
    print(f"🖼️  Media count: {NumMedia}")
    
    # Detect message type
    if int(NumMedia) > 0 and "image" in MediaContentType0:
        message_type = "image"
    elif Body:
        message_type = "text"
    else:
        message_type = "unknown"
    
    print(f"📌 Type: {message_type}")
    
    # Route to correct handler
    if message_type == "image":
        reply = handle_image(MediaUrl0, From)
    elif message_type == "text":
        reply = handle_text(Body, From)
    else:
        reply = "Kripya ek message ya photo bhejiye."
    
    # Send reply back via Twilio
    response = MessagingResponse()
    response.message(reply)
    return PlainTextResponse(str(response), media_type="application/xml")


def handle_text(body: str, sender: str) -> str:
    """Handle text messages"""
    body_lower = body.lower().strip()
    
    if any(word in body_lower for word in ["hello", "hi", "namaste", "helo"]):
        return (
            "Namaste! 🙏 VyapaarBandhu mein aapka swagat hai!\n\n"
            "Main aapki GST compliance mein madad kar sakta hoon:\n"
            "1️⃣ Invoice ki photo bhejiye → ITC calculate karunga\n"
            "2️⃣ 'tax' likhiye → is mahine ka GST liability\n"
            "3️⃣ 'deadline' likhiye → filing dates\n\n"
            "Kya karna chahenge?"
        )
    
    elif any(word in body_lower for word in ["tax", "gst", "kitna", "liability"]):
        return (
            "📊 Aapka GST Status:\n"
            "Is mahine abhi tak koi invoice upload nahi hua.\n"
            "Invoice ki photo bhejiye — main turant calculate karunga! 📸"
        )
    
    elif any(word in body_lower for word in ["deadline", "date", "last date", "due"]):
        from app.services.compliance_engine import get_filing_deadlines
        from datetime import datetime
        period = datetime.now().strftime("%Y-%m")
        deadlines = get_filing_deadlines(period)
        return (
            f"📅 Filing Deadlines:\n"
            f"GSTR-1: {deadlines['gstr1_deadline']} "
            f"({deadlines['days_to_gstr1']} din baaki)\n"
            f"GSTR-3B: {deadlines['gstr3b_deadline']} "
            f"({deadlines['days_to_gstr3b']} din baaki)\n\n"
            f"Waqt par file karein — penalty se bachein! ✅"
        )
    
    else:
        return (
            "Samajh nahi aaya. 😊\n"
            "'hello' likhiye shuru karne ke liye\n"
            "Ya invoice ki photo bhejiye!"
        )


def handle_image(media_url: str, sender: str) -> str:
    """Handle image messages — OCR pipeline"""
    from app.services.ocr_service import extract_text_from_image_url, parse_invoice_fields
    from app.services.gstin_validator import validate_gstin

    TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

    ocr_result = extract_text_from_image_url(media_url, TWILIO_SID, TWILIO_TOKEN)

    if not ocr_result["success"]:
        return "Photo padh nahi paya. Dobara try karein — achhi roshni mein photo lein. 📸"

    parsed = parse_invoice_fields(ocr_result["full_text"])
    fields  = parsed["fields"]
    confidence = parsed["overall_confidence"]

    gstin_info = ""
    if fields["seller_gstin"]["value"]:
        validation = validate_gstin(fields["seller_gstin"]["value"])
        if validation["is_valid"]:
            gstin_info = f"Supplier: {validation['state_name']}\n"
        else:
            gstin_info = "Supplier GSTIN: Invalid — ITC risk! ⚠️\n"

    if parsed["needs_confirmation"]:
        msg = "Invoice mil gayi! Kuch details confirm karein:\n\n"
        if fields["seller_gstin"]["value"]:
            msg += f"GSTIN: {fields['seller_gstin']['value']}\n"
        if fields["total_amount"]["value"]:
            msg += f"Total: Rs.{fields['total_amount']['value']}\n"
        if fields["cgst"]["value"]:
            msg += f"CGST: Rs.{fields['cgst']['value']}\n"
        if fields["sgst"]["value"]:
            msg += f"SGST: Rs.{fields['sgst']['value']}\n"
        msg += f"\nConfidence: {int(confidence*100)}%\n"
        msg += "Sahi hai → 'yes' likhein\nGalat hai → photo dobara bhejein"
        return msg

    msg = "Invoice process ho gayi! ✅\n\n"
    msg += gstin_info
    if fields["invoice_no"]["value"]:
        msg += f"Invoice No: {fields['invoice_no']['value']}\n"
    if fields["total_amount"]["value"]:
        msg += f"Total: Rs.{fields['total_amount']['value']}\n"
    if fields["cgst"]["value"]:
        msg += f"CGST: Rs.{fields['cgst']['value']}\n"
    if fields["sgst"]["value"]:
        msg += f"SGST: Rs.{fields['sgst']['value']}\n"

    total_tax = (fields["cgst"]["value"] or 0) + (fields["sgst"]["value"] or 0)
    if total_tax > 0:
        msg += f"\nITC Add Hua: Rs.{total_tax} ✅"

    msg += "\n\nAur invoices bhejte rahein!"
    return msg