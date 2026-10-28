"""Testy integrace PV Forecast s napodobenou odpovědí Open-Meteo."""

import math
import re
from datetime import datetime, timedelta, timezone

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.pv_forecast import energy
from custom_components.pv_forecast.const import DEFAULT_STRINGS, DOMAIN

OPEN_METEO = re.compile(r"https://api\.open-meteo\.com/.*")
DATA = {
    "latitude": 50.0078,
    "longitude": 14.7144,
    "altitude": 384.0,
    "days_ahead": 2,
    "strings": DEFAULT_STRINGS,
}


def fake_payload() -> dict:
    """Pět dní syntetických hodinových dat (průměry za předchozí hodinu, UTC)."""
    start = datetime(2026, 10, 26, tzinfo=timezone.utc)
    hourly = {k: [] for k in ("time", "shortwave_radiation", "direct_normal_irradiance",
                              "diffuse_radiation", "temperature_2m")}
    for i in range(24 * 5):
        ts = start + timedelta(hours=i)
        h = ts.hour - 0.5
        s = max(0.0, math.sin(math.pi * (h - 6) / 10)) if 6 <= h <= 16 else 0.0
        hourly["time"].append(ts.strftime("%Y-%m-%dT%H:%M"))
        hourly["shortwave_radiation"].append(round(450 * s, 1))
        hourly["direct_normal_irradiance"].append(round(600 * s, 1))
        hourly["diffuse_radiation"].append(round(120 * s, 1))
        hourly["temperature_2m"].append(10.0)
    return {"hourly": hourly}


async def _setup(hass: HomeAssistant, aioclient_mock) -> MockConfigEntry:
    await hass.config.async_set_time_zone("Europe/Prague")
    aioclient_mock.get(OPEN_METEO, json=fake_payload())
    entry = MockConfigEntry(domain=DOMAIN, title="Solar production forecast", data=DATA)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _float(hass: HomeAssistant, entity_id: str) -> float:
    return float(hass.states.get(entity_id).state)


@pytest.mark.freeze_time("2026-10-27 12:40:00+00:00")
async def test_sensors(hass: HomeAssistant, aioclient_mock) -> None:
    """Všechny senzory mají hodnotu a dávají smysl."""
    await _setup(hass, aioclient_mock)

    today = _float(hass, "sensor.energy_production_today")
    remaining = _float(hass, "sensor.energy_production_today_remaining")
    assert today > 0
    assert 0 < remaining < today
    assert _float(hass, "sensor.energy_production_tomorrow") > 0
    assert _float(hass, "sensor.energy_production_d2") > 0

    now_w = _float(hass, "sensor.power_production_now")
    assert now_w > 0
    assert _float(hass, "sensor.energy_current_hour") == pytest.approx(now_w / 1000, abs=1e-3)
    assert _float(hass, "sensor.power_production_next_12hours") == 0   # 00:40 v noci

    peak = hass.states.get("sensor.power_highest_peak_time_today").state
    assert peak.startswith("2026-10-27T")

    attrs = hass.states.get("sensor.energy_production_today").attributes
    assert len(attrs["watts"]) == 24
    assert sum(attrs["wh_period"].values()) / 1000 == pytest.approx(today, abs=0.01)
    assert attrs["unit_of_measurement"] == "kWh"


@pytest.mark.freeze_time("2026-10-27 12:40:00+00:00")
async def test_energy_platform(hass: HomeAssistant, aioclient_mock) -> None:
    """Energetický panel dostane hodinové Wh podle začátku hodiny."""
    entry = await _setup(hass, aioclient_mock)
    forecast = await energy.async_get_solar_forecast(hass, entry.entry_id)
    wh = forecast["wh_hours"]
    assert "2026-10-27T12:00:00+00:00" in wh
    assert wh["2026-10-27T12:00:00+00:00"] == _float(hass, "sensor.power_production_now")
    assert await energy.async_get_solar_forecast(hass, "neexistuje") is None


@pytest.mark.freeze_time("2026-10-27 12:40:00+00:00")
async def test_remaining_updates_over_time(
    hass: HomeAssistant, aioclient_mock, freezer: FrozenDateTimeFactory
) -> None:
    """„Zbývá dnes“ klesá s časem i bez nového stažení dat."""
    await _setup(hass, aioclient_mock)
    before = _float(hass, "sensor.energy_production_today_remaining")
    freezer.move_to("2026-10-27 12:55:00+00:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert _float(hass, "sensor.energy_production_today_remaining") < before
    assert aioclient_mock.call_count == 1


async def test_config_flow(hass: HomeAssistant, aioclient_mock) -> None:
    """Neplatné stringy vrátí chybu, platné vytvoří instanci."""
    aioclient_mock.get(OPEN_METEO, json=fake_payload())
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    user_input = {**DATA, "name": "Moje FVE",
                  "strings": [{"name": "a", "panels": 0, "orientations": []}]}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)
    assert result["errors"] == {"strings": "invalid_strings"}

    user_input["strings"] = DEFAULT_STRINGS
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Moje FVE"
    assert "name" not in result["data"]
    await hass.async_block_till_done()


@pytest.mark.freeze_time("2026-10-27 12:40:00+00:00")
async def test_options_flow(hass: HomeAssistant, aioclient_mock) -> None:
    """Změna stringů v možnostech integraci znovu načte s novými hodnotami."""
    entry = await _setup(hass, aioclient_mock)
    before = _float(hass, "sensor.energy_production_today")

    result = await hass.config_entries.options.async_init(entry.entry_id)
    single = [{"name": "s", "panels": 20, "orientations": [
        {"peak_power_wp": 450, "tilt_deg": 35, "azimuth_from_north_deg": 182}]}]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**DATA, "strings": single}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert _float(hass, "sensor.energy_production_today") != before
