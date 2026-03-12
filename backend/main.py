from __future__ import annotations

import os
import asyncio
import base64
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import secrets
import json
from typing import Any, Literal
import httpx
from bson import ObjectId
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pymongo import AsyncMongoClient
from pymongo.server_api import ServerApi
from backend.routes.market_router import router as market_router

load_dotenv()

def normalize_runtime_path(path: Path) -> Path:
    value = str(path)
    if os.name == "nt" and value.startswith("\\\\?\\"):
        return Path(value[4:])
    return path


BASE_DIR = normalize_runtime_path(Path(__file__).resolve().parent.parent)


def default_argos_base_dir() -> Path:
    override = os.getenv("ARGOS_BASE_DIR", "").strip()
    if override:
        return normalize_runtime_path(Path(override))
    if os.getenv("VERCEL"):
        return Path("/tmp/argos")
    return BASE_DIR / ".argos"


ARGOS_BASE_DIR = default_argos_base_dir()
os.environ.setdefault("XDG_DATA_HOME", str(normalize_runtime_path(ARGOS_BASE_DIR / "data")))
os.environ.setdefault("XDG_CACHE_HOME", str(normalize_runtime_path(ARGOS_BASE_DIR / "cache")))
os.environ.setdefault("XDG_CONFIG_HOME", str(normalize_runtime_path(ARGOS_BASE_DIR / "config")))

try:
    import argostranslate.package as argos_package
    import argostranslate.translate as argos_translate
    import argostranslate.sbd as argos_sbd
    from stanza.pipeline.core import DownloadMethod

    def _offline_lazy_pipeline(self):
        if self.stanza_pipeline is None:
            self.stanza_pipeline = argos_sbd.stanza.Pipeline(
                lang=self.stanza_lang_code,
                dir=str(self.pkg.package_path / "stanza"),
                processors="tokenize",
                use_gpu=False,
                logging_level="WARNING",
                download_method=DownloadMethod.NONE,
            )
        return self.stanza_pipeline

    argos_sbd.StanzaSentencizer.lazy_pipeline = _offline_lazy_pipeline
except Exception:
    argos_package = None
    argos_translate = None

ARGOS_TRANSLATION_READY: bool | None = None

MONGODB_URL = (os.getenv("MONGODB_URL") or os.getenv("MONGODB_URI") or "").strip()
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "global_signal_map").strip() or "global_signal_map"
NEWSAPI_API_KEY = os.getenv("NEWSAPI_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "gid_session").strip() or "gid_session"
FALLBACK_AUTH_COOKIE_NAME = f"{SESSION_COOKIE_NAME}_nickname"
FALLBACK_SAVED_COOKIE_NAME = f"{SESSION_COOKIE_NAME}_saved"
COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30
MAX_FALLBACK_SAVED_ARTICLES = 20
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000").split(",")
    if origin.strip()
]

CATEGORY_NEWS_CONFIG = {
    "home": {
        "query": '((war OR conflict OR missile OR sanctions) OR (inflation OR "interest rates" OR economy OR market) OR (earthquake OR wildfire OR flood OR storm) OR (election OR diplomacy OR summit))',
        "include_any": ["war", "conflict", "missile", "airstrike", "sanctions", "inflation", "interest rates", "economy", "market", "earthquake", "wildfire", "flood", "storm", "election", "diplomacy", "summit"],
        "exclude_any": ["soccer", "football", "basketball", "baseball", "tennis", "golf", "movie", "music", "celebrity", "fashion", "airfare", "flight", "roundtrip", "basic economy", "regular economy", "hotel", "travel deal"],
        "color": "#2563EB",
    },
    "war": {
        "query": '((war OR conflict OR missile OR airstrike OR shelling OR "drone attack" OR "border clash" OR troops OR ceasefire) NOT (sports OR football OR soccer))',
        "include_any": ["war", "conflict", "missile", "airstrike", "shelling", "drone attack", "border clash", "troops", "ceasefire"],
        "exclude_any": ["soccer", "football", "basketball", "video game", "movie"],
        "color": "#EF4444",
    },
    "politics": {
        "query": '((election OR parliament OR government OR president OR "prime minister" OR diplomacy OR sanctions OR summit OR cabinet OR ministry) NOT (sports OR celebrity))',
        "include_any": ["election", "parliament", "government", "president", "prime minister", "diplomacy", "sanctions", "summit", "cabinet", "ministry"],
        "exclude_any": ["soccer", "football", "celebrity", "movie", "music"],
        "color": "#F59E0B",
    },
    "economy": {
        "query": '((inflation OR "interest rates" OR "central bank" OR economy OR exports OR currency OR "bond yields" OR stocks OR GDP OR recession OR tariff OR yen OR nikkei OR "bank of japan") NOT (sports OR entertainment))',
        "include_any": ["inflation", "interest rates", "central bank", "economy", "exports", "currency", "bond yields", "stocks", "gdp", "recession", "tariff", "yen", "nikkei", "bank of japan"],
        "exclude_any": ["soccer", "football", "movie", "music", "celebrity", "airfare", "flight", "roundtrip", "basic economy", "regular economy", "hotel", "travel deal"],
        "color": "#22C55E",
    },
    "disaster": {
        "query": '((earthquake OR wildfire OR flood OR storm OR hurricane OR typhoon OR eruption OR disaster OR tsunami) NOT (sports OR movie))',
        "include_any": ["earthquake", "wildfire", "flood", "storm", "hurricane", "typhoon", "eruption", "disaster", "tsunami"],
        "exclude_any": ["soccer", "football", "movie", "music", "celebrity"],
        "color": "#F97316",
    },
}


NEWS_RESULT_CACHE: dict[str, dict[str, Any]] = {}
NEWS_API_REQUEST_CACHE_TTL_SECONDS = 5
NEWS_API_REQUEST_CACHE: dict[str, dict[str, Any]] = {}
NEWS_API_INFLIGHT_REQUESTS: dict[str, asyncio.Task[list[dict[str, Any]]]] = {}

FALLBACK_NEWS = {
    "home": [
        {"title": "Global markets watch Middle East tension", "description": "Investors are balancing conflict risk, oil sensitivity, and central-bank expectations.", "url": "https://example.com/global-markets-middle-east", "source": {"name": "Global Signal Desk"}},
        {"title": "Japan policy signals keep Asia markets alert", "description": "Currency and bond markets in Asia remain sensitive to Bank of Japan commentary.", "url": "https://example.com/japan-policy-signals", "source": {"name": "Global Signal Desk"}},
        {"title": "Storm disruption raises supply-chain concerns", "description": "Transport delays and logistics rerouting are becoming a key issue for regional exporters.", "url": "https://example.com/storm-supply-chain", "source": {"name": "Global Signal Desk"}},
        {"title": "Washington and Brussels watch sanctions spillover", "description": "Diplomatic and economic officials are watching whether geopolitical pressure broadens into trade and energy markets.", "url": "https://example.com/sanctions-spillover", "source": {"name": "Global Signal Desk"}},
        {"title": "Seoul exporters assess currency and shipping risk", "description": "Export-driven firms are monitoring freight routes, oil moves, and FX volatility in Asia.", "url": "https://example.com/seoul-export-risk", "source": {"name": "Global Signal Desk"}},
        {"title": "London rate debate keeps investors cautious", "description": "Bond traders are reacting to slower growth expectations and rate-cut timing.", "url": "https://example.com/london-rate-debate", "source": {"name": "Global Signal Desk"}},
        {"title": "Tehran conflict headlines lift safe-haven demand", "description": "Energy and precious-metal traders are responding to elevated regional tension.", "url": "https://example.com/tehran-safe-haven", "source": {"name": "Global Signal Desk"}},
        {"title": "Brussels trade signals reshape industrial outlook", "description": "Manufacturing names are responding to changing policy and tariff guidance.", "url": "https://example.com/brussels-industrial-outlook", "source": {"name": "Global Signal Desk"}},
        {"title": "Jakarta logistics delays ripple across supply chains", "description": "Regional transport bottlenecks are becoming visible in export scheduling.", "url": "https://example.com/jakarta-logistics-delays", "source": {"name": "Global Signal Desk"}},
        {"title": "Sydney market mood shifts on commodity volatility", "description": "Investors are recalibrating risk as commodity-linked currencies remain unstable.", "url": "https://example.com/sydney-commodity-volatility", "source": {"name": "Global Signal Desk"}},
    ],
    "war": [
        {"title": "Tehran security alerts keep conflict risk elevated", "description": "Regional markets are monitoring retaliation risk, energy exposure, and diplomatic messaging around Tehran.", "url": "https://example.com/tehran-conflict-risk", "source": {"name": "Global Signal Desk"}},
        {"title": "Israel border tension draws renewed military focus", "description": "Cross-border security concerns are lifting safe-haven demand and energy-market attention.", "url": "https://example.com/israel-border-tension", "source": {"name": "Global Signal Desk"}},
        {"title": "Ukraine front-line pressure shapes risk sentiment", "description": "Defense, commodities, and European risk assets remain sensitive to new battlefield updates.", "url": "https://example.com/ukraine-risk-sentiment", "source": {"name": "Global Signal Desk"}},
        {"title": "Beirut security brief raises regional alert level", "description": "Neighboring markets are pricing in broader military uncertainty as security warnings spread across the Levant.", "url": "https://example.com/beirut-alert-level", "source": {"name": "Global Signal Desk"}},
        {"title": "Damascus military signals keep oil traders cautious", "description": "Energy and shipping desks remain sensitive to any sign of wider escalation around Syria and nearby corridors.", "url": "https://example.com/damascus-oil-caution", "source": {"name": "Global Signal Desk"}},
        {"title": "Khartoum clashes renew Africa risk concerns", "description": "Investors are watching whether prolonged instability spreads into nearby trade routes.", "url": "https://example.com/khartoum-risk-concerns", "source": {"name": "Global Signal Desk"}},
        {"title": "Ankara security monitoring rises after border reports", "description": "Military planners and markets are both reacting to heightened border uncertainty.", "url": "https://example.com/ankara-border-reports", "source": {"name": "Global Signal Desk"}},
        {"title": "Riyadh defense posture sharpens amid regional tension", "description": "Energy traders are following Saudi responses for signs of wider market disruption.", "url": "https://example.com/riyadh-defense-posture", "source": {"name": "Global Signal Desk"}},
        {"title": "Moscow war messaging affects European risk assets", "description": "European equities and commodity markets remain sensitive to conflict-linked statements from Moscow.", "url": "https://example.com/moscow-war-messaging", "source": {"name": "Global Signal Desk"}},
        {"title": "Kyiv battlefield updates keep volatility elevated", "description": "Fresh updates from Ukraine are feeding directly into defense and energy sentiment.", "url": "https://example.com/kyiv-volatility", "source": {"name": "Global Signal Desk"}},
    ],
    "politics": [
        {"title": "Brussels policy talks refocus trade expectations", "description": "EU-level regulatory and diplomatic signals are feeding into trade and sanctions pricing.", "url": "https://example.com/brussels-policy-talks", "source": {"name": "Global Signal Desk"}},
        {"title": "Washington debate keeps election-driven uncertainty high", "description": "Policy direction, fiscal outlook, and diplomatic posture remain key variables for investors.", "url": "https://example.com/washington-election-risk", "source": {"name": "Global Signal Desk"}},
        {"title": "London government messaging moves regulation outlook", "description": "Domestic policy announcements are shaping the near-term direction of rates and business sentiment.", "url": "https://example.com/london-regulation-outlook", "source": {"name": "Global Signal Desk"}},
        {"title": "Seoul diplomatic schedule shapes regional policy watch", "description": "Upcoming foreign-policy meetings are influencing market expectations around sanctions and trade alignment.", "url": "https://example.com/seoul-diplomatic-watch", "source": {"name": "Global Signal Desk"}},
        {"title": "Tokyo cabinet signals move regulatory expectations", "description": "New policy messaging is shifting investor focus toward industrial policy and cross-border cooperation.", "url": "https://example.com/tokyo-regulatory-signals", "source": {"name": "Global Signal Desk"}},
        {"title": "Paris coalition talks reshape reform outlook", "description": "Domestic political negotiations are changing the expected pace of reforms and fiscal plans.", "url": "https://example.com/paris-coalition-talks", "source": {"name": "Global Signal Desk"}},
        {"title": "Berlin sanctions review affects investor mood", "description": "Markets are watching Germany's next diplomatic step for clues on European coordination.", "url": "https://example.com/berlin-sanctions-review", "source": {"name": "Global Signal Desk"}},
        {"title": "Taipei policy speech sharpens regional focus", "description": "Investors are reassessing geopolitical and technology risk after new government remarks.", "url": "https://example.com/taipei-policy-speech", "source": {"name": "Global Signal Desk"}},
        {"title": "Islamabad cabinet tensions weigh on reform path", "description": "Political uncertainty is clouding expectations for economic and diplomatic stability.", "url": "https://example.com/islamabad-cabinet-tensions", "source": {"name": "Global Signal Desk"}},
        {"title": "New Delhi election signals influence market positioning", "description": "Investors are adjusting to the possibility of policy shifts after new campaign messaging.", "url": "https://example.com/new-delhi-election-signals", "source": {"name": "Global Signal Desk"}},
    ],
    "economy": [
        {"title": "Tokyo rate outlook keeps yen and Nikkei sensitive", "description": "Bank of Japan signals continue to affect currency pricing and equity positioning in Japan.", "url": "https://example.com/tokyo-rate-outlook", "source": {"name": "Global Signal Desk"}},
        {"title": "US inflation path keeps bond market on edge", "description": "Interest-rate expectations and growth concerns remain central for stocks, oil, and gold.", "url": "https://example.com/us-inflation-path", "source": {"name": "Global Signal Desk"}},
        {"title": "Trade friction raises pressure on exporters", "description": "Tariff headlines are feeding into logistics costs, currency volatility, and industrial earnings risk.", "url": "https://example.com/trade-friction-exporters", "source": {"name": "Global Signal Desk"}},
        {"title": "Seoul chip exporters monitor won and freight costs", "description": "Technology exporters are balancing FX pressure with softer demand and shipping uncertainty.", "url": "https://example.com/seoul-chip-exporters", "source": {"name": "Global Signal Desk"}},
        {"title": "London bond market reacts to growth and rate outlook", "description": "Government-bond pricing reflects a tighter link between recession concerns and policy expectations.", "url": "https://example.com/london-bond-outlook", "source": {"name": "Global Signal Desk"}},
        {"title": "Beijing policy easing revives commodity expectations", "description": "Industrial metals and shipping names are reacting to possible demand support from China.", "url": "https://example.com/beijing-policy-easing", "source": {"name": "Global Signal Desk"}},
        {"title": "New York equity desks rotate into defensive names", "description": "Traders are reducing cyclical exposure as growth and rate expectations shift.", "url": "https://example.com/new-york-defensive-rotation", "source": {"name": "Global Signal Desk"}},
        {"title": "Paris exporters confront weaker demand outlook", "description": "European manufacturers are recalibrating guidance as orders soften.", "url": "https://example.com/paris-export-demand", "source": {"name": "Global Signal Desk"}},
        {"title": "Jakarta currency pressure affects import pricing", "description": "A softer local currency is increasing costs for fuel and imported inputs.", "url": "https://example.com/jakarta-currency-pressure", "source": {"name": "Global Signal Desk"}},
        {"title": "Sydney miners track China demand and oil swings", "description": "Commodity-linked equities remain sensitive to macro and trade headlines.", "url": "https://example.com/sydney-miners-demand", "source": {"name": "Global Signal Desk"}},
    ],
    "disaster": [
        {"title": "Typhoon disruption pressures Asian transport routes", "description": "Ports, flights, and regional trucking networks are facing knock-on disruption risk.", "url": "https://example.com/typhoon-transport-routes", "source": {"name": "Global Signal Desk"}},
        {"title": "Earthquake damage review slows industrial recovery", "description": "Manufacturing and logistics operators are reassessing output schedules after the shock.", "url": "https://example.com/earthquake-industrial-recovery", "source": {"name": "Global Signal Desk"}},
        {"title": "Wildfire response expands supply-chain monitoring", "description": "Road closures and insurance-loss estimates are now key variables for nearby businesses.", "url": "https://example.com/wildfire-supply-chain", "source": {"name": "Global Signal Desk"}},
        {"title": "Jakarta flood damage slows port and truck movement", "description": "Logistics operators are adjusting schedules as water damage delays cargo transfers and inland transport.", "url": "https://example.com/jakarta-flood-logistics", "source": {"name": "Global Signal Desk"}},
        {"title": "Tokyo quake readiness keeps supply hubs on alert", "description": "Manufacturing and transport firms are reassessing continuity plans after renewed seismic warnings.", "url": "https://example.com/tokyo-quake-readiness", "source": {"name": "Global Signal Desk"}},
        {"title": "Seoul storm disruption affects airport operations", "description": "Air and road transport schedules are tightening as weather risks increase.", "url": "https://example.com/seoul-storm-airport", "source": {"name": "Global Signal Desk"}},
        {"title": "Sydney bushfire smoke disrupts logistics planning", "description": "Carriers and insurers are reviewing route safety and operational exposure.", "url": "https://example.com/sydney-bushfire-logistics", "source": {"name": "Global Signal Desk"}},
        {"title": "Beijing flood response tests urban transport resilience", "description": "Heavy rain and water damage are complicating freight and commuter movement.", "url": "https://example.com/beijing-flood-response", "source": {"name": "Global Signal Desk"}},
        {"title": "Riyadh heat risk strains infrastructure maintenance", "description": "Utility and transport operators are adjusting schedules as temperatures rise.", "url": "https://example.com/riyadh-heat-risk", "source": {"name": "Global Signal Desk"}},
        {"title": "Ankara quake drills prompt fresh supply-chain checks", "description": "Manufacturers are reviewing continuity plans as disaster readiness returns to focus.", "url": "https://example.com/ankara-quake-drills", "source": {"name": "Global Signal Desk"}},
    ],
}

LOCATION_CATALOG = [
    {"label": "Tehran", "label_ko": "Tehran, Iran", "keywords": ["tehran", "iran"], "lat": 35.6892, "lng": 51.3890, "country": "IR", "continent": "Asia"},
    {"label": "Israel", "label_ko": "Israel", "keywords": ["tel aviv", "jerusalem", "israel", "gaza", "west bank"], "lat": 31.7683, "lng": 35.2137, "country": "IL", "continent": "Asia"},
    {"label": "Lebanon", "label_ko": "Lebanon", "keywords": ["beirut", "lebanon"], "lat": 33.8938, "lng": 35.5018, "country": "LB", "continent": "Asia"},
    {"label": "Syria", "label_ko": "Syria", "keywords": ["damascus", "syria"], "lat": 33.5138, "lng": 36.2765, "country": "SY", "continent": "Asia"},
    {"label": "Ukraine", "label_ko": "Ukraine", "keywords": ["kyiv", "ukraine"], "lat": 50.4501, "lng": 30.5234, "country": "UA", "continent": "Europe"},
    {"label": "Russia", "label_ko": "Russia", "keywords": ["moscow", "russia", "kremlin"], "lat": 55.7558, "lng": 37.6173, "country": "RU", "continent": "Europe"},
    {"label": "Brussels", "label_ko": "Brussels, Belgium", "keywords": ["brussels", "european union", "european commission", "eu commission"], "lat": 50.8503, "lng": 4.3517, "country": "BE", "continent": "Europe"},
    {"label": "London", "label_ko": "London, UK", "keywords": ["london", "britain", "england", "bank of england", "uk treasury"], "lat": 51.5072, "lng": -0.1276, "country": "GB", "continent": "Europe"},
    {"label": "Paris", "label_ko": "Paris, France", "keywords": ["paris", "france"], "lat": 48.8566, "lng": 2.3522, "country": "FR", "continent": "Europe"},
    {"label": "Berlin", "label_ko": "Berlin, Germany", "keywords": ["berlin", "germany"], "lat": 52.5200, "lng": 13.4050, "country": "DE", "continent": "Europe"},
    {"label": "Washington", "label_ko": "Washington, US", "keywords": ["washington", "white house", "united states", "u.s.", "u.s. ", "usa", "america"], "lat": 38.9072, "lng": -77.0369, "country": "US", "continent": "NorthAmerica"},
    {"label": "New York", "label_ko": "New York, US", "keywords": ["new york", "wall street"], "lat": 40.7128, "lng": -74.0060, "country": "US", "continent": "NorthAmerica"},
    {"label": "Los Angeles", "label_ko": "Los Angeles, US", "keywords": ["california", "los angeles"], "lat": 34.0522, "lng": -118.2437, "country": "US", "continent": "NorthAmerica"},
    {"label": "Tokyo", "label_ko": "Tokyo, Japan", "keywords": ["tokyo", "japan", "nikkei", "yen", "bank of japan", "boj", "osaka"], "lat": 35.6762, "lng": 139.6503, "country": "JP", "continent": "Asia"},
    {"label": "Seoul", "label_ko": "Seoul, Korea", "keywords": ["seoul", "south korea", "korea", "kospi", "won"], "lat": 37.5665, "lng": 126.9780, "country": "KR", "continent": "Asia"},
    {"label": "Beijing", "label_ko": "Beijing, China", "keywords": ["beijing", "china", "yuan", "pboc"], "lat": 39.9042, "lng": 116.4074, "country": "CN", "continent": "Asia"},
    {"label": "Taipei", "label_ko": "Taipei, Taiwan", "keywords": ["taipei", "taiwan"], "lat": 25.0330, "lng": 121.5654, "country": "TW", "continent": "Asia"},
    {"label": "Jakarta", "label_ko": "Jakarta, Indonesia", "keywords": ["jakarta", "indonesia"], "lat": -6.2088, "lng": 106.8456, "country": "ID", "continent": "Asia"},
    {"label": "Ankara", "label_ko": "Ankara, Turkiye", "keywords": ["ankara", "istanbul", "turkey"], "lat": 39.9334, "lng": 32.8597, "country": "TR", "continent": "Asia"},
    {"label": "New Delhi", "label_ko": "New Delhi, India", "keywords": ["new delhi", "india", "rupee"], "lat": 28.6139, "lng": 77.2090, "country": "IN", "continent": "Asia"},
    {"label": "Islamabad", "label_ko": "Islamabad, Pakistan", "keywords": ["islamabad", "pakistan"], "lat": 33.6844, "lng": 73.0479, "country": "PK", "continent": "Asia"},
    {"label": "Riyadh", "label_ko": "Riyadh, Saudi Arabia", "keywords": ["riyadh", "saudi arabia"], "lat": 24.7136, "lng": 46.6753, "country": "SA", "continent": "Asia"},
    {"label": "Khartoum", "label_ko": "Khartoum, Sudan", "keywords": ["khartoum", "sudan"], "lat": 15.5007, "lng": 32.5599, "country": "SD", "continent": "Africa"},
    {"label": "Sydney", "label_ko": "Sydney, Australia", "keywords": ["sydney", "australia"], "lat": -33.8688, "lng": 151.2093, "country": "AU", "continent": "Oceania"},
]

CATEGORY_NEUTRAL_LOCATIONS = {
    "home": {"lat": 22.0, "lng": 18.0, "country": "GL", "continent": "Global", "location_label": "Global"},
    "war": {"lat": 31.0, "lng": 38.0, "country": "GL", "continent": "Global", "location_label": "Conflict Zone"},
    "politics": {"lat": 35.0, "lng": 8.0, "country": "GL", "continent": "Global", "location_label": "Global Politics"},
    "economy": {"lat": 28.0, "lng": 18.0, "country": "GL", "continent": "Global", "location_label": "Global Market"},
    "disaster": {"lat": 16.0, "lng": 110.0, "country": "GL", "continent": "Global", "location_label": "Risk Zone"},
}

COUNTRY_LABELS = {
    "IR": "Iran", "IL": "Israel", "LB": "Lebanon", "SY": "Syria", "UA": "Ukraine", "RU": "Russia",
    "BE": "Belgium", "GB": "United Kingdom", "FR": "France", "DE": "Germany", "US": "United States", "JP": "Japan", "KR": "Korea",
    "CN": "China", "TW": "Taiwan", "ID": "Indonesia", "TR": "Turkiye", "IN": "India", "PK": "Pakistan",
    "SA": "Saudi Arabia", "SD": "Sudan", "AU": "Australia", "GL": "Global",
}

AI_KEYWORDS = {
    "war": {
        "military": ["missile", "airstrike", "shelling", "troops", "drone attack", "military"],
        "negotiation": ["ceasefire", "talks", "summit", "negotiation"],
    },
    "politics": {
        "election": ["election", "vote", "poll", "campaign"],
        "diplomacy": ["summit", "diplomacy", "foreign minister", "allies"],
        "policy": ["parliament", "cabinet", "bill", "ministry", "government"],
    },
    "economy": {
        "rates": ["interest rate", "rates", "central bank", "bank of japan", "boj", "fed"],
        "inflation": ["inflation", "prices", "cpi", "pce"],
        "trade": ["tariff", "exports", "imports", "trade"],
        "currency": ["yen", "dollar", "won", "yuan", "currency", "fx"],
        "market": ["stocks", "equity", "bond yields", "nikkei", "s&p", "market"],
    },
    "disaster": {
        "quake": ["earthquake", "aftershock", "tsunami"],
        "weather": ["storm", "hurricane", "typhoon", "flood", "wildfire"],
        "supply": ["supply chain", "port", "shipping", "airport", "rail"],
    },
}


def resolve_location(article: dict[str, Any], category: str, index: int) -> dict[str, Any]:
    text = article_text(article)
    title_text = ((article.get("title_original") or article.get("title") or "") + " " + (article.get("summary_original") or article.get("description") or "")).lower()

    best_entry = None
    best_score = 0.0
    for entry in LOCATION_CATALOG:
        score = 0.0
        for keyword in entry["keywords"]:
            if keyword in text:
                score += 1.0 + (0.6 if keyword in title_text else 0.0) + min(len(keyword.split()) * 0.15, 0.5)
        if score > best_score:
            best_score = score
            best_entry = entry

    if best_entry is not None and best_score > 0:
        return {
            "lat": best_entry["lat"],
            "lng": best_entry["lng"],
            "country": best_entry["country"],
            "country_name": COUNTRY_LABELS.get(best_entry["country"], best_entry.get("label_ko", best_entry["country"])),
            "continent": best_entry["continent"],
            "location_label": best_entry.get("label_ko", best_entry["country"]),
            "matched": True,
            "confidence": round(min(best_score / 3.0, 1.0), 2),
        }

    neutral = dict(CATEGORY_NEUTRAL_LOCATIONS.get(category, CATEGORY_NEUTRAL_LOCATIONS["home"]))
    offsets = [(-3.0, -6.0), (2.5, 8.0), (4.0, -9.0), (-4.5, 6.5), (0.0, 12.0)]
    lat_offset, lng_offset = offsets[index % len(offsets)]
    neutral["lat"] = round(neutral["lat"] + lat_offset, 4)
    neutral["lng"] = round(neutral["lng"] + lng_offset, 4)
    neutral["country_name"] = COUNTRY_LABELS.get(neutral["country"], neutral["location_label"])
    neutral["matched"] = False
    neutral["confidence"] = 0.0
    return neutral


def first_matching_theme(text: str, category: str) -> str | None:
    category_keywords = AI_KEYWORDS.get(category, {})
    for theme, keywords in category_keywords.items():
        if any(keyword in text for keyword in keywords):
            return theme
    return None


def choose_pin_color(category: str, article: dict[str, Any], index: int) -> str:
    text = article_text(article)
    theme = first_matching_theme(text, category)

    if category == "war":
        if theme == "military":
            return "#EF4444"
        if theme == "negotiation":
            return "#2563EB"
        return ["#EF4444", "#F59E0B", "#8B5CF6", "#2563EB", "#22C55E"][index % 5]

    if category == "economy":
        if theme == "rates":
            return "#2563EB"
        if theme == "trade":
            return "#F59E0B"
        if theme == "currency":
            return "#22C55E"
        return ["#2563EB", "#22C55E", "#F59E0B", "#8B5CF6", "#EF4444"][index % 5]

    if category == "politics":
        return ["#F59E0B", "#2563EB", "#8B5CF6", "#22C55E", "#EF4444"][index % 5]

    if category == "disaster":
        return ["#F97316", "#EF4444", "#2563EB", "#22C55E", "#8B5CF6"][index % 5]

    return ["#2563EB", "#EF4444", "#22C55E", "#F59E0B", "#8B5CF6"][index % 5]


def build_ai_analysis(article: dict[str, Any], category: str, location: dict[str, Any]) -> dict[str, str]:
    text = article_text(article)
    location_name = location.get("location_label") or COUNTRY_LABELS.get(location.get("country", "GL"), "Global")
    theme = first_matching_theme(text, category)

    if category == "economy":
        if theme == "rates":
            opinion = f"\uc774 \uae30\uc0ac\ub294 {location_name}\uc758 \uae08\ub9ac\uc640 \uc911\uc559\uc740\ud589 \uc815\ucc45 \ubcc0\ud654\uac00 \ud575\uc2ec\uc778 \uacbd\uc81c \uc774\uc288\uc785\ub2c8\ub2e4."
            forecast = f"\ub2e8\uae30\uc801\uc73c\ub85c {location_name} \uad00\ub828 \uae08\ub9ac \uae30\ub300\uc640 \uc99d\uc2dc \ubcc0\ub3d9\uc131\uc774 \ud568\uaed8 \ucee4\uc9c8 \uac00\ub2a5\uc131\uc774 \uc788\uc2b5\ub2c8\ub2e4."
            impact = "\uae08 \uac00\uaca9, WTI \uc720\uac00, S&P500 \uac19\uc740 \ub300\ud45c \uc9c0\ud45c\uac00 \ubbfc\uac10\ud558\uac8c \ubc18\uc751\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4."
        elif theme == "trade":
            opinion = f"\uc774 \uae30\uc0ac\ub294 {location_name}\uc758 \uad00\uc138, \uc218\ucd9c\uc785, \uacf5\uae09\ub9dd \uc555\ubc15\uc774 \uc911\uc2ec\uc778 \ubb34\uc5ed \uc774\uc288\uc785\ub2c8\ub2e4."
            forecast = f"\ud6c4\uc18d \ubcf4\ub3c4\uac00 \uc774\uc5b4\uc9c0\uba74 {location_name}\uc640 \uc5f0\uacb0\ub41c \ubb3c\ub958 \ud750\ub984\uacfc \ud658\uc728 \uae30\ub300\uac00 \ub354 \ud754\ub4e4\ub9b4 \uc218 \uc788\uc2b5\ub2c8\ub2e4."
            impact = "\ubb34\uc5ed \uad00\ub828 \uc5c5\uc885, \ud658\uc728, \uc6d0\uc790\uc7ac \uac00\uaca9, \ubb3c\ub958 \ube44\uc6a9\uc774 \uc9c1\uc811 \uc601\ud5a5\uc744 \ubc1b\uc744 \uc218 \uc788\uc2b5\ub2c8\ub2e4."
        elif theme == "currency":
            opinion = f"\uc774 \uae30\uc0ac\ub294 {location_name}\uc758 \ud1b5\ud654 \ubc29\ud5a5\uc131\uacfc \uc678\ud658\uc2dc\uc7a5 \uc2ec\ub9ac\ub97c \uc77d\ub294 \ub370 \uc911\uc694\ud55c \uc2e0\ud638\uc785\ub2c8\ub2e4."
            forecast = f"\ub2e8\uae30\uc801\uc73c\ub85c \ud658\uc728 \ubcc0\ub3d9\uc131\uc774 \ud655\ub300\ub418\uba74\uc11c \uc218\uc785\uc8fc\uc640 \uc218\ucd9c\uc8fc \uac04 \ucc28\ubcc4\ud654\uac00 \ucee4\uc9c8 \uc218 \uc788\uc2b5\ub2c8\ub2e4."
            impact = "\ud658\uc728, \uae08\ub9ac \uae30\ub300, \ud574\uc678 \uc790\uae08 \ud750\ub984, \uc8fc\uc2dd\uc2dc\uc7a5 \uc2ec\ub9ac\uac00 \ud568\uaed8 \uc6c0\uc9c1\uc77c \uac00\ub2a5\uc131\uc774 \uc788\uc2b5\ub2c8\ub2e4."
        else:
            opinion = f"\uc774 \uae30\uc0ac\ub294 {location_name}\uc640 \uc5f0\uacb0\ub41c \uc2dc\uc7a5 \ubbfc\uac10\ud615 \uacbd\uc81c \ub274\uc2a4\uc785\ub2c8\ub2e4."
            forecast = "\ud6c4\uc18d \ubcf4\ub3c4\uac00 \ub298\uc5b4\ub098\uba74 \uac70\uc2dc\uc9c0\ud45c\uc640 \uc704\ud5d8\uc120\ud638\uac00 \ud568\uaed8 \ud754\ub4e4\ub9b4 \uc218 \uc788\uc2b5\ub2c8\ub2e4."
            impact = "\uae08, \uc720\uac00, \uc8fc\uc2dd, \ud658\uc728\uc774 \uc21c\ucc28\uc801\uc73c\ub85c \ubc18\uc751\ud560 \uac00\ub2a5\uc131\uc774 \uc788\uc2b5\ub2c8\ub2e4."
    elif category == "war":
        if theme == "military":
            opinion = f"\uc774 \uae30\uc0ac\ub294 {location_name} \uc8fc\ubcc0\uc758 \uad70\uc0ac \uae34\uc7a5\uacfc \ucda9\ub3cc \uac15\ub3c4\uac00 \ub192\uc544\uc9c0\ub294 \uc2e0\ud638\ub85c \ubcfc \uc218 \uc788\uc2b5\ub2c8\ub2e4."
            forecast = "\ubcf4\ubcf5\uc774\ub098 \ucd94\uac00 \uacf5\uaca9\uc774 \uc774\uc5b4\uc9c0\uba74 \uc548\uc804\uc790\uc0b0 \uc218\uc694\uc640 \uc5d0\ub108\uc9c0 \uac00\uaca9 \uc555\ub825\uc774 \ub354 \ucee4\uc9c8 \uc218 \uc788\uc2b5\ub2c8\ub2e4."
            impact = "\uae08 \uac00\uaca9, \uc720\uac00, \ubc29\uc0b0\uc8fc, \uc804\ubc18\uc801\uc778 \uc704\ud5d8\ud68c\ud53c \uc2ec\ub9ac\uac00 \ube60\ub974\uac8c \ubc18\uc751\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4."
        elif theme == "negotiation":
            opinion = f"\uc774 \uae30\uc0ac\ub294 {location_name} \uc8fc\ubcc0\uc5d0\uc11c \ud734\uc804 \ub610\ub294 \ud611\uc0c1 \uc2e0\ud638\uac00 \uac10\uc9c0\ub418\ub294 \uc0c1\ud669\uc785\ub2c8\ub2e4."
            forecast = "\ud611\uc0c1\uc774 \uc9c4\uc804\ub418\uba74 \ub2e8\uae30 \ubcc0\ub3d9\uc131\uc740 \uc644\ud654\ub420 \uc218 \uc788\uc9c0\ub9cc \ud5e4\ub4dc\ub77c\uc778 \ubbfc\uac10\ub3c4\ub294 \uc5ec\uc804\ud788 \ub192\uc744 \uc218 \uc788\uc2b5\ub2c8\ub2e4."
            impact = "\uc6d0\uc790\uc7ac \uc555\ubc15\uacfc \uc548\uc804\uc790\uc0b0 \uc120\ud638\uac00 \uc77c\ubd80 \uc644\ud654\ub420 \uac00\ub2a5\uc131\uc774 \uc788\uc2b5\ub2c8\ub2e4."
        else:
            opinion = f"\uc774 \uae30\uc0ac\ub294 {location_name}\ub97c \uc911\uc2ec\uc73c\ub85c \uad70\uc0ac\uc801 \uae34\uc7a5\uacfc \uc678\uad50 \ud750\ub984\uc744 \ud568\uaed8 \ubd10\uc57c \ud558\ub294 \ubd84\uc7c1 \ub274\uc2a4\uc785\ub2c8\ub2e4."
            forecast = "\ud6c4\uc18d \ubcf4\ub3c4\uac00 \uac15\ud574\uc9c8\uc218\ub85d \uc9c0\uc5ed \uc99d\uc2dc\uc640 \uc5d0\ub108\uc9c0 \uc2dc\uc7a5\uc758 \ub2e8\uae30 \ubcc0\ub3d9\uc131\uc774 \ud655\ub300\ub420 \uc218 \uc788\uc2b5\ub2c8\ub2e4."
            impact = "\uae08, \uc720\uac00, \uc8fc\uc2dd\uc2dc\uc7a5 \uc2ec\ub9ac\uac00 \uc9c1\uc811\uc801\uc73c\ub85c \ud754\ub4e4\ub9b4 \uc218 \uc788\uc2b5\ub2c8\ub2e4."
    elif category == "politics":
        opinion = f"\uc774 \uae30\uc0ac\ub294 {location_name}\uc758 \uc815\ucc45 \ubc29\ud5a5\uacfc \uc678\uad50 \ub9ac\uc2a4\ud06c\ub97c \ud568\uaed8 \uc77d\uc5b4\uc57c \ud558\ub294 \uc815\uce58 \uc774\uc288\uc785\ub2c8\ub2e4."
        forecast = "\ucd94\uac00 \uc815\ucc45 \ubc1c\ud45c\ub098 \uc678\uad50 \uc77c\uc815\uc774 \uc774\uc5b4\uc9c0\uba74 \uaddc\uc81c, \ubb34\uc5ed, \uc81c\uc7ac \uad00\ub828 \uae30\ub300\uac00 \ube60\ub974\uac8c \uc7ac\uc870\uc815\ub420 \uc218 \uc788\uc2b5\ub2c8\ub2e4."
        impact = "\uc678\uad50 \uad00\uacc4, \ubb34\uc5ed \ud750\ub984, \uc2dc\uc7a5 \uc2ec\ub9ac, \uc5c5\uc885\ubcc4 \uaddc\uc81c \uae30\ub300\uac00 \ubcc0\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4."
    elif category == "disaster":
        opinion = f"\uc774 \uae30\uc0ac\ub294 {location_name}\uc758 \uc7ac\ub09c \ud53c\ud574\uac00 \ubb3c\ub958\uc640 \uc0dd\uc0b0 \ucc28\uc9c8\ub85c \uc774\uc5b4\uc9c8 \uac00\ub2a5\uc131\uc744 \ubcf4\uc5ec\uc90d\ub2c8\ub2e4."
        forecast = "\ud53c\ud574 \ubc94\uc704\uac00 \ucee4\uc9c0\uba74 \ud56d\ub9cc, \uacf5\ud56d, \ub3c4\ub85c, \uc0b0\uc5c5 \ubcf5\uad6c \uc77c\uc815\uc774 \ud575\uc2ec \ubcc0\uc218\ub85c \ub5a0\uc624\ub97c \uc218 \uc788\uc2b5\ub2c8\ub2e4."
        impact = "\uacf5\uae09\ub9dd, \uad50\ud1b5, \uc0b0\uc5c5 \uc0dd\uc0b0, \ubcf4\ud5d8 \uc190\uc2e4 \uae30\ub300\uac00 \ud568\uaed8 \ubc18\uc751\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4."
    else:
        opinion = f"\uc774 \uae30\uc0ac\ub294 {location_name}\uc640 \uc5f0\uacb0\ub41c \ud575\uc2ec \uae00\ub85c\ubc8c \uc774\uc288\uc785\ub2c8\ub2e4."
        forecast = "\uad00\ub828 \ud5e4\ub4dc\ub77c\uc778 \uac15\ub3c4\uac00 \ub192\uc544\uc9c8\uc218\ub85d \uc2dc\uc7a5\uacfc \uc815\ucc45\uc758 \uc5f0\uacb0\uc131\uc774 \ub354 \ucee4\uc9c8 \uc218 \uc788\uc2b5\ub2c8\ub2e4."
        impact = "\uc8fc\uc694 \uc6d0\uc790\uc7ac, \ub300\ud45c \uc9c0\uc218, \uae00\ub85c\ubc8c \ub274\uc2a4 \ud750\ub984 \uc804\ubc18\uc5d0 \uc601\ud5a5\uc744 \uc904 \uc218 \uc788\uc2b5\ub2c8\ub2e4."

    return {"opinion": opinion, "forecast": forecast, "impact": impact}


def ensure_offline_translation_ready() -> bool:
    global ARGOS_TRANSLATION_READY

    if ARGOS_TRANSLATION_READY is not None:
        return ARGOS_TRANSLATION_READY
    if argos_translate is None or argos_package is None:
        ARGOS_TRANSLATION_READY = False
        return False

    def has_translation() -> bool:
        try:
            installed_languages = argos_translate.get_installed_languages()
            from_lang = next((language for language in installed_languages if language.code == "en"), None)
            to_lang = next((language for language in installed_languages if language.code == "ko"), None)
            if from_lang is None or to_lang is None:
                return False
            return from_lang.get_translation(to_lang) is not None
        except Exception:
            return False

    if has_translation():
        ARGOS_TRANSLATION_READY = True
        return True

    try:
        ARGOS_TRANSLATION_READY = argos_package.install_package_for_language_pair("en", "ko") and has_translation()
    except Exception:
        ARGOS_TRANSLATION_READY = False
    return ARGOS_TRANSLATION_READY


def translate_text_offline(text: str) -> str:
    if not text or argos_translate is None:
        return text
    if not ensure_offline_translation_ready():
        return text

    try:
        installed_languages = argos_translate.get_installed_languages()
        from_lang = next((language for language in installed_languages if language.code == "en"), None)
        to_lang = next((language for language in installed_languages if language.code == "ko"), None)
        if from_lang is None or to_lang is None:
            return text
        translation = from_lang.get_translation(to_lang)
        return translation.translate(text) or text
    except Exception:
        return text


def translate_articles_to_korean_offline(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    translated_articles = []
    for article in articles:
        article_copy = dict(article)
        article_copy["title_original"] = article.get("title")
        article_copy["summary_original"] = article.get("description")
        article_copy["title"] = translate_text_offline(article.get("title") or "")
        article_copy["description"] = translate_text_offline(article.get("description") or "")
        translated_articles.append(article_copy)
    return translated_articles


async def translate_articles_to_korean(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not articles:
        return articles

    if not OPENAI_API_KEY:
        return translate_articles_to_korean_offline(articles)

    payload_articles = [
        {
            "index": index,
            "title": article.get("title") or "",
            "summary": article.get("description") or "",
        }
        for index, article in enumerate(articles)
    ]

    prompt = {
        "role": "user",
        "content": (
            "Translate each news item's title and summary into natural Korean. "
            "Return JSON array only with objects shaped as {index, title_ko, summary_ko}. "
            "Keep names of people, places, organizations accurate.\n" + json.dumps(payload_articles, ensure_ascii=False)
        ),
    }

    body = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": "You are a precise Korean news translator. Return valid JSON only."},
            prompt,
        ],
        "temperature": 0.2,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"]
        translated_rows = json.loads(content)
        translated_by_index = {row["index"]: row for row in translated_rows if isinstance(row, dict) and "index" in row}

        translated_articles = []
        for index, article in enumerate(articles):
            row = translated_by_index.get(index, {})
            article_copy = dict(article)
            article_copy["title_original"] = article.get("title")
            article_copy["summary_original"] = article.get("description")
            article_copy["title"] = row.get("title_ko") or article.get("title")
            article_copy["description"] = row.get("summary_ko") or article.get("description")
            translated_articles.append(article_copy)
        return translated_articles
    except Exception:
        return translate_articles_to_korean_offline(articles)


def article_relevance_text(article: dict[str, Any]) -> str:
    title = article.get("title_original") or article.get("title") or ""
    description = article.get("summary_original") or article.get("description") or ""
    return f"{title} {description}".lower()


def article_text(article: dict[str, Any]) -> str:
    text = article_relevance_text(article)
    url = article.get("url") or ""
    source_name = article.get("source", {}).get("name") if isinstance(article.get("source"), dict) else article.get("source") or ""
    return f"{text} {url} {source_name}".lower()


def article_score(article: dict[str, Any], config: dict[str, Any]) -> int:
    text = article_relevance_text(article)
    title_text = (article.get("title_original") or article.get("title") or "").lower()
    include_any = config.get("include_any", [])
    score = 0
    for term in include_any:
        normalized = term.lower()
        if normalized in text:
            score += 1
        if normalized in title_text:
            score += 2
    return score


def filter_articles_for_category(articles: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    filtered = []
    for article in articles:
        text = article_relevance_text(article)
        if not text.strip():
            continue
        include_any = config.get("include_any", [])
        exclude_any = config.get("exclude_any", [])
        include_matches = sum(1 for term in include_any if term.lower() in text)
        if include_any and include_matches == 0:
            continue
        if exclude_any and any(term.lower() in text for term in exclude_any):
            continue
        filtered.append(article)

    filtered.sort(key=lambda item: article_score(item, config), reverse=True)
    return filtered


def spread_pin_position(location: dict[str, Any], occurrence: int) -> tuple[float, float]:
    offsets = [
        (0.0, 0.0),
        (0.7, 1.1),
        (-0.8, 1.3),
        (0.9, -1.2),
        (-1.0, -1.0),
        (1.3, 0.3),
        (-1.4, 0.4),
        (0.5, 1.9),
        (-0.6, -1.8),
        (1.7, -0.5),
    ]
    lat_offset, lng_offset = offsets[occurrence % len(offsets)]
    return round(location["lat"] + lat_offset, 4), round(location["lng"] + lng_offset, 4)


def build_news_payload(current_category: str, articles: list[dict[str, Any]], *, message: str, source_type: str) -> dict[str, Any]:
    config = CATEGORY_NEWS_CONFIG[current_category]
    top_headlines: list[dict[str, Any]] = []
    map_pins: list[dict[str, Any]] = []
    location_counts: dict[str, int] = {}

    for i, article in enumerate(articles):
        location = resolve_location(article, current_category, i)
        analysis = build_ai_analysis(article, current_category, location)
        source_name = article.get("source", {}).get("name") if isinstance(article.get("source"), dict) else article.get("source")
        location_key = f"{location['location_label']}::{location['country']}"
        occurrence = location_counts.get(location_key, 0)
        location_counts[location_key] = occurrence + 1
        pin_lat, pin_lng = spread_pin_position(location, occurrence)
        headline = {
            "id": f"news_{i}",
            "title": article.get("title"),
            "source": source_name,
            "summary": article.get("description"),
            "url": article.get("url"),
            "country": location["country"],
            "location_label": location["location_label"],
        }
        top_headlines.append(headline)

        pin = {
            "id": f"news_{i}",
            "title": article.get("title"),
            "summary": article.get("description"),
            "url": article.get("url"),
            "source": source_name,
            "lat": pin_lat,
            "lng": pin_lng,
            "category": current_category,
            "country": location["country"],
            "country_name": location["country_name"],
            "location_label": location["location_label"],
            "matched_location": location["matched"],
            "location_confidence": location["confidence"],
            "pin_color": choose_pin_color(current_category, article, i),
            "ai_opinion": analysis["opinion"],
            "ai_forecast": analysis["forecast"],
            "ai_impact": analysis["impact"],
        }
        map_pins.append(pin)

    payload = {
        "success": True,
        "message": message,
        "source_type": source_type,
        "data": {
            "map_pins": map_pins,
            "top_headlines": top_headlines,
        },
    }
    NEWS_RESULT_CACHE[current_category] = payload
    return payload


def build_fallback_news_response(current_category: str, reason: str) -> dict[str, Any]:
    return {
        "success": True,
        "message": f"Live article load failed: {reason}",
        "source_type": "unavailable",
        "data": {
            "map_pins": [],
            "top_headlines": [],
        },
    }


async def get_database(request: Request):
    database = getattr(request.app.state, "mongo_db", None)
    if database is None:
        detail = getattr(request.app.state, "mongo_error", None) or "MongoDB is not connected"
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)
    return database


class SessionLoginRequest(BaseModel):
    nickname: str = Field(..., min_length=2, max_length=24)


class SessionResponse(BaseModel):
    authenticated: bool
    nickname: str | None = None


def normalize_nickname(nickname: str) -> tuple[str, str]:
    cleaned = " ".join((nickname or "").split()).strip()
    if len(cleaned) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nickname must be at least 2 characters.")
    return cleaned, cleaned.casefold()


def request_uses_secure_cookie(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return forwarded_proto == "https" or request.url.scheme == "https"


def encode_cookie_payload(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cookie_payload(value: str | None, *, default: Any) -> Any:
    if not value:
        return default
    try:
        padding = "=" * (-len(value) % 4)
        raw = base64.urlsafe_b64decode((value + padding).encode("ascii"))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return default


def get_cookie_saved_articles(request: Request) -> list[dict[str, Any]]:
    payload = decode_cookie_payload(request.cookies.get(FALLBACK_SAVED_COOKIE_NAME), default=[])
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def set_cookie_saved_articles(response: Response, request: Request, articles: list[dict[str, Any]]) -> None:
    response.set_cookie(
        key=FALLBACK_SAVED_COOKIE_NAME,
        value=encode_cookie_payload(articles[:MAX_FALLBACK_SAVED_ARTICLES]),
        httponly=True,
        samesite="lax",
        secure=request_uses_secure_cookie(request),
        max_age=COOKIE_MAX_AGE_SECONDS,
    )


async def get_optional_session_user(request: Request) -> dict[str, Any] | None:
    database = getattr(request.app.state, "mongo_db", None)
    if database is None:
        fallback_nickname = request.cookies.get(FALLBACK_AUTH_COOKIE_NAME)
        if not fallback_nickname:
            return None
        nickname, nickname_key = normalize_nickname(fallback_nickname)
        return {
            "session_token": None,
            "user_id": f"cookie:{nickname_key}",
            "nickname": nickname,
            "storage": "cookie",
        }

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    session = await database.user_sessions.find_one({"token": token})
    if session is None:
        return None

    user = await database.users.find_one({"_id": session.get("user_id")})
    if user is None:
        return None

    await database.user_sessions.update_one(
        {"_id": session["_id"]},
        {"$set": {"last_seen_at": datetime.now(timezone.utc)}},
    )
    return {
        "session_token": token,
        "user_id": user["_id"],
        "nickname": user.get("nickname", "Guest"),
        "storage": "database",
    }


async def require_session_user(session_user: dict[str, Any] | None = Depends(get_optional_session_user)) -> dict[str, Any]:
    if session_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please log in to continue.")
    return session_user


class SavedArticleCreate(BaseModel):
    article_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    category: Literal["home", "war", "politics", "economy", "disaster"] = "home"
    source: str | None = None
    summary: str | None = None
    region: str | None = None
    continent: str | None = None
    location_label: str | None = None
    country: str | None = None
    country_name: str | None = None
    lat: float | None = None
    lng: float | None = None
    pin_color: str | None = None


class SavedArticleResponse(SavedArticleCreate):
    id: str
    saved_at: str
    nickname: str | None = None


def serialize_saved_article(document: dict[str, Any]) -> SavedArticleResponse:
    return SavedArticleResponse(
        id=str(document["_id"]),
        article_id=document["article_id"],
        title=document["title"],
        url=document["url"],
        category=document["category"],
        source=document.get("source"),
        summary=document.get("summary"),
        region=document.get("region"),
        continent=document.get("continent"),
        location_label=document.get("location_label"),
        country=document.get("country"),
        country_name=document.get("country_name"),
        lat=document.get("lat"),
        lng=document.get("lng"),
        pin_color=document.get("pin_color"),
        nickname=document.get("nickname"),
        saved_at=document["saved_at"].astimezone(timezone.utc).isoformat(),
    )


def serialize_cookie_saved_article(document: dict[str, Any]) -> SavedArticleResponse:
    return SavedArticleResponse(
        id=str(document["id"]),
        article_id=document["article_id"],
        title=document["title"],
        url=document["url"],
        category=document["category"],
        source=document.get("source"),
        summary=document.get("summary"),
        region=document.get("region"),
        continent=document.get("continent"),
        location_label=document.get("location_label"),
        country=document.get("country"),
        country_name=document.get("country_name"),
        lat=document.get("lat"),
        lng=document.get("lng"),
        pin_color=document.get("pin_color"),
        nickname=document.get("nickname"),
        saved_at=document["saved_at"],
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.mongo_client = None
    app.state.mongo_db = None
    app.state.mongo_error = None

    if MONGODB_URL:
        try:
            client = AsyncMongoClient(MONGODB_URL, server_api=ServerApi("1"))
            database = client.get_database(MONGODB_DB_NAME)
            await database.command("ping")
            app.state.mongo_client = client
            app.state.mongo_db = database
        except Exception as exc:  # pragma: no cover
            app.state.mongo_error = str(exc)
    else:
        app.state.mongo_error = "MONGODB_URL is not configured"

    yield

    client = app.state.mongo_client
    if client is not None:
        close_result = client.close()
        if close_result is not None:
            await close_result


app = FastAPI(title="Global Signal Map API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.include_router(market_router)

@app.get("/", include_in_schema=False)
async def read_index():
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/info")
async def root() -> dict[str, Any]:
    return {
        "service": "global-signal-map-api",
        "mongodb_connected": bool(app.state.mongo_db),
        "database": MONGODB_DB_NAME,
    }


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "mongodb_connected": bool(app.state.mongo_db),
        "database": MONGODB_DB_NAME,
        "error": app.state.mongo_error,
    }


@app.get("/api/health/db")
async def db_health(database=Depends(get_database)) -> dict[str, Any]:
    ping = await database.command("ping")
    return {"status": "ok", "ping": ping.get("ok", 0), "database": MONGODB_DB_NAME}


def format_gdelt_term(term: str) -> str:
    cleaned = (term or "").strip()
    if not cleaned:
        return ""
    return f'"{cleaned}"' if " " in cleaned else cleaned


def build_gdelt_request_params(config: dict[str, Any], *, keyword: str | None = None, max_records: int = 50) -> dict[str, Any]:
    include_parts = []
    for term in config.get("include_any", []):
        formatted_term = format_gdelt_term(term)
        if formatted_term:
            include_parts.append(formatted_term)

    exclude_parts = []
    for term in config.get("exclude_any", []):
        formatted_term = format_gdelt_term(term)
        if formatted_term:
            exclude_parts.append(f'-{formatted_term}')

    keyword_term = format_gdelt_term(keyword or "")
    if keyword_term and include_parts:
        gdelt_query = f"({keyword_term}) AND ({' OR '.join(include_parts)}) {' '.join(exclude_parts)}".strip()
    elif keyword_term:
        gdelt_query = f"{keyword_term} {' '.join(exclude_parts)}".strip()
    else:
        gdelt_query = f"({' OR '.join(include_parts)}) {' '.join(exclude_parts)}".strip()

    return {
        "query": gdelt_query,
        "mode": "ArtList",
        "maxrecords": max_records,
        "format": "json",
        "timespan": "3d",
        "sort": "DateDesc",
    }


def build_news_api_request_params(config: dict[str, Any], *, keyword: str | None = None, page_size: int = 30) -> dict[str, Any]:
    query = config.get("query", "").strip()
    cleaned_keyword = (keyword or "").strip()
    if cleaned_keyword:
        query = f"({cleaned_keyword}) AND ({query})" if query else cleaned_keyword

    return {
        "q": query,
        "pageSize": page_size,
        "language": "en",
        "sortBy": "publishedAt",
        "searchIn": "title,description",
    }


def build_news_api_request_cache_key(params: dict[str, Any]) -> str:
    return json.dumps(params, sort_keys=True)


async def fetch_news_api_articles_from_api(params: dict[str, Any]) -> list[dict[str, Any]]:
    if not NEWSAPI_API_KEY:
        raise RuntimeError("NEWSAPI_API_KEY is not configured")

    url = "https://newsapi.org/v2/everything"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            url,
            params=params,
            headers={"X-Api-Key": NEWSAPI_API_KEY},
        )
        response.raise_for_status()

    news_data = response.json()
    raw_articles: list[dict[str, Any]] = []
    if news_data and "articles" in news_data:
        for article in news_data["articles"]:
            raw_articles.append({
                "title": article.get("title"),
                "description": article.get("description") or article.get("title"),
                "url": article.get("url"),
                "source": {"name": (article.get("source") or {}).get("name")},
                "publishedAt": article.get("publishedAt"),
            })
    return raw_articles


async def fetch_news_api_articles(config: dict[str, Any], *, keyword: str | None = None, page_size: int = 30) -> list[dict[str, Any]]:
    params = build_news_api_request_params(config, keyword=keyword, page_size=page_size)
    cache_key = build_news_api_request_cache_key(params)
    now = datetime.now(timezone.utc)
    cached_entry = NEWS_API_REQUEST_CACHE.get(cache_key)
    if cached_entry is not None and cached_entry["expires_at"] > now:
        return cached_entry["articles"]

    inflight_request = NEWS_API_INFLIGHT_REQUESTS.get(cache_key)
    if inflight_request is not None:
        return await inflight_request

    request_task = asyncio.create_task(fetch_news_api_articles_from_api(params))
    NEWS_API_INFLIGHT_REQUESTS[cache_key] = request_task

    try:
        raw_articles = await request_task
        NEWS_API_REQUEST_CACHE[cache_key] = {
            "articles": raw_articles,
            "expires_at": datetime.now(timezone.utc) + timedelta(seconds=NEWS_API_REQUEST_CACHE_TTL_SECONDS),
        }
        return raw_articles
    finally:
        if NEWS_API_INFLIGHT_REQUESTS.get(cache_key) is request_task:
            NEWS_API_INFLIGHT_REQUESTS.pop(cache_key, None)


async def load_news_from_newsapi(current_category: str, *, keyword: str | None = None) -> dict[str, Any]:
    config = CATEGORY_NEWS_CONFIG[current_category]
    normalized_keyword = (keyword or "").strip()

    try:
        raw_articles = await fetch_news_api_articles(config, keyword=normalized_keyword or None)
        filtered_articles = filter_articles_for_category(raw_articles, config)
        if normalized_keyword:
            filtered_articles = [article for article in (filtered_articles or raw_articles) if normalized_keyword.casefold() in article_text(article)]
        selected_articles = (filtered_articles or raw_articles)[:10]
        translated_articles = await translate_articles_to_korean(selected_articles)
        message = "News loaded successfully from NewsAPI"
        if normalized_keyword:
            message = f'News loaded successfully from NewsAPI for keyword "{normalized_keyword}"'
        return build_news_payload(
            current_category,
            translated_articles,
            message=message,
            source_type="live_newsapi",
        )
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        try:
            error_detail = exc.response.json().get("message", exc.response.text)
        except Exception:
            error_detail = exc.response.text

        if status_code == 429:
            cached = NEWS_RESULT_CACHE.get(current_category)
            if cached:
                cached_response = dict(cached)
                cached_response["message"] = f"Cached news loaded because NewsAPI limit was likely exceeded: {error_detail}"
                cached_response["source_type"] = "cache"
                return cached_response
            return build_fallback_news_response(current_category, f"NewsAPI limit exceeded: {error_detail}")

        return build_fallback_news_response(current_category, f"NewsAPI HTTP {status_code}: {error_detail}")
    except Exception as exc:
        cached = NEWS_RESULT_CACHE.get(current_category)
        if cached:
            cached_response = dict(cached)
            cached_response["message"] = f"Cached news loaded because live NewsAPI fetch failed: {exc}"
            cached_response["source_type"] = "cache"
            return cached_response
        return build_fallback_news_response(current_category, f"Live NewsAPI fetch failed: {exc}")


@app.get("/api/news/home")
async def get_home_news(category: str = "home", keyword: str | None = None):
    current_category = category if category in CATEGORY_NEWS_CONFIG else "home"
    return await load_news_from_newsapi(current_category, keyword=keyword)


@app.get("/api/news/category/{category}")
async def get_category_news(category: Literal["war", "politics", "economy", "disaster"], keyword: str | None = None):
    return await load_news_from_newsapi(category, keyword=keyword)


@app.get("/api/auth/session", response_model=SessionResponse)
async def get_auth_session(session_user: dict[str, Any] | None = Depends(get_optional_session_user)) -> SessionResponse:
    if session_user is None:
        return SessionResponse(authenticated=False, nickname=None)
    return SessionResponse(authenticated=True, nickname=session_user["nickname"])


@app.post("/api/auth/login", response_model=SessionResponse)
async def login(request: Request, payload: SessionLoginRequest, response: Response) -> SessionResponse:
    nickname, nickname_key = normalize_nickname(payload.nickname)
    secure_cookie = request_uses_secure_cookie(request)
    database = getattr(request.app.state, "mongo_db", None)

    if database is None:
        response.set_cookie(
            key=FALLBACK_AUTH_COOKIE_NAME,
            value=nickname,
            httponly=True,
            samesite="lax",
            secure=secure_cookie,
            max_age=COOKIE_MAX_AGE_SECONDS,
        )
        return SessionResponse(authenticated=True, nickname=nickname)

    user = await database.users.find_one({"nickname_key": nickname_key})
    if user is None:
        insert_result = await database.users.insert_one(
            {
                "nickname": nickname,
                "nickname_key": nickname_key,
                "created_at": datetime.now(timezone.utc),
            }
        )
        user = await database.users.find_one({"_id": insert_result.inserted_id})

    token = secrets.token_urlsafe(24)
    await database.user_sessions.insert_one(
        {
            "token": token,
            "user_id": user["_id"],
            "nickname": nickname,
            "created_at": datetime.now(timezone.utc),
            "last_seen_at": datetime.now(timezone.utc),
        }
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=secure_cookie,
        max_age=COOKIE_MAX_AGE_SECONDS,
    )
    return SessionResponse(authenticated=True, nickname=nickname)


@app.post("/api/auth/logout", response_model=SessionResponse)
async def logout(request: Request, response: Response) -> SessionResponse:
    database = getattr(request.app.state, "mongo_db", None)
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if database is not None and token:
        await database.user_sessions.delete_many({"token": token})
    secure_cookie = request_uses_secure_cookie(request)
    response.delete_cookie(SESSION_COOKIE_NAME, samesite="lax", secure=secure_cookie)
    response.delete_cookie(FALLBACK_AUTH_COOKIE_NAME, samesite="lax", secure=secure_cookie)
    return SessionResponse(authenticated=False, nickname=None)


@app.get("/api/articles/saved", response_model=list[SavedArticleResponse])
async def list_saved_articles(
    request: Request,
    session_user: dict[str, Any] = Depends(require_session_user),
) -> list[SavedArticleResponse]:
    database = getattr(request.app.state, "mongo_db", None)
    if database is None:
        documents = [
            article
            for article in get_cookie_saved_articles(request)
            if article.get("user_id") == session_user["user_id"]
        ]
        documents.sort(key=lambda item: item.get("saved_at", ""), reverse=True)
        return [serialize_cookie_saved_article(document) for document in documents]

    documents = await database.saved_articles.find({"user_id": session_user["user_id"]}).sort("saved_at", -1).to_list(length=100)
    return [serialize_saved_article(document) for document in documents]


@app.post("/api/articles/saved", response_model=SavedArticleResponse, status_code=status.HTTP_201_CREATED)
async def create_saved_article(
    request: Request,
    response: Response,
    payload: SavedArticleCreate,
    session_user: dict[str, Any] = Depends(require_session_user),
) -> SavedArticleResponse:
    database = getattr(request.app.state, "mongo_db", None)
    if database is None:
        documents = get_cookie_saved_articles(request)
        for document in documents:
            if document.get("user_id") == session_user["user_id"] and (document.get("article_id") == payload.article_id or document.get("url") == payload.url):
                return serialize_cookie_saved_article(document)

        document = payload.model_dump()
        document["id"] = secrets.token_urlsafe(8)
        document["user_id"] = session_user["user_id"]
        document["nickname"] = session_user["nickname"]
        document["saved_at"] = datetime.now(timezone.utc).isoformat()
        documents.insert(0, document)
        set_cookie_saved_articles(response, request, documents)
        return serialize_cookie_saved_article(document)

    existing = await database.saved_articles.find_one({
        "user_id": session_user["user_id"],
        "$or": [{"article_id": payload.article_id}, {"url": payload.url}],
    })
    if existing is not None:
        return serialize_saved_article(existing)

    document = payload.model_dump()
    document["user_id"] = session_user["user_id"]
    document["nickname"] = session_user["nickname"]
    document["saved_at"] = datetime.now(timezone.utc)
    result = await database.saved_articles.insert_one(document)
    created = await database.saved_articles.find_one({"_id": result.inserted_id})
    if created is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Saved article was not created")
    return serialize_saved_article(created)


@app.delete("/api/articles/saved/{saved_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_article(
    request: Request,
    response: Response,
    saved_id: str,
    session_user: dict[str, Any] = Depends(require_session_user),
) -> None:
    database = getattr(request.app.state, "mongo_db", None)
    if database is None:
        documents = get_cookie_saved_articles(request)
        filtered_documents = [
            article
            for article in documents
            if not (article.get("id") == saved_id and article.get("user_id") == session_user["user_id"])
        ]
        if len(filtered_documents) == len(documents):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved article not found")
        set_cookie_saved_articles(response, request, filtered_documents)
        return None

    try:
        object_id = ObjectId(saved_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid saved_id") from exc

    result = await database.saved_articles.delete_one({"_id": object_id, "user_id": session_user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved article not found")
