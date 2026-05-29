"""Config flows for our integration.

This config flow demonstrates many aspects of possible config flows.

Multi step flows
Menus
Using your api data in your flow
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow
)
from homeassistant.const import (
    CONF_SENSORS,
    CONF_SCAN_INTERVAL,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import selector

from solem_blip_ble import SolemClient, SolemConnectionError

from .api import APIConnectionError
from .bluetooth import async_scan_devices
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    CONTROLLER_MAC_ADDRESS,
    NUM_STATIONS,
    WEATHER_ENTITY,
    SPRINKLE_WITH_RAIN,
    MAX_SPRINKLES_PER_DAY,
    SOIL_MOISTURE_SENSOR,
    SOIL_MOISTURE_THRESHOLD,
    DEFAULT_SOIL_MOISTURE,
    MONTHS,
    BLUETOOTH_TIMEOUT,
    BLUETOOTH_MIN_TIMEOUT,
    BLUETOOTH_DEFAULT_TIMEOUT,
    WEATHER_CACHE_TIMEOUT,
    WEATHER_CACHE_MIN_TIMEOUT,
    WEATHER_CACHE_DEFAULT_TIMEOUT,
    OPEN_WEATHER_MAP_API_CACHE_TIMEOUT,
    SOLEM_API_MOCK
)

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    try:
        # ----------------------------------------------------------------------------
        # If your api is not async, use the executor to access it
        # If you cannot connect, raise CannotConnect
        # If the authentication is wrong, raise InvalidAuth
        # ----------------------------------------------------------------------------
        mac_address = data[CONTROLLER_MAC_ADDRESS].rsplit(' - ', 1)
        _LOGGER.debug(mac_address)
        api = SolemClient(mac_address[1], BLUETOOTH_DEFAULT_TIMEOUT)
        await api.connect()
        _LOGGER.debug(f"Connected to Bluetooth controller {mac_address[1]}")
    except (APIConnectionError, SolemConnectionError) as err:
        raise CannotConnect from err
    return {"title": "Solem BL-IP"}


async def validate_settings(hass: HomeAssistant, data: dict[str, Any]) -> bool:
    """Another validation method for our config steps."""
    return True


class SolemConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solem BL-IP."""

    VERSION = 2
    _input_data: dict[str, Any]
    _title: str

    def __init__(self):
        self.current_month_index = 0
        self._num_stations: int = 0

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return SolemOptionsFlowHandler(config_entry)

    @staticmethod
    @callback
    def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
        """Migrate config entries from OpenWeatherMap API key to optional HA weather."""
        if config_entry.version == 1:
            data = dict(config_entry.data)
            data.pop("open_weather_map_api_key", None)
            data.setdefault(WEATHER_ENTITY, None)
            hass.config_entries.async_update_entry(
                config_entry,
                data=data,
                version=2,
            )
        return True

    def _build_basic_schema(
        self,
        *,
        controller_default: str | None = None,
        num_stations_default: int = 1,
        zone_default: str | None = None,
        weather_default: str | None = None,
        sprinkle_default: str = "false",
        soil_sensor_default: str | None = None,
        soil_threshold_default: float = DEFAULT_SOIL_MOISTURE,
        bt_options: list[dict[str, str]],
    ) -> vol.Schema:
        """Shared schema for initial setup and reconfigure."""
        return vol.Schema(
            {
                vol.Required(
                    CONTROLLER_MAC_ADDRESS,
                    default=controller_default,
                ): selector(
                    {
                        "select": {
                            "options": bt_options,
                            "mode": "dropdown",
                        }
                    }
                ),
                vol.Required(NUM_STATIONS, default=num_stations_default): (
                    vol.All(vol.Coerce(int), vol.Clamp(min=1))
                ),
                vol.Required(CONF_SENSORS, default=zone_default): selector(
                    {"entity": {"domain": "zone"}}
                ),
                vol.Optional(WEATHER_ENTITY, default=weather_default): selector(
                    {"entity": {"domain": "weather"}}
                ),
                vol.Optional(SPRINKLE_WITH_RAIN, default=sprinkle_default): selector(
                    {
                        "select": {
                            "options": ["false", "true"],
                            "mode": "dropdown",
                            "translation_key": "true_false_selector",
                        }
                    }
                ),
                vol.Optional(SOIL_MOISTURE_SENSOR, default=soil_sensor_default): selector(
                    {"entity": {"domain": "sensor", "device_class": "humidity"}}
                ),
                vol.Optional(
                    SOIL_MOISTURE_THRESHOLD, default=soil_threshold_default
                ): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
            }
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step.

        Called when you initiate adding an integration via the UI
        """

        errors: dict[str, str] = {}
        

        if user_input is not None:
            # The form has been filled in and submitted, so process the data provided.
            try:
                # ----------------------------------------------------------------------------
                # Validate that the setup data is valid and if not handle errors.
                # You can do any validation you want or no validation on each step.
                # The errors["base"] values match the values in your strings.json and translation files.
                # ----------------------------------------------------------------------------
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
                _LOGGER.exception("Cannot connect")
            except InvalidAuth:
                errors["base"] = "invalid_auth"
                _LOGGER.exception("Invalid Auth")
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            if "base" not in errors:
                # Validation was successful, so proceed to the next step.

                # ----------------------------------------------------------------------------
                # Setting our unique id here just because we have the info at this stage to do that
                # and it will abort early on in the process if alreay setup.
                # You can put this in any step however.
                # ----------------------------------------------------------------------------
                await self.async_set_unique_id(user_input[CONTROLLER_MAC_ADDRESS].rsplit(' - ', 1)[1])
                self._abort_if_unique_id_configured()

                # Set our title variable here for use later
                self._title = info["title"]

                # ----------------------------------------------------------------------------
                # You need to save the input data to a class variable as you go through each step
                # to ensure it is accessible across all steps.
                # ----------------------------------------------------------------------------
                self._input_data = user_input

                # Finish the configuration
                #return self.async_create_entry(title=self._input_data[CONTROLLER_MAC_ADDRESS], data=self._input_data)
                
                self.num_stations = self._input_data[NUM_STATIONS]
                return await self.async_step_station_areas()

        existing_entries = {entry.data.get(CONTROLLER_MAC_ADDRESS) for entry in self.hass.config_entries.async_entries(DOMAIN)}

        bt_devices = await async_scan_devices(self.hass)
        options = [
            {"value": f"{device.name or 'Unknown'} - {device.address}", "label": f"{device.name or 'Unknown'} - {device.address}"}
            for device in bt_devices
            if f"{device.name or 'Unknown'} - {device.address}" not in existing_entries
        ]
        schema = self._build_basic_schema(bt_options=options)

        # Show initial form.
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            last_step=False,  # Adding last_step True/False decides whether form shows Next or Submit buttons
        )

    async def async_step_station_areas(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step to collect lawn area per station."""
        
        errors: dict[str, str] = {}
    
        if user_input is not None:
            try:
                station_areas = [
                    user_input[f"station_{i}_area"]
                    for i in range(1, self.num_stations + 1)
                ]
                self._input_data["station_areas"] = station_areas
                if not self._input_data.get(WEATHER_ENTITY):
                    self._input_data[WEATHER_ENTITY] = None
                if SPRINKLE_WITH_RAIN not in self._input_data:
                    self._input_data[SPRINKLE_WITH_RAIN] = "false"
    
                return self.async_create_entry(
                    title=self._input_data[CONTROLLER_MAC_ADDRESS],
                    data=self._input_data,
                )
            except Exception as e:
                _LOGGER.exception("Failed to process station areas")
                errors["base"] = "unknown"
    
        area_schema = self._build_station_area_schema()
    
        return self.async_show_form(
            step_id="station_areas",
            data_schema=area_schema,
            errors=errors,
            last_step=True,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add reconfigure step to allow to reconfigure a config entry.

        This methid displays a reconfigure option in the integration and is
        different to options.
        It can be used to reconfigure any of the data submitted when first installed.
        This is optional and can be removed if you do not want to allow reconfiguration.
        """

        errors: dict[str, str] = {}
        config_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        
        self.num_stations = config_entry.data.get(NUM_STATIONS, 1)

        if user_input is not None:
            try:
                await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
                _LOGGER.exception("Cannot connect")
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            if "base" not in errors:
                # Validation was successful, so proceed to the next step.

                # ----------------------------------------------------------------------------
                # Setting our unique id here just because we have the info at this stage to do that
                # and it will abort early on in the process if alreay setup.
                # You can put this in any step however.
                # ----------------------------------------------------------------------------
                #await self.async_set_unique_id(info.get("title"))
                #self._abort_if_unique_id_configured()

                # Set our title variable here for use later
                #self._title = info["title"]

                # ----------------------------------------------------------------------------
                # You need to save the input data to a class variable as you go through each step
                # to ensure it is accessible across all steps.
                # ----------------------------------------------------------------------------
                self._input_data = user_input

                # Finish configuration
                #return self.async_update_reload_and_abort(config_entry, unique_id=config_entry.unique_id, data=self._input_data, reason="reconfigure_successful")
                
                return await self.async_step_station_areas_reconfigure()

        bt_devices = await async_scan_devices(self.hass)
        options = [
            {"value": f"{device.name or 'Unknown'} - {device.address}", "label": f"{device.name or 'Unknown'} - {device.address}"}
            for device in bt_devices
        ]

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._build_basic_schema(
                controller_default=config_entry.data[CONTROLLER_MAC_ADDRESS],
                num_stations_default=config_entry.data[NUM_STATIONS],
                zone_default=config_entry.data[CONF_SENSORS],
                weather_default=config_entry.data.get(WEATHER_ENTITY),
                sprinkle_default=config_entry.data.get(SPRINKLE_WITH_RAIN, "false"),
                soil_sensor_default=config_entry.data.get(SOIL_MOISTURE_SENSOR),
                soil_threshold_default=config_entry.data.get(
                    SOIL_MOISTURE_THRESHOLD, DEFAULT_SOIL_MOISTURE
                ),
                bt_options=options,
            ),
            errors=errors,
            last_step=False,
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure lawn area per station."""
        errors: dict[str, str] = {}
        config_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        previous_areas = config_entry.data.get("station_areas", [])
    
        if user_input is not None:
            try:
                station_areas = [
                    user_input[f"station_{i}_area"]
                    for i in range(1, self.num_stations + 1)
                ]
                self._input_data["station_areas"] = station_areas
                if not self._input_data.get(WEATHER_ENTITY):
                    self._input_data[WEATHER_ENTITY] = None
                if SPRINKLE_WITH_RAIN not in self._input_data:
                    self._input_data[SPRINKLE_WITH_RAIN] = "false"
    
                return self.async_update_reload_and_abort(
                    config_entry,
                    unique_id=config_entry.unique_id,
                    data=self._input_data,
                    reason="reconfigure_successful",
                )
            except Exception as e:
                _LOGGER.exception("Failed to process reconfigured station areas")
                errors["base"] = "unknown"
    
        area_schema = self._build_station_area_schema(previous_areas)
    
        return self.async_show_form(
            step_id="station_areas_reconfigure",
            data_schema=area_schema,
            errors=errors,
            last_step=True,
        )
        
    def _build_station_area_schema(self, defaults: list[float] | None = None) -> vol.Schema:
        """Generate schema for station areas with optional defaults."""
        return vol.Schema({
            vol.Required(
                f"station_{i}_area",
                default=defaults[i - 1] if defaults and i - 1 < len(defaults) else 0,
                description={"translation_key": f"station_{i}_area"},
            ): vol.All(vol.Coerce(float), vol.Range(min=0))
            for i in range(1, self.num_stations + 1)
        })

class SolemOptionsFlowHandler(OptionsFlow):
    """Handles the options flow."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):
        """Handle options flow."""
        if user_input is not None:
            options = self.config_entry.options | user_input
            return self.async_create_entry(title="", data=options)

        # It is recommended to prepopulate options fields with default values if available.
        # These will be the same default values you use on your coordinator for setting variable values
        # if the option has not been set.
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): (vol.All(vol.Coerce(int), vol.Clamp(min=MIN_SCAN_INTERVAL))),
                vol.Required(
                    BLUETOOTH_TIMEOUT,
                    default=self.options.get(BLUETOOTH_TIMEOUT, BLUETOOTH_DEFAULT_TIMEOUT),
                ): (vol.All(vol.Coerce(int), vol.Clamp(min=BLUETOOTH_MIN_TIMEOUT))),
                vol.Required(
                    WEATHER_CACHE_TIMEOUT,
                    default=self.options.get(
                        WEATHER_CACHE_TIMEOUT,
                        self.options.get(
                            OPEN_WEATHER_MAP_API_CACHE_TIMEOUT,
                            WEATHER_CACHE_DEFAULT_TIMEOUT,
                        ),
                    ),
                ): (vol.All(vol.Coerce(int), vol.Clamp(min=WEATHER_CACHE_MIN_TIMEOUT))),
                vol.Required(SOLEM_API_MOCK, default=self.options.get(SOLEM_API_MOCK, "false")): selector(
                    {
                        "select": {
                            "options": ["false", "true"],
                            "mode": "dropdown",
                            "translation_key": "true_false_selector",
                        }
                    }
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=data_schema)
class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
