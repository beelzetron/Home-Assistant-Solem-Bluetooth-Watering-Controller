# Home Assistant Solem BL-IP Integration

> **Note:** This beelzetron fork is archived for personal housekeeping. Ongoing minimal BL-IP work (BLE status, battery, manual control + HA automations) lives in **[beelzetron/solem-blip-ha](https://github.com/beelzetron/solem-blip-ha)** — a separate project with a different scope.
>
> For the full scheduler integration, rain math, and [Solem Schedule Card](https://github.com/hcraveiro/solem-schedule-card), use **[Henrique Craveiro's original integration](https://github.com/hcraveiro/Home-Assistant-Solem-Bluetooth-Watering-Controller)**.

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/beelzetron/Home-Assistant-Solem-Bluetooth-Watering-Controller.svg)](https://github.com/beelzetron/Home-Assistant-Solem-Bluetooth-Watering-Controller/releases/)

Integrate the Solem **BL-IP** Bluetooth irrigation controller into Home Assistant. This integration allows you to manually control irrigation or create a schedule.

- [Home Assistant Solem BL-IP Integration](#home-assistant-solem-bl-ip-integration)
    - [Installation](#installation)
    - [Configuration](#configuration)
    - [Documentation](#documentation)
    - [Sensors](#sensors)
    - [FAQ](#faq)

## Installation

This integration depends on the **`solem-blip-ble`** Python package ([PyPI](https://pypi.org/project/solem-blip-ble/), [source](https://github.com/beelzetron/solem-blip-ble)). Home Assistant installs it from PyPI automatically when you set up or update the integration (currently requires `solem-blip-ble>=0.1.9`).

For local development against a checkout of the library (overrides the PyPI install):

```bash
pip install -e /path/to/solem-blip-ble
```

### HACS

Use this link to directly open this repository in HACS:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=beelzetron&repository=Home-Assistant-Solem-Bluetooth-Watering-Controller&category=integration)

_or_

1. Install [HACS](https://hacs.xyz/) if you do not have it already
2. Open HACS → **Integrations**
3. Open the menu (⋮) → **Custom repositories**
4. Add `https://github.com/beelzetron/Home-Assistant-Solem-Bluetooth-Watering-Controller` as category **Integration**
5. Search for **Solem BL-IP** and install
6. Restart Home Assistant

When the integration is installed in HACS, add it in Home Assistant: Settings → Devices & Services → Add Integration → Search for **Solem BL-IP**.

The configuration happens in the configuration flow when you add the integration.
If you want to configure the schedule you should install the card [Solem Schedule Card](https://github.com/hcraveiro/solem-schedule-card).

## Documentation

BLE protocol (commands, notifications, remaining-time byte layout): [solem-blip-ble `docs/ble_protocol.md`](https://github.com/beelzetron/solem-blip-ble/blob/main/docs/ble_protocol.md)

## Configuration

For each BL-IP controller that you want to use, you should add a config entry. You will have a config flow where it is asked:
* which is the bluetooth device
* the number of stations your controller have
* the controller location (it loads the zones you have in HA)
* an optional **Home Assistant weather entity** (for rain skip, rain sensors, and forecast-based irrigation adjustments — uses whatever weather integration you already have, e.g. Met.no, Open-Meteo, or OpenWeatherMap via HA)
* sprinkle even when raining (only applies when a weather entity is configured)

Afterwards an empty irrigation schedule is created. If you want to control it you will need the [Solem Schedule Card](https://github.com/hcraveiro/solem-schedule-card) installed. Previously I had it on the config flow but it is so not user friendly that I decided that a card would be better.

## Sensors

There is a number of sensors that are mande available for each controller/config entry:
* Controller status - on or off and also has an attribute that stores the schedule in json
* Battery - percentage (0–100) mapped from MySOLEM level 0–5
* Battery voltage - estimated volts (raw byte / 10; diagnostic entity, disabled by default)
* Battery low - binary alert when voltage drops below MySOLEM threshold
* Station(n) status - stopped or sprinkling
* Has rained today - true if it has, false otherwise (requires weather entity)
* Is it raining now - true if it is raining, false otherwise (requires weather entity)
* Will it rain today - true if it will rain from this moment, false otherwise (requires weather entity)
* Last rain - datetime of last time it rained
* Last sprinkle - last time there was a sprinkle either manual or scheduled
* Next schedule - next time that it is scheduled to sprinkle
* Rain time today - amount of minutes that rained today
* Total amount of rain today - amount of mm of rain until now
* Total forecasted rain today - amount of mm of forecasted rain, taking into account what already rained and what will rain from now 
* Water flow rate (n) - water flow rate for station n (Liter/minute)
* Total water consumption - total water consumption for the whole system, taking into account how much time it sprinkles and the water flow rate
* Irrigation manual duration - number of minutes for sprinkle (manual)
* Sprinkle station (n) - trigger sprinkling on station n
* Stop sprinkle - stop any ongoing sprinkling
* Turn on controller - turn on controller
* Turn off controller - turn off controller

## FAQ

### Can I configure other controller models?

No. This integration targets the **BL-IP** only. Other Solem models are not supported yet.
