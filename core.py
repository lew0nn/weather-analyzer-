from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

import pandas as pd
import numpy as np
import requests


API_URL = "https://archive-api.open-meteo.com/v1/archive"
GEOCODING_API_URL = "https://geocoding-api.open-meteo.com/v1/search"
MIN_YEAR = 1940


@dataclass(frozen=True)
class WeatherRequest:
    country: str
    city: str
    latitude: float
    longitude: float
    timezone: str
    year: int

    @property
    def start_date(self):
        return f"{self.year}-01-01"

    @property
    def end_date(self):
        return date.today().isoformat() if self.year == date.today().year else f"{self.year}-12-31"

    @property
    def title(self):
        suffix = f"{self.year} year to date" if self.year == date.today().year else str(self.year)
        return f"{self.city}, {self.country} - {suffix}"


def suggestion(label, **values):
    return SimpleNamespace(label=label, **values)


def normalize_text(value):
    return str(value).strip().casefold()


def validate_year(year):
    try:
        year = int(str(year).strip())
    except ValueError as error:
        raise ValueError("Year must be a number.") from error

    if not MIN_YEAR <= year <= date.today().year:
        raise ValueError(f"Year must be between {MIN_YEAR} and {date.today().year}.")

    return year


def get_geocoding_results(query, count):
    response = requests.get(
        GEOCODING_API_URL,
        params={
            "name": query,
            "count": min(max(int(count), 1), 100),
            "language": "en",
            "format": "json",
        },
        timeout=15,
    )
    response.raise_for_status()

    data = response.json()
    if data.get("error"):
        raise ValueError(data.get("reason", "The location search failed."))

    results = data.get("results", [])
    if not isinstance(results, list):
        raise ValueError("The location search returned an unexpected response.")
    return results


def search_locations(country, city, limit=8):
    city, country = str(city).strip(), str(country).strip()
    if not city:
        return []

    country_query, city_query = normalize_text(country), normalize_text(city)
    suggestions = []

    for result in get_geocoding_results(city, limit * 4):
        result_country, result_city = result.get("country", ""), result.get("name", "")

        if country_query and not (
            country_query in normalize_text(result_country)
            or country_query == normalize_text(result.get("country_code", ""))
        ):
            continue
        if city_query and city_query not in normalize_text(result_city):
            continue
        if not all(key in result for key in ("latitude", "longitude", "timezone")):
            continue

        suggestions.append(
            suggestion(
                ", ".join(part for part in (result_city, result.get("admin1", ""), result_country) if part),
                country=result_country,
                city=result_city,
                latitude=float(result["latitude"]),
                longitude=float(result["longitude"]),
                timezone=result["timezone"],
            )
        )

    suggestions.sort(
        key=lambda item: (
            normalize_text(item.country) != country_query if country_query else False,
            normalize_text(item.city) != city_query,
            item.country,
            item.city,
        )
    )
    return suggestions[:limit]


def search_countries(country, limit=8):
    country = str(country).strip()
    if not country:
        return []

    suggestions, seen, country_query = [], set(), normalize_text(country)
    for result in get_geocoding_results(country, max(limit * 12, 30)):
        candidates = [result.get("country", "")]
        if str(result.get("feature_code", "")).startswith("PCL"):
            candidates.append(result.get("name", ""))

        for common_name in candidates:
            normalized_name = normalize_text(common_name)
            if (
                not common_name
                or country_query not in normalized_name
                or normalized_name in seen
            ):
                continue

            seen.add(normalized_name)
            suggestions.append(suggestion(common_name, name=common_name))

    suggestions.sort(
        key=lambda item: (
            normalize_text(item.name) != country_query,
            not normalize_text(item.name).startswith(country_query),
            normalize_text(item.name),
        )
    )
    return suggestions[:limit]


def search_country_cities(country, city="", limit=8):
    country, city = str(country).strip(), str(city).strip()
    if not country or not city:
        return []
    return search_locations(country, city, limit=limit)


def create_weather_request(country, city, year, location=None):
    country, city = str(country).strip(), str(city).strip()

    if not country:
        raise ValueError("Please enter a country.")

    if not city:
        raise ValueError("Please enter a city.")

    year = validate_year(year)

    if location is not None and (
        normalize_text(location.country) != normalize_text(country)
        or normalize_text(location.city) != normalize_text(city)
    ):
        location = None

    if location is None:
        try:
            location = search_locations(country, city, limit=1)[0]
        except IndexError as error:
            raise ValueError("No matching city was found for that country.") from error

    return WeatherRequest(
        country=location.country,
        city=location.city,
        latitude=location.latitude,
        longitude=location.longitude,
        timezone=location.timezone,
        year=year,
    )


def get_weather_data(request):
    params = {
        "latitude": request.latitude,
        "longitude": request.longitude,
        "start_date": request.start_date,
        "end_date": request.end_date,
        "daily": "temperature_2m_max,temperature_2m_min,temperature_2m_mean,precipitation_sum,wind_speed_10m_max",
        "timezone": request.timezone,
    }

    response = requests.get(API_URL, params=params, timeout=25)
    response.raise_for_status()

    data = response.json()

    if "daily" not in data:
        raise ValueError("The weather API did not return daily weather data.")

    weather_table = pd.DataFrame(data["daily"])
    weather_table["time"] = pd.to_datetime(weather_table["time"])

    add_weather_features(weather_table)
    return weather_table


def moving_average(values, days=7):
    values = values.to_numpy(float)
    if len(values) == 0:
        return values
    days = min(days, len(values))
    weights = np.ones(days)
    valid = np.isfinite(values)
    total = np.convolve(np.where(valid, values, 0), weights, "same")
    count = np.convolve(valid, weights, "same")
    return np.divide(total, count, out=np.full_like(values, np.nan), where=count != 0)


def add_weather_features(weather_table):
    if {"temperature_2m_max", "temperature_2m_min", "temperature_2m_mean"}.issubset(weather_table):
        weather_table["temperature_range"] = np.subtract(
            weather_table["temperature_2m_max"].to_numpy(float),
            weather_table["temperature_2m_min"].to_numpy(float),
        )
        weather_table["temperature_smooth"] = moving_average(weather_table["temperature_2m_mean"])
    if "precipitation_sum" in weather_table:
        weather_table["rainy_day"] = np.greater(weather_table["precipitation_sum"].to_numpy(float), 0)


def analyze_weather_data(weather_table):
    mean_temp = weather_table["temperature_2m_mean"].to_numpy(float)
    high_temp = weather_table["temperature_2m_max"].to_numpy(float)
    low_temp = weather_table["temperature_2m_min"].to_numpy(float)
    rain = weather_table["precipitation_sum"].to_numpy(float)
    summary = {
        "Average temperature": float(np.nanmean(mean_temp)),
        "Highest temperature": float(np.nanmax(high_temp)),
        "Lowest temperature": float(np.nanmin(low_temp)),
        "Temperature variation": float(np.nanstd(mean_temp)),
        "Total rain": float(np.nansum(rain)),
        "Rainy days": int(np.count_nonzero(rain > 0)),
    }

    if "wind_speed_10m_max" in weather_table:
        summary["Average wind"] = float(np.nanmean(weather_table["wind_speed_10m_max"].to_numpy(float)))

    return summary
