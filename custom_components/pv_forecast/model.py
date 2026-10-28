"""Fyzikální model FVE bez externích závislostí.

Přepis výpočtu z pv_forecast.py (pvlib) do čistého Pythonu, aby integrace
nepotřebovala pvlib/scipy/h5py, které se v Home Assistant OS špatně instalují.
Použité modely odpovídají výchozím volbám pvlib:

- poloha Slunce: algoritmus NOAA + refrakce podle NREL SPA (T = 12 °C,
  tlak z nadmořské výšky), tj. zdánlivý zenit jako v pvlib
- extraterestrické záření: Spencer, solární konstanta 1366.1 W/m²
- relativní airmass: Kasten & Young 1989
- difuzní složka na panel: Perez (allsitescomposite1990), albedo 0.25
- teplota článku: NOCT, výkon: lineární teplotní koeficient + performance ratio
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any

ALBEDO = 0.25
SOLAR_CONSTANT = 1366.1   # výchozí hodnota pvlib
SPA_TEMPERATURE_C = 12.0

# Perez, allsitescomposite1990: řádky = 8 tříd jasnosti, sloupce = (x0, x1·Δ, x2·Z)
_PEREZ_F1 = (
    (-0.008, 0.588, -0.062), (0.130, 0.683, -0.151), (0.330, 0.487, -0.221),
    (0.568, 0.187, -0.295), (0.873, -0.392, -0.362), (1.132, -1.237, -0.412),
    (1.060, -1.600, -0.359), (0.678, -0.327, -0.250),
)
_PEREZ_F2 = (
    (-0.060, 0.072, -0.022), (-0.019, 0.066, -0.029), (0.055, -0.064, -0.026),
    (0.109, -0.152, -0.014), (0.226, -0.462, 0.001), (0.288, -0.823, 0.056),
    (0.264, -1.127, 0.131), (0.156, -1.377, 0.251),
)
_PEREZ_EPS_BINS = (1.065, 1.23, 1.5, 1.95, 2.8, 4.5, 6.2)


def _sind(x: float) -> float:
    return math.sin(math.radians(x))


def _cosd(x: float) -> float:
    return math.cos(math.radians(x))


# ---------------------------------------------------------------------------
# Poloha Slunce
# ---------------------------------------------------------------------------

def pressure_from_altitude(altitude_m: float) -> float:
    """Tlak vzduchu (Pa) z nadmořské výšky — stejný vzorec jako pvlib.alt2pres."""
    return 100 * ((44331.514 - altitude_m) / 11880.516) ** (1 / 0.1902632)


def solar_position(
    when: datetime, latitude: float, longitude: float, altitude_m: float
) -> tuple[float, float]:
    """Vrátí (zdánlivý zenit °, azimut ° od severu po směru hod. ručiček)."""
    jd = when.timestamp() / 86400.0 + 2440587.5
    t = (jd - 2451545.0) / 36525.0

    l0 = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    c = (_sind(m) * (1.914602 - t * (0.004817 + 0.000014 * t))
         + _sind(2 * m) * (0.019993 - 0.000101 * t)
         + _sind(3 * m) * 0.000289)
    omega = 125.04 - 1934.136 * t
    app_long = l0 + c - 0.00569 - 0.00478 * _sind(omega)
    eps0 = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
    eps = eps0 + 0.00256 * _cosd(omega)
    decl = math.degrees(math.asin(_sind(eps) * _sind(app_long)))

    y = math.tan(math.radians(eps / 2)) ** 2
    eot_min = 4 * math.degrees(
        y * _sind(2 * l0) - 2 * e * _sind(m) + 4 * e * y * _sind(m) * _cosd(2 * l0)
        - 0.5 * y * y * _sind(4 * l0) - 1.25 * e * e * _sind(2 * m)
    )

    utc = when.astimezone(timezone.utc)
    minutes = utc.hour * 60 + utc.minute + utc.second / 60 + utc.microsecond / 6e7
    tst = (minutes + eot_min + 4 * longitude) % 1440
    hour_angle = tst / 4 - 180

    cos_z = (_sind(latitude) * _sind(decl)
             + _cosd(latitude) * _cosd(decl) * _cosd(hour_angle))
    zenith = math.degrees(math.acos(max(-1.0, min(1.0, cos_z))))
    azimuth = (math.degrees(math.atan2(
        _sind(hour_angle),
        _cosd(hour_angle) * _sind(latitude) - math.tan(math.radians(decl)) * _cosd(latitude),
    )) + 180) % 360

    # Atmosférická refrakce (NREL SPA)
    elev = 90 - zenith
    if elev >= -(0.26667 + 0.5667):
        pressure_hpa = pressure_from_altitude(altitude_m) / 100
        elev += ((pressure_hpa / 1010) * (283 / (273 + SPA_TEMPERATURE_C))
                 * 1.02 / (60 * math.tan(math.radians(elev + 10.3 / (elev + 5.11)))))
    return 90 - elev, azimuth


def extra_radiation(when: datetime) -> float:
    """Extraterestrické normálové záření (W/m²), metoda Spencer."""
    b = 2 * math.pi / 365 * (when.timetuple().tm_yday - 1)
    return SOLAR_CONSTANT * (1.00011 + 0.034221 * math.cos(b) + 0.00128 * math.sin(b)
                             + 0.000719 * math.cos(2 * b) + 0.000077 * math.sin(2 * b))


def relative_airmass(zenith: float) -> float | None:
    """Relativní airmass (Kasten & Young 1989); None pro Slunce pod obzorem."""
    if zenith > 90:
        return None
    return 1.0 / (_cosd(zenith) + 0.50572 * (6.07995 + (90 - zenith)) ** -1.6364)


# ---------------------------------------------------------------------------
# Záření na panel a výkon
# ---------------------------------------------------------------------------

def poa_irradiance(
    tilt: float, surface_azimuth: float, zenith: float, sun_azimuth: float,
    dni: float, ghi: float, dhi: float, dni_extra: float, airmass: float | None,
) -> float:
    """Celkové záření v rovině panelu (W/m²), Perez + odraz od země."""
    cos_aoi = (_cosd(tilt) * _cosd(zenith)
               + _sind(tilt) * _sind(zenith) * _cosd(sun_azimuth - surface_azimuth))
    cos_aoi = max(-1.0, min(1.0, cos_aoi))

    sun_up = airmass is not None and zenith < 90
    beam = max(dni * cos_aoi, 0.0) if sun_up else 0.0
    ground = ghi * ALBEDO * (1 - _cosd(tilt)) * 0.5

    if dhi <= 0:
        sky = 0.0
    elif not sun_up:
        sky = dhi * (1 + _cosd(tilt)) * 0.5   # izotropní obloha
    else:
        z = math.radians(zenith)
        kappa = 1.041
        delta = dhi * airmass / dni_extra
        eps = ((dhi + dni) / dhi + kappa * z ** 3) / (1 + kappa * z ** 3)
        idx = sum(1 for b in _PEREZ_EPS_BINS if eps >= b)
        f1c, f2c = _PEREZ_F1[idx], _PEREZ_F2[idx]
        f1 = max(f1c[0] + f1c[1] * delta + f1c[2] * z, 0.0)
        f2 = f2c[0] + f2c[1] * delta + f2c[2] * z
        a = max(cos_aoi, 0.0)
        b = max(_cosd(zenith), _cosd(85))
        sky = max(dhi * (0.5 * (1 - f1) * (1 + _cosd(tilt)) + f1 * a / b
                         + f2 * _sind(tilt)), 0.0)

    return max(beam + sky + ground, 0.0)


def panel_power(
    poa: float, t_air: float, peak_power_wp: float,
    performance_ratio: float = 0.80, temp_coefficient: float = -0.004,
    t_ref: float = 25.0, noct: float = 48.0,
) -> float:
    """AC výkon jednoho panelu (W) — stejný vzorec jako compute_pv_power()."""
    t_cell = t_air + (poa / 800.0) * (noct - 20.0)
    temp_factor = 1.0 + temp_coefficient * (t_cell - t_ref)
    return max(poa / 1000.0 * peak_power_wp * performance_ratio * temp_factor, 0.0)


# ---------------------------------------------------------------------------
# Předpověď
# ---------------------------------------------------------------------------

@dataclass
class ForecastData:
    """Hodinová předpověď. Klíče = začátek hodiny v UTC, hodnoty = průměrný
    výkon v hodině (W), tedy zároveň energie v hodině (Wh)."""

    generated_at: datetime
    total: dict[datetime, float] = field(default_factory=dict)
    strings: dict[str, dict[datetime, float]] = field(default_factory=dict)

    @staticmethod
    def _hour_start(when: datetime) -> datetime:
        return when.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)

    def power_at(self, when: datetime) -> float | None:
        """Výkon (W) v hodině, do které `when` patří."""
        return self.total.get(self._hour_start(when))

    def _day_hours(self, day: date, tz: tzinfo) -> list[datetime]:
        return [t for t in self.total if t.astimezone(tz).date() == day]

    def day_energy_kwh(self, day: date, tz: tzinfo) -> float | None:
        hours = self._day_hours(day, tz)
        if not hours:
            return None
        return round(sum(self.total[t] for t in hours) / 1000, 3)

    def remaining_today_kwh(self, now: datetime) -> float | None:
        """Zbývající energie do půlnoci; aktuální hodina poměrnou částí."""
        start = self._hour_start(now)
        hours = [t for t in self._day_hours(now.date(), now.tzinfo) if t >= start]
        if not hours:
            return None
        frac = 1 - (now - start).total_seconds() / 3600
        wh = sum(self.total[t] * (frac if t == start else 1.0) for t in hours)
        return round(wh / 1000, 3)

    def peak_time(self, day: date, tz: tzinfo) -> datetime | None:
        hours = self._day_hours(day, tz)
        if not hours:
            return None
        peak = max(hours, key=lambda t: self.total[t])
        return peak if self.total[peak] > 0 else None

    def day_series(self, day: date, tz: tzinfo) -> dict[str, float]:
        """{"ISO začátek hodiny (lokálně)": W} pro atributy watts / wh_period."""
        return {t.astimezone(tz).isoformat(): self.total[t]
                for t in sorted(self._day_hours(day, tz))}


def build_forecast(
    hourly: dict[str, list[Any]],
    latitude: float, longitude: float, altitude_m: float,
    strings: list[dict[str, Any]],
    now: datetime | None = None,
) -> ForecastData:
    """Spočítá předpověď z bloku `hourly` odpovědi Open-Meteo (timezone=UTC)."""
    data = ForecastData(generated_at=now or datetime.now(timezone.utc))
    data.strings = {s["name"]: {} for s in strings}

    rows = zip(hourly["time"], hourly["shortwave_radiation"],
               hourly["direct_normal_irradiance"], hourly["diffuse_radiation"],
               hourly["temperature_2m"])
    for time_str, ghi, dni, dhi, t_air in rows:
        if None in (ghi, dni, dhi, t_air):
            continue
        end = datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc)
        start = end - timedelta(hours=1)
        mid = end - timedelta(minutes=30)

        zenith, sun_az = solar_position(mid, latitude, longitude, altitude_m)
        airmass = relative_airmass(zenith)
        dni_extra = extra_radiation(mid)

        total = 0.0
        for s in strings:
            per_panel = []
            for o in s["orientations"]:
                poa = poa_irradiance(
                    o["tilt_deg"], o["azimuth_from_north_deg"] % 360, zenith, sun_az,
                    dni, ghi, dhi, dni_extra, airmass,
                )
                per_panel.append(panel_power(
                    poa, t_air, o["peak_power_wp"],
                    o.get("performance_ratio", 0.80), o.get("temp_coefficient", -0.004),
                    o.get("t_ref", 25.0), o.get("noct", 48.0),
                ))
            # string je omezen nejslabším panelem
            p = round(min(per_panel) * s["panels"], 1)
            data.strings[s["name"]][start] = p
            total += p
        data.total[start] = round(total, 1)
    return data
