import requests
import os
from dotenv import load_dotenv

load_dotenv()

HF_API_KEY = os.getenv("HF_API_KEY")

# Map your trained model's categories to GST ITC rules
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


def classify_invoice_description(description: str) -> dict:
    if not description or len(description.strip()) < 3:
        return {"category": "Other", "confidence": 0, "itc_blocked": False, "reason": "No description"}

    print(f"🧠 Classifying with VyapaarBandhu model: {description[:80]}")

    headers = {
        "Authorization": f"Bearer {HF_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            "https://router.huggingface.co/hf-inference/models/meet136/indicbert-gst-classifier",
            headers=headers,
            json={"inputs": description},
            timeout=30
        )

        print(f"📥 Model status: {response.status_code}")

        if response.status_code == 503:
            print("⏳ Model loading, using keyword fallback...")
            return classify_with_keywords(description)

        if response.status_code != 200:
            print(f"❌ Model error: {response.text[:200]}")
            return classify_with_keywords(description)

        result = response.json()

        if isinstance(result, list) and len(result) > 0:
            items = result[0] if isinstance(result[0], list) else result
            top = max(items, key=lambda x: x["score"])
            top_label = top["label"]
            top_score = top["score"]
        else:
            return classify_with_keywords(description)

        # If model confidence is low, fall back to keywords
        if top_score < 0.6:
            print(f"⚠️ Low confidence ({top_score:.2f}), using keyword fallback...")
            return classify_with_keywords(description)

        category_info = CATEGORY_MAP.get(top_label, CATEGORY_MAP["Other"])
        print(f"✅ Category: {top_label} | Score: {top_score:.2f} | Blocked: {category_info['blocked']}")

        return {
            "category":    top_label,
            "confidence":  round(top_score, 3),
            "itc_blocked": category_info["blocked"],
            "reason":      category_info["reason"],
            "all_scores":  {item["label"]: round(item["score"], 3) for item in items[:3]}
        }

    except Exception as e:
        print(f"❌ Classification error: {e}")
        return classify_with_keywords(description)


def classify_with_keywords(description: str) -> dict:
    desc = description.lower()

    rules = [

        # ── ELECTRONICS ──────────────────────────────────────────────────────
        ([
            # Brands
            "dell", "hp", "lenovo", "asus", "acer", "apple", "samsung", "sony",
            "lg", "mi", "xiaomi", "oneplus", "realme", "oppo", "vivo", "nokia",
            "motorola", "redmi", "poco", "iqoo", "nothing", "google pixel",
            "bose", "jbl", "boat", "zebronics", "intex", "micromax", "lava",
            "panasonic", "philips", "whirlpool", "bosch", "siemens", "godrej",
            "voltas", "hitachi", "haier", "tcl", "hisense", "onida",
            # Computers & Peripherals
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
            # Phones & Tablets
            "mobile", "phone", "smartphone", "iphone", "tablet", "ipad",
            "android", "smartwatch", "fitness band",
            # Appliances
            "refrigerator", "fridge", "washing machine", "microwave", "oven",
            "air conditioner", "cooler", "geyser", "water heater",
            "television", "smart tv", "set top box",
            "vacuum cleaner", "iron box", "mixer", "grinder", "juicer",
            "induction", "chimney", "dishwasher",
            # Camera & AV
            "camera", "dslr", "mirrorless", "gopro", "drone", "lens",
            # Tech Services
            "amc", "annual maintenance", "software license", "antivirus",
            "cloud storage", "aws", "azure", "google cloud", "web hosting",
            "domain", "ssl certificate",
        ], "Electronics"),

        # ── FOOD & BEVERAGE ──────────────────────────────────────────────────
        ([
            # Meals
            "lunch", "dinner", "breakfast", "meal", "tiffin", "thali",
            "snack", "nashta", "bhojan", "khana", "khane",
            # Drinks
            "tea", "chai", "coffee", "juice", "cold drink", "beverage",
            "water bottle", "mineral water", "soft drink", "lassi",
            # Restaurants & Delivery
            "restaurant", "cafe", "dhaba", "canteen", "mess",
            "swiggy", "zomato", "food delivery", "catering", "banquet",
            "refreshment",
            # Raw Food Items
            "rice", "wheat", "dal", "flour", "atta", "maida", "besan",
            "oil", "ghee", "butter", "sugar", "salt", "spice", "masala",
            "grocery", "vegetables", "fruits", "dairy", "milk", "paneer",
            "eggs", "chicken", "mutton", "fish", "meat",
            "biscuit", "bread", "cake", "sweets", "mithai", "namkeen",
            "chocolate", "ice cream", "dry fruits", "nuts",
            # Food Brands
            "amul", "nestle", "haldiram", "bikaji", "parle", "britannia",
            "itc foods", "dabur foods", "patanjali", "mdh", "everest",
        ], "Food"),

        # ── VEHICLE ──────────────────────────────────────────────────────────
        ([
            # Vehicle Types
            "car", "bike", "motorcycle", "scooter", "auto rickshaw",
            "truck", "tempo", "van", "tractor", "jeep", "suv",
            "sedan", "hatchback",
            # Brands
            "maruti", "hyundai", "tata motors", "mahindra",
            "honda cars", "toyota", "ford", "volkswagen", "kia", "mg motor",
            "bajaj", "hero motocorp", "tvs motor", "royal enfield", "yamaha",
            "activa", "pulsar", "splendor", "apache",
            # Fuel & Maintenance
            "petrol", "diesel", "cng", "engine oil", "lubricant",
            "tyre", "tire", "car battery", "spare parts", "car accessories",
            "car wash", "vehicle service", "gaadi",
            "motor vehicle",
            # Insurance & Registration
            "vehicle insurance", "car insurance", "bike insurance",
            "rto", "vehicle registration", "fastag",
        ], "Vehicle"),

        # ── TRAVEL & HOTEL ───────────────────────────────────────────────────
        ([
            # Airlines
            "flight", "air ticket", "airline", "indigo", "air india",
            "spicejet", "vistara", "akasa air",
            # Ground Transport
            "train ticket", "railway", "irctc", "bus ticket", "volvo bus",
            "redbus", "cab booking", "ola", "uber", "taxi",
            # Accommodation
            "hotel", "resort", "lodge", "guest house", "oyo", "makemytrip",
            "goibibo", "airbnb", "treebo", "fabhotel",
            "accommodation", "lodging", "room rent",
            # Travel Related
            "travel", "yatra", "tour package", "tourism", "holiday",
            "boarding pass", "passport", "visa fee",
            "travel insurance", "forex", "foreign exchange",
        ], "Travel"),

        # ── PHARMA & MEDICAL ─────────────────────────────────────────────────
        ([
            # Medicines
            "medicine", "capsule", "syrup", "injection",
            "pharmaceutical", "pharma", "generic medicine",
            "dawa", "dawai", "chemist", "medical store", "pharmacy",
            # Medical Services
            "doctor", "hospital", "clinic", "lab test", "blood test",
            "x-ray", "mri", "ct scan", "health checkup", "consultation",
            "surgical", "medical equipment",
            # Medical Supplies
            "glucometer", "bp monitor", "oximeter", "nebulizer",
            "wheelchair", "bandage", "surgical gloves", "mask",
            "sanitizer", "ppe kit",
            # Brands
            "cipla", "sun pharma", "dr reddy", "lupin", "torrent pharma",
            "alkem", "zydus", "mankind pharma", "abbott", "pfizer",
            "1mg", "netmeds", "medplus", "apollo pharmacy",
        ], "Pharma"),

        # ── CLOTHING & APPAREL ───────────────────────────────────────────────
        ([
            # Garments
            "shirt", "trouser", "jeans", "t-shirt", "kurta",
            "saree", "salwar", "dress", "skirt", "jacket", "coat",
            "blazer", "tie", "uniform", "jersey",
            "undergarment", "innerwear", "socks",
            # Fabric & Materials
            "cloth", "fabric", "textile", "cotton fabric", "silk fabric",
            "polyester", "wool", "linen", "denim", "kapda", "kapde",
            # Footwear
            "shoes", "sandal", "chappal", "boots", "sneakers",
            # Accessories
            "purse", "wallet", "belt", "sunglasses",
            "jewellery", "jewelry", "necklace", "ring", "earring",
            # Brands
            "raymond", "peter england", "arrow", "van heusen",
            "allen solly", "louis philippe", "zara", "max fashion",
            "westside", "myntra", "ajio", "bata", "liberty", "woodland",
            "adidas", "nike", "puma", "reebok",
        ], "Clothing"),

        # ── OFFICE & SUPPLIES ────────────────────────────────────────────────
        ([
            # Stationery
            "a4 paper", "bond paper", "pen", "pencil", "marker", "highlighter",
            "stapler", "staple pin", "punch machine", "scissor", "adhesive",
            "file folder", "binder", "register", "notebook", "diary",
            "envelope", "letterhead", "visiting card", "stamp pad",
            # Office Equipment
            "photocopy", "xerox", "lamination", "binding", "shredder",
            "calculator", "whiteboard", "notice board",
            # Furniture
            "office chair", "office table", "workstation desk",
            "filing cabinet", "almirah", "bookshelf", "storage rack", "locker",
            # Cleaning & Housekeeping
            "cleaning supplies", "housekeeping", "mop", "broom", "dustbin",
            "toilet cleaner", "phenyl", "floor cleaner", "detergent",
            # Rent & Utilities
            "office rent", "electricity bill", "water bill",
            "maintenance charges", "society charges",
            # Business Services
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