"""ML classifier for local mode - TF-IDF + Logistic Regression, bootstrapped with seed data.

The classifier is always active: it starts with built-in seed examples that encode
domain knowledge (common merchants and their categories), and improves as user
corrections and transaction history accumulate.  User data is weighted higher than
seed data so the model progressively personalises.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

import numpy as np

from spectra.ai import CategorySuggestion
from spectra.categories import normalize_category

logger = logging.getLogger("spectra.ml")


@dataclass(frozen=True)
class TrainingExample:
    raw_description: str
    clean_name: str
    category: str
    label_source: str
    sample_weight: float


@dataclass(frozen=True)
class PredictionResult:
    category: str
    confidence: float
    margin: float
    suggestions: list[CategorySuggestion]


_SEED_WEIGHT = 1.0
_TX_HISTORY_WEIGHT = 1.0
_MERCHANT_MEMORY_WEIGHT = 4.0
_USER_OVERRIDE_WEIGHT = 10.0

_SOURCE_WEIGHTS = {
    "seed": _SEED_WEIGHT,
    "tx_history": _TX_HISTORY_WEIGHT,
    "merchant_memory": _MERCHANT_MEMORY_WEIGHT,
    "user_override": _USER_OVERRIDE_WEIGHT,
}

_SOURCE_PRIORITIES = {
    "seed": 0,
    "tx_history": 1,
    "merchant_memory": 2,
    "user_override": 3,
}

# -- Seed knowledge ----------------------------------------------
# Each tuple is (description_example, category).  These bootstrap the model
# so it works from day-0 without any user history.

_SEED_MERCHANTS: list[tuple[list[str], str]] = [
    # Vietnam-first merchants
    (["Grab", "Grab Bike", "GrabCar", "Grab Ride", "Be Bike", "Be Group", "Gojek", "Xanh SM"], "Di chuyển"),
    (["Shopee", "ShopeePay", "Lazada", "Tiki", "TikTok Shop", "Sendo"], "Mua sắm"),
    (["MoMo", "ZaloPay", "VNPay", "VietQR"], "Chuyển khoản"),
    (["Viettel", "MobiFone", "Vinaphone", "FPT Telecom", "VNPT"], "Điện nước"),
    (["EVN", "Tien dien", "Tiền điện", "Nuoc sach", "Nước sạch"], "Điện nước"),
    (["WinMart", "VinMart", "Co.opmart", "Coopmart", "Bach Hoa Xanh", "Bách Hóa Xanh", "GO!"], "Đi chợ/Siêu thị"),
    (["Highlands Coffee", "Phuc Long", "Phúc Long", "The Coffee House", "KFC", "Lotteria", "Jollibee"], "Ăn uống"),
    (["CGV", "Galaxy Cinema", "Lotte Cinema", "BHD Star"], "Giải trí"),
    (["Pharmacity", "Long Chau", "Long Châu", "An Khang", "Benh vien", "Bệnh viện"], "Sức khỏe"),
    (["Vietnam Airlines", "Vietjet", "Bamboo Airways", "Agoda", "Traveloka", "Booking.com"], "Du lịch"),

    # -- Digital Subscriptions ----------------------------------
    (["Netflix", "NETFLIX.COM", "ADDEBITO SDD NETFLIX.COM", "Netflix subscription"], "Đăng ký định kỳ"),
    (["Spotify", "SPOTIFY AB", "ADDEBITO SDD SPOTIFY AB", "Spotify Premium"], "Đăng ký định kỳ"),
    (["Apple", "APPLE.COM/BILL", "Apple Music", "Apple One", "iTunes"], "Đăng ký định kỳ"),
    (["Disney+", "DISNEYPLUS", "Disney Plus"], "Đăng ký định kỳ"),
    (["Amazon Prime", "AMAZON PRIME", "AMZN PRIME"], "Đăng ký định kỳ"),
    (["YouTube Premium", "YOUTUBE PREMIUM"], "Đăng ký định kỳ"),
    (["ChatGPT", "OPENAI", "OpenAI subscription"], "Đăng ký định kỳ"),
    (["GitHub", "GITHUB.COM"], "Đăng ký định kỳ"),
    (["Dropbox", "DROPBOX.COM"], "Đăng ký định kỳ"),
    (["Google One", "GOOGLE STORAGE", "GOOGLE WORKSPACE", "GOOGLE CLOUD"], "Đăng ký định kỳ"),
    (["iCloud", "ICLOUD STORAGE"], "Đăng ký định kỳ"),
    (["Adobe", "ADOBE CREATIVE CLOUD", "ADOBE.COM"], "Đăng ký định kỳ"),
    (["Microsoft 365", "OFFICE 365"], "Đăng ký định kỳ"),
    (["Notion", "NOTION.SO"], "Đăng ký định kỳ"),
    (["Slack", "SLACK TECHNOLOGIES"], "Đăng ký định kỳ"),
    (["Zoom", "ZOOM.US"], "Đăng ký định kỳ"),
    (["LinkedIn Premium", "LINKEDIN PREMIUM"], "Đăng ký định kỳ"),
    (["DAZN", "DAZN SUBSCRIPTION"], "Đăng ký định kỳ"),
    (["Paramount+", "PARAMOUNT PLUS"], "Đăng ký định kỳ"),
    (["Sky", "SKY ITALIA", "SKY TV"], "Đăng ký định kỳ"),
    (["NordVPN", "NORDVPN.COM", "ExpressVPN", "ProtonVPN", "Surfshark"], "Đăng ký định kỳ"),
    (["AWS", "AMAZON WEB SERVICES", "Heroku", "DigitalOcean", "Vercel", "Netlify", "Cloudflare"], "Đăng ký định kỳ"),
    (["1Password", "Bitwarden", "LastPass"], "Đăng ký định kỳ"),
    (["Twitch", "TWITCH.TV"], "Đăng ký định kỳ"),
    (["Claude AI", "ANTHROPIC"], "Đăng ký định kỳ"),
    (["Midjourney", "MIDJOURNEY.COM"], "Đăng ký định kỳ"),
    (["Setapp", "SETAPP.COM"], "Đăng ký định kỳ"),
    (["Apple TV+", "TV.APPLE.COM"], "Đăng ký định kỳ"),
    (["Porkbun", "Namecheap", "GoDaddy", "Hover.com", "Gandi.net", "Registro.it"], "Đăng ký định kỳ"),

    # -- Transport ---------------------------------------------
    (["Uber", "UBER TRIP", "UBER BV", "HELP.UBER.COM"], "Di chuyển"),
    (["Bolt", "BOLT.EU", "BOLT RIDE"], "Di chuyển"),
    (["Lyft", "LYFT RIDE"], "Di chuyển"),
    (["Trenitalia", "TRENITALIA SPA"], "Di chuyển"),
    (["Italo Treno", "ITALO NTV"], "Di chuyển"),
    (["FlixBus", "FLIXBUS.IT"], "Di chuyển"),
    (["ATM Milano", "TPER", "GTT TORINO"], "Di chuyển"),
    (["TfL Travel Charge", "TFL TRAVEL CHARGE LONDON", "MTA", "RATP", "SNCF", "RENFE", "SBB"], "Di chuyển"),
    (["ENI STATION", "Q8", "AGIP", "IP STATION", "Shell", "BP", "TotalEnergies"], "Di chuyển"),
    (["Autostrade", "TELEPASS", "VIACARD"], "Di chuyển"),
    (["Taxi", "RADIOTAXI", "TAXIFY"], "Di chuyển"),
    (["Lime scooter", "Bird scooter", "Tier scooter", "FreeNow"], "Di chuyển"),

    # -- Travel ------------------------------------------------
    (["Ryanair", "RYANAIR LTD", "RYANAIR FR"], "Du lịch"),
    (["EasyJet", "EASYJET PLC"], "Du lịch"),
    (["Vueling", "WizzAir", "Lufthansa", "ITA Airways", "Alitalia"], "Du lịch"),
    (["Turkish Airlines", "KLM", "Air France", "British Airways", "Iberia", "TAP"], "Du lịch"),
    (["Booking.com", "BOOKING.COM AMSTERDAM", "BOOKING COM"], "Du lịch"),
    (["Airbnb", "AIRBNB.COM"], "Du lịch"),
    (["Expedia", "Hotels.com", "Trivago", "LastMinute"], "Du lịch"),
    (["Hotel", "Albergo", "B&B", "Bed and Breakfast", "Hostel"], "Du lịch"),
    (["Resort", "Motel", "Lodge", "Camping"], "Du lịch"),
    (["Hertz", "Avis", "Europcar", "Sixt", "Enterprise Rent", "Maggiore"], "Du lịch"),
    (["Aeroporto", "Airport"], "Du lịch"),
    (["Tirrenia", "Grimaldi Lines", "GNV", "Ferry"], "Du lịch"),
    (["Frecciarossa", "Frecciargento", "Frecciabianca"], "Du lịch"),

    # -- Entertainment -----------------------------------------
    (["Cinema", "UCI Cinema", "The Space Cinema"], "Giải trí"),
    (["Stadio", "Stadium", "Biglietti"], "Giải trí"),
    (["Concerto", "Concert", "Teatro", "Opera", "Museo"], "Giải trí"),
    (["TicketOne", "Ticketmaster", "Vivaticket", "Eventbrite"], "Giải trí"),
    (["Steam", "PlayStation", "Xbox", "Nintendo", "Epic Games", "PSN"], "Giải trí"),
    (["Gardaland", "Mirabilandia", "Disneyland", "Parco divertimenti"], "Giải trí"),

    # -- Groceries ---------------------------------------------
    (["Esselunga", "ESSELUNGA SPA", "POS ESSELUNGA"], "Đi chợ/Siêu thị"),
    (["Carrefour", "CARREFOUR EXPRESS", "CARREFOUR MARKET", "DIR. CARREFOUR"], "Đi chợ/Siêu thị"),
    (["Coop", "COOP ITALIA", "IPERCOOP", "NOVACOOP", "COOP ALLEANZA 3.0", "UNICOOP"], "Đi chợ/Siêu thị"),
    (["Conad", "CONAD SUPERMERCATO", "SPAZIO CONAD", "CONAD CITY", "MARGHERITA CONAD"], "Đi chợ/Siêu thị"),
    (["Lidl", "LIDL ITALIA", "POS LIDL", "LIDL SRL"], "Đi chợ/Siêu thị"),
    (["Aldi", "ALDI SUD", "ALDI SRL"], "Đi chợ/Siêu thị"),
    (["Eurospin", "EUROSPIN SPA", "EUROSPIN ITALIA"], "Đi chợ/Siêu thị"),
    (["PAM", "PAM SUPERMERCATO", "PANORAMA", "PAM PANORAMA"], "Đi chợ/Siêu thị"),
    (["MD", "MD DISCOUNT", "MD SPA", "L D MARKET"], "Đi chợ/Siêu thị"),
    (["Famila", "FAMILA SUPERSTORE", "IPERFAMILA", "DOK SUPERMERCATI", "A E O", "MEGA"], "Đi chợ/Siêu thị"),
    (["Despar", "INTERSPAR", "EUROSPAR", "DESPAR"], "Đi chợ/Siêu thị"),
    (["Il Gigante", "IL GIGANTE SPA", "RIALTO SPA"], "Đi chợ/Siêu thị"),
    (["Basko", "BASKO SPA", "SOGEGROSS"], "Đi chợ/Siêu thị"),
    (["Tigros", "TIGROS SPA"], "Đi chợ/Siêu thị"),
    (["Iper", "IPER LA GRANDE I", "FINIPER"], "Đi chợ/Siêu thị"),
    (["NaturaSì", "NATURASI"], "Đi chợ/Siêu thị"),
    (["Tesco", "Sainsbury", "ASDA", "Waitrose", "Morrisons", "Marks Spencer"], "Đi chợ/Siêu thị"),
    (["Rewe", "Edeka", "Kaufland", "Netto", "Migros", "Denner"], "Đi chợ/Siêu thị"),
    (["Auchan", "Leclerc", "Intermarche", "Monoprix", "Carrefour"], "Đi chợ/Siêu thị"),
    (["Mercadona", "Pingo Doce", "Continente"], "Đi chợ/Siêu thị"),
    (["Walmart", "Target", "Kroger", "Whole Foods", "Trader Joe", "7-Eleven"], "Đi chợ/Siêu thị"),
    (["Supermercato", "Supermarket", "Grocery", "Alimentari"], "Đi chợ/Siêu thị"),

    # -- Food & Dining -----------------------------------------
    (["Uber Eats", "UBER EATS DELIVERY", "UBEREATS"], "Ăn uống"),
    (["Deliveroo", "DELIVEROO.COM", "DELIVEROO ITALY"], "Ăn uống"),
    (["Glovo", "GLOVO APP", "FOODINHO"], "Ăn uống"),
    (["Just Eat", "JUST EAT", "JUSTEAT", "JUST EAT ITALY"], "Ăn uống"),
    (["Old Wild West", "OLD WILD WEST", "CIGIERRE", "ROADHOUSE", "ROADHOUSE GRILL", "CALAVERA", "SUSHI DAILY", "SUSHIKO", "POKE HOUSE", "I LOVE POKE", "MACHA POKE", "LA PIADINERIA", "ALICE PIZZA", "SPONTINI", "ROM'ANTICA", "ROSSOPOMODORO", "FRATELLI LA BUFALA", "GROM", "VENCHI"], "Ăn uống"),
    (["Ristorante", "Trattoria", "Pizzeria", "Osteria", "Enoteca", "Restaurant"], "Ăn uống"),
    (["Bar Caffè", "Caffè Roma", "Cafeteria", "Pasticceria", "Costa Coffee", "Dunkin"], "Ăn uống"),
    (["Sushi", "Sushiko", "Ramen", "Udon"], "Ăn uống"),
    (["Poke bowl", "Pokè house"], "Ăn uống"),
    (["Bakery", "Panetteria", "Forno", "Boulangerie", "Pret a Manger"], "Ăn uống"),
    (["Gelateria", "Gelato shop"], "Ăn uống"),
    (["Domino", "Papa Johns", "Pizza Hut"], "Ăn uống"),
    (["Autogrill", "AUTOGRILL SPA"], "Ăn uống"),
    (["Wolt", "WOLT.COM"], "Ăn uống"),

    # -- Shopping ----------------------------------------------
    (["Amazon", "AMAZON EU SARL", "AMZN MKTP", "AMAZON.IT", "AMAZON MARKETPLACE", "AMAZON PAY", "AMAZON PRIME"], "Mua sắm"),
    (["AliExpress", "ALIPAY", "ALIPAY*ALIEXPRESS", "ALIBABA", "Temu", "TEMU.COM", "Shein", "SHEIN.COM", "ASOS", "Zalando", "ZALANDO SE", "ZALANDO PRIVE"], "Mua sắm"),
    (["IKEA", "IKEA ITALIA RETAIL", "POS IKEA", "IKEA.IT"], "Mua sắm"),
    (["Zara", "ZARA ITALIA", "H&M", "H & M HENNES", "Uniqlo", "UNIQLO EUROPE", "Decathlon", "DECATHLON ITALIA", "Primark", "PRIMARK ITALIA", "Muji", "OVS", "OVS SPA", "PULL AND BEAR", "BERSHKA", "STRADIVARIUS", "MANGO", "CALZEDONIA", "INTIMISSIMI", "TEZENIS", "YOOX", "NIKE", "ADIDAS"], "Mua sắm"),
    (["MediaWorld", "MEDIAMARKET", "MEDIAWORLD", "Unieuro", "UNIEURO SPA", "Euronics", "EURONICS ITALIA", "Expert", "EXPERT ITALIA", "Trony", "TRONY", "Comet", "Apple Store", "APPLE STORE RETAIL", "Best Buy"], "Mua sắm"),
    (["Sephora", "SEPHORA ITALIA", "Kiko", "KIKO SPA", "MAC Cosmetics", "DOUGLAS", "ACQUA E SAPONE", "TIGOTA", "GOTTARDO SPA", "NOTINO"], "Mua sắm"),
    (["Etsy", "ETSY.COM", "ETSY IRELAND"], "Mua sắm"),
    (["Vinted", "VINTED.COM", "VINTED UAB", "MANGOPAY*VINTED"], "Mua sắm"),
    (["eBay", "EBAY.COM", "EBAY EUROPE", "PAYPAL *EBAY"], "Mua sắm"),
    (["Leroy Merlin", "LEROY MERLIN ITALIA", "OBI", "OBI ITALIA", "Brico", "BRICOCENTER", "BRICOMAN", "TECNOMAT", "Home Depot"], "Mua sắm"),
    (["Satispay", "SATISPAY", "SATISPAY EUROPE"], "Mua sắm"),
    (["PayPal purchase", "PAYPAL PAYMENT", "PAYPAL *"], "Mua sắm"),

    # -- Health ------------------------------------------------
    (["Farmacia", "Pharmacy", "Pharmacie", "Apotheke", "CVS", "Walgreens"], "Sức khỏe"),
    (["Rossmann", "DM Drogerie"], "Sức khỏe"),
    (["Dottore", "Medico", "Clinica", "Ospedale", "Hospital"], "Sức khỏe"),
    (["Dentista", "Odontoiatra", "Dental clinic"], "Sức khỏe"),
    (["Psicologo", "Psicologa", "Terapista", "Fisioterapista"], "Sức khỏe"),
    (["Ottica", "Visita oculistica", "Optician"], "Sức khỏe"),

    # -- Health & Fitness --------------------------------------
    (["Palestra", "Gym", "Fitness club", "Wellness center", "CrossFit", "Pilates", "Yoga"], "Sức khỏe"),

    # -- Insurance ---------------------------------------------
    (["Assicurazione", "Bảo hiểm", "AXA", "Allianz", "Generali", "Zurich", "UnipolSai"], "Bảo hiểm"),
    (["RC Auto", "Polizza auto", "Premio assicurativo", "Direct Line", "BUPA"], "Bảo hiểm"),

    # -- Utilities ---------------------------------------------
    (["Vodafone", "VODAFONE ITALIA", "VODAFONE OMNITEL"], "Điện nước"),
    (["TIM", "TIM TELECOM", "TELECOM ITALIA"], "Điện nước"),
    (["Wind Tre", "WINDTRE SPA", "WIND TRE", "INFOSTRADA"], "Điện nước"),
    (["Enel", "ENEL ENERGIA", "ENEL SERVIZIO ELETTRICO", "SERVIZIO ELETTRICO NAZIONALE"], "Điện nước"),
    (["A2A", "A2A ENERGIA", "IREN", "IREN MERCATO", "HERA", "HERA COMM", "ACEA", "ACEA ENERGIA", "ENI PLENITUDE", "EDISON", "EDISON ENERGIA", "E.ON", "E.ON ENERGIA", "ENGIE", "ENGIE ITALIA", "SORGENIA"], "Điện nước"),
    (["Bolletta", "Utenza", "Gas luce", "Electricity", "Water bill", "Fattura", "Acqua", "Teleriscaldamento"], "Điện nước"),
    (["Telepass", "TELEPASS SPA", "TELEPASS FAMILY"], "Di chuyển"),

    # -- Cash --------------------------------------------------
    (["Versamento contanti", "Deposito contanti", "Cash deposit"], "Tiền mặt"),
    (["Prelievo", "Prelievo Bancomat", "ATM Cash", "Cash withdrawal", "Prelievo con carta"], "Tiền mặt"),

    # -- Taxes -------------------------------------------------
    (["F24", "Agenzia Entrate", "Tasse", "Tributi", "IMU", "TARI", "Tax"], "Khác"),
    (["Comune di", "Regione", "Provincia di", "ASL", "Council"], "Khác"),
    (["Bollo auto", "PRA", "DVLA"], "Khác"),

    # -- Education ---------------------------------------------
    (["Università", "Politecnico", "Accademia", "Corso di", "College", "School"], "Giáo dục"),
    (["Udemy", "Coursera", "Skillshare", "Duolingo", "Busuu"], "Giáo dục"),
    (["Libreria Feltrinelli", "Mondadori", "Libri", "Waterstones", "Barnes Noble"], "Giáo dục"),

    # -- Income & Transfers ------------------------------------
    (["Stipendio", "STIPENDIO MESE", "Lương", "Payroll", "Retribuzione",
      "ACCREDITO STIPENDIO", "ACCREDITO RETRIBUZIONE", "ACCREDITO SALARIO",
      "Accredito competenze", "Accredito emolumenti", "Bonifico stipendio",
      "Emolumenti", "Competenze mensili", "Retribuzione mensile",
      "Gehalt", "Lohn", "Gehaltseingang",           # German
      "Salaire", "Virement salaire",                # French
      "Nómina", "Salario",                          # Spanish
      "Salário", "Ordenado"], "Lương"),             # Portuguese
    (["Pensione", "Thu nhập", "ACCREDITO PENSIONE", "INPS pensione",
      "Rente", "Retraite", "Jubilación", "Pensão"], "Thu nhập"),
    (["Bonifico ricevuto", "Accredito bonifico", "Bonifico in entrata",
      "ACCREDITO BONIFICO", "Accredito da",
      "Incoming transfer", "Überweisung eingegangen",
      "Virement reçu", "Transferencia recibida"], "Chuyển khoản"),
    (["Rimborso", "Refund", "Cashback",
      "Remboursement", "Reembolso", "Erstattung"], "Hoàn tiền"),
    (["Revolut top-up", "REVOLUT TOP UP"], "Chuyển khoản"),
]

# Banking prefixes used to augment seed data with realistic raw descriptions.
_BANKING_PREFIXES = [
    # Italian
    "",
    "POS ",
    "POS 1234 ",
    "ADDEBITO SDD ",
    "ADDEBITO DIRETTO ",
    "PAGAMENTO ",
    "PAGAMENTO SU POS ",
    "PAGAMENTO SU POS ESTERO ",
    # English / UK
    "CARD PAYMENT ",
    "CARD PAYMENT TO ",
    "DIRECT DEBIT ",
    "CONTACTLESS ",
    # German
    "Kartenzahlung ",
    "Lastschrift ",
    # French
    "Paiement CB ",
    "Prélèvement SEPA ",
    # Spanish
    "Pago con tarjeta ",
]


def build_seed_data() -> list[tuple[str, str]]:
    """Expand _SEED_MERCHANTS into a flat list of (description, category) pairs."""
    data: list[tuple[str, str]] = []
    for examples, category in _SEED_MERCHANTS:
        for example in examples:
            data.append((example, category))
            # Add prefixed variants for the first/main example of each group
            if example == examples[0]:
                for prefix in _BANKING_PREFIXES:
                    if prefix:
                        data.append((f"{prefix}{example}", category))
                        data.append((f"{prefix}{example.upper()}", category))
    return data


def _extract_clean_name(text: str) -> str:
    from spectra.local_categorizer import _extract_merchant_name

    return _extract_merchant_name(text) if text else ""


def _normalize_feature_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()


def _source_priority(label_source: str) -> int:
    return _SOURCE_PRIORITIES.get(str(label_source or ""), -1)


def _weight_for_source(label_source: str) -> float:
    return _SOURCE_WEIGHTS.get(str(label_source or ""), _TX_HISTORY_WEIGHT)


def _make_training_example(
    *,
    raw_description: str,
    clean_name: str,
    category: str,
    label_source: str,
) -> TrainingExample | None:
    normalized_source = str(label_source or "tx_history").strip().lower()
    normalized_category = normalize_category(str(category or "").strip())
    raw = str(raw_description or "").strip()
    merchant = str(clean_name or "").strip()
    if raw:
        merchant = _extract_clean_name(raw)
    elif merchant:
        merchant = _extract_clean_name(merchant)

    if not normalized_category or not (raw or merchant):
        return None

    return TrainingExample(
        raw_description=raw,
        clean_name=merchant,
        category=normalized_category,
        label_source=normalized_source,
        sample_weight=_weight_for_source(normalized_source),
    )


def _training_key(example: TrainingExample) -> str:
    base = example.raw_description or example.clean_name
    return _normalize_feature_text(base)


def build_training_examples(
    training_data: list[dict[str, str]] | list[tuple[str, str]] | None = None,
) -> list[TrainingExample]:
    """Resolve seed and user data into de-duplicated weighted training examples."""
    resolved: dict[str, TrainingExample] = {}

    def consider(example: TrainingExample | None) -> None:
        if example is None:
            return
        key = _training_key(example)
        if not key:
            return
        existing = resolved.get(key)
        if existing is None or _source_priority(example.label_source) > _source_priority(existing.label_source):
            resolved[key] = example

    for raw_description, category in build_seed_data():
        consider(
            _make_training_example(
                raw_description=raw_description,
                clean_name="",
                category=category,
                label_source="seed",
            )
        )

    for item in training_data or []:
        if isinstance(item, tuple):
            raw_description, category = item
            consider(
                _make_training_example(
                    raw_description=str(raw_description or ""),
                    clean_name="",
                    category=str(category or ""),
                    label_source="user_override",
                )
            )
            continue

        consider(
            _make_training_example(
                raw_description=str(item.get("raw_description", "")),
                clean_name=str(item.get("clean_name", "")),
                category=str(item.get("category", "")),
                label_source=str(item.get("label_source", "tx_history")),
            )
        )

    return list(resolved.values())


def _feature_row(raw_description: str, clean_name: str) -> dict[str, str]:
    normalized_clean_name = _normalize_feature_text(clean_name)
    combined_text = " ".join(part for part in [raw_description.strip(), clean_name.strip()] if part).strip()
    if not combined_text:
        combined_text = clean_name.strip() or raw_description.strip()
    return {
        "combined_text": combined_text,
        "clean_name_normalized": normalized_clean_name or _normalize_feature_text(combined_text),
    }


def _select_combined_text(rows: list[dict[str, str]]) -> list[str]:
    return [row["combined_text"] for row in rows]


def _select_clean_name_text(rows: list[dict[str, str]]) -> list[str]:
    return [row["clean_name_normalized"] for row in rows]


def train_classifier(
    training_data: list[dict[str, str]] | list[tuple[str, str]] | None = None,
) -> Any | None:
    """Train a weighted TF-IDF + LogisticRegression local classifier."""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import FeatureUnion, Pipeline
        from sklearn.preprocessing import FunctionTransformer
    except ImportError:
        logger.info("scikit-learn not installed - ML classifier disabled. Install with: pip install scikit-learn")
        return None

    training_examples = build_training_examples(training_data)
    feature_rows = [
        _feature_row(example.raw_description, example.clean_name)
        for example in training_examples
    ]
    categories: list[str] = []
    weights: list[float] = []
    source_counts: dict[str, int] = {}
    for example in training_examples:
        categories.append(example.category)
        weights.append(example.sample_weight)
        source_counts[example.label_source] = source_counts.get(example.label_source, 0) + 1

    unique_cats = set(categories)
    if len(unique_cats) < 2:
        logger.info("Only 1 category in combined data - ML classifier not useful")
        return None

    pipeline = Pipeline([
        ("features", FeatureUnion([
            ("word_tfidf", Pipeline([
                ("selector", FunctionTransformer(_select_combined_text, validate=False)),
                ("tfidf", TfidfVectorizer(
                    max_features=15000,
                    ngram_range=(1, 3),
                    sublinear_tf=True,
                    strip_accents="unicode",
                    lowercase=True,
                    min_df=1,
                )),
            ])),
            ("char_tfidf", Pipeline([
                ("selector", FunctionTransformer(_select_clean_name_text, validate=False)),
                ("tfidf", TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=(2, 6),
                    sublinear_tf=True,
                    lowercase=True,
                    min_df=1,
                    max_features=15000,
                )),
            ])),
        ])),
        ("clf", LogisticRegression(
            max_iter=2000,
            C=3.0,
            class_weight="balanced",
            solver="lbfgs",
            random_state=42,
        )),
    ])

    pipeline.fit(feature_rows, categories, clf__sample_weight=np.array(weights))

    logger.info(
        "ML classifier trained: %d examples (%s), %d categories",
        len(training_examples),
        ", ".join(f"{source}={count}" for source, count in sorted(source_counts.items())),
        len(unique_cats),
    )
    return pipeline


def predict_details(
    classifier: Any,
    description: str,
    *,
    clean_name: str | None = None,
    limit: int = 3,
) -> PredictionResult:
    """Predict category plus ranked suggestions for a raw bank description."""
    resolved_clean_name = clean_name or _extract_clean_name(description)
    feature_row = _feature_row(description, resolved_clean_name)
    proba = classifier.predict_proba([feature_row])[0]
    ordered = np.argsort(proba)[::-1]
    top_indices = ordered[: max(1, limit)]
    suggestions = [
        CategorySuggestion(
            category=str(classifier.classes_[idx]),
            score=round(float(proba[idx]), 4),
        )
        for idx in top_indices
    ]
    top_confidence = suggestions[0].score
    second_confidence = suggestions[1].score if len(suggestions) > 1 else 0.0
    return PredictionResult(
        category=suggestions[0].category,
        confidence=top_confidence,
        margin=round(top_confidence - second_confidence, 4),
        suggestions=suggestions,
    )


def predict(classifier: Any, description: str) -> tuple[str, float]:
    """Predict category for a raw banking description.

    Returns
    -------
    (category, confidence) - confidence is the max class probability.
    """
    result = predict_details(classifier, description)
    return result.category, result.confidence

