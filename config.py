SEARCH_QUERIES = [
    # Construction subcontractors
    {"query": "plasterers Melbourne", "category": "Construction – Plasterers"},
    {"query": "tilers Melbourne", "category": "Construction – Tilers"},
    {"query": "concreters Melbourne", "category": "Construction – Concreters"},
    {"query": "roofers Melbourne", "category": "Construction – Roofers"},
    {"query": "painters Melbourne", "category": "Construction – Painters"},
    {"query": "scaffolding company Melbourne", "category": "Construction – Scaffolding"},

    # Allied health
    {"query": "physiotherapy clinic Melbourne", "category": "Allied Health – Physio"},
    {"query": "chiropractic clinic Melbourne", "category": "Allied Health – Chiro"},
    {"query": "podiatrist Melbourne", "category": "Allied Health – Podiatry"},
    {"query": "psychologist Melbourne", "category": "Allied Health – Psychology"},
    {"query": "dentist Melbourne", "category": "Allied Health – Dental"},
    {"query": "cosmetic clinic Melbourne", "category": "Allied Health – Cosmetic"},

    # Real estate
    {"query": "boutique real estate agency Melbourne", "category": "Real Estate – Agency"},
    {"query": "property management Melbourne", "category": "Real Estate – Property Management"},

    # Automotive
    {"query": "mechanic Melbourne", "category": "Automotive – Mechanic"},
    {"query": "smash repair Melbourne", "category": "Automotive – Smash Repair"},
    {"query": "tyre shop Melbourne", "category": "Automotive – Tyres"},
    {"query": "auto electrician Melbourne", "category": "Automotive – Auto Electrician"},
    {"query": "car detailing Melbourne", "category": "Automotive – Detailing"},

    # NDIS
    {"query": "NDIS disability support provider Melbourne", "category": "NDIS – Support Provider"},
    {"query": "NDIS support coordinator Melbourne", "category": "NDIS – Support Coordinator"},
    {"query": "NDIS allied health Melbourne", "category": "NDIS – Allied Health"},

    # Beauty & wellness
    {"query": "hair salon Melbourne", "category": "Beauty – Hair Salon"},
    {"query": "injectables clinic Melbourne", "category": "Beauty – Injectables"},
    {"query": "med spa Melbourne", "category": "Beauty – Med Spa"},
    {"query": "barber shop Melbourne", "category": "Beauty – Barber"},
    {"query": "massage clinic Melbourne", "category": "Beauty – Massage"},

    # Hospitality suppliers / wholesalers
    {"query": "food distributor Melbourne wholesale", "category": "Hospitality Supply – Food"},
    {"query": "beverage supplier Melbourne wholesale", "category": "Hospitality Supply – Beverage"},
    {"query": "packaging supplier Melbourne wholesale", "category": "Hospitality Supply – Packaging"},
]

# Results per query (Outscraper charges per result — tune based on budget)
RESULTS_PER_QUERY = 20

# Seconds to wait between website crawl requests (be polite)
CRAWL_DELAY = 1.5

# Max pages to crawl per business website (homepage + /contact)
MAX_PAGES_PER_SITE = 2

# Output file
OUTPUT_FILE = "delvix_leads_melbourne.xlsx"
