"""
In-memory dataset for the demo pharmacy chain ("FarmaValle").

This stands in for what, in a real deployment, would be a product database and
an inventory/orders service. Everything here is over-the-counter (OTC) and the
data is fictional and for demonstration only.
"""
from __future__ import annotations

# --- Store branches ---------------------------------------------------------
STORES = [
    {"id": "S1", "name": "FarmaValle Zona 10", "city": "Guatemala", "hours": "07:00-22:00"},
    {"id": "S2", "name": "FarmaValle Zona 15", "city": "Guatemala", "hours": "08:00-21:00"},
    {"id": "S3", "name": "FarmaValle Cayalá", "city": "Guatemala", "hours": "09:00-20:00"},
]

# --- Product catalogue (OTC only) -------------------------------------------
# price is in Guatemalan Quetzales (GTQ).
MEDICATIONS = [
    {
        "id": "MED-001",
        "name": "Acetaminophen 500mg (24 tabs)",
        "brand": "Tylenol",
        "active_ingredient": "acetaminophen",
        "category": "analgesic/antipyretic",
        "form": "tablet",
        "otc": True,
        "price": 35.0,
        "symptoms": ["headache", "fever", "body ache", "pain"],
        "dosage": "Adults: 1-2 tablets every 6-8h. Max 4g/day.",
        "warnings": "Do not combine with alcohol. Liver risk on overdose.",
    },
    {
        "id": "MED-002",
        "name": "Ibuprofen 400mg (20 tabs)",
        "brand": "Advil",
        "active_ingredient": "ibuprofen",
        "category": "NSAID",
        "form": "tablet",
        "otc": True,
        "price": 42.0,
        "symptoms": ["headache", "inflammation", "menstrual pain", "fever", "pain"],
        "dosage": "Adults: 1 tablet every 8h with food. Max 1200mg/day OTC.",
        "warnings": "Avoid with gastric ulcers or kidney disease. Take with food.",
    },
    {
        "id": "MED-003",
        "name": "Loratadine 10mg (10 tabs)",
        "brand": "Clarityne",
        "active_ingredient": "loratadine",
        "category": "antihistamine",
        "form": "tablet",
        "otc": True,
        "price": 28.0,
        "symptoms": ["allergy", "runny nose", "sneezing", "itchy eyes", "rash"],
        "dosage": "Adults & children >12: 1 tablet once daily.",
        "warnings": "May cause mild drowsiness in sensitive people.",
    },
    {
        "id": "MED-004",
        "name": "Loperamide 2mg (12 caps)",
        "brand": "Imodium",
        "active_ingredient": "loperamide",
        "category": "antidiarrheal",
        "form": "capsule",
        "otc": True,
        "price": 31.0,
        "symptoms": ["diarrhea"],
        "dosage": "Adults: 2 caps first dose, then 1 after each loose stool.",
        "warnings": "Do not use if there is high fever or blood in stool. Hydrate.",
    },
    {
        "id": "MED-005",
        "name": "Omeprazole 20mg (14 caps)",
        "brand": "Prilosec",
        "active_ingredient": "omeprazole",
        "category": "proton-pump inhibitor",
        "form": "capsule",
        "otc": True,
        "price": 55.0,
        "symptoms": ["heartburn", "acid reflux", "indigestion", "gastritis"],
        "dosage": "Adults: 1 capsule daily before breakfast, up to 14 days.",
        "warnings": "See a doctor if symptoms persist beyond 14 days.",
    },
    {
        "id": "MED-006",
        "name": "Dextromethorphan syrup 120ml",
        "brand": "Robitussin DM",
        "active_ingredient": "dextromethorphan",
        "category": "antitussive",
        "form": "syrup",
        "otc": True,
        "price": 48.0,
        "symptoms": ["dry cough", "cough"],
        "dosage": "Adults: 10ml every 6-8h.",
        "warnings": "Not for productive (mucus) cough. Avoid with MAOIs.",
    },
    {
        "id": "MED-007",
        "name": "Oral rehydration salts (5 sachets)",
        "brand": "Suero Oral",
        "active_ingredient": "electrolytes/glucose",
        "category": "rehydration",
        "form": "powder",
        "otc": True,
        "price": 18.0,
        "symptoms": ["diarrhea", "dehydration", "vomiting"],
        "dosage": "Dissolve 1 sachet in 1L clean water; sip throughout the day.",
        "warnings": "Seek care for severe dehydration or persistent vomiting.",
    },
    {
        "id": "MED-008",
        "name": "Cetirizine 10mg (10 tabs)",
        "brand": "Zyrtec",
        "active_ingredient": "cetirizine",
        "category": "antihistamine",
        "form": "tablet",
        "otc": True,
        "price": 30.0,
        "symptoms": ["allergy", "hives", "runny nose", "itchy eyes", "rash"],
        "dosage": "Adults: 1 tablet once daily.",
        "warnings": "May cause drowsiness; avoid driving until you know its effect.",
    },
    {
        "id": "MED-009",
        "name": "Guaifenesin 200mg (20 tabs)",
        "brand": "Mucinex",
        "active_ingredient": "guaifenesin",
        "category": "expectorant",
        "form": "tablet",
        "otc": True,
        "price": 40.0,
        "symptoms": ["chest congestion", "productive cough", "cough"],
        "dosage": "Adults: 1 tablet every 12h with plenty of water.",
        "warnings": "Drink extra fluids to help loosen mucus.",
    },
    {
        "id": "MED-010",
        "name": "Naproxen 220mg (20 tabs)",
        "brand": "Aleve",
        "active_ingredient": "naproxen",
        "category": "NSAID",
        "form": "tablet",
        "otc": True,
        "price": 46.0,
        "symptoms": ["menstrual pain", "back pain", "inflammation", "pain"],
        "dosage": "Adults: 1 tablet every 12h with food.",
        "warnings": "Avoid with heart, kidney or gastric conditions.",
    },
]

# --- Inventory: units in stock per (store_id, medication_id) ----------------
INVENTORY = {
    ("S1", "MED-001"): 120, ("S1", "MED-002"): 60, ("S1", "MED-003"): 45,
    ("S1", "MED-004"): 30, ("S1", "MED-005"): 25, ("S1", "MED-006"): 15,
    ("S1", "MED-007"): 200, ("S1", "MED-008"): 40, ("S1", "MED-009"): 0,
    ("S1", "MED-010"): 22,
    ("S2", "MED-001"): 80, ("S2", "MED-002"): 0, ("S2", "MED-003"): 60,
    ("S2", "MED-005"): 10, ("S2", "MED-007"): 150, ("S2", "MED-008"): 12,
    ("S2", "MED-010"): 5,
    ("S3", "MED-001"): 35, ("S3", "MED-003"): 20, ("S3", "MED-004"): 18,
    ("S3", "MED-006"): 9, ("S3", "MED-007"): 75, ("S3", "MED-009"): 14,
}

# --- Symptoms that should NOT be self-treated (route to professional care) ---
RED_FLAG_SYMPTOMS = {
    "chest pain", "difficulty breathing", "shortness of breath",
    "severe bleeding", "blood in stool", "coughing blood", "fainting",
    "stiff neck with fever", "severe abdominal pain", "vision loss",
    "slurred speech", "numbness on one side", "suicidal", "seizure",
}
