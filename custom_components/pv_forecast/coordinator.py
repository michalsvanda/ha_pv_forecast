"""Koordinátor: stahuje Open-Meteo a počítá předpověď jednou za hodinu."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ALTITUDE,
    CONF_DAYS_AHEAD,
    CONF_STRINGS,
    DEFAULT_DAYS_AHEAD,
    DOMAIN,
    LOGGER,
    OPEN_METEO_HOURLY,
    OPEN_METEO_URL,
    RETRY_INTERVAL,
    UPDATE_INTERVAL,
)
from .model import ForecastData, build_forecast

type PVForecastConfigEntry = ConfigEntry[PVForecastCoordinator]


class PVForecastCoordinator(DataUpdateCoordinator[ForecastData]):
    """Drží poslední spočítanou předpověď."""

    config_entry: PVForecastConfigEntry

    def __init__(self, hass: HomeAssistant, entry: PVForecastConfigEntry) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self._session = async_get_clientsession(hass)

    @property
    def settings(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def _async_update_data(self) -> ForecastData:
        cfg = self.settings
        days_ahead = int(cfg.get(CONF_DAYS_AHEAD, DEFAULT_DAYS_AHEAD))
        params = {
            "latitude": cfg[CONF_LATITUDE],
            "longitude": cfg[CONF_LONGITUDE],
            "hourly": ",".join(OPEN_METEO_HOURLY),
            "timezone": "UTC",
            # dny se počítají v UTC → +1 den na konci a 1 den zpět, aby byly
            # pokryté celé lokální dny včetně půlnoci
            "past_days": 1,
            "forecast_days": min(days_ahead + 2, 16),
        }
        try:
            async with asyncio.timeout(30):
                resp = await self._session.get(OPEN_METEO_URL, params=params)
                resp.raise_for_status()
                payload = await resp.json()
            data = build_forecast(
                payload["hourly"],
                cfg[CONF_LATITUDE],
                cfg[CONF_LONGITUDE],
                cfg[CONF_ALTITUDE],
                cfg[CONF_STRINGS],
            )
        except (aiohttp.ClientError, TimeoutError) as err:
            self.update_interval = RETRY_INTERVAL
            raise UpdateFailed(f"Chyba při stahování z Open-Meteo: {err}") from err
        except (KeyError, TypeError, ValueError) as err:
            self.update_interval = RETRY_INTERVAL
            raise UpdateFailed(f"Neočekávaná odpověď Open-Meteo: {err}") from err

        self.update_interval = UPDATE_INTERVAL
        return data
