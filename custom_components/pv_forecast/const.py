"""Konstanty integrace PV Forecast."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

DOMAIN = "pv_forecast"
LOGGER = logging.getLogger(__package__)

CONF_ALTITUDE = "altitude"
CONF_DAYS_AHEAD = "days_ahead"
CONF_STRINGS = "strings"

DEFAULT_NAME = "Solar production forecast"
DEFAULT_DAYS_AHEAD = 2

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_HOURLY = (
    "shortwave_radiation",        # GHI, průměr za předchozí hodinu
    "direct_normal_irradiance",   # DNI
    "diffuse_radiation",          # DHI
    "temperature_2m",
)

UPDATE_INTERVAL = timedelta(hours=1)
RETRY_INTERVAL = timedelta(minutes=10)    # po chybě stahování
STATE_REFRESH_MINUTES = 5                 # přepočet „now“ senzorů

# Výchozí konfigurace stringů = elektrárna z původního skriptu.
# Každý string: počet panelů + jedna či více orientací (parametry 1 panelu).
# Při více orientacích se bere minimum (string omezen nejslabším panelem).
# Volitelné klíče orientace: performance_ratio (0.80), temp_coefficient
# (-0.004), t_ref (25), noct (48).
DEFAULT_STRINGS: list[dict[str, Any]] = [
    {
        "name": "string1",
        "panels": 10,
        "orientations": [
            {"peak_power_wp": 450, "tilt_deg": 35, "azimuth_from_north_deg": 182},
        ],
    },
    {
        "name": "string2",
        "panels": 10,
        "orientations": [
            {"peak_power_wp": 500, "tilt_deg": 35, "azimuth_from_north_deg": 182},
            {"peak_power_wp": 500, "tilt_deg": 15, "azimuth_from_north_deg": 182},
        ],
    },
]
