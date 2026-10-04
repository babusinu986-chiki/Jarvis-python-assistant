"""Current weather summaries from the key-free Open-Meteo APIs."""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from functools import lru_cache
from typing import Any

import requests


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Open-Meteo's city index does not reliably resolve Goa or Panaji. Use Panaji's
# stable coordinates for these common spoken names and geocode all other places.
KNOWN_LOCATIONS = {
    "goa": {
        "name": "Panaji",
        "admin1": "Goa",
        "country": "India",
        "latitude": 15.4909,
        "longitude": 73.8278,
    },
    "panaji": {
        "name": "Panaji",
        "admin1": "Goa",
        "country": "India",
        "latitude": 15.4909,
        "longitude": 73.8278,
    },
    "panjim": {
        "name": "Panaji",
        "admin1": "Goa",
        "country": "India",
        "latitude": 15.4909,
        "longitude": 73.8278,
    },
}

WEATHER_CODES = {
    0: "clear skies",
    1: "mainly clear skies",
    2: "partly cloudy skies",
    3: "overcast skies",
    45: "fog",
    48: "freezing fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    56: "light freezing drizzle",
    57: "freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "freezing rain",
    71: "light snowfall",
    73: "snowfall",
    75: "heavy snowfall",
    77: "snow grains",
    80: "light rain showers",
    81: "rain showers",
    82: "heavy rain showers",
    85: "light snow showers",
    86: "heavy snow showers",
    95: "a thunderstorm",
    96: "a thunderstorm with light hail",
    99: "a thunderstorm with heavy hail",
}


class WeatherServiceError(RuntimeError):
    """A short user-facing weather lookup failure."""


class WeatherService:
    def __init__(
        self,
        *,
        http_get: Callable[..., Any] = requests.get,
        timeout_seconds: float = 12,
    ) -> None:
        self.http_get = http_get
        self.timeout_seconds = timeout_seconds

    def current_summary(self, city: str) -> str:
        clean_city = " ".join(city.split())
        if not clean_city:
            raise WeatherServiceError("Tell me which city's weather you want.")

        try:
            place = self._find_place(clean_city)
            weather = self._get_weather(place["latitude"], place["longitude"])
            current = weather["current"]
            daily = weather.get("daily", {})

            temperature = round(float(current["temperature_2m"]))
            feels_like = round(float(current["apparent_temperature"]))
            humidity = round(float(current["relative_humidity_2m"]))
            wind_speed = round(float(current["wind_speed_10m"]))
            precipitation = float(current.get("precipitation", 0))
            weather_code = int(current["weather_code"])
            rain_values = daily.get("precipitation_probability_max") or [0]
            rain_chance = round(float(rain_values[0] or 0))
        except WeatherServiceError:
            raise
        except (KeyError, TypeError, ValueError, IndexError) as error:
            raise WeatherServiceError(
                "The weather service returned incomplete data. Please try again."
            ) from error
        except requests.RequestException as error:
            raise WeatherServiceError(
                "I could not reach the weather service right now."
            ) from error

        condition = WEATHER_CODES.get(weather_code, "mixed weather conditions")
        location_name = self._plain_text(place.get("name") or clean_city)
        area = self._plain_text(place.get("admin1") or "").strip()
        if area and area.lower() != location_name.lower():
            location_name = f"{location_name}, {area}"

        rain_now = (
            f" Current precipitation is {precipitation:g} millimeters."
            if precipitation > 0
            else ""
        )
        return (
            f"In {location_name}, current conditions are {condition}. The temperature is "
            f"{temperature} degrees Celsius and feels like {feels_like}. "
            f"Humidity is {humidity} percent, wind speed is {wind_speed} "
            f"kilometers per hour, and today's highest rain chance is "
            f"{rain_chance} percent.{rain_now}"
        )

    @lru_cache(maxsize=32)
    def _find_place(self, city: str) -> dict[str, Any]:
        known_place = KNOWN_LOCATIONS.get(city.casefold())
        if known_place:
            return dict(known_place)

        search_name = city
        response = self.http_get(
            GEOCODING_URL,
            params={
                "name": search_name,
                "count": 10,
                "language": "en",
                "format": "json",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        results = response.json().get("results") or []
        if not results:
            raise WeatherServiceError(
                f"I could not find a place named {city}. Please try another city."
            )

        requested_name, _, requested_country = search_name.partition(",")
        exact_matches = [
            result
            for result in results
            if str(result.get("name", "")).casefold()
            == requested_name.strip().casefold()
        ]
        if requested_country.strip():
            country_matches = [
                result
                for result in exact_matches
                if str(result.get("country", "")).casefold()
                == requested_country.strip().casefold()
            ]
            if country_matches:
                return country_matches[0]
        return (exact_matches or results)[0]

    @staticmethod
    def _plain_text(value: object) -> str:
        """Return Windows-console-safe place text from external API data."""
        normalized = unicodedata.normalize("NFKD", str(value))
        return normalized.encode("ascii", "ignore").decode("ascii")

    def _get_weather(self, latitude: float, longitude: float) -> dict[str, Any]:
        response = self.http_get(
            FORECAST_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": (
                    "temperature_2m,apparent_temperature,relative_humidity_2m,"
                    "precipitation,weather_code,wind_speed_10m"
                ),
                "daily": (
                    "temperature_2m_max,temperature_2m_min,"
                    "precipitation_probability_max"
                ),
                "forecast_days": 1,
                "timezone": "auto",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
