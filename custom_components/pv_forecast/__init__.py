"""PV Forecast — hodinová předpověď výroby FVE z Open-Meteo."""

from __future__ import annotations

from datetime import datetime

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change

from .const import STATE_REFRESH_MINUTES
from .coordinator import PVForecastConfigEntry, PVForecastCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: PVForecastConfigEntry) -> bool:
    coordinator = PVForecastCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Senzory „teď / zbývá dnes“ závisí na čase → přepsat stav každých 5 min
    @callback
    def _refresh_states(_: datetime) -> None:
        coordinator.async_update_listeners()

    entry.async_on_unload(
        async_track_time_change(
            hass, _refresh_states,
            minute=list(range(0, 60, STATE_REFRESH_MINUTES)), second=0,
        )
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: PVForecastConfigEntry) -> None:
    """Po změně možností integraci znovu načíst."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: PVForecastConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
