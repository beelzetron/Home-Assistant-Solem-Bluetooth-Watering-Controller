"""OpenWeatherMap API for Solem BL-IP integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from homeassistant.util import dt as dt_util
from homeassistant.util.dt import as_local

from solem_blip_ble import APIConnectionError, SolemConnectionError

from .const import OPEN_WEATHER_MAP_CURRENT_URL, OPEN_WEATHER_MAP_FORECAST_URL

_LOGGER = logging.getLogger(__name__)

# Re-export for existing integration code
__all__ = ["OpenWeatherMapAPI", "APIConnectionError", "SolemConnectionError"]


class OpenWeatherMapAPI:
    """Class for OpenWeatherMap API."""

    def __init__(self, api_key: str, latitude: str, longitude: str, timeout: int) -> None:
        """Initialise."""
        self.api_key = api_key
        self.latitude = latitude
        self.longitude = longitude
        self.timeout = timeout
        self._cache_forecast = None
        self._cache_current = None
        self._last_forecast_fetch_time = None
        self.last_forecast_date = datetime.now().date()
        self._last_current_fetch_time = None

    async def get_current_weather(self) -> Any:
        now = dt_util.now()

        if (
            self._cache_current
            and self._last_current_fetch_time
            and now - self._last_current_fetch_time < timedelta(minutes=self.timeout)
        ):
            _LOGGER.debug("Returning cached data.")
            return self._cache_current

        weather_url = (
            f"{OPEN_WEATHER_MAP_CURRENT_URL}appid={self.api_key}"
            f"&lat={self.latitude}&lon={self.longitude}"
        )
        _LOGGER.debug("Getting current weather at : %s", weather_url)

        async with aiohttp.ClientSession() as session:
            async with session.get(weather_url) as response:
                try:
                    data = await response.json()
                    _LOGGER.debug("Current Weather Data: %s", data)

                    if "dt" in data:
                        utc_dt = datetime.fromtimestamp(data["dt"], tz=timezone.utc)
                        local_dt = as_local(utc_dt)
                        data["dt_txt"] = local_dt.strftime("%Y-%m-%d %H:%M:%S")

                    self._cache_current = data
                    self._last_current_fetch_time = now
                except Exception as ex:
                    _LOGGER.error("Error processing Current Weather data: JSON format invalid!")
                    raise APIConnectionError(
                        "Error processing Current Weather data: JSON format invalid!"
                    ) from ex

        return self._cache_current

    async def is_raining(self) -> dict:
        current_weather = await self.get_current_weather()

        return {
            "is_raining": "rain" in current_weather,
            "current": current_weather,
        }

    async def get_forecast(self) -> list:
        """Obtains and preserves data from 00h till 00h of the next day."""
        now = datetime.now()

        if (
            self._cache_forecast
            and self._last_forecast_fetch_time
            and now - self._last_forecast_fetch_time < timedelta(minutes=self.timeout)
        ):
            _LOGGER.debug("Returning cached data.")
            return self._cache_forecast

        temp_cache = self._cache_forecast.copy() if self._cache_forecast else []

        if self.last_forecast_date != now.date():
            _LOGGER.debug("Day changed, will get 00h forecast to new day...")
            last_00_03_forecast = None

            for forecast in self._cache_forecast or []:
                forecast_time_str = forecast["dt_txt"]
                forecast_dt = datetime.strptime(forecast_time_str, "%Y-%m-%d %H:%M:%S")
                if forecast_dt.hour == 0:
                    last_00_03_forecast = forecast
                    break

            self._cache_forecast = []
            self.last_forecast_date = now.date()

            if last_00_03_forecast:
                self._cache_forecast.append(last_00_03_forecast)

        current_hour = now.hour
        forecast_hours = [h for h in range(0, 21, 3) if h >= current_hour]
        forecast_hours.append(0)
        items = len(forecast_hours)

        weather_url = (
            f"{OPEN_WEATHER_MAP_FORECAST_URL}&appid={self.api_key}"
            f"&lat={self.latitude}&lon={self.longitude}&cnt={items}"
        )
        _LOGGER.debug("Getting forecast at: %s", weather_url)

        async with aiohttp.ClientSession() as session:
            async with session.get(weather_url) as response:
                try:
                    data = await response.json()
                    _LOGGER.debug("Forecast Weather Data: %s", data)

                    for item in data["list"]:
                        forecast_time_str = item["dt_txt"]

                        existing_index = next(
                            (
                                index
                                for index, forecast in enumerate(self._cache_forecast)
                                if forecast["dt_txt"] == forecast_time_str
                            ),
                            None,
                        )

                        if existing_index is not None:
                            self._cache_forecast[existing_index] = item
                        else:
                            self._cache_forecast.append(item)

                    self._last_forecast_fetch_time = now

                except Exception as ex:
                    _LOGGER.error(
                        "Error processing Forecast Weather data: JSON format invalid!",
                        exc_info=True,
                    )

                    if not self._cache_forecast:
                        self._cache_forecast = temp_cache

                    raise APIConnectionError(
                        "Error processing Forecast Weather data: JSON format invalid!"
                    ) from ex

        return self._cache_forecast

    async def will_it_rain(self) -> dict:
        """Verifies if it will rain for the rest of the day."""
        forecast = await self.get_forecast()

        now = dt_util.now()
        today_str = now.strftime("%Y-%m-%d")
        current_hour = now.hour

        block_hours = [h for h in range(0, 21, 3)]
        current_block = max([h for h in block_hours if h <= current_hour])

        relevant_forecasts = []
        for item in forecast:
            forecast_time_str = item["dt_txt"]
            forecast_date, forecast_hour_minute = forecast_time_str.split(" ")
            forecast_hour, _, _ = forecast_hour_minute.split(":")
            forecast_hour = int(forecast_hour)

            if forecast_date == today_str and forecast_hour >= current_block:
                relevant_forecasts.append(item)

        will_rain = any(item.get("pop", 0) > 0.50 for item in relevant_forecasts)

        return {
            "will_rain": will_rain,
            "forecast": forecast,
        }

    async def get_total_rain_forecast_for_today(self) -> float:
        """Calculates total amount of rain predicted (mm) for the rest of the day."""
        will_it_rain_result = await self.will_it_rain()
        forecasts = will_it_rain_result.get("forecast", [])

        now = dt_util.now()
        current_time = now.hour * 60 + now.minute
        today_str = now.strftime("%Y-%m-%d")
        total_rain_mm = 0.0

        for item in forecasts:
            forecast_time_str = item["dt_txt"]
            forecast_date, forecast_hour_minute = forecast_time_str.split(" ")
            forecast_hour, _, _ = forecast_hour_minute.split(":")
            forecast_hour = int(forecast_hour)

            rain_data = item.get("rain", {})
            rain_mm = rain_data.get("3h", 0.0)

            if forecast_date != today_str:
                continue

            forecast_start_minute = forecast_hour * 60
            forecast_end_minute = forecast_start_minute + 180

            if forecast_end_minute <= current_time:
                continue

            if forecast_start_minute <= current_time < forecast_end_minute:
                remaining_minutes = forecast_end_minute - current_time
                rain_mm = (remaining_minutes / 180) * rain_mm

            total_rain_mm += rain_mm

        return total_rain_mm
