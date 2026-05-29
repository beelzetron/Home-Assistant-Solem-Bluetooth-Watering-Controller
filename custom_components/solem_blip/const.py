"""Constants for our integration."""

DOMAIN = "solem_blip"

DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 10
CONTROLLER_MAC_ADDRESS = "controller_mac_address"
NUM_STATIONS = "num_stations"
SPRINKLE_WITH_RAIN = "sprinkle_with_rain"
WEATHER_ENTITY = "weather_entity"
SOIL_MOISTURE_SENSOR = "soil_moisture_sensor"
SOIL_MOISTURE_THRESHOLD = "soil_moisture_threshold"
DEFAULT_SOIL_MOISTURE = 40
MAX_SPRINKLES_PER_DAY = 5
MONTHS = [
    "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"
]

CHARACTERISTIC_UUID = "108b0002-eab5-bc09-d0ea-0b8f467ce8ee"
BLUETOOTH_TIMEOUT = "bluetooth_timeout"
BLUETOOTH_MIN_TIMEOUT = 5
BLUETOOTH_DEFAULT_TIMEOUT = 30

CONFIG_FLOW_BLUETOOTH_TIMEOUT = 60
CONFIG_FLOW_CONNECT_RETRIES = 3
CONFIG_FLOW_CONNECT_RETRY_DELAY = 5

WEATHER_CACHE_TIMEOUT = "weather_cache_timeout"
WEATHER_CACHE_MIN_TIMEOUT = 1
WEATHER_CACHE_DEFAULT_TIMEOUT = 5
WEATHER_RAIN_PROBABILITY_THRESHOLD = 50

# Legacy option key from OpenWeatherMap-based releases.
OPEN_WEATHER_MAP_API_CACHE_TIMEOUT = "openweathermap_api_cache_timeout"

SOLEM_API_MOCK = "solem_api_mock"
