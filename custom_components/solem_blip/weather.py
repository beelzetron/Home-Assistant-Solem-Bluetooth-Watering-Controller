"""Home Assistant weather entity provider for rain-aware irrigation."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from solem_blip_ble import APIConnectionError

from .const import WEATHER_RAIN_PROBABILITY_THRESHOLD

_LOGGER = logging.getLogger(__name__)

RAIN_CONDITIONS = frozenset(
    {
        "rainy",
        "pouring",
        "lightning-rainy",
        "hail",
        "snowy-rainy",
    }
)

DEFAULT_RAIN_MM_PER_HOUR = {
    "pouring": 4.0,
    "lightning-rainy": 3.0,
    "rainy": 1.5,
    "snowy-rainy": 1.0,
    "hail": 2.0,
}


class HomeAssistantWeatherProvider:
    """Read rain data from a Home Assistant weather entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        entity_id: str | None,
        cache_timeout_minutes: int,
    ) -> None:
        self.hass = hass
        self.entity_id = entity_id
        self.cache_timeout = cache_timeout_minutes
        self._cache_forecast: list[dict[str, Any]] | None = None
        self._cache_current: dict[str, Any] | None = None
        self._last_forecast_fetch_time: datetime | None = None
        self.last_forecast_date = dt_util.now().date()
        self._last_current_fetch_time: datetime | None = None

    @property
    def enabled(self) -> bool:
        """Return True when a weather entity is configured."""
        return bool(self.entity_id)

    def _get_state(self):
        if not self.enabled:
            return None
        return self.hass.states.get(self.entity_id)

    @staticmethod
    def _condition_is_rainy(condition: str | None) -> bool:
        return (condition or "").lower() in RAIN_CONDITIONS

    @staticmethod
    def _parse_forecast_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return dt_util.as_local(value) if value.tzinfo is None else value
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
            return dt_util.as_local(parsed) if parsed.tzinfo is None else parsed
        return None

    def _build_current_snapshot(self, state) -> dict[str, Any]:
        attrs = dict(state.attributes)
        condition = state.state
        precipitation = attrs.get("precipitation")
        if precipitation is None:
            precipitation = attrs.get("precipitation_intensity")

        return {
            "entity_id": state.entity_id,
            "condition": condition,
            "precipitation": precipitation,
            "precipitation_unit": attrs.get("precipitation_unit"),
            "temperature": attrs.get("temperature"),
            "dt_txt": dt_util.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    async def get_current_weather(self) -> dict[str, Any]:
        """Return a normalized snapshot of the configured weather entity."""
        if not self.enabled:
            return {}

        now = dt_util.now()
        if (
            self._cache_current
            and self._last_current_fetch_time
            and now - self._last_current_fetch_time
            < timedelta(minutes=self.cache_timeout)
        ):
            return self._cache_current

        state = self._get_state()
        if state is None or state.state in ("unknown", "unavailable"):
            raise APIConnectionError(
                f"Weather entity {self.entity_id} is unavailable"
            )

        self._cache_current = self._build_current_snapshot(state)
        self._last_current_fetch_time = now
        return self._cache_current

    async def is_raining(self) -> dict[str, Any]:
        if not self.enabled:
            return {"is_raining": False, "current": {}}

        current = await self.get_current_weather()
        condition = current.get("condition")
        precipitation = current.get("precipitation")

        is_raining = self._condition_is_rainy(condition)
        if not is_raining and precipitation is not None:
            try:
                is_raining = float(precipitation) > 0
            except (TypeError, ValueError):
                pass

        return {"is_raining": is_raining, "current": current}

    async def _fetch_hourly_forecast(self) -> list[dict[str, Any]]:
        if not self.enabled:
            return []

        state = self._get_state()
        if state is None or state.state in ("unknown", "unavailable"):
            raise APIConnectionError(
                f"Weather entity {self.entity_id} is unavailable"
            )

        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": self.entity_id, "type": "hourly"},
                blocking=True,
                return_response=True,
            )
        except Exception as exc:
            _LOGGER.debug(
                "weather.get_forecasts failed for %s: %s",
                self.entity_id,
                exc,
            )
            legacy = state.attributes.get("forecast")
            if isinstance(legacy, list):
                return legacy
            raise APIConnectionError(
                f"Could not read forecast from {self.entity_id}"
            ) from exc

        service_result = response.get("weather.get_forecasts", {})
        entity_result = service_result.get(self.entity_id, {})
        forecast = entity_result.get("forecast", [])
        if not isinstance(forecast, list):
            return []
        return forecast

    async def get_forecast(self) -> list[dict[str, Any]]:
        """Return cached hourly forecast entries for today and later."""
        if not self.enabled:
            return []

        now = dt_util.now()
        if (
            self._cache_forecast is not None
            and self._last_forecast_fetch_time
            and now - self._last_forecast_fetch_time
            < timedelta(minutes=self.cache_timeout)
        ):
            return self._cache_forecast

        if self.last_forecast_date != now.date():
            self._cache_forecast = []
            self.last_forecast_date = now.date()

        try:
            forecast_items = await self._fetch_hourly_forecast()
        except APIConnectionError:
            if self._cache_forecast:
                return self._cache_forecast
            raise

        normalized: list[dict[str, Any]] = []
        for item in forecast_items:
            if not isinstance(item, dict):
                continue
            forecast_dt = self._parse_forecast_datetime(
                item.get("datetime") or item.get("datetime_iso")
            )
            if forecast_dt is None:
                continue
            normalized.append(
                {
                    **item,
                    "dt_txt": forecast_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "condition": item.get("condition"),
                    "precipitation": item.get("precipitation"),
                    "precipitation_probability": item.get(
                        "precipitation_probability"
                    ),
                }
            )

        self._cache_forecast = normalized
        self._last_forecast_fetch_time = now
        return self._cache_forecast

    async def will_it_rain(self) -> dict[str, Any]:
        if not self.enabled:
            return {"will_rain": False, "forecast": []}

        forecast = await self.get_forecast()
        now = dt_util.now()
        today_str = now.strftime("%Y-%m-%d")

        relevant: list[dict[str, Any]] = []
        for item in forecast:
            forecast_dt = self._parse_forecast_datetime(item.get("dt_txt"))
            if forecast_dt is None or forecast_dt < now:
                continue
            if forecast_dt.strftime("%Y-%m-%d") != today_str:
                continue
            relevant.append(item)

        will_rain = False
        for item in relevant:
            condition = item.get("condition")
            probability = item.get("precipitation_probability")
            precipitation = item.get("precipitation")

            if self._condition_is_rainy(condition):
                will_rain = True
                break
            if probability is not None:
                try:
                    if float(probability) >= WEATHER_RAIN_PROBABILITY_THRESHOLD:
                        will_rain = True
                        break
                except (TypeError, ValueError):
                    pass
            if precipitation is not None:
                try:
                    if float(precipitation) > 0:
                        will_rain = True
                        break
                except (TypeError, ValueError):
                    pass

        return {"will_rain": will_rain, "forecast": forecast}

    async def get_total_rain_forecast_for_today(self) -> float:
        """Return predicted rainfall (mm) from now until end of today."""
        if not self.enabled:
            return 0.0

        forecast = (await self.will_it_rain()).get("forecast", [])
        now = dt_util.now()
        today_str = now.strftime("%Y-%m-%d")
        total_rain_mm = 0.0

        for item in forecast:
            forecast_dt = self._parse_forecast_datetime(item.get("dt_txt"))
            if forecast_dt is None or forecast_dt < now:
                continue
            if forecast_dt.strftime("%Y-%m-%d") != today_str:
                continue

            precipitation = item.get("precipitation")
            if precipitation is None:
                if self._condition_is_rainy(item.get("condition")):
                    precipitation = DEFAULT_RAIN_MM_PER_HOUR.get(
                        (item.get("condition") or "").lower(), 1.0
                    )
                else:
                    continue

            try:
                total_rain_mm += float(precipitation)
            except (TypeError, ValueError):
                continue

        return total_rain_mm

    def estimate_current_rain_mm(self, poll_interval_seconds: float) -> float:
        """Estimate rainfall accumulated since the last poll."""
        if not self.is_raining_now_snapshot():
            return 0.0

        current = self._cache_current or {}
        precipitation = current.get("precipitation")
        if precipitation is not None:
            try:
                mm_per_hour = float(precipitation)
                return mm_per_hour * (poll_interval_seconds / 3600)
            except (TypeError, ValueError):
                pass

        condition = (current.get("condition") or "").lower()
        mm_per_hour = DEFAULT_RAIN_MM_PER_HOUR.get(condition, 1.0)
        return mm_per_hour * (poll_interval_seconds / 3600)

    def is_raining_now_snapshot(self) -> bool:
        current = self._cache_current or {}
        if self._condition_is_rainy(current.get("condition")):
            return True
        precipitation = current.get("precipitation")
        if precipitation is not None:
            try:
                return float(precipitation) > 0
            except (TypeError, ValueError):
                pass
        return False
