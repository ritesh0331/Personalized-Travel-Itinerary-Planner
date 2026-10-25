from __future__ import annotations

import io
import json
import logging
import math
import os
import re
import secrets
from datetime import date
from typing import Any
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from supabase import Client, create_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("travel-planner")
def currency_label(usd: float, currency_code: str, usd_rate: float) -> str:
    return f"{currency_code} {usd * usd_rate:,.0f}"


class Settings(BaseSettings):
    supabase_url: str = ""
    supabase_anon_key: str = ""
    ai_provider: str = "groq"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    groq_api_key: str = ""
    unsplash_access_key: str = ""
    frontend_origin: str = "http://localhost:5173"
    groq_model: str = "openai/gpt-oss-20b"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


settings = Settings()
app = FastAPI(title="Personalized Travel Itinerary Planner API", version="1.0.0")
allowed_origins = [x.strip().rstrip("/") for x in settings.frontend_origin.split(",") if x.strip()]
if not allowed_origins or "*" in allowed_origins:
    raise ValueError("FRONTEND_ORIGIN must contain one or more explicit origins; wildcard origins are not allowed.")


class RequestBodyTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    def __init__(self, app, max_body_bytes: int = 1_000_000):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                parsed_length = int(content_length)
                if parsed_length < 0:
                    raise ValueError
            except ValueError:
                response = JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header."})
                await response(scope, receive, send)
                return
            if parsed_length > self.max_body_bytes:
                response = JSONResponse(status_code=413, content={"detail": "Request body is too large."})
                await response(scope, receive, send)
                return
        received_bytes = 0
        response_started = False

        async def limited_receive():
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_body_bytes:
                    raise RequestBodyTooLarge
            return message

        async def tracked_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except RequestBodyTooLarge:
            if not response_started:
                response = JSONResponse(status_code=413, content={"detail": "Request body is too large."})
                await response(scope, receive, tracked_send)


app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=1_000_000)
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


class Preferences(BaseModel):
    destination: str | None = Field(default=None, max_length=120)
    currency_code: str | None = Field(default=None, pattern=r"^[A-Za-z]{3}$")
    price_estimate_version: int = 2
    vibe: str = Field(default="Cultural", max_length=40)
    duration: int = Field(ge=1, le=21)
    start_date: date
    budget: str = Field(default="Moderate", max_length=40)
    party: str = Field(default="Solo", max_length=40)
    group_size: int = Field(default=1, ge=1, le=12)
    pace: str = Field(default="Moderate", max_length=40)
    interests: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("interests")
    @classmethod
    def validate_interests(cls, interests: list[str]) -> list[str]:
        if any(len(interest) > 60 for interest in interests):
            raise ValueError("Each interest must be 60 characters or fewer.")
        return interests


class GenerateRequest(BaseModel):
    preferences: Preferences


class SwapRequest(BaseModel):
    day_index: int = Field(ge=0, le=20)
    slot_index: int = Field(ge=0, le=3)
    request: str = Field(default="Suggest a fresh local option", max_length=400)
    days: list[dict[str, Any]] = Field(max_length=21)
    preferences: dict[str, Any] = Field(max_length=40)


class DayRequest(BaseModel):
    day_index: int = Field(ge=0, le=20)
    request: str = Field(default="Fresh ideas", max_length=400)
    days: list[dict[str, Any]] = Field(max_length=21)
    preferences: dict[str, Any] = Field(max_length=40)


class TripPayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    destination: str = Field(min_length=1, max_length=120)
    start_date: date
    duration: int = Field(ge=1, le=21)
    preferences: dict[str, Any] = Field(max_length=40)
    itinerary: list[dict[str, Any]] = Field(max_length=21)
    accommodations: list[dict[str, Any]] = Field(default_factory=list, max_length=5)
    transportation: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def itinerary_matches_duration(self):
        if len(self.itinerary) != self.duration:
            raise ValueError("Itinerary day count must match trip duration.")
        return self


class TripUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    preferences: dict[str, Any] | None = Field(default=None, max_length=40)
    itinerary: list[dict[str, Any]] | None = Field(default=None, max_length=21)
    accommodations: list[dict[str, Any]] | None = Field(default=None, max_length=5)
    transportation: dict[str, Any] | None = None


SLOTS = ["Morning Sightseeing", "Lunch Recommendation", "Afternoon Leisure", "Evening Dining & Entertainment"]
TIMES = ["09:00–12:00", "12:30–14:00", "14:30–17:00", "18:30–21:00"]
ITINERARY_SCHEMA = {
    "type": "object",
    "properties": {
        "days": {"type": "array", "items": {"type": "object", "properties": {
            "day": {"type": "integer"}, "area": {"type": "string"}, "route_note": {"type": "string"},
            "items": {"type": "array", "items": {"type": "object", "properties": {
                "slot": {"type": "string"}, "time": {"type": "string"}, "title": {"type": "string"},
                "description": {"type": "string"}, "cost_usd_per_person": {"type": "number"},
                "category": {"type": "string"}, "transit_to_next": {"type": "string"},
            }, "required": ["slot", "time", "title", "description", "cost_usd_per_person", "category", "transit_to_next"], "additionalProperties": False}},
        }, "required": ["day", "area", "route_note", "items"], "additionalProperties": False}},
        "accommodations": {"type": "array", "items": {"type": "object", "properties": {
            "style": {"type": "string"}, "area": {"type": "string"}, "estimated_nightly_usd": {"type": "number"}, "why": {"type": "string"},
        }, "required": ["style", "area", "estimated_nightly_usd", "why"], "additionalProperties": False}},
        "transportation": {"type": "object", "properties": {
            "arrival": {"type": "string"}, "local": {"type": "string"}, "route_method": {"type": "string"},
            "day_routes": {"type": "array", "items": {"type": "object", "properties": {
                "day": {"type": "integer"}, "area": {"type": "string"}, "stops": {"type": "array", "items": {"type": "string"}},
                "suggested_modes": {"type": "array", "items": {"type": "string"}}, "estimated_minutes": {"type": "array", "items": {"type": "integer"}},
                "distance_km": {"type": "array", "items": {"type": "number"}},
            }, "required": ["day", "area", "stops", "suggested_modes", "estimated_minutes", "distance_km"], "additionalProperties": False}},
        }, "required": ["arrival", "local", "route_method", "day_routes"], "additionalProperties": False},
        "route_summary": {"type": "string"},
    },
    "required": ["days", "accommodations", "transportation", "route_summary"],
    "additionalProperties": False,
}
CITY_DATA = [
    ("Lisbon", "Coastal culture, tiled lanes and sunset viewpoints", ["Beach", "Cultural", "Urban"], "Moderate", "Sunny spring–fall", "Pastéis, tram rides, ocean air"),
    ("Kyoto", "Temple paths, gardens and a slower rhythm", ["Cultural", "Mountains"], "Moderate", "Best spring and autumn", "Tea, history, tranquil walks"),
    ("Bangkok", "Street-food energy and golden temples", ["Cultural", "Urban", "Beach"], "Budget", "Drier Nov–Feb", "Markets, food, nightlife"),
    ("Bali", "Surf, green highlands and restorative stays", ["Beach", "Mountains"], "Moderate", "Drier Apr–Oct", "Adventure, beaches, wellness"),
    ("Mexico City", "World-class food and layered city history", ["Cultural", "Urban"], "Budget", "Mild dry season Nov–Apr", "Museums, food, nightlife"),
    ("Cape Town", "Mountain panoramas, beaches and vineyards", ["Beach", "Mountains", "Urban"], "Moderate", "Warmest Nov–Mar", "Hikes, food, coast"),
    ("Jaipur", "Rose-colored forts, bazaars and Rajasthani craft", ["Cultural", "Urban"], "Budget", "Pleasant Oct–Mar", "History, markets, food"),
    ("Paris", "Museum mornings and long café evenings", ["Cultural", "Urban"], "Luxury", "Lovely Apr–Jun and Sep–Oct", "Art, dining, city walks"),
    ("Marrakech", "A sensory medina beside the Atlas foothills", ["Cultural", "Mountains"], "Budget", "Comfortable Mar–May and Sep–Nov", "Markets, food, day trips"),
]
PLACES = {
    "Lisbon": ["Alfama & São Jorge Castle", "Time Out Market", "Belém waterfront", "Bairro Alto"],
    "Kyoto": ["Higashiyama & Kiyomizu-dera", "Nishiki Market", "Philosopher’s Path", "Pontocho"],
    "Bangkok": ["Grand Palace & Wat Pho", "Or Tor Kor Market", "Lumphini Park", "Chinatown Yaowarat"],
    "Bali": ["Ubud rice terraces", "Ubud market", "Tirta Empul springs", "Seminyak sunset beach"],
    "Mexico City": ["Centro Histórico & Zócalo", "Mercado de San Juan", "Chapultepec Park", "Roma Norte"],
    "Cape Town": ["Table Mountain & Bo-Kaap", "Oranjezicht Market", "Kirstenbosch Gardens", "V&A Waterfront"],
    "Jaipur": ["Amber Fort & Panna Meena", "Johari Bazaar", "City Palace", "Hawa Mahal at sunset"],
    "Paris": ["Île de la Cité & Sainte-Chapelle", "Marché des Enfants Rouges", "Tuileries Garden", "Saint-Germain"],
    "Marrakech": ["Bahia Palace & Mellah", "Rahba Kedima souk", "Majorelle Garden", "Jemaa el-Fnaa"],
}
BASE_COSTS = [28, 18, 22, 48]
FACTORS = {"Budget": .72, "Moderate": 1, "Luxury": 1.75}
PRICE_INDEX_BY_CURRENCY = {"INR": .14, "THB": .42, "IDR": .40, "VND": .32, "PHP": .40, "MYR": .45, "MXN": .55, "ZAR": .60, "TRY": .50, "CNY": .65, "KRW": .75, "JPY": .85, "EUR": .95, "GBP": 1, "USD": 1, "AUD": 1, "CAD": 1, "SGD": .90, "AED": .90, "CHF": 1.15, "NZD": .95, "SEK": 1, "NOK": 1.05, "DKK": 1, "CZK": .75, "PLN": .75}
ACTIVITY_PRICE_INDEX_BY_CURRENCY = {"INR": .12, "THB": .24, "IDR": .22, "VND": .18, "PHP": .22, "MYR": .28, "MXN": .35, "ZAR": .40, "TRY": .35, "CNY": .45, "KRW": .60, "JPY": .75, "EUR": .80, "GBP": .90, "USD": 1, "AUD": .90, "CAD": .90, "SGD": .75, "AED": .80, "CHF": 1, "NZD": .85, "SEK": .85, "NOK": .90, "DKK": .85, "CZK": .55, "PLN": .55}
def destination_cost_factor(destination: str, currency_code: str | None = None) -> float:
    city = destination.lower()
    for names, factor in [
        (("india", "goa", "jaipur", "bhopal", "mumbai", "delhi", "bengaluru", "bangalore", "kochi", "kolkata", "chennai", "hyderabad", "agra", "varanasi"), .14),
        (("thailand", "bangkok", "chiang mai", "phuket"), .42),
        (("indonesia", "bali", "jakarta"), .40),
        (("vietnam", "hanoi", "ho chi minh"), .32),
        (("philippines", "manila", "cebu"), .40),
        (("malaysia", "kuala lumpur"), .45),
        (("mexico", "mexico city"), .55),
        (("south africa", "cape town", "johannesburg"), .60),
        (("turkey", "türkiye", "istanbul"), .50),
        (("china", "beijing", "shanghai"), .65),
        (("south korea", "seoul"), .75),
        (("japan", "tokyo", "kyoto", "osaka"), .85),
    ]:
        if any(name in city for name in names): return factor
    if currency_code:
        factor = PRICE_INDEX_BY_CURRENCY.get(currency_code.upper())
        if factor is not None: return factor
    return 1.0


def destination_activity_factor(destination: str, currency_code: str | None = None) -> float:
    city = destination.lower()
    if any(name in city for name in ("india", "goa", "jaipur", "bhopal", "mumbai", "delhi", "bengaluru", "bangalore", "kochi", "kolkata", "chennai", "hyderabad", "agra", "varanasi")): return .12
    code = (currency_code or "").upper()
    return ACTIVITY_PRICE_INDEX_BY_CURRENCY.get(code, destination_cost_factor(destination, currency_code) * .75)


def localized_ai_cost(value: Any, destination: str, currency_code: str | None, fallback: float = 0) -> float:
    amount = estimated_cost(value, fallback)
    return round(amount * destination_activity_factor(destination, currency_code), 2)


def estimated_cost(value: Any, default: float = 0) -> float:
    if isinstance(value, (int, float)) and math.isfinite(value):
        return max(0, min(50000, float(value)))
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return max(0, min(50000, float(match.group(0)))) if match else default


def supabase_client() -> Client:
    if not supabase_is_configured():
        raise HTTPException(status_code=503, detail="Supabase is not configured. Add SUPABASE_URL and SUPABASE_ANON_KEY.")
    return create_client(settings.supabase_url, settings.supabase_anon_key)


def supabase_is_configured() -> bool:
    url = settings.supabase_url.strip()
    key = settings.supabase_anon_key.strip()
    return (
        url.startswith("https://")
        and ".supabase.co" in url
        and "your-project" not in url.lower()
        and bool(key)
        and not any(marker in key.lower() for marker in ("your-supabase", "placeholder", "replace-me"))
    )


def current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    token = authorization.split(" ", 1)[1]
    try:
        client = supabase_client()
        user = client.auth.get_user(token).user
        if not user: raise ValueError("No user")
        client.postgrest.auth(token)
        return {"id": user.id, "email": user.email, "client": client}
    except HTTPException: raise
    except Exception as exc:
        logger.info("Supabase authentication failed: %s", exc)
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.") from exc


def enforce_ai_quota(client: Client) -> None:
    try:
        allowed = client.rpc("consume_ai_quota", {}).execute().data
    except Exception as exc:
        logger.exception("AI quota check failed")
        raise HTTPException(status_code=503, detail="AI usage protection is not configured. Apply the latest backend/schema.sql migration and retry.") from exc
    if allowed is not True:
        raise HTTPException(status_code=429, detail="AI planning limit reached. Try again in about an hour.")


def demo_day(city: str, day_num: int, budget: str, interests: list[str], pace: str, request: str = "", currency_code: str | None = None) -> dict[str, Any]:
    places = PLACES.get(city, [f"{city} historic quarter", f"{city} local food market", f"{city} gardens or waterfront", f"{city} evening district"])
    shift = (day_num - 1) % 4
    spots = places[shift:] + places[:shift]
    if pace == "Relaxed": spots[2] = f"Leisure time near {spots[0].split('&')[0].strip()}"
    if request and "vegetarian" in request.lower() and "lunch" in request.lower(): spots[1] = "Vegetarian-friendly neighborhood café"
    if request and "market" in request.lower(): spots[slot_for_request(request)] = f"Local outdoor market in {city}"
    items = []
    titles = [spots[0], "Vegetarian-friendly local café" if "Vegetarian" in interests else f"Local flavors near {spots[1]}", spots[2], spots[3]]
    descriptions = ["Begin in one walkable neighborhood; allow time for a relaxed visit.", "Choose a nearby spot; check opening hours and dietary needs.", "Keep the afternoon flexible for a park, gallery, rest, or weather change.", "Book ahead where useful; use licensed transport for your return."]
    for i in range(4):
        factor = FACTORS.get(budget, 1)
        bump = 1.12 if "Food" in interests and i in (1, 3) else 1
        items.append({"slot": SLOTS[i], "time": TIMES[i], "title": titles[i], "description": descriptions[i], "cost_usd": round(BASE_COSTS[i] * factor * bump * destination_activity_factor(city, currency_code) / 2) * 2, "category": ["Sightseeing", "Food", "Leisure", "Dining"][i]})
    return {"day": day_num, "area": spots[0].split("&")[0].strip(), "items": items}


def demo_stays(city: str, budget: str, currency_code: str | None = None) -> list[dict[str, Any]]:
    center = {"Lisbon": "Baixa or Chiado", "Kyoto": "Downtown Kawaramachi", "Bangkok": "Sukhumvit near a BTS station", "Bali": "Ubud center or Seminyak", "Mexico City": "Roma Norte or Condesa", "Cape Town": "Sea Point or Gardens", "Jaipur": "Bani Park", "Paris": "Le Marais", "Marrakech": "Medina near a main gate"}.get(city, f"Central {city}")
    scale = FACTORS.get(budget, 1)
    picks = [("Good-value guesthouse", 55), ("Comfortable boutique stay", 125), ("Special-occasion hotel", 260)]
    local_factor = destination_cost_factor(city, currency_code)
    return [{"style": label, "area": center, "estimated_nightly_usd": round(price * scale * local_factor), "why": f"A practical base for reaching the clustered {city} itinerary; compare current reviews, accessibility, and cancellation terms."} for label, price in picks]


def demo_transport(city: str, currency_code: str | None = None) -> dict[str, Any]:
    local_factor = destination_cost_factor(city, currency_code)
    return {"arrival": f"Compare official airport rail, licensed taxis, and pre-booked transfers into {city}; fares and schedules vary by date.", "local": "The daily plan groups nearby stops. Prefer walking for short hops, then use licensed public transit or ride services for longer transfers.", "route_method": "Activities are grouped by neighborhood and ordered as a practical day sequence. Verify live routes, traffic, accessibility, and service hours in a maps app before departure.", "daily_transfers": [{"day": i, "area": f"{city} local neighborhood", "legs": ["Walk between nearby stops", "Use public transit or licensed ride service for longer hops"], "estimated_transit_usd_per_person": round(8 * local_factor, 2)} for i in range(1, 5)]}


def slot_for_request(request: str) -> int:
    req = request.lower()
    return 1 if "lunch" in req or "food" in req else (2 if "afternoon" in req else (3 if "evening" in req or "dinner" in req else 0))


async def groq_json(prompt: str, schema: dict[str, Any] | None = None, unconstrained_retry: bool = False) -> Any:
    if not settings.groq_api_key: raise HTTPException(status_code=503, detail="Groq is not configured. Add GROQ_API_KEY or use demo mode.")
    try:
        async with httpx.AsyncClient(timeout=50) as client:
            payload = {"model": settings.groq_model, "temperature": .55, "max_completion_tokens": 16384, "reasoning_effort": "low", "messages": [{"role": "system", "content": "Return one valid JSON object only. Keep recommendations practical; never claim real-time availability."}, {"role": "user", "content": prompt}]}
            if schema:
                payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "travel_itinerary", "strict": True, "schema": schema}}
            elif not unconstrained_retry:
                payload["response_format"] = {"type": "json_object"}
            response = await client.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {settings.groq_api_key}"}, json=payload)
            response.raise_for_status()
            text = response.json()["choices"][0]["message"]["content"]
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                for opening, closing in (("{", "}"), ("[", "]")):
                    start, end = cleaned.find(opening), cleaned.rfind(closing)
                    if start >= 0 and end > start:
                        try:
                            return json.loads(cleaned[start:end + 1])
                        except json.JSONDecodeError:
                            continue
                raise
    except HTTPException: raise
    except httpx.HTTPStatusError as exc:
        try:
            provider_error = exc.response.json().get("error", {})
            provider_message = str(provider_error.get("message", ""))[:400]
            provider_code = str(provider_error.get("code", ""))[:80]
        except Exception:
            provider_message, provider_code = "", ""
        logger.warning("Groq returned status %s (%s): %s", exc.response.status_code, provider_code, provider_message)
        if exc.response.status_code == 400 and provider_code == "json_validate_failed":
            if schema and not unconstrained_retry:
                logger.info("Retrying Groq itinerary generation without constrained output mode")
                return await groq_json(prompt, unconstrained_retry=True)
            raise HTTPException(status_code=502, detail=f"Groq rejected its structured itinerary output: {provider_message or 'response validation failed'}. Try again or shorten the trip.") from exc
        if exc.response.status_code in (401, 403):
            raise HTTPException(status_code=502, detail="Groq rejected the API key. Add a valid GroqCloud API key to backend/.env and restart FastAPI.") from exc
        if exc.response.status_code == 404:
            raise HTTPException(status_code=502, detail=f"Groq model '{settings.groq_model}' was not found. Update GROQ_MODEL in backend/.env to an active model ID and restart FastAPI.") from exc
        raise HTTPException(status_code=502, detail="The itinerary service is temporarily unavailable. Try demo mode.") from exc
    except Exception as exc:
        logger.exception("Groq request failed")
        raise HTTPException(status_code=502, detail="Could not read the generated itinerary. Please try again.") from exc


def active_ai_provider() -> str:
    provider = settings.ai_provider.strip().lower()
    return provider if provider in {"gemini", "groq"} else "gemini"


def ai_is_configured() -> bool:
    return bool(settings.gemini_api_key) if active_ai_provider() == "gemini" else bool(settings.groq_api_key)


async def gemini_json(prompt: str) -> Any:
    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="Gemini is not configured. Add GEMINI_API_KEY to backend/.env or use demo mode.")
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://generativelanguage.googleapis.com/v1beta/interactions",
                headers={"x-goog-api-key": settings.gemini_api_key},
                json={
                    "model": settings.gemini_model,
                    "input": prompt,
                    "system_instruction": "Return valid JSON only. Keep recommendations practical; never claim real-time availability.",
                    "generation_config": {"temperature": 0.55, "max_output_tokens": 16384},
                    "response_format": {"type": "text", "mime_type": "application/json"},
                },
            )
            response.raise_for_status()
            payload = response.json()
            text = "".join(
                content.get("text", "")
                for step in payload.get("steps", [])
                if step.get("type") == "model_output"
                for content in step.get("content", [])
                if content.get("type") == "text"
            )
            if not text:
                raise ValueError("Gemini returned no text. The prompt may have been blocked or the response limit reached.")
            return json.loads(text.strip())
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        try:
            error = exc.response.json().get("error", {})
            message = str(error.get("message", ""))[:400]
            code = str(error.get("status", ""))[:80]
        except Exception:
            message, code = "", ""
        logger.warning("Gemini returned status %s (%s): %s", exc.response.status_code, code, message)
        if exc.response.status_code in (401, 403) or "API key not valid" in message:
            raise HTTPException(status_code=502, detail="Gemini rejected the API key. Check GEMINI_API_KEY in backend/.env and restart FastAPI.") from exc
        if exc.response.status_code == 404:
            raise HTTPException(status_code=502, detail=f"Gemini model '{settings.gemini_model}' was not found. Update GEMINI_MODEL in backend/.env and restart FastAPI.") from exc
        if exc.response.status_code == 429:
            raise HTTPException(status_code=502, detail="Gemini's quota or rate limit was reached. Wait and try again, or check your Google AI Studio usage limits.") from exc
        raise HTTPException(status_code=502, detail="Gemini is temporarily unavailable. Try again or use demo mode.") from exc
    except Exception as exc:
        logger.exception("Gemini request failed")
        raise HTTPException(status_code=502, detail="Could not read the Gemini itinerary. Please try again.") from exc


async def ai_json(prompt: str, schema: dict[str, Any] | None = None) -> Any:
    if active_ai_provider() == "gemini":
        return await gemini_json(prompt)
    return await groq_json(prompt, schema)


@app.get("/api/health")
def health() -> dict[str, str]: return {"status": "ok", "service": "travel-planner-api"}


@app.get("/api/config")
def public_config() -> dict[str, Any]: return {"supabase_configured": supabase_is_configured(), "ai_provider": active_ai_provider(), "ai_configured": ai_is_configured(), "gemini_configured": bool(settings.gemini_api_key), "groq_configured": bool(settings.groq_api_key), "unsplash_configured": bool(settings.unsplash_access_key)}


@app.get("/api/auth/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return {"id": user["id"], "email": user["email"]}


@app.get("/api/recommendations")
def recommendations(vibe: str = Query(default="Cultural", max_length=40), budget: str = Query(default="Moderate", max_length=40), interests: str = Query(default="", max_length=300), start_date: date | None = None) -> list[dict[str, Any]]:
    selected = [i.strip() for i in interests.split(",") if i.strip()]
    month = (start_date or date.today()).month
    matches = []
    for city, desc, vibes, level, season, tags in CITY_DATA:
        score = (3 if vibe in vibes else 0) + (2 if budget == level else 0) + min(2, sum(1 for i in selected if i.lower() in tags.lower()))
        season_good = any(term in season.lower() for term in ("year-round", "spring", "autumn", "fall")) or ("nov" in season.lower() and month in (11, 12, 1, 2)) or ("oct" in season.lower() and month in (10, 11, 12, 1, 2, 3)) or ("apr" in season.lower() and month in range(4, 11)) or ("mar" in season.lower() and month in (3, 4, 5, 9, 10, 11))
        score += 2 if season_good else 0
        matches.append((score, {"city": city, "description": desc, "tags": vibes[:2] + [level], "season": season, "highlights": tags}))
    return [x[1] for x in sorted(matches, key=lambda x: (-x[0], x[1]["city"]))[:3]]


@app.get("/api/images")
async def image_search(query: str = Query(min_length=1, max_length=120), _user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if not settings.unsplash_access_key: return {"results": []}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get("https://api.unsplash.com/search/photos", params={"query": query, "per_page": 8, "orientation": "landscape"}, headers={"Authorization": f"Client-ID {settings.unsplash_access_key}"})
            response.raise_for_status()
            payload = response.json()
            return {"results": [{"id": p["id"], "url": p["urls"]["regular"], "alt": p.get("alt_description") or query, "credit": p["user"]["name"], "credit_url": p["user"]["links"]["html"] + "?utm_source=travel_planner&utm_medium=referral"} for p in payload.get("results", [])]}
    except Exception as exc:
        logger.warning("Unsplash search failed: %s", exc)
        return {"results": []}


@app.post("/api/itinerary/generate")
async def generate(req: GenerateRequest, _user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    pref = req.preferences
    if not pref.destination: raise HTTPException(status_code=422, detail="Choose a destination before generating an itinerary.")
    days = [demo_day(pref.destination, n, pref.budget, pref.interests, pref.pace, currency_code=pref.currency_code) for n in range(1, pref.duration + 1)]
    stays = demo_stays(pref.destination, pref.budget, pref.currency_code)
    transportation = demo_transport(pref.destination, pref.currency_code)
    source = "demo"
    ai_warning = None
    if ai_is_configured():
        enforce_ai_quota(_user["client"])
        prompt = f'''Create a complete travel plan for {pref.destination}: {pref.duration} days starting {pref.start_date}. Party {pref.party}, group size {pref.group_size}, budget {pref.budget}, pace {pref.pace}, interests {pref.interests}. Geography: keep each day within one compact neighborhood to reduce backtracking. Return JSON object with: (1) "days": exactly {pref.duration} objects, each with day, area, exactly 4 items in this order {SLOTS}; each item has time, title, description, cost_usd_per_person, category. Use times {TIMES}. Include nearby transit guidance between stops and a route_note on each day. (2) "accommodations": 3 lodging area/style suggestions across budget, midrange, and premium, with estimated nightly USD per person, rationale, and a note these are not live listings. Do not invent specific properties. (3) "transportation": arrival guidance, local transit options, accessibility caveats, and a day_routes array with grouped stops, suggested mode for each leg, estimated minutes per leg and distance_km when sensible. (4) "route_summary": explain the geographic clustering. All costs are estimates; do not claim live availability or actual traffic.'''
        try:
            result = await ai_json(prompt, ITINERARY_SCHEMA)
            if isinstance(result, list):
                result = {"days": result}
            generated = result.get("days", [])
            if not isinstance(generated, list): generated = []
            # Normalize incomplete provider output into four stable slots per day.
            normalized = []
            filled_slots = False
            for di in range(pref.duration):
                day = generated[di] if di < len(generated) and isinstance(generated[di], dict) else {}
                if not day: filled_slots = True
                items = day.get("items", day.get("activities", []))
                if not isinstance(items, list): items = []
                clean_items = []
                for i in range(4):
                    item = items[i] if i < len(items) and isinstance(items[i], dict) else None
                    if item is None: filled_slots = True
                    fallback_item = days[di]["items"][i]
                    item = item or fallback_item
                    raw_cost = item.get("cost_usd_per_person", item.get("cost_usd"))
                    cost = fallback_item["cost_usd"] if raw_cost is None else localized_ai_cost(raw_cost, pref.destination, pref.currency_code, fallback_item["cost_usd"])
                    clean_items.append({"slot": SLOTS[i], "time": TIMES[i], "title": str(item.get("title", fallback_item["title"]))[:160], "description": str(item.get("description", fallback_item["description"]))[:400], "cost_usd": cost, "category": str(item.get("category", fallback_item["category"]))[:50], "transit_to_next": str(item.get("transit_to_next", "Walk or use local transit; verify the live route."))[:180]})
                normalized.append({"day": di + 1, "area": str(day.get("area", days[di]["area"]))[:120], "route_note": str(day.get("route_note", "Nearby stops are grouped to limit backtracking."))[:300], "items": clean_items})
            if isinstance(result.get("accommodations"), list) and result["accommodations"]:
                fallback_stays = demo_stays(pref.destination, pref.budget, pref.currency_code)
                normalized_stays = []
                for i, stay in enumerate(x for x in result["accommodations"][:5] if isinstance(x, dict)):
                    fallback_stay = fallback_stays[min(i, len(fallback_stays) - 1)]
                    style = str(stay.get("style", "")).strip()
                    area = str(stay.get("area", "")).strip()
                    why = str(stay.get("why", "")).strip()
                    nightly_cost = estimated_cost(stay.get("estimated_nightly_usd"), fallback_stay["estimated_nightly_usd"])
                    if stay.get("estimated_nightly_usd") is not None:
                        nightly_cost = round(nightly_cost * destination_cost_factor(pref.destination, pref.currency_code))
                    normalized_stays.append({
                        "style": style[:100] if style and style.lower() != "stay option" else fallback_stay["style"],
                        "area": area[:120] if area and area.lower() != "central area" else fallback_stay["area"],
                        "estimated_nightly_usd": min(20000, nightly_cost or fallback_stay["estimated_nightly_usd"]),
                        "why": why[:300] if why else fallback_stay["why"],
                    })
                stays = normalized_stays or fallback_stays
            if isinstance(result.get("transportation"), dict):
                transportation.update(result["transportation"])
                transfers = transportation.get("daily_transfers")
                if isinstance(transfers, list):
                    for transfer in transfers:
                        if isinstance(transfer, dict) and "estimated_transit_usd_per_person" in transfer:
                            transfer["estimated_transit_usd_per_person"] = round(estimated_cost(transfer["estimated_transit_usd_per_person"]) * destination_cost_factor(pref.destination, pref.currency_code), 2)
            transportation["route_summary"] = str(result.get("route_summary", transportation["route_method"]))[:500]
            days = normalized
            source = active_ai_provider()
            if filled_slots: ai_warning = f"{active_ai_provider().title()} returned an incomplete day, so missing moments were filled with local sample suggestions."
        except Exception as exc:
            logger.warning("Using local itinerary fallback (%s): %s", type(exc).__name__, exc)
            ai_warning = exc.detail if isinstance(exc, HTTPException) else f"{active_ai_provider().title()} itinerary validation failed: {str(exc)[:180]}. Using the demo itinerary instead."
    return {"preferences": pref.model_dump(mode="json"), "days": days, "accommodations": stays, "transportation": transportation, "source": source, "ai_warning": ai_warning}


@app.post("/api/itinerary/swap")
async def swap(req: SwapRequest, _user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    days = req.days; preferences = req.preferences
    if not isinstance(days, list) or req.day_index >= len(days): raise HTTPException(status_code=404, detail="Day not found.")
    day = days[req.day_index]
    if not isinstance(day, dict) or not isinstance(day.get("items"), list) or req.slot_index >= len(day["items"]):
        raise HTTPException(status_code=404, detail="Itinerary activity not found.")
    if not isinstance(preferences, dict): preferences = {}
    old = day["items"][req.slot_index]
    if not isinstance(old, dict): raise HTTPException(status_code=422, detail="The selected itinerary activity is invalid.")
    destination = str(preferences.get("destination", "Your destination"))
    fallback = demo_day(destination, req.day_index + 2, preferences.get("budget", "Moderate"), preferences.get("interests", []), preferences.get("pace", "Moderate"), req.request, preferences.get("currency_code"))["items"][req.slot_index]
    ai_warning = None
    item = None
    if ai_is_configured():
        enforce_ai_quota(_user["client"])
        prompt = f"Suggest one specific, different, geographically nearby replacement for a {old.get('slot')} slot in {destination}, neighborhood {day.get('area')}. Do not repeat the current item: {old.get('title')}. Follow this traveler request: {req.request}. Budget: {preferences.get('budget')}. Return a JSON object with title, description, cost_usd (USD per person), and category."
        try:
            result = await ai_json(prompt)
            candidate = result.get("item", result) if isinstance(result, dict) else {}
            title = str(candidate.get("title", "")).strip() if isinstance(candidate, dict) else ""
            if not title or title.casefold() == str(old.get("title", "")).strip().casefold():
                raise ValueError("AI did not provide a distinct replacement activity")
            item = {**old, "title": title[:160], "description": str(candidate.get("description") or fallback["description"])[:400], "cost_usd": localized_ai_cost(candidate.get("cost_usd"), destination, preferences.get("currency_code"), fallback["cost_usd"]), "category": str(candidate.get("category") or fallback["category"])[:50]}
        except Exception as exc:
            logger.warning("Swap suggestion fell back to local option (%s)", type(exc).__name__)
            ai_warning = "The AI suggestion was unavailable, so we used a local replacement idea."
    else:
        ai_warning = "AI is unavailable, so we used a local replacement idea."
    if item is None:
        item = {**fallback, "slot": old.get("slot", fallback["slot"]), "time": old.get("time", fallback["time"])}
    day["items"][req.slot_index] = item
    return {"days": days, "ai_warning": ai_warning}


@app.post("/api/itinerary/regenerate-day")
async def regenerate_day(req: DayRequest, _user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    days = req.days; preferences = req.preferences
    if not isinstance(days, list) or req.day_index >= len(days): raise HTTPException(status_code=404, detail="Day not found.")
    old = days[req.day_index]
    if not isinstance(old, dict): raise HTTPException(status_code=422, detail="The selected itinerary day is invalid.")
    if not isinstance(preferences, dict): preferences = {}
    destination = str(preferences.get("destination", "Your destination"))
    budget = str(preferences.get("budget", "Moderate"))
    currency_code = preferences.get("currency_code")
    fallback = demo_day(destination, req.day_index + 2, budget, preferences.get("interests", []), preferences.get("pace", "Moderate"), req.request, currency_code)
    repl = None
    ai_warning = None
    if ai_is_configured():
        enforce_ai_quota(_user["client"])
        prompt = f"Return a complete JSON object with a day object for {destination}, with area and exactly four items (slot, time, title, description, cost_usd, category). Keep the stops within one neighborhood near {old.get('area')}. Party {preferences.get('party')}, budget {budget}, pace {preferences.get('pace')}, interests {preferences.get('interests')}, traveler direction: {req.request}. Each title must be specific and each item must include all six fields. Use exactly this order and times: {list(zip(SLOTS,TIMES))}. Costs are USD per person and should reflect local prices and the selected budget."
        try:
            result = await ai_json(prompt)
            candidate = result.get("day", result) if isinstance(result, dict) else {}
            items = candidate.get("items") if isinstance(candidate, dict) else None
            if not isinstance(items, list) or len(items) != 4 or any(not isinstance(item, dict) or not str(item.get("title", "")).strip() for item in items):
                raise ValueError("AI returned an incomplete day")
            repl = {**candidate, "day": req.day_index + 1, "items": items}
            for i, item in enumerate(items):
                raw_cost = item.get("cost_usd")
                item.update({"slot": SLOTS[i], "time": TIMES[i], "description": str(item.get("description") or fallback["items"][i]["description"])[:400], "cost_usd": fallback["items"][i]["cost_usd"] if raw_cost is None else localized_ai_cost(raw_cost, destination, currency_code, fallback["items"][i]["cost_usd"])})
            repl["area"] = str(repl.get("area") or old.get("area") or destination)[:120]
        except Exception as exc:
            logger.warning("Day reimagination fell back to local suggestions (%s)", type(exc).__name__)
            ai_warning = "The AI returned an incomplete day, so we filled it with local suggestions."
    else:
        ai_warning = "AI is unavailable, so we used local suggestions."
    if repl is None:
        repl = fallback
        repl["day"] = req.day_index + 1
    days[req.day_index] = repl
    return {"days": days, "ai_warning": ai_warning}


@app.get("/api/trips")
def list_trips(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    try: return user["client"].table("trips").select("id,user_id,name,destination,start_date,duration,preferences,itinerary,accommodations,transportation,share_code,created_at,updated_at").order("updated_at", desc=True).execute().data
    except Exception as exc:
        logger.exception("Could not list trips")
        raise HTTPException(status_code=500, detail="Could not load saved trips. Check the Supabase schema and row-level security setup.") from exc


@app.post("/api/trips", status_code=status.HTTP_201_CREATED)
def save_trip(payload: TripPayload, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    row = {"user_id": user["id"], "name": payload.name, "destination": payload.destination, "start_date": payload.start_date.isoformat(), "duration": payload.duration, "preferences": payload.preferences, "itinerary": payload.itinerary, "accommodations": payload.accommodations, "transportation": payload.transportation, "share_code": secrets.token_urlsafe(9)}
    try: return user["client"].table("trips").insert(row).execute().data[0]
    except Exception as exc:
        logger.exception("Could not save trip")
        raise HTTPException(status_code=500, detail="Could not save trip. Check your Supabase trips table and row-level security policies.") from exc


@app.post("/api/trips/join")
def join_trip(payload: dict[str, str], user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    code = payload.get("share_code", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,32}", code): raise HTTPException(status_code=422, detail="Enter a valid trip sharing code.")
    try:
        result = user["client"].rpc("join_trip_by_code", {"p_code": code}).execute()
        if not result.data: raise HTTPException(status_code=404, detail="No trip found for that sharing code.")
        return {"id": result.data, "joined": True}
    except HTTPException: raise
    except Exception as exc:
        logger.exception("Could not join trip")
        raise HTTPException(status_code=400, detail="Could not join this trip. Confirm the latest Supabase collaboration migration was applied.") from exc


@app.patch("/api/trips/{trip_id}")
def update_trip(trip_id: UUID, payload: TripUpdate, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    updates = payload.model_dump(exclude_none=True)
    if not updates: raise HTTPException(status_code=400, detail="No changes supplied.")
    try:
        rows = user["client"].table("trips").update(updates).eq("id", str(trip_id)).execute().data
        if not rows: raise HTTPException(status_code=404, detail="Trip not found.")
        return rows[0]
    except HTTPException: raise
    except Exception as exc:
        logger.exception("Could not update trip")
        raise HTTPException(status_code=500, detail="Could not update trip.") from exc


@app.post("/api/trips/{trip_id}/share")
def create_share_code(trip_id: UUID, user: dict[str, Any] = Depends(current_user)) -> dict[str, str]:
    try:
        result = user["client"].rpc("create_trip_share_code", {"p_trip_id": str(trip_id), "p_code": secrets.token_urlsafe(9)}).execute()
        if not result.data: raise HTTPException(status_code=404, detail="Trip not found.")
        return {"share_code": result.data}
    except HTTPException: raise
    except Exception as exc:
        logger.exception("Could not create trip invitation")
        raise HTTPException(status_code=500, detail="Could not create an invite. Apply the updated Supabase schema first.") from exc


@app.delete("/api/trips/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trip(trip_id: UUID, user: dict[str, Any] = Depends(current_user)) -> Response:
    try:
        rows = user["client"].table("trips").delete().eq("id", str(trip_id)).execute().data
        if not rows: raise HTTPException(status_code=404, detail="Trip not found.")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HTTPException: raise
    except Exception as exc:
        logger.exception("Could not delete trip")
        raise HTTPException(status_code=500, detail="Could not delete trip.") from exc


def pdf_text(value: Any) -> str:
    return str(value).encode("latin-1", "replace").decode("latin-1").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@app.post("/api/itinerary/pdf")
def export_pdf(plan: dict[str, Any], _user: dict[str, Any] = Depends(current_user)) -> Response:
    pref = plan.get("preferences", {}); days = plan.get("days", [])
    if not isinstance(pref, dict) or not isinstance(days, list) or not days or len(days) > 21:
        raise HTTPException(status_code=422, detail="Provide an itinerary with 1 to 21 days to export.")
    if any(not isinstance(day, dict) or not isinstance(day.get("items", []), list) or len(day.get("items", [])) > 4 for day in days):
        raise HTTPException(status_code=422, detail="Each itinerary day must contain at most four activities.")
    currency_code = str(plan.get("currency_code", "INR"))
    if not re.fullmatch(r"[A-Z]{3}", currency_code): currency_code = "INR"
    try: currency_rate = float(plan.get("currency_rate", 94.78))
    except (TypeError, ValueError): currency_rate = 94.78
    if not math.isfinite(currency_rate) or currency_rate <= 0 or currency_rate > 1000000: currency_rate = 94.78
    buffer = io.BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=45, leftMargin=45, topMargin=45, bottomMargin=45)
    styles = getSampleStyleSheet(); styles.add(ParagraphStyle(name="TravelTitle", parent=styles["Title"], textColor=colors.HexColor("#176b55"), fontSize=24, leading=28)); styles.add(ParagraphStyle(name="TravelSmall", parent=styles["BodyText"], fontSize=8, leading=11))
    story = [Paragraph("Personalized Travel Itinerary Planner", styles["TravelTitle"]), Paragraph(f"{pdf_text(pref.get('destination','Trip'))} · {len(days)} days · {pdf_text(pref.get('start_date',''))} · {pdf_text(pref.get('party',''))} · {int(pref.get('group_size',1))} travelers", styles["Heading2"]), Spacer(1, 14)]
    stays = plan.get("accommodations", [])
    if not isinstance(stays, list): stays = []
    stay_index = 0 if pref.get("budget") == "Budget" else 2 if pref.get("budget") == "Luxury" else 1
    selected_stays = [stays[min(stay_index, len(stays) - 1)]] if stays and isinstance(stays[min(stay_index, len(stays) - 1)], dict) else []
    transport = plan.get("transportation", {})
    if not isinstance(transport, dict): transport = {}
    if selected_stays:
        story.append(Paragraph("Stay recommendation", styles["Heading2"]))
        story.append(Paragraph("Area/style suggestions only; verify current accommodation listings and nightly rates.", styles["TravelSmall"]))
        for stay in selected_stays:
            story.extend([Paragraph(f"<b>{pdf_text(stay.get('style','Stay'))}</b> · {pdf_text(stay.get('area',''))} · about {currency_label(estimated_cost(stay.get('estimated_nightly_usd',0)), currency_code, currency_rate)}/night/person", styles["TravelSmall"]), Paragraph(pdf_text(stay.get("why", "")), styles["TravelSmall"]), Spacer(1, 4)])
    if transport:
        story.extend([Paragraph("Arrival & local transport", styles["Heading2"]), Paragraph(pdf_text(transport.get("arrival", "")), styles["TravelSmall"]), Paragraph(pdf_text(transport.get("local", "")), styles["TravelSmall"]), Paragraph("Route notes are geographic planning suggestions, not live directions or traffic data.", styles["TravelSmall"]), Spacer(1, 8)])
    activity_total = sum(estimated_cost(item.get("cost_usd", 0)) for day in days for item in day.get("items", []) if isinstance(item, dict))
    nightly = estimated_cost(stays[min(stay_index, len(stays) - 1)].get("estimated_nightly_usd", 0)) if stays and isinstance(stays[min(stay_index, len(stays) - 1)], dict) else 0
    trip_nights = max(1, len(days) - 1)
    transit_daily = transport.get("daily_transfers", [])
    transit_total = sum(estimated_cost(x.get("estimated_transit_usd_per_person", 8), 8) for x in transit_daily[:len(days)] if isinstance(x, dict)) if isinstance(transit_daily, list) and transit_daily else 8 * len(days)
    try: group_size = max(1, min(12, int(pref.get("group_size", 1))))
    except (TypeError, ValueError): group_size = 1
    trip_total = (activity_total + nightly * trip_nights + transit_total) * group_size
    story.extend([Paragraph("Estimated trip budget", styles["Heading2"]), Paragraph(f"Activities: {currency_label(activity_total, currency_code, currency_rate)}/person · lodging: about {currency_label(nightly * trip_nights, currency_code, currency_rate)}/person · ground transit: about {currency_label(transit_total, currency_code, currency_rate)}/person", styles["TravelSmall"]), Paragraph(f"Estimated group total for {group_size} travelers: {currency_label(trip_total, currency_code, currency_rate)}, excluding flights. All amounts are indicative.", styles["TravelSmall"]), Spacer(1, 8)])
    for day in days:
        story.extend([Paragraph(f"Day {pdf_text(day.get('day',''))} — {pdf_text(day.get('area','Explore'))}", styles["Heading2"]), Spacer(1, 5)])
        rows = [["Time", "Plan", "Est. cost"]]
        for i, item in enumerate(day.get("items", [])):
            if not isinstance(item, dict): continue
            rows.append([Paragraph(pdf_text(item.get("time", TIMES[min(i, 3)])), styles["TravelSmall"]), Paragraph(f"<b>{pdf_text(item.get('slot',''))}: {pdf_text(item.get('title',''))}</b><br/>{pdf_text(item.get('description',''))}", styles["TravelSmall"]), Paragraph(currency_label(estimated_cost(item.get("cost_usd",0)), currency_code, currency_rate), styles["TravelSmall"])])
        table = Table(rows, colWidths=[1.05*inch, 4.55*inch, 1.1*inch], repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#176b55")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.35,colors.HexColor("#dce4dc")),("VALIGN",(0,0),(-1,-1),"TOP"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f4f7f3")]),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7)]))
        story.extend([table, Spacer(1, 10)])
    story.extend([Spacer(1, 15), Paragraph("Before you go", styles["Heading1"]), Paragraph("Emergency & arrival checklist", styles["Heading2"])])
    for line in ["Save your accommodation address and local emergency number offline.", "Share your itinerary and check-in plan with someone you trust.", "Keep passport, insurance details, and medication information accessible.", "Use licensed transport and confirm pickup points.", "Check current entry requirements, weather, local advisories, and attraction hours.", "Carry a backup payment method and note your bank’s international support number."]:
        story.extend([Paragraph(f"☐  {line}", styles["BodyText"]), Spacer(1, 7)])
    story.extend([Spacer(1, 8), Paragraph("Planning estimates are indicative. Confirm current prices, opening hours, local guidance, and emergency contacts before travel.", styles["TravelSmall"])]); doc.build(story)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", pref.get("destination", "trip")).strip("-").lower()
    return Response(buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={slug or 'trip'}-itinerary.pdf"})
