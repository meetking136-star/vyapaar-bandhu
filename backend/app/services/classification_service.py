import requests
import os
from dotenv import load_dotenv

load_dotenv()

HF_API_KEY = os.getenv("HF_API_KEY")

CATEGORY_MAP = {
    "Food":        {"blocked": True,  "reason": "Section 17(5)(b) — food/beverages"},
    "Vehicle":     {"blocked": True,  "reason": "Section 17(5)(a) — motor vehicle personal use"},
    "Clothing":    {"blocked": True,  "reason": "Section 17(5) — personal use apparel"},
    "Electronics": {"blocked": False, "reason": "Capital goods — fully eligible"},
    "Office":      {"blocked": False, "reason": "Office supplies — fully eligible"},
    "Pharma":      {"blocked": False, "reason": "Business use — eligible"},
    "Travel":      {"blocked": False, "reason": "Business travel — eligible"},
    "Other":       {"blocked": False, "reason": "Verify manually"},
}

# Mapping bart-large-mnli labels to our categories
BART_LABEL_MAP = {
    "Food & Beverage":       "Food",
    "Personal Vehicle":      "Vehicle",
    "Clothing & Apparel":    "Clothing",
    "Electronics":           "Electronics",
    "Office Supplies":       "Office",
    "Pharmaceuticals":       "Pharma",
    "Travel & Hotel":        "Travel",
    "Health & Fitness":      "Other",
    "Club Membership":       "Other",
    "Professional Services": "Office",
    "Raw Materials":         "Office",
    "Furniture":             "Office",
    "Other":                 "Other",
}

BART_CANDIDATE_LABELS = list(BART_LABEL_MAP.keys())


def classify_invoice_description(description: str) -> dict:
    if not description or len(description.strip()) < 3:
        return {"category": "Other", "confidence": 0, "itc_blocked": False, "reason": "No description"}

    # ── LAYER 1: Keywords — fast, deterministic, handles known brands ─────────
    keyword_result = classify_with_keywords(description)
    if keyword_result["category"] != "Other":
        print(f"✅ Layer 1 (keyword): {keyword_result['category']}")
        _log_your_model_prediction(description, keyword_result["category"])
        return keyword_result

    # ── LAYER 2: bart-large-mnli — best zero-shot accuracy ───────────────────
    print(f"🧠 Layer 2 (bart-large-mnli): classifying '{description[:60]}'")
    bart_result = _call_bart(description)
    if bart_result and bart_result["category"] != "Other":
        print(f"✅ Layer 2 (bart): {bart_result['category']} | score: {bart_result['confidence']}")
        _log_your_model_prediction(description, bart_result["category"])
        return bart_result

    # ── LAYER 3: Your fine-tuned model — fallback, improving over time ────────
    print(f"🤖 Layer 3 (meet136/indicbert-gst-classifier): classifying...")
    your_result = _call_your_model(description)
    if your_result:
        print(f"✅ Layer 3 (your model): {your_result['category']} | score: {your_result['confidence']}")
        return your_result

    return {
        "category": "Other", "confidence": 0.5,
        "itc_blocked": False,
        "reason": "Could not classify — verify manually",
        "all_scores": {}
    }


def _call_bart(description: str) -> dict | None:
    """Call facebook/bart-large-mnli for zero-shot classification."""
    headers = {"Authorization": f"Bearer {HF_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "inputs": description,
        "parameters": {"candidate_labels": BART_CANDIDATE_LABELS, "multi_label": False}
    }
    try:
        response = requests.post(
            "https://router.huggingface.co/hf-inference/models/facebook/bart-large-mnli",
            headers=headers, json=payload, timeout=30
        )
        if response.status_code == 503:
            print("⏳ bart-large-mnli loading...")
            return None
        if response.status_code != 200:
            print(f"❌ bart error: {response.text[:100]}")
            return None

        result = response.json()
        top_label = result[0]["label"]
        top_score = result[0]["score"]
        category = BART_LABEL_MAP.get(top_label, "Other")
        category_info = CATEGORY_MAP.get(category, CATEGORY_MAP["Other"])

        return {
            "category":    category,
            "confidence":  round(top_score, 3),
            "itc_blocked": category_info["blocked"],
            "reason":      category_info["reason"],
            "all_scores":  {r["label"]: round(r["score"], 3) for r in result[:3]}
        }
    except Exception as e:
        print(f"❌ bart error: {e}")
        return None


def _call_your_model(description: str) -> dict | None:
    """Call your fine-tuned meet136/indicbert-gst-classifier."""
    headers = {"Authorization": f"Bearer {HF_API_KEY}", "Content-Type": "application/json"}
    try:
        response = requests.post(
            "https://router.huggingface.co/hf-inference/models/meet136/indicbert-gst-classifier",
            headers=headers, json={"inputs": description}, timeout=30
        )
        if response.status_code != 200:
            return None

        result = response.json()
        if isinstance(result, list) and len(result) > 0:
            items = result[0] if isinstance(result[0], list) else result
            top = max(items, key=lambda x: x["score"])
            category_info = CATEGORY_MAP.get(top["label"], CATEGORY_MAP["Other"])
            return {
                "category":    top["label"],
                "confidence":  round(top["score"], 3),
                "itc_blocked": category_info["blocked"],
                "reason":      category_info["reason"],
                "all_scores":  {}
            }
        return None
    except Exception as e:
        print(f"❌ Your model error: {e}")
        return None


def _log_your_model_prediction(description: str, ground_truth: str):
    """
    Run your model silently in background and log prediction vs ground truth.
    This data is used to retrain the model on real invoice descriptions.
    Does NOT affect the classification result.
    """
    import threading
    def _log():
        try:
            headers = {"Authorization": f"Bearer {HF_API_KEY}", "Content-Type": "application/json"}
            response = requests.post(
                "https://router.huggingface.co/hf-inference/models/meet136/indicbert-gst-classifier",
                headers=headers, json={"inputs": description}, timeout=15
            )
            if response.status_code == 200:
                result = response.json()
                items = result[0] if isinstance(result[0], list) else result
                top = max(items, key=lambda x: x["score"])
                match = "✅" if top["label"] == ground_truth else "❌"
                print(f"📊 Model log | predicted={top['label']} | actual={ground_truth} | {match} | score={top['score']:.2f}")
        except Exception:
            pass
    threading.Thread(target=_log, daemon=True).start()


def classify_with_keywords(description: str) -> dict:
    desc = description.lower()

    rules = [

        # ── ELECTRONICS ──────────────────────────────────────────────────────
        ([
            "dell", "hp", "lenovo", "asus", "acer", "apple", "samsung", "sony",
            "lg", "mi", "xiaomi", "oneplus", "realme", "oppo", "vivo", "nokia",
            "motorola", "redmi", "poco", "iqoo", "nothing", "google pixel",
            "bose", "jbl", "boat", "zebronics", "intex", "micromax", "lava",
            "panasonic", "philips", "whirlpool", "bosch", "siemens", "godrej",
            "voltas", "hitachi", "haier", "tcl", "hisense", "onida",
            "laptop", "notebook", "desktop", "computer", "pc", "macbook",
            "imac", "mac mini", "chromebook", "ultrabook", "workstation",
            "inspiron", "thinkpad", "ideapad", "vivobook", "zenbook", "aspire",
            "pavilion", "elitebook", "spectre", "envy", "surface",
            "monitor", "display", "led monitor", "lcd monitor", "curved monitor",
            "keyboard", "mouse", "trackpad", "webcam", "headset", "headphone",
            "earphone", "earbuds", "speaker", "microphone", "printer", "scanner",
            "projector", "router", "modem", "network switch", "hub", "access point",
            "pen drive", "usb drive", "hard disk", "hdd", "ssd", "ram", "memory",
            "processor", "cpu", "gpu", "graphics card", "motherboard", "smps",
            "ups", "inverter battery", "stabilizer", "extension board",
            "hdmi", "charger", "adapter", "power bank",
            "mobile", "phone", "smartphone", "iphone", "tablet", "ipad",
            "android", "smartwatch", "fitness band",
            "refrigerator", "fridge", "washing machine", "microwave", "oven",
            "air conditioner", "cooler", "geyser", "water heater",
            "television", "smart tv", "set top box",
            "vacuum cleaner", "iron box", "mixer", "grinder", "juicer",
            "induction", "chimney", "dishwasher",
            "camera", "dslr", "mirrorless", "gopro", "drone", "lens",
            "amc", "annual maintenance", "software license", "antivirus",
            "cloud storage", "aws", "azure", "google cloud", "web hosting",
            "domain", "ssl certificate",
        ], "Electronics"),

        # ── FOOD & BEVERAGE ──────────────────────────────────────────────────
        ([
            "lunch", "dinner", "breakfast", "meal", "tiffin", "thali",
            "snack", "nashta", "bhojan", "khana", "khane",
            "tea", "chai", "coffee", "juice", "cold drink", "beverage",
            "water bottle", "mineral water", "soft drink", "lassi",
            "restaurant", "cafe", "dhaba", "canteen", "mess",
            "swiggy", "zomato", "food delivery", "catering", "banquet", "refreshment",
            "rice", "wheat", "dal", "flour", "atta", "maida", "besan",
            "oil", "ghee", "butter", "sugar", "salt", "spice", "masala",
            "grocery", "vegetables", "fruits", "dairy", "milk", "paneer",
            "eggs", "chicken", "mutton", "fish", "meat",
            "biscuit", "bread", "cake", "sweets", "mithai", "namkeen",
            "chocolate", "ice cream", "dry fruits", "nuts",
            "amul", "nestle", "haldiram", "bikaji", "parle", "britannia",
            "patanjali", "mdh", "everest",
        ], "Food"),

        # ── VEHICLE ──────────────────────────────────────────────────────────
        ([
            "car", "bike", "motorcycle", "scooter", "auto rickshaw",
            "truck", "tempo", "van", "tractor", "jeep", "suv", "sedan", "hatchback",
            "maruti", "hyundai", "tata motors", "mahindra",
            "honda cars", "toyota", "ford", "volkswagen", "kia", "mg motor",
            "bajaj", "hero motocorp", "tvs motor", "royal enfield", "yamaha",
            "activa", "pulsar", "splendor", "apache",
            "petrol", "diesel", "cng", "engine oil", "lubricant",
            "tyre", "tire", "car battery", "spare parts", "car accessories",
            "car wash", "vehicle service", "gaadi", "motor vehicle",
            "vehicle insurance", "car insurance", "bike insurance",
            "rto", "vehicle registration", "fastag",
        ], "Vehicle"),

        # ── TRAVEL & HOTEL ───────────────────────────────────────────────────
        ([
            "flight", "air ticket", "airline", "indigo", "air india",
            "spicejet", "vistara", "akasa air",
            "train ticket", "railway", "irctc", "bus ticket", "volvo bus",
            "redbus", "cab booking", "ola", "uber", "taxi",
            "hotel", "resort", "lodge", "guest house", "oyo", "makemytrip",
            "goibibo", "airbnb", "treebo", "fabhotel",
            "accommodation", "lodging", "room rent",
            "travel", "yatra", "tour package", "tourism", "holiday",
            "boarding pass", "passport", "visa fee",
            "travel insurance", "forex", "foreign exchange",
        ], "Travel"),

        # ── PHARMA & MEDICAL ─────────────────────────────────────────────────
        ([
            "medicine", "capsule", "syrup", "injection",
            "pharmaceutical", "pharma", "generic medicine",
            "dawa", "dawai", "chemist", "medical store", "pharmacy",
            "doctor", "hospital", "clinic", "lab test", "blood test",
            "x-ray", "mri", "ct scan", "health checkup", "consultation",
            "surgical", "medical equipment",
            "glucometer", "bp monitor", "oximeter", "nebulizer",
            "bandage", "surgical gloves", "sanitizer", "ppe kit",
            "cipla", "sun pharma", "dr reddy", "lupin", "torrent pharma",
            "alkem", "zydus", "mankind pharma", "abbott", "pfizer",
            "1mg", "netmeds", "medplus", "apollo pharmacy",
        ], "Pharma"),

        # ── CLOTHING & APPAREL ───────────────────────────────────────────────
        ([
            "shirt", "trouser", "jeans", "t-shirt", "kurta",
            "saree", "salwar", "dress", "skirt", "jacket", "coat",
            "blazer", "tie", "uniform", "jersey",
            "undergarment", "innerwear", "socks",
            "cloth", "fabric", "textile", "cotton fabric", "silk fabric",
            "polyester", "wool", "linen", "denim", "kapda", "kapde",
            "shoes", "sandal", "chappal", "boots", "sneakers",
            "purse", "wallet", "belt", "sunglasses",
            "jewellery", "jewelry", "necklace", "ring", "earring",
            "raymond", "peter england", "arrow", "van heusen",
            "allen solly", "louis philippe", "zara", "max fashion",
            "westside", "myntra", "ajio", "bata", "liberty", "woodland",
            "adidas", "nike", "puma", "reebok",
        ], "Clothing"),

        # ── OFFICE & SUPPLIES ────────────────────────────────────────────────
        ([
            "a4 paper", "bond paper", "pen", "pencil", "marker", "highlighter",
            "stapler", "staple pin", "punch machine", "scissor", "adhesive",
            "file folder", "binder", "register", "notebook", "diary",
            "envelope", "letterhead", "visiting card", "stamp pad",
            "photocopy", "xerox", "lamination", "binding", "shredder",
            "calculator", "whiteboard", "notice board",
            "office chair", "office table", "workstation desk",
            "filing cabinet", "almirah", "bookshelf", "storage rack", "locker",
            "cleaning supplies", "housekeeping", "mop", "broom", "dustbin",
            "toilet cleaner", "phenyl", "floor cleaner", "detergent",
            "office rent", "electricity bill", "water bill",
            "maintenance charges", "society charges",
            "courier", "dtdc", "bluedart", "delhivery", "fedex", "ecom express",
            "printing charges", "packaging material", "carton box",
            "advertisement", "banner", "flex printing",
            "signboard", "branding", "graphic design",
        ], "Office"),

    ]

    for keywords, category in rules:
        if any(kw in desc for kw in keywords):
            info = CATEGORY_MAP.get(category, {"blocked": False, "reason": "Verify manually"})
            return {
                "category":    category,
                "confidence":  0.85,
                "itc_blocked": info["blocked"],
                "reason":      info["reason"] + " (keyword match)",
                "all_scores":  {}
            }

    return {
        "category":    "Other",
        "confidence":  0.60,
        "itc_blocked": False,
        "reason":      "Could not classify — verify manually",
        "all_scores":  {}
    }


def classify_invoice(invoice_fields: dict) -> dict:
    description = (
        invoice_fields.get("description", {}).get("value") or
        invoice_fields.get("item_name", {}).get("value") or
        invoice_fields.get("product", {}).get("value") or
        "Business purchase invoice"
    )

    result = classify_invoice_description(description)

    # Fix: inter-state (IGST only) vs intra-state (CGST + SGST)
    igst = invoice_fields.get("igst", {}).get("value") or 0
    cgst = invoice_fields.get("cgst", {}).get("value") or 0
    sgst = invoice_fields.get("sgst", {}).get("value") or 0

    if igst > 0:
        total_tax = igst          # inter-state transaction
    else:
        total_tax = cgst + sgst   # intra-state transaction

    itc_eligible = 0 if result["itc_blocked"] else total_tax
    itc_blocked  = total_tax if result["itc_blocked"] else 0

    result["total_tax"]    = round(total_tax, 2)
    result["itc_eligible"] = round(itc_eligible, 2)
    result["itc_blocked"]  = round(itc_blocked, 2)

    return result