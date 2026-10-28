"""Konfigurace přes UI."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ALTITUDE,
    CONF_DAYS_AHEAD,
    CONF_STRINGS,
    DEFAULT_DAYS_AHEAD,
    DEFAULT_NAME,
    DEFAULT_STRINGS,
    DOMAIN,
)
from .coordinator import PVForecastConfigEntry

_ORIENTATION_REQUIRED = ("peak_power_wp", "tilt_deg", "azimuth_from_north_deg")
_ORIENTATION_OPTIONAL = ("performance_ratio", "temp_coefficient", "t_ref", "noct")


def validate_strings(value: Any) -> list[dict[str, Any]]:
    """Ověří a normalizuje definici stringů; při chybě vyhodí ValueError."""
    if not isinstance(value, list) or not value:
        raise ValueError("strings must be a non-empty list")
    out, names = [], set()
    for s in value:
        if not isinstance(s, dict):
            raise ValueError("string must be a mapping")
        name = str(s.get("name", "")).strip()
        if not name or name in names:
            raise ValueError("missing or duplicate string name")
        names.add(name)
        panels = int(s["panels"])
        orientations = s.get("orientations")
        if panels <= 0 or not isinstance(orientations, list) or not orientations:
            raise ValueError("invalid panels/orientations")
        norm = []
        for o in orientations:
            n = {k: float(o[k]) for k in _ORIENTATION_REQUIRED}
            n.update({k: float(o[k]) for k in _ORIENTATION_OPTIONAL if k in o})
            if n["peak_power_wp"] <= 0 or not 0 <= n["tilt_deg"] <= 90:
                raise ValueError("invalid orientation values")
            norm.append(n)
        out.append({"name": name, "panels": panels, "orientations": norm})
    return out


def _schema(defaults: dict[str, Any], with_name: bool) -> vol.Schema:
    fields: dict[Any, Any] = {}
    if with_name:
        fields[vol.Required(CONF_NAME, default=defaults[CONF_NAME])] = str
    fields.update({
        vol.Required(CONF_LATITUDE, default=defaults[CONF_LATITUDE]): vol.Coerce(float),
        vol.Required(CONF_LONGITUDE, default=defaults[CONF_LONGITUDE]): vol.Coerce(float),
        vol.Required(CONF_ALTITUDE, default=defaults[CONF_ALTITUDE]): vol.Coerce(float),
        vol.Required(CONF_DAYS_AHEAD, default=defaults[CONF_DAYS_AHEAD]):
            selector.NumberSelector(selector.NumberSelectorConfig(
                min=1, max=14, step=1, mode=selector.NumberSelectorMode.BOX)),
        vol.Required(CONF_STRINGS, default=defaults[CONF_STRINGS]): selector.ObjectSelector(),
    })
    return vol.Schema(fields)


def _process(user_input: dict[str, Any], errors: dict[str, str]) -> dict[str, Any] | None:
    data = dict(user_input)
    data[CONF_DAYS_AHEAD] = int(data[CONF_DAYS_AHEAD])
    if not -90 <= data[CONF_LATITUDE] <= 90 or not -180 <= data[CONF_LONGITUDE] <= 180:
        errors["base"] = "invalid_location"
    try:
        data[CONF_STRINGS] = validate_strings(data[CONF_STRINGS])
    except (KeyError, TypeError, ValueError):
        errors[CONF_STRINGS] = "invalid_strings"
    return None if errors else data


class PVForecastConfigFlow(ConfigFlow, domain=DOMAIN):
    """Vytvoření instance (jedna instance = jedna elektrárna)."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: PVForecastConfigEntry) -> OptionsFlow:
        return PVForecastOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None and (data := _process(user_input, errors)):
            name = data.pop(CONF_NAME)
            return self.async_create_entry(title=name, data=data)

        defaults = user_input or {
            CONF_NAME: DEFAULT_NAME,
            CONF_LATITUDE: self.hass.config.latitude,
            CONF_LONGITUDE: self.hass.config.longitude,
            CONF_ALTITUDE: float(self.hass.config.elevation),
            CONF_DAYS_AHEAD: DEFAULT_DAYS_AHEAD,
            CONF_STRINGS: DEFAULT_STRINGS,
        }
        return self.async_show_form(
            step_id="user", data_schema=_schema(defaults, with_name=True), errors=errors
        )


class PVForecastOptionsFlow(OptionsFlow):
    """Úprava polohy a stringů po instalaci."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None and (data := _process(user_input, errors)):
            return self.async_create_entry(data=data)

        defaults = user_input or {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=_schema(defaults, with_name=False), errors=errors
        )
