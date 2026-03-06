import requests
import base64
import os
import re
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY")
VISION_API_URL = f"https://vision.googleapis.com/v1/images:annotate?key={VISION_API_KEY}"


def extract_text_from_image_url(image_url: str, twilio_sid: str, twilio_token: str) -> dict:

    print(f"🔍 Downloading from: {image_url}")
    response = requests.get(image_url, auth=(twilio_sid, twilio_token))
    print(f"📥 Download status: {response.status_code}")

    if response.status_code != 200:
        print(f"❌ Download failed: {response.text[:200]}")
        return {"success": False, "error": f"Download failed: {response.status_code}"}

    print(f"✅ Image downloaded: {len(response.content)} bytes")

    image_base64 = base64.b64encode(response.content).decode("utf-8")

    payload = {
        "requests": [{
            "image": {"content": image_base64},
            "features": [
                {"type": "TEXT_DETECTION", "maxResults": 1},
                {"type": "DOCUMENT_TEXT_DETECTION", "maxResults": 1}
            ]
        }]
    }

    print(f"🔍 Calling Google Vision...")
    vision_response = requests.post(VISION_API_URL, json=payload)
    print(f"📥 Vision status: {vision_response.status_code}")

    if vision_response.status_code != 200:
        print(f"❌ Vision failed: {vision_response.text[:200]}")
        return {"success": False, "error": "Google Vision API call failed"}

    result = vision_response.json()
    print(f"✅ Vision response received")

    try:
        full_text = result["responses"][0]["fullTextAnnotation"]["text"]
        print(f"📝 Extracted {len(full_text)} chars")
        return {"success": True, "full_text": full_text, "raw_response": result}
    except (KeyError, IndexError) as e:
        print(f"❌ Parse error: {e}")
        return {"success": False, "error": "No text found in image"}


def parse_invoice_fields(full_text: str) -> dict:

    print(f"🤖 Sending OCR text to Claude for extraction...")

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"""Extract invoice fields from this OCR text. Return ONLY valid JSON, nothing else. No explanation, no markdown, just the JSON object.

OCR TEXT:
{full_text}

Return exactly this JSON structure (use null for missing fields, numbers for amounts):
{{
  "seller_gstin": "15-char GSTIN or null",
  "invoice_no": "invoice number or null",
  "invoice_date": "date or null",
  "taxable_amount": number or null,
  "cgst": number or null,
  "sgst": number or null,
  "igst": number or null,
  "total_amount": number or null
}}"""
        }]
    )

    raw = response.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    print(f"🤖 Claude response: {raw}")

    try:
        extracted = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}")
        # Return empty fields on failure
        extracted = {
            "seller_gstin": None, "invoice_no": None, "invoice_date": None,
            "taxable_amount": None, "cgst": None, "sgst": None,
            "igst": None, "total_amount": None
        }

    fields = {k: {"value": v, "confidence": 0.90 if v is not None else 0} for k, v in extracted.items()}
    filled = [f for f in fields.values() if f["value"] is not None]
    avg_confidence = sum(f["confidence"] for f in filled) / len(filled) if filled else 0

    print(f"📊 Parsed fields: {[(k, v['value']) for k, v in fields.items() if v['value']]}")
    print(f"📊 Confidence: {avg_confidence:.2f} | Filled: {len(filled)}/{len(fields)}")

    return {
        "fields": fields,
        "overall_confidence": round(avg_confidence, 2),
        "needs_confirmation": avg_confidence < 0.80,
        "filled_count": len(filled),
        "total_fields": len(fields)
    }