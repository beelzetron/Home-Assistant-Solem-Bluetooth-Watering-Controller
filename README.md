# Home Assistant Solem BL-IP Integration

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

This integration depends on the **`solem-blip-ble`** Python package ([PyPI](https://pypi.org/project/solem-blip-ble/), [source](https://github.com/beelzetron/solem-blip-ble)). Home Assistant installs it from PyPI automatically when you set up or update the integration (currently requires `solem-blip-ble>=0.1.8`).

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
* the OpenWeatherMap API key (you will need to create an API key. first you need to create an [account](https://home.openweathermap.org/users/sign_up))
* sprinkle even when raining (a true/false dropdown - true if you still want to sprinke even if it's raining, false otherwise)

Afterwards an empty irrigation schedule is created. If you want to control it you will need the [Solem Schedule Card](https://github.com/hcraveiro/solem-schedule-card) installed. Previously I had it on the config flow but it is so not user friendly that I decided that a card would be better.

## Sensors

There is a number of sensors that are mande available for each controller/config entry:
* Controller status - on or off and also has an attribute that stores the schedule in json
* Station(n) status - stopped or sprinkling
* Has rained today - true if it has, false otherwise
* Is it raining now - true if it is raining, false otherwise
* Will it rain today - true if it will rain from this moment, false otherwise
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
