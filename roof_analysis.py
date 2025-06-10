"""Roof Analysis module.

This module fetches property details, recent permits, and storm events
for properties in ZIP code 30519, computes a score, and uploads results
to Google Sheets.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup  # type: ignore

try:
    import gspread  # type: ignore
    from google.oauth2.service_account import Credentials  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    gspread = None
    Credentials = None


LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

@dataclass
class PermitRecord:
    date: datetime
    description: str

@dataclass
class PropertyDetails:
    address: str
    year_built: int
    square_feet: int
    roof_age: Optional[int] = None
    permits: List[PermitRecord] | None = None
    weather_events: List[Dict[str, Any]] | None = None


class Config:
    """Configuration for data sources."""

    GWinnett_URL = "https://example.com/gwinnett/permits"  # placeholder
    ZILLOW_URL = "https://www.zillow.com/homes/"  # placeholder
    NOAA_URL = (
        "https://www.ncdc.noaa.gov/swdiws/json/nx3tvs"  # not actual but example
    )
    GOOGLE_SHEET_ID = "YOUR_SHEET_ID"
    GOOGLE_CREDS_JSON = "google_creds.json"


def fetch_gwinnett_permits(zip_code: str) -> List[PermitRecord]:
    """Fetch permit records from Gwinnett County."""
    try:
        response = requests.get(Config.GWinnett_URL, params={"zip": zip_code}, timeout=10)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - broad for logging
        LOGGER.error("Failed to fetch Gwinnett permits: %s", exc)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    permits: List[PermitRecord] = []
    for row in soup.select("table.permits tr"):
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) >= 2:
            try:
                date = datetime.strptime(cols[0], "%m/%d/%Y")
            except ValueError:
                continue
            permits.append(PermitRecord(date=date, description=cols[1]))
    return permits


def fetch_zillow_details(zip_code: str) -> List[PropertyDetails]:
    """Fetch property details from Zillow."""
    try:
        response = requests.get(Config.ZILLOW_URL + zip_code, timeout=10)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - broad for logging
        LOGGER.error("Failed to fetch Zillow data: %s", exc)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    properties: List[PropertyDetails] = []
    for card in soup.select("article"):
        address = card.select_one(".address").get_text(strip=True) if card.select_one(".address") else ""
        year = int(card.get("data-year-built", 0)) if card.get("data-year-built") else 0
        sqft = int(card.get("data-sqft", 0)) if card.get("data-sqft") else 0
        properties.append(PropertyDetails(address=address, year_built=year, square_feet=sqft))
    return properties


def fetch_noaa_events(zip_code: str, years: int = 3) -> List[Dict[str, Any]]:
    """Fetch severe weather events from NOAA within the last `years` years."""
    start_date = (datetime.utcnow() - timedelta(days=365 * years)).strftime("%Y-%m-%d")
    try:
        response = requests.get(
            Config.NOAA_URL,
            params={"zip": zip_code, "since": start_date},
            timeout=10,
        )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - broad for logging
        LOGGER.error("Failed to fetch NOAA events: %s", exc)
        return []

    try:
        data = response.json()
    except json.JSONDecodeError:
        LOGGER.error("NOAA response was not valid JSON")
        return []

    return data.get("events", [])


def compute_score(property: PropertyDetails) -> int:
    """Compute score based on roof age, permits, and weather events."""
    score = 0
    # Roof age scoring
    if property.roof_age is not None:
        if property.roof_age < 5:
            score += 10
        elif property.roof_age < 10:
            score += 5
        else:
            score -= 5
    # Weather events scoring
    events = property.weather_events or []
    score -= 2 * len(events)
    # Permit activity
    if property.permits:
        score += len(property.permits)
    return score


def update_google_sheet(rows: List[List[Any]], sheet_name: str) -> None:
    """Upload rows to Google Sheets."""
    if gspread is None:
        LOGGER.warning("gspread not installed; skipping Google Sheets upload")
        return
    try:
        credentials = Credentials.from_service_account_file(Config.GOOGLE_CREDS_JSON)
        gc = gspread.authorize(credentials)
        sh = gc.open_by_key(Config.GOOGLE_SHEET_ID)
        worksheet = sh.worksheet(sheet_name)
        worksheet.clear()
        worksheet.update("A1", rows)
    except Exception as exc:  # noqa: BLE001 - broad for logging
        LOGGER.error("Failed to update Google Sheet: %s", exc)


def analyze_properties(zip_code: str = "30519") -> None:
    """Main analysis function."""
    zillow_data = fetch_zillow_details(zip_code)
    for prop in zillow_data:
        prop.permits = fetch_gwinnett_permits(zip_code)
        prop.weather_events = fetch_noaa_events(zip_code)
        if prop.year_built:
            prop.roof_age = datetime.utcnow().year - prop.year_built

    rows = [["Address", "Year Built", "SqFt", "Roof Age", "Permit Count", "Weather Events", "Score"]]
    for prop in zillow_data:
        score = compute_score(prop)
        rows.append(
            [
                prop.address,
                prop.year_built,
                prop.square_feet,
                prop.roof_age,
                len(prop.permits or []),
                len(prop.weather_events or []),
                score,
            ]
        )
    update_google_sheet(rows, sheet_name="Roof Analysis")


if __name__ == "__main__":  # pragma: no cover
    analyze_properties()
