"""
Layered location extractor for job items.

Tries a priority chain of extraction strategies and returns the first match.
All inputs are optional; any failure silently returns None.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from urllib.parse import unquote

import geonamescache as _gnc_module

# ---------------------------------------------------------------------------
# Geonamescache corpus (built once at import time)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _gc():
    return _gnc_module.GeonamesCache()


@lru_cache(maxsize=None)
def _country_names_lower() -> frozenset[str]:
    """Lowercase set of all geonamescache country names plus common aliases."""
    gc = _gc()
    names = {c["name"].lower() for c in gc.get_countries().values()}
    aliases = {
        "uk", "england", "scotland", "wales", "northern ireland",
        "usa", "u.s.a.", "u.s.", "america",
        "holland", "netherlands",
        "czech republic", "czechia",
        "south korea", "north korea",
        "ivory coast",
        "taiwan",
        "russia",
        "iran",
        "syria",
        "bolivia",
        "venezuela",
        "tanzania",
        "moldova",
        "laos",
    }
    return frozenset(names | aliases)


@lru_cache(maxsize=None)
def _iso_to_country() -> dict[str, str]:
    return {c["iso"]: c["name"] for c in _gc().get_countries().values()}


@lru_cache(maxsize=None)
def _cities_by_name_100k() -> dict[str, list[dict]]:
    """City name -> list of city dicts for cities with population >= 100,000."""
    gc = _gc()
    result: dict[str, list[dict]] = {}
    for city in gc.get_cities().values():
        if city["population"] >= 100_000:
            result.setdefault(city["name"], []).append(city)
    return result


@lru_cache(maxsize=None)
def _country_name_to_iso() -> dict[str, str]:
    """Lowercase country name -> ISO-2 code, including aliases."""
    gc = _gc()
    mapping = {c["name"].lower(): c["iso"] for c in gc.get_countries().values()}
    aliases = {
        "uk": "GB", "england": "GB", "scotland": "GB",
        "wales": "GB", "northern ireland": "GB",
        "usa": "US", "u.s.a.": "US", "u.s.": "US", "america": "US",
        "holland": "NL", "netherlands": "NL",
        "czech republic": "CZ", "czechia": "CZ",
        "south korea": "KR", "north korea": "KP",
        "ivory coast": "CI", "taiwan": "TW",
        "russia": "RU", "iran": "IR", "syria": "SY",
        "bolivia": "BO", "venezuela": "VE", "tanzania": "TZ",
        "moldova": "MD", "laos": "LA",
    }
    mapping.update(aliases)
    return mapping


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# UN duty station city -> country name
UN_DUTY_STATIONS: dict[str, str] = {
    "Abidjan": "Côte d'Ivoire",
    "Abuja": "Nigeria",
    "Accra": "Ghana",
    "Addis Ababa": "Ethiopia",
    "Algiers": "Algeria",
    "Almaty": "Kazakhstan",
    "Amman": "Jordan",
    "Amsterdam": "The Netherlands",
    "Ankara": "Turkey",
    "Antananarivo": "Madagascar",
    "Apia": "Samoa",
    "Ashgabat": "Turkmenistan",
    "Asmara": "Eritrea",
    "Astana": "Kazakhstan",
    "Asuncion": "Paraguay",
    "Athens": "Greece",
    "Baghdad": "Iraq",
    "Baku": "Azerbaijan",
    "Bamako": "Mali",
    "Bangkok": "Thailand",
    "Bangui": "Central African Republic",
    "Banjul": "Gambia",
    "Beijing": "China",
    "Beirut": "Lebanon",
    "Belgrade": "Serbia",
    "Bern": "Switzerland",
    "Bishkek": "Kyrgyzstan",
    "Bissau": "Guinea-Bissau",
    "Bogota": "Colombia",
    "Brazzaville": "Republic of the Congo",
    "Brussels": "Belgium",
    "Bucharest": "Romania",
    "Budapest": "Hungary",
    "Buenos Aires": "Argentina",
    "Bujumbura": "Burundi",
    "Cairo": "Egypt",
    "Caracas": "Venezuela",
    "Chisinau": "Moldova",
    "Colombo": "Sri Lanka",
    "Conakry": "Guinea",
    "Copenhagen": "Denmark",
    "Dakar": "Senegal",
    "Dar Es Salaam": "Tanzania",
    "Dhaka": "Bangladesh",
    "Dili": "Timor-Leste",
    "Djibouti": "Djibouti",
    "Doha": "Qatar",
    "Dubai": "United Arab Emirates",
    "Dushanbe": "Tajikistan",
    "Freetown": "Sierra Leone",
    "Gaborone": "Botswana",
    "Geneva": "Switzerland",
    "Georgetown": "Guyana",
    "Guatemala City": "Guatemala",
    "Hanoi": "Vietnam",
    "Harare": "Zimbabwe",
    "Havana": "Cuba",
    "Helsinki": "Finland",
    "Islamabad": "Pakistan",
    "Istanbul": "Turkey",
    "Jakarta": "Indonesia",
    "Juba": "South Sudan",
    "Kabul": "Afghanistan",
    "Kampala": "Uganda",
    "Kathmandu": "Nepal",
    "Khartoum": "Sudan",
    "Kigali": "Rwanda",
    "Kinshasa": "Democratic Republic of the Congo",
    "Kingston": "Jamaica",
    "Kuala Lumpur": "Malaysia",
    "Kuwait City": "Kuwait",
    "Kyiv": "Ukraine",
    "Lagos": "Nigeria",
    "Libreville": "Gabon",
    "Lilongwe": "Malawi",
    "Lima": "Peru",
    "Lisbon": "Portugal",
    "Lome": "Togo",
    "London": "United Kingdom",
    "Luanda": "Angola",
    "Lusaka": "Zambia",
    "Luxembourg": "Luxembourg",
    "Madrid": "Spain",
    "Malabo": "Equatorial Guinea",
    "Male": "Maldives",
    "Managua": "Nicaragua",
    "Manila": "Philippines",
    "Maputo": "Mozambique",
    "Maseru": "Lesotho",
    "Mbabane": "Eswatini",
    "Mexico City": "Mexico",
    "Minsk": "Belarus",
    "Mogadishu": "Somalia",
    "Monrovia": "Liberia",
    "Montevideo": "Uruguay",
    "Moroni": "Comoros",
    "Moscow": "Russia",
    "Muscat": "Oman",
    "Nairobi": "Kenya",
    "Nassau": "Bahamas",
    "New Delhi": "India",
    "New York": "United States",
    "Niamey": "Niger",
    "Nicosia": "Cyprus",
    "Nouakchott": "Mauritania",
    "Nuku'alofa": "Tonga",
    "Ouagadougou": "Burkina Faso",
    "Panama City": "Panama",
    "Paramaribo": "Suriname",
    "Paris": "France",
    "Phnom Penh": "Cambodia",
    "Port-Au-Prince": "Haiti",
    "Port Louis": "Mauritius",
    "Port Moresby": "Papua New Guinea",
    "Port Of Spain": "Trinidad and Tobago",
    "Port Vila": "Vanuatu",
    "Prague": "Czech Republic",
    "Pretoria": "South Africa",
    "Pyongyang": "North Korea",
    "Quito": "Ecuador",
    "Rabat": "Morocco",
    "Ramallah": "Palestinian Territories",
    "Rangoon": "Myanmar",
    "Riga": "Latvia",
    "Riyadh": "Saudi Arabia",
    "Rome": "Italy",
    "San Jose": "Costa Rica",
    "San Salvador": "El Salvador",
    "Santiago": "Chile",
    "Santo Domingo": "Dominican Republic",
    "Sarajevo": "Bosnia and Herzegovina",
    "Seoul": "South Korea",
    "Singapore": "Singapore",
    "Skopje": "North Macedonia",
    "Sofia": "Bulgaria",
    "Stockholm": "Sweden",
    "Suva": "Fiji",
    "Taipei": "Taiwan",
    "Tallinn": "Estonia",
    "Tashkent": "Uzbekistan",
    "Tbilisi": "Georgia",
    "Tehran": "Iran",
    "Thimphu": "Bhutan",
    "Tirana": "Albania",
    "Tokyo": "Japan",
    "Tripoli": "Libya",
    "Tunis": "Tunisia",
    "Ulaanbaatar": "Mongolia",
    "Vaduz": "Liechtenstein",
    "Valletta": "Malta",
    "Vienna": "Austria",
    "Vientiane": "Laos",
    "Vilnius": "Lithuania",
    "Warsaw": "Poland",
    "Washington": "United States",
    "Berlin": "Germany",
    "Windhoek": "Namibia",
    "Yamoussoukro": "Côte d'Ivoire",
    "Yaounde": "Cameroon",
    "Yerevan": "Armenia",
    "Zagreb": "Croatia",
}

# Ambiguous city names that Layer 6 must never return (disambiguated by
# higher layers that have surrounding context).
AMBIGUOUS_CITIES: frozenset[str] = frozenset({
    "Kingston", "Cambridge", "Birmingham", "Manchester", "Newcastle",
    "Perth", "Richmond", "Hamilton", "London", "Albany", "Springfield",
    "Wellington", "Adelaide", "Reading", "Oxford", "Durham", "York",
})

# Layer 1 label phrases (matched case-insensitively)
_L1_LABELS = [
    "posting location",
    "place of employment",
    "place of work",
    "office location",
    "job location",
    "position based in",
    "position based at",
    "role based in",
    "role based at",
    "duty station",
    "based in",
    "based at",
    "workplace",
    "location",
    "office",
    "where",
]

# Values that are not real locations; Layer 1 rejects these.
_NON_LOCATION_VALUES: frozenset[str] = frozenset({
    "tbd", "tbc", "various", "multiple", "remote", "hybrid",
    "anywhere", "worldwide", "global", "field-based", "flexible",
    "n/a", "na", "negotiable", "home-based", "home based",
    "multiple locations", "multiple countries",
})

# Role keywords that disqualify a title parenthetical/suffix (Layer 4)
_ROLE_KEYWORDS: frozenset[str] = frozenset({
    "senior", "junior", "lead", "head", "director", "analyst", "assistant",
    "officer", "manager", "coordinator", "intern", "trainee", "adviser",
    "advisor", "specialist", "consultant", "expert", "associate", "principal",
    "deputy", "executive",
})

# Layer 6 context words that anchor a city match
_L6_CONTEXT_WORDS = (
    "based", "located", "office", "headquartered",
    "position in", "role in", "work in", "posted in",
    "vacancy in", "opening in",
)

# Layer 1 boilerplate suffixes to strip
_L1_BOILERPLATE = re.compile(
    r"\s*(?:staffing exercise|posted date|job id|posting date|"
    r"requisition|ref(?:erence)?[\s#]|salary|grade|level|"
    r"contract type|closing date|apply by|deadline)\b.*$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_valid_country(text: str) -> bool:
    return text.strip().lower() in _country_names_lower()


def _is_valid_city(name: str) -> bool:
    return name in _cities_by_name_100k()


def _city_country(city_name: str) -> str | None:
    """Return country name for a city if it is unambiguous (single country)."""
    entries = _cities_by_name_100k().get(city_name, [])
    if not entries:
        return None
    codes = {e["countrycode"] for e in entries}
    if len(codes) == 1:
        return _iso_to_country().get(codes.pop())
    return None


def _title_case_upper(text: str) -> str:
    """Title-case an all-uppercase string, respecting spaces and hyphens."""
    if not text.isupper():
        return text
    return " ".join(
        "-".join(part.capitalize() for part in word.split("-"))
        for word in text.split()
    )


def _clean_l1_capture(raw: str) -> str | None:
    """Apply Layer 1 cleanup rules. Returns None if value should be discarded."""
    value = raw.strip()
    value = _L1_BOILERPLATE.sub("", value).strip().rstrip(".,;:")
    value = _title_case_upper(value)
    if len(value) < 2 or len(value) > 80:
        return None
    # Reject if value is exactly a non-location word, or starts with one
    value_lower = value.lower()
    for junk in _NON_LOCATION_VALUES:
        if value_lower == junk or value_lower.startswith(junk + " ") or value_lower.startswith(junk + "("):
            return None
    return value or None


# ---------------------------------------------------------------------------
# Layer implementations
# ---------------------------------------------------------------------------

def _layer1(description: str) -> str | None:
    """Explicit location labels in description."""
    label_pattern = re.compile(
        r"(?i)(?:^|[\s\n.;])(?P<label>" + "|".join(re.escape(lbl) for lbl in _L1_LABELS) + r")"
        r"\s*[:\-]\s*(?P<value>.+?)(?:\.|,\s*(?:posted|closing|apply|deadline)|[\n]|$)",
        re.IGNORECASE | re.MULTILINE,
    )
    best: tuple[int, str] | None = None  # (label_priority, value)
    for m in label_pattern.finditer(description):
        label = m.group("label").lower()
        raw_value = m.group("value")
        cleaned = _clean_l1_capture(raw_value)
        if not cleaned:
            continue
        priority = _L1_LABELS.index(label) if label in _L1_LABELS else len(_L1_LABELS)
        if best is None or priority < best[0]:
            is_duty_station = label == "duty station"
            if is_duty_station:
                country = UN_DUTY_STATIONS.get(cleaned)
                if country:
                    result = f"{cleaned}, {country}"
                else:
                    result = cleaned
            else:
                result = cleaned
            best = (priority, result)
    return best[1] if best else None


def _layer2(description: str) -> str | None:
    """Inline city-country pairs in the first 1000 characters of description."""
    text = description[:1000]

    # Pattern 1: "City in [The] Country. Deadline/Closing/Apply"
    p1 = re.compile(
        r"([A-Z][a-zA-Z\-]+(?:\s+[A-Z][a-zA-Z\-]+)*)"
        r"\s+in\s+(The\s+)?([A-Z][a-zA-Z\-]+(?:\s+[A-Z][a-zA-Z\-]+)*)"
        r"[,.]?\s+(?:Deadline|Closing|Apply|Contract|Salary)",
        re.IGNORECASE,
    )
    for m in p1.finditer(text):
        city = m.group(1).strip()
        the_prefix = m.group(2) or ""
        country_raw = m.group(3).strip()
        country = (the_prefix + country_raw).strip()
        if _is_valid_country(country):
            return f"{city}, {country}"

    # Pattern 2: "City, Country" where Country is a recognised name.
    # Use an overlapping scan so "Senior Analyst, Brussels, Belgium" finds
    # "Brussels, Belgium" even after "Senior Analyst, Brussels" is tried first.
    p2 = re.compile(
        r"([A-Z][a-zA-Z\-]+(?:\s+[A-Z][a-zA-Z\-]+)*)"
        r",\s+"
        r"([A-Z][a-zA-Z\-]+(?:\s+[A-Z][a-zA-Z\-]+)*)"
        r"(?=[\s.,;)]|$)",
    )
    pos = 0
    while pos < len(text):
        m = p2.search(text, pos)
        if not m:
            break
        city = m.group(1).strip()
        country = m.group(2).strip()
        if _is_valid_country(country):
            return f"{city}, {country}"
        pos = m.start() + 1

    return None


def _layer3(url: str) -> str | None:
    """URL slug patterns."""
    if not url:
        return None

    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(url)
    path = parsed.path
    query = parsed.query

    # EuroBrussels-style: path ends with /Word_Word_Country or /Word_Country
    eb = re.search(r"/([A-Za-z]+(?:_[A-Za-z]+)*)_([A-Za-z]+)$", path)
    if eb:
        raw_city = eb.group(1).replace("_", " ").title()
        raw_country = eb.group(2).replace("_", " ").title()
        if raw_city.lower() in {"multiple", "various"}:
            return None
        if _is_valid_country(raw_country):
            return f"{raw_city}, {raw_country}"

    # Multiple countries/locations slug
    if re.search(r"multiple[_-](?:countries|locations)", path, re.IGNORECASE):
        return None

    # Lever ATS: /locations/City-Name
    lever = re.search(r"/locations/([A-Za-z][A-Za-z\-]+)", path)
    if lever:
        return lever.group(1).replace("-", " ").title()

    # Greenhouse: location= query param (urlparse.query has no leading ?)
    gh_match = re.search(r"(?:^|&)location=([^&]+)", query, re.IGNORECASE)
    if gh_match:
        return unquote(gh_match.group(1)).replace("+", " ").strip()

    # iCIMS: location= or city= query param
    icims = re.search(r"(?:^|&)(?:location|city)=([^&]+)", query, re.IGNORECASE)
    if icims:
        return unquote(icims.group(1)).replace("+", " ").strip()

    return None


def _layer4(title: str) -> str | None:
    """Title parentheticals and suffixes."""
    if not title:
        return None

    def _contains_role_word(text: str) -> bool:
        words = set(re.split(r"[\s,\-]+", text.lower()))
        return bool(words & _ROLE_KEYWORDS)

    # Trailing parenthetical: (Location)
    paren = re.search(r"\(([^)]{2,50})\)\s*$", title)
    if paren:
        candidate = paren.group(1).strip()
        if not _contains_role_word(candidate):
            if _is_valid_city(candidate) or _is_valid_country(candidate):
                return candidate

    # Trailing dash or pipe segment: - Location or | Location
    suffix = re.search(r"(?:-|\|)\s*([A-Z][a-zA-Z\s,\-]{1,48})\s*$", title)
    if suffix:
        candidate = suffix.group(1).strip()
        if not _contains_role_word(candidate):
            # Accept if city or country, or if it contains a comma (City, Country)
            parts = candidate.split(",")
            city_part = parts[0].strip()
            if _is_valid_city(city_part) or _is_valid_country(city_part) or _is_valid_country(candidate):
                return candidate

    return None


def _layer5(description: str) -> str | None:
    """Pipe-delimited description segments."""
    if not description or description.count("|") < 3:
        return None

    segments = [s.strip() for s in description.split("|")]

    for i, seg in enumerate(segments):
        # Segment containing comma where right side is a country
        if "," in seg:
            parts = seg.rsplit(",", 1)
            right = parts[1].strip()
            left = parts[0].strip()
            if _is_valid_country(right):
                return f"{left}, {right}"
            # Institution name: left contains an institution keyword, right is a
            # short plain word (the town name, even if below geonames threshold)
            _INST_KEYWORDS = {"university", "college", "school", "institute", "foundation", "centre", "center"}
            if any(kw in left.lower() for kw in _INST_KEYWORDS):
                if 2 <= len(right) <= 40 and re.match(r"^[A-Za-z][a-zA-Z\s\-]+$", right):
                    return right
            # Validated city after comma
            if _is_valid_city(right):
                return right

        # Segment that is itself a recognised city (short, clean)
        if _is_valid_city(seg) and 2 <= len(seg) <= 40:
            # Prefer segments near salary indicators
            next_seg = segments[i + 1] if i + 1 < len(segments) else ""
            if re.search(r"salary|£|\$|€|pay|remuneration", next_seg, re.IGNORECASE):
                return seg
            # Accept any city segment if it looks standalone
            if re.match(r"^[A-Z][a-zA-Z\s\-]+$", seg):
                return seg

    return None


def _layer6(description: str) -> str | None:
    """Geonamescache corpus scan with conservative safeguards."""
    if not description:
        return None

    window = description[:500]
    cities_map = _cities_by_name_100k()
    country_map = _country_name_to_iso()
    iso_to_name = _iso_to_country()

    # Find country mentions in window
    country_found: str | None = None  # ISO code
    country_pos: int | None = None
    country_found_name: str | None = None
    # Try longest country names first to avoid partial matches
    sorted_countries = sorted(country_map.keys(), key=len, reverse=True)
    for cname in sorted_countries:
        pattern = re.compile(r"\b" + re.escape(cname) + r"\b", re.IGNORECASE)
        m = pattern.search(window)
        if m:
            country_found = country_map[cname]
            country_pos = m.start()
            country_found_name = iso_to_name.get(country_found, cname.title())
            break

    # Find city mentions - check against blocklist
    city_found: str | None = None
    city_pos: int | None = None
    ambiguous_blocked = False  # True if an ambiguous city was found in the window

    # Try cities that appear in window
    for city_name in cities_map:
        if city_name in AMBIGUOUS_CITIES:
            # Mark that an ambiguous city appeared so we suppress country-only fallback
            pattern = re.compile(r"\b" + re.escape(city_name) + r"\b")
            if pattern.search(window):
                ambiguous_blocked = True
            continue
        pattern = re.compile(r"\b" + re.escape(city_name) + r"\b")
        m = pattern.search(window)
        if not m:
            continue

        pos = m.start()

        # City match requires: a country in window, OR a context word nearby
        has_country = country_found is not None
        context_pattern = re.compile(
            r"(?:" + "|".join(re.escape(w) for w in _L6_CONTEXT_WORDS) + r")",
            re.IGNORECASE,
        )
        # Check within 50 chars before or after the city match
        vicinity = window[max(0, pos - 50): pos + len(city_name) + 50]
        has_context = bool(context_pattern.search(vicinity))

        if not has_country and not has_context:
            continue

        # Prefer city closer to country mention
        if city_found is None:
            city_found = city_name
            city_pos = pos
        else:
            # Prefer leftmost city, or one nearer to country
            if country_pos is not None:
                current_dist = abs((city_pos or 0) - country_pos)
                new_dist = abs(pos - country_pos)
                if new_dist < current_dist:
                    city_found = city_name
                    city_pos = pos
            elif pos < (city_pos or 0):
                city_found = city_name
                city_pos = pos

    if city_found and country_found_name:
        # Consistency check: is the city in the matched country?
        city_entries = cities_map.get(city_found, [])
        city_countries = {e["countrycode"] for e in city_entries}
        if country_found in city_countries:
            return f"{city_found}, {country_found_name}"
        else:
            return city_found  # inconsistent — return city only
    elif city_found:
        return city_found
    elif country_found_name and not ambiguous_blocked:
        # Suppress country-only result when an ambiguous city was the only signal,
        # since we cannot tell which city the country refers to.
        return country_found_name

    return None


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def extract_location(
    description: str | None,
    url: str | None,
    title: str | None,
    creator: str | None,  # reserved, not used in v1
) -> str | None:
    """
    Try a priority chain of extraction strategies. Return the first match.
    Returns a free-text location string (e.g. "Brussels, Belgium" or "London")
    or None if no layer matches.
    """
    desc = (description or "").strip()
    u = (url or "").strip()
    t = (title or "").strip()

    try:
        if desc:
            result = _layer1(desc)
            if result:
                return result
        if desc:
            result = _layer2(desc)
            if result:
                return result
        if u:
            result = _layer3(u)
            if result:
                return result
        if t:
            result = _layer4(t)
            if result:
                return result
        if desc:
            result = _layer5(desc)
            if result:
                return result
        if desc:
            result = _layer6(desc)
            if result:
                return result
    except Exception:
        return None

    return None
