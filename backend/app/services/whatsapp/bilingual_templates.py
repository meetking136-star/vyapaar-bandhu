"""
VyapaarBandhu -- Bilingual Message Templates (Hindi + English)
Every user-facing message available in both languages.

RULE 2: Hindi + English support. Language detected from first message.
"""
from __future__ import annotations

BILINGUAL_TEMPLATES: dict[str, dict[str, str]] = {
    "consent_request": {
        "en": (
            "Welcome to VyapaarBandhu! To process your invoices, we need your "
            "consent to store your data as per DPDP Act 2023. Reply YES to "
            "consent or NO to decline."
        ),
        "hi": (
            "VyapaarBandhu \u092e\u0947\u0902 \u0906\u092a\u0915\u093e "
            "\u0938\u094d\u0935\u093e\u0917\u0924 \u0939\u0948! "
            "\u0906\u092a\u0915\u0947 \u091a\u093e\u0932\u093e\u0928 "
            "\u0938\u0902\u0938\u093e\u0927\u093f\u0924 \u0915\u0930\u0928\u0947 "
            "\u0915\u0947 \u0932\u093f\u090f, \u0939\u092e\u0947\u0902 DPDP "
            "\u0905\u0927\u093f\u0928\u093f\u092f\u092e 2023 \u0915\u0947 "
            "\u0905\u0928\u0941\u0938\u093e\u0930 \u0906\u092a\u0915\u093e "
            "\u0921\u0947\u091f\u093e \u0938\u0902\u0917\u094d\u0930\u0939\u0940\u0924 "
            "\u0915\u0930\u0928\u0947 \u0915\u0940 \u0938\u0939\u092e\u0924\u093f "
            "\u091a\u093e\u0939\u093f\u090f\u0964 "
            "\u0938\u0939\u092e\u0924\u093f \u0915\u0947 \u0932\u093f\u090f YES "
            "\u0914\u0930 \u0905\u0938\u094d\u0935\u0940\u0915\u093e\u0930 "
            "\u0915\u0947 \u0932\u093f\u090f NO \u0932\u093f\u0916\u0947\u0902\u0964"
        ),
    },
    "consent_given": {
        "en": (
            "Thank you! Your consent has been recorded. "
            "You can now send invoice photos for processing. "
            "Send an image to get started!"
        ),
        "hi": (
            "\u0927\u0928\u094d\u092f\u0935\u093e\u0926! "
            "\u0906\u092a\u0915\u0940 \u0938\u0939\u092e\u0924\u093f "
            "\u0926\u0930\u094d\u091c \u0939\u094b \u0917\u0908 \u0939\u0948\u0964 "
            "\u0905\u092c \u0906\u092a \u091a\u093e\u0932\u093e\u0928 "
            "\u0915\u0940 \u092b\u094b\u091f\u094b \u092d\u0947\u091c "
            "\u0938\u0915\u0924\u0947 \u0939\u0948\u0902\u0964 "
            "\u0936\u0941\u0930\u0942 \u0915\u0930\u0928\u0947 \u0915\u0947 "
            "\u0932\u093f\u090f \u090f\u0915 \u092b\u094b\u091f\u094b "
            "\u092d\u0947\u091c\u093f\u090f!"
        ),
    },
    "consent_denied": {
        "en": (
            "OK, your data will not be processed. "
            "Contact your CA if you change your mind later."
        ),
        "hi": (
            "\u0920\u0940\u0915 \u0939\u0948\u0964 "
            "\u0906\u092a\u0915\u093e \u0921\u0947\u091f\u093e "
            "\u092a\u094d\u0930\u094b\u0938\u0947\u0938 \u0928\u0939\u0940\u0902 "
            "\u0915\u093f\u092f\u093e \u091c\u093e\u090f\u0917\u093e\u0964 "
            "\u092c\u093e\u0926 \u092e\u0947\u0902 \u0909\u092a\u092f\u094b\u0917 "
            "\u0915\u0930\u0928\u093e \u0939\u094b \u0924\u094b \u0905\u092a\u0928\u0947 "
            "CA \u0938\u0947 \u0938\u0902\u092a\u0930\u094d\u0915 \u0915\u0930\u0947\u0902\u0964"
        ),
    },
    "invoice_received": {
        "en": "Invoice received. Processing now...",
        "hi": "\u091a\u093e\u0932\u093e\u0928 \u092a\u094d\u0930\u093e\u092a\u094d\u0924 \u0939\u0941\u0906\u0964 \u0905\u092d\u0940 \u0938\u0902\u0938\u093e\u0927\u093f\u0924 \u0939\u094b \u0930\u0939\u093e \u0939\u0948...",
    },
    "ocr_success": {
        "en": "Invoice processed. GSTIN: {gstin}, Amount: \u20b9{amount}",
        "hi": "\u091a\u093e\u0932\u093e\u0928 \u0938\u0902\u0938\u093e\u0927\u093f\u0924\u0964 GSTIN: {gstin}, \u0930\u093e\u0936\u093f: \u20b9{amount}",
    },
    "ocr_low_confidence": {
        "en": "Image unclear. Please resend a clearer photo.",
        "hi": "\u091b\u0935\u093f \u0905\u0938\u094d\u092a\u0937\u094d\u091f \u0939\u0948\u0964 \u0915\u0943\u092a\u092f\u093e \u0938\u094d\u092a\u0937\u094d\u091f \u092b\u094b\u091f\u094b \u092d\u0947\u091c\u0947\u0902\u0964",
    },
    "ocr_failed": {
        "en": "Could not read invoice. Please send a clearer photo.",
        "hi": "\u091a\u093e\u0932\u093e\u0928 \u092a\u0922\u093c \u0928\u0939\u0940\u0902 \u092a\u093e\u0908\u0964 \u0915\u0943\u092a\u092f\u093e \u0938\u094d\u092a\u0937\u094d\u091f \u092b\u094b\u091f\u094b \u092d\u0947\u091c\u0947\u0902\u0964",
    },
    "deadline_reminder": {
        "en": "GSTR-3B deadline in {days} days. {count} invoices pending.",
        "hi": "GSTR-3B \u0915\u0940 \u0905\u0902\u0924\u093f\u092e \u0924\u093f\u0925\u093f {days} \u0926\u093f\u0928 \u092e\u0947\u0902\u0964 {count} \u091a\u093e\u0932\u093e\u0928 \u0932\u0902\u092c\u093f\u0924\u0964",
    },
    "send_invoice_image": {
        "en": "Please send a photo of the invoice you want to process.",
        "hi": "\u0915\u0943\u092a\u092f\u093e \u091c\u093f\u0938 \u091a\u093e\u0932\u093e\u0928 \u0915\u094b \u092a\u094d\u0930\u094b\u0938\u0947\u0938 \u0915\u0930\u0928\u093e \u0939\u0948 \u0909\u0938\u0915\u0940 \u092b\u094b\u091f\u094b \u092d\u0947\u091c\u0947\u0902\u0964",
    },
    "status_check": {
        "en": "Checking your invoice status... Your CA will review processed invoices.",
        "hi": "\u0906\u092a\u0915\u0947 \u091a\u093e\u0932\u093e\u0928 \u0915\u0940 \u0938\u094d\u0925\u093f\u0924\u093f \u091c\u093e\u0901\u091a \u0930\u0939\u0947 \u0939\u0948\u0902... \u0906\u092a\u0915\u0947 CA \u092a\u094d\u0930\u094b\u0938\u0947\u0938\u094d\u0921 \u091a\u093e\u0932\u093e\u0928 \u0915\u0940 \u0938\u092e\u0940\u0915\u094d\u0937\u093e \u0915\u0930\u0947\u0902\u0917\u0947\u0964",
    },
    "still_processing": {
        "en": "Your invoice is still being processed. Please wait a moment.",
        "hi": "\u0906\u092a\u0915\u093e \u091a\u093e\u0932\u093e\u0928 \u0905\u092d\u0940 \u092a\u094d\u0930\u094b\u0938\u0947\u0938 \u0939\u094b \u0930\u0939\u093e \u0939\u0948\u0964 \u0915\u0943\u092a\u092f\u093e \u0925\u094b\u0921\u093c\u093e \u0907\u0902\u0924\u091c\u093e\u0930 \u0915\u0930\u0947\u0902\u0964",
    },
    "help": {
        "en": (
            "You can:\n"
            "- Send an invoice photo to process it\n"
            "- Type 'invoice' to start upload\n"
            "- Type 'status' to check processing status\n"
            "- Type 'stop' to cancel current operation\n"
            "- Type 'help' to see this message"
        ),
        "hi": (
            "\u0906\u092a \u092f\u0947 \u0915\u0930 \u0938\u0915\u0924\u0947 \u0939\u0948\u0902:\n"
            "- \u091a\u093e\u0932\u093e\u0928 \u0915\u0940 \u092b\u094b\u091f\u094b \u092d\u0947\u091c\u0947\u0902\n"
            "- 'invoice' \u091f\u093e\u0907\u092a \u0915\u0930\u0947\u0902 \u0905\u092a\u0932\u094b\u0921 \u0936\u0941\u0930\u0942 \u0915\u0930\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f\n"
            "- 'status' \u091f\u093e\u0907\u092a \u0915\u0930\u0947\u0902 \u0938\u094d\u0925\u093f\u0924\u093f \u091c\u093e\u0928\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f\n"
            "- 'stop' \u091f\u093e\u0907\u092a \u0915\u0930\u0947\u0902 \u0930\u0926\u094d\u0926 \u0915\u0930\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f\n"
            "- 'help' \u091f\u093e\u0907\u092a \u0915\u0930\u0947\u0902 \u092f\u0939 \u0938\u0902\u0926\u0947\u0936 \u0926\u0947\u0916\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f"
        ),
    },
    "cancelled": {
        "en": "Operation cancelled.",
        "hi": "\u0911\u092a\u0930\u0947\u0936\u0928 \u0930\u0926\u094d\u0926 \u0915\u093f\u092f\u093e \u0917\u092f\u093e\u0964",
    },
    "consent_withdrawn": {
        "en": "Your consent has been withdrawn. Your data will be retained per legal requirements but not processed further.",
        "hi": "\u0906\u092a\u0915\u0940 \u0938\u0939\u092e\u0924\u093f \u0935\u093e\u092a\u0938 \u0932\u0947 \u0932\u0940 \u0917\u0908 \u0939\u0948\u0964 \u0915\u093e\u0928\u0942\u0928\u0940 \u0906\u0935\u0936\u094d\u092f\u0915\u0924\u093e\u0913\u0902 \u0915\u0947 \u0905\u0928\u0941\u0938\u093e\u0930 \u0906\u092a\u0915\u093e \u0921\u0947\u091f\u093e \u0930\u0916\u093e \u091c\u093e\u090f\u0917\u093e \u0932\u0947\u0915\u093f\u0928 \u0906\u0917\u0947 \u092a\u094d\u0930\u094b\u0938\u0947\u0938 \u0928\u0939\u0940\u0902 \u0939\u094b\u0917\u093e\u0964",
    },
    "media_timeout": {
        "en": "Image download timed out. Please resend the photo.",
        "hi": "\u092b\u094b\u091f\u094b \u0921\u093e\u0909\u0928\u0932\u094b\u0921 \u0938\u092e\u092f \u0938\u0940\u092e\u093e \u092a\u093e\u0930\u0964 \u0915\u0943\u092a\u092f\u093e \u092b\u094b\u091f\u094b \u0926\u094b\u092c\u093e\u0930\u093e \u092d\u0947\u091c\u0947\u0902\u0964",
    },
    "not_registered": {
        "en": "Your number is not registered. Please contact your CA about VyapaarBandhu.",
        "hi": "\u0906\u092a\u0915\u093e \u0928\u0902\u092c\u0930 \u0930\u091c\u093f\u0938\u094d\u091f\u0930\u094d\u0921 \u0928\u0939\u0940\u0902 \u0939\u0948\u0964 \u0915\u0943\u092a\u092f\u093e \u0905\u092a\u0928\u0947 CA \u0938\u0947 VyapaarBandhu \u0915\u0947 \u092c\u093e\u0930\u0947 \u092e\u0947\u0902 \u092a\u0942\u091b\u0947\u0902\u0964",
    },
}
