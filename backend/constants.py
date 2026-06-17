import os


REVOLUT_CLIENT_ID = os.getenv("REVOLUT_CLIENT_ID", "05f4b015-b95a-423b-a7c8-c4e33c17b97d")
REVOLUT_AUTH_URL = "https://sandbox-oba.revolut.com/ui/index.html"
REVOLUT_TOKEN_URL = "https://sandbox-oba.revolut.com/token"
REVOLUT_API_BASE = "https://sandbox-oba.revolut.com"
REVOLUT_REDIRECT_FALLBACK = os.getenv("REVOLUT_REDIRECT_URI", "")

PROFILES = ("balanced", "aggressive", "ethical", "mindful", "savings_beast")
ETHICAL_PENALTY_CATS = {"Fast Food", "Clothes", "Entertainment", "Ethical Penalty"}
SAVINGS_BEAST_TRIGGER_AMOUNT = 5.00

DEST_TYPES = ("external_iban", "revolut_pocket")
FREQUENCIES = ("instant", "daily", "weekly")
TRANSFER_STATUSES = ("pending", "executed", "failed", "requires_review")

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

DEFAULT_CATEGORIES = [
    {"name": "Coffee", "icon": "coffee", "tax_rate": 0.25,
     "merchant_keywords": ["starbucks", "coffee", "café", "costa", "pret", "tim hortons"],
     "rep_increment": 0.05, "max_tax_rate": 0.50, "daily_cap_amount": 10.0},
    {"name": "Fast Food", "icon": "utensils", "tax_rate": 0.30,
     "merchant_keywords": ["mcdonalds", "burger king", "kfc", "subway", "five guys",
                           "uber eats", "deliveroo", "just eat"],
     "rep_increment": 0.05, "max_tax_rate": 0.50, "daily_cap_amount": 15.0},
    {"name": "Groceries", "icon": "shopping-cart", "tax_rate": 0.05,
     "merchant_keywords": ["carrefour", "aldi", "lidl", "delhaize", "colruyt",
                           "cactus", "match"],
     "rep_increment": 0.02, "max_tax_rate": 0.20, "daily_cap_amount": 20.0},
    {"name": "Clothes", "icon": "shopping-bag", "tax_rate": 0.15,
     "merchant_keywords": ["zara", "h&m", "primark", "uniqlo", "asos", "mango"],
     "rep_increment": 0.05, "max_tax_rate": 0.50, "daily_cap_amount": 25.0},
    {"name": "Entertainment", "icon": "film", "tax_rate": 0.20,
     "merchant_keywords": ["netflix", "spotify", "steam", "cinema", "ticketmaster"],
     "rep_increment": 0.05, "max_tax_rate": 0.50, "daily_cap_amount": 15.0},
    {"name": "Transport", "icon": "car", "tax_rate": 0.10,
     "merchant_keywords": ["uber", "taxi", "stib", "tec", "de lijn", "parking"],
     "rep_increment": 0.03, "max_tax_rate": 0.30, "daily_cap_amount": 10.0},
    {"name": "Other", "icon": "tag", "tax_rate": 0.10,
     "merchant_keywords": [],
     "rep_increment": 0.05, "max_tax_rate": 0.50, "daily_cap_amount": 10.0},
    {"name": "Ethical Penalty", "icon": "alert-triangle", "tax_rate": 0.35,
     "merchant_keywords": ["amazon", "mcdonalds", "kfc", "primark", "h&m",
                           "coca-cola", "pepsi", "nestlé", "monsanto", "shein"],
     "rep_increment": 0.05, "max_tax_rate": 0.70, "daily_cap_amount": 20.0},
]
