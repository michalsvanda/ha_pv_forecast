"""Předpověď pro energetický panel Home Assistantu."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_solar_forecast(
    hass: HomeAssistant, config_entry_id: str
) -> dict[str, dict[str, float]] | None:
    """Vrátí {"wh_hours": {"ISO začátek hodiny": Wh}} pro danou instanci."""
    entry = hass.config_entries.async_get_entry(config_entry_id)
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        return None
    data = entry.runtime_data.data
    if data is None:
        return None
    return {"wh_hours": {t.isoformat(): wh for t, wh in sorted(data.total.items())}}
