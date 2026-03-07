import requests
import base64
import os
import json
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


def extract_text_from_image_url(image_url: str, twilio_sid: str, twilio_token: str) -> dict:

    print(f"🔍 Downloading image...")
    response = requests.get(image_url, auth=(twilio_sid, twilio_token))
    print(f"📥 Download status: {response.status_code}")

    if response.status_code != 200:
        return {"success": False, "error": "Could not download image"}

    print(f"✅ Downloaded: {len(response.content)} bytes")
    image_base64 = base64.b64encode(response.content).decode("utf-8")

    return parse_invoice_with_openrouter(image_base64)


def parse_invoice_with_openrouter(image_base64: str) -> dict:

    print(f"🤖 Sending to OpenRouter VLM...")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://vyapaarbandhu.app",
        "X-Title": "VyapaarBandhu"
    }

    payload = {
        "model": "nvidia/nemotron-nano-12b-v2-vl:free",
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    }
                },
                {
                    "type": "text",
                    "text": """You are an expert at reading Indian GST invoices.
Extract these fields and return ONLY a valid JSON object. No explanation, no markdown, no reasoning.

{
  "seller_gstin": "15-character GSTIN string or null",
  "invoice_no": "invoice number string or null",
  "invoice_date": "date as DD-MM-YYYY string or null",
  "taxable_amount": numeric rupee amount or null,
  "cgst": numeric CGST tax rupee amount (NOT percentage) or null,
  "sgst": numeric SGST tax rupee amount (NOT percentage) or null,
  "igst": numeric IGST tax rupee amount (NOT percentage) or null,
  "total_amount": numeric grand total rupee amount or null
}

Rules:
- GSTIN is always exactly 15 characters
- Extract tax AMOUNTS in rupees, never percentages
- total_amount is the Grand Total
- Return null for missing fields
- Return ONLY the JSON object, nothing else"""
                }
            ]
        }],
        "max_tokens": 3000,
        "temperature": 0,
        "include_reasoning": False,
    }

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=40
        )

        print(f"📥 OpenRouter status: {response.status_code}")

        if response.status_code != 200:
            print(f"❌ Error: {response.text[:300]}")
            return {"success": False, "error": f"OpenRouter error: {response.status_code}"}

        result = response.json()
        content = result["choices"][0]["message"]["content"]

        if content is None:
            print(f"❌ Empty response. Full result: {result}")
            return {"success": False, "error": "Empty response from model"}

        raw = content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        print(f"🤖 Response: {raw}")

        extracted = json.loads(raw)

        fields = {}
        for key in ["seller_gstin", "invoice_no", "invoice_date",
                    "taxable_amount", "cgst", "sgst", "igst", "total_amount"]:
            val = extracted.get(key)
            fields[key] = {"value": val, "confidence": 0.93 if val is not None else 0}

        filled = [f for f in fields.values() if f["value"] is not None]
        avg = sum(f["confidence"] for f in filled) / len(filled) if filled else 0

        print(f"📊 Fields: {[(k, v['value']) for k, v in fields.items() if v['value']]}")
        print(f"📊 Confidence: {avg:.2f} | Filled: {len(filled)}/{len(fields)}")

        return {
            "success": True,
            "fields": fields,
            "overall_confidence": round(avg, 2),
            "needs_confirmation": avg < 0.85,
            "filled_count": len(filled),
            "total_fields": len(fields)
        }

    except json.JSONDecodeError as e:
        print(f"❌ JSON error: {e} | Raw: {raw}")
        return {"success": False, "error": "Could not parse response"}

    except Exception as e:
        print(f"❌ Error: {e}")
        return {"success": False, "error": str(e)}


def parse_invoice_fields(full_text: str) -> dict:
    pass