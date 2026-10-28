"""Senzory pojmenované a typované stejně jako v integraci Forecast.Solar."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import PVForecastConfigEntry, PVForecastCoordinator
from .model import ForecastData


@dataclass(frozen=True, kw_only=True)
class PVForecastSensorDescription(SensorEntityDescription):
    """value_fn(data, now) → stav; attrs_fn(data, now) → atributy."""

    value_fn: Callable[[ForecastData, datetime], Any]
    attrs_fn: Callable[[ForecastData, datetime], dict[str, Any]] | None = None


def _day(offset: int) -> Callable[[datetime], Any]:
    return lambda now: (now + timedelta(days=offset)).date()


def _energy_day(key: str, offset: int) -> PVForecastSensorDescription:
    def series(d: ForecastData, now: datetime) -> dict[str, Any]:
        s = d.day_series(_day(offset)(now), now.tzinfo)
        # formát Open-Meteo Solar Forecast: hodinový průměr W = Wh za hodinu
        return {"watts": s, "wh_period": s}

    return PVForecastSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda d, now: d.day_energy_kwh(_day(offset)(now), now.tzinfo),
        attrs_fn=series,
    )


def _power_in(key: str, hours: int, **kwargs: Any) -> PVForecastSensorDescription:
    return PVForecastSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=lambda d, now: d.power_at(now + timedelta(hours=hours)),
        **kwargs,
    )


def _energy_hour(key: str, hours: int) -> PVForecastSensorDescription:
    def value(d: ForecastData, now: datetime) -> float | None:
        p = d.power_at(now + timedelta(hours=hours))
        return None if p is None else round(p / 1000, 3)

    return PVForecastSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        value_fn=value,
    )


def _peak_time(key: str, offset: int) -> PVForecastSensorDescription:
    return PVForecastSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d, now: d.peak_time(_day(offset)(now), now.tzinfo),
    )


SENSORS: tuple[PVForecastSensorDescription, ...] = (
    _energy_day("energy_production_today", 0),
    PVForecastSensorDescription(
        key="energy_production_today_remaining",
        translation_key="energy_production_today_remaining",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda d, now: d.remaining_today_kwh(now),
    ),
    _energy_day("energy_production_tomorrow", 1),
    _energy_day("energy_production_d2", 2),
    _peak_time("power_highest_peak_time_today", 0),
    _peak_time("power_highest_peak_time_tomorrow", 1),
    _power_in("power_production_now", 0, state_class=SensorStateClass.MEASUREMENT),
    _power_in("power_production_next_hour", 1),
    _power_in("power_production_next_12hours", 12),
    _power_in("power_production_next_24hours", 24),
    _energy_hour("energy_current_hour", 0),
    _energy_hour("energy_next_hour", 1),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PVForecastConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(PVForecastSensor(coordinator, d) for d in SENSORS)


class PVForecastSensor(CoordinatorEntity[PVForecastCoordinator], SensorEntity):
    """Jeden senzor předpovědi."""

    entity_description: PVForecastSensorDescription
    _attr_has_entity_name = True
    # hodinové řady neukládat do historie (zbytečně by zvětšovaly databázi)
    _unrecorded_attributes = frozenset({"watts", "wh_period"})

    def __init__(
        self, coordinator: PVForecastCoordinator, description: PVForecastSensorDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        # stejná entity_id jako Forecast.Solar (sensor.energy_production_today …);
        # při kolizi HA přidá příponu _2
        self.entity_id = f"{SENSOR_DOMAIN}.{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Open-Meteo",
            model="PV forecast model",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data, dt_util.now())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data, dt_util.now())
