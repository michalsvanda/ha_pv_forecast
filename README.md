# PV Forecast (Open-Meteo) pro Home Assistant

Vlastní integrace pro [Home Assistant](https://www.home-assistant.io), která počítá hodinovou předpověď výroby fotovoltaické elektrárny z předpovědi slunečního záření [Open-Meteo](https://open-meteo.com). Předpověď se zobrazuje v **energetickém panelu** a zároveň je dostupná jako sada senzorů se stejnými názvy jako v integraci [Forecast.Solar](https://www.home-assistant.io/integrations/forecast_solar/), takže na ni lze přepnout existující dashboardy a automatizace.

Na rozdíl od Forecast.Solar počítá výkon přímo z panelů: každý string může mít víc orientací (např. část panelů se sklonem 35° a část 15°) a výpočet zohledňuje teplotu článků.

Pozn.: Původní [skript](https://github.com/michalsvanda/pv_forecast) využívající pvlib přepsán pomocí LLM jako integrace do Home Assistantu. 

## Funkce

- Hodinová předpověď na dnešek a následující dny (výchozí 2, nastavitelné až 14).
- Předpověď v grafu solární výroby v energetickém panelu.
- Senzory kompatibilní s Forecast.Solar (`sensor.energy_production_today`, `sensor.power_production_now`, …).
- Hodinové řady v atributech `watts` a `wh_period` (formát integrace Open-Meteo Solar Forecast) pro grafy a optimalizátory baterií.
- Libovolný počet stringů; string s více orientacemi je omezen nejslabším panelem.
- Celé nastavení přes UI, změny bez restartu.
- Žádné závislosti navíc: fyzikální model je napsaný v čistém Pythonu, není potřeba pvlib ani scipy.
- Bez API klíče, jeden dotaz na Open-Meteo za hodinu.

## Instalace

Vyžaduje Home Assistant 2025.2 nebo novější.

### Ručně

1. Zkopírujte složku `custom_components/pv_forecast` do `/config/custom_components/` ve vaší instalaci Home Assistantu.
2. Restartujte Home Assistant.
3. Otevřete **Nastavení → Zařízení a služby → Přidat integraci** a vyhledejte **PV Forecast**.

### HACS (vlastní repozitář)

V HACS zvolte **⋮ → Vlastní repozitáře**, vložte URL tohoto repozitáře a jako typ vyberte **Integrace**. Pak integraci nainstalujte a restartujte Home Assistant.

## Nastavení

Při přidání integrace se vyplňuje:

| Pole | Popis |
|---|---|
| Název | Název zařízení v HA, např. „Solar production forecast“. |
| Zeměpisná šířka / délka | Poloha elektrárny ve stupních. Předvyplní se z nastavení HA. |
| Nadmořská výška | V metrech. Ovlivňuje výpočet atmosférické refrakce. |
| Počet dní dopředu | Kolik dní po dnešku se má předpovídat (1–14). |
| Stringy | Definice panelů ve formátu YAML, viz níže. |

Všechny hodnoty kromě názvu lze později změnit přes **Nastavení → Zařízení a služby → PV Forecast → Konfigurovat**.

### Definice stringů

Každý string má název, počet panelů a jednu nebo více orientací. Orientace popisuje parametry **jednoho panelu**.

```yaml
- name: string1
  panels: 10
  orientations:
    - peak_power_wp: 450
      tilt_deg: 35
      azimuth_from_north_deg: 182
- name: string2
  panels: 10
  orientations:
    - peak_power_wp: 500
      tilt_deg: 35
      azimuth_from_north_deg: 182
    - peak_power_wp: 500
      tilt_deg: 15
      azimuth_from_north_deg: 182
```

Výkon stringu se počítá jako výkon jednoho panelu krát počet panelů. Má-li string víc orientací, použije se v každé hodině nejnižší výkon z nich, protože proud v sériovém zapojení omezuje nejslabší panel. Celková výroba je součet všech stringů.

Parametry orientace:

| Klíč | Povinný | Výchozí | Popis |
|---|---|---|---|
| `peak_power_wp` | ano | | Špičkový výkon panelu (Wp). |
| `tilt_deg` | ano | | Sklon od vodorovné roviny: 0 = naplocho, 90 = svisle. |
| `azimuth_from_north_deg` | ano | | Azimut po směru hodinových ručiček od severu: 90 = východ, 180 = jih, 270 = západ. |
| `performance_ratio` | ne | 0.80 | Ztráty systému (střídač, kabeláž, znečištění…). |
| `temp_coefficient` | ne | -0.004 | Teplotní koeficient výkonu na °C (-0,4 %/°C). |
| `t_ref` | ne | 25 | Referenční teplota článku (°C). |
| `noct` | ne | 48 | Nominální provozní teplota článku (°C). |

Pozor na azimut: Forecast.Solar používá jinou konvenci (0 = jih). Tato integrace měří od severu, stejně jako kompas.

## Energetický panel

V **Nastavení → Energie** u solární výroby otevřete úpravu zdroje a v části **Předpověď výroby** zaškrtněte tuto integraci. Předpověď se pak kreslí vedle skutečné hodinové výroby.

## Entity

Entity patří zařízení se zvoleným názvem. Entity ID odpovídají integraci Forecast.Solar.

| Entita | Jednotka | Význam |
|---|---|---|
| `sensor.energy_production_today` | kWh | Výroba za celý dnešní den |
| `sensor.energy_production_today_remaining` | kWh | Zbývající výroba do půlnoci (aktuální hodina poměrnou částí) |
| `sensor.energy_production_tomorrow` | kWh | Výroba zítra |
| `sensor.energy_production_d2` | kWh | Výroba pozítří |
| `sensor.energy_current_hour` | kWh | Výroba v aktuální hodině |
| `sensor.energy_next_hour` | kWh | Výroba v příští hodině |
| `sensor.power_production_now` | W | Průměrný výkon v aktuální hodině |
| `sensor.power_production_next_hour` | W | Průměrný výkon v příští hodině |
| `sensor.power_production_next_12hours` | W | Průměrný výkon v hodině za 12 h |
| `sensor.power_production_next_24hours` | W | Průměrný výkon v hodině za 24 h |
| `sensor.power_highest_peak_time_today` | čas | Začátek hodiny s nejvyšším výkonem dnes |
| `sensor.power_highest_peak_time_tomorrow` | čas | Totéž pro zítřek |

Denní senzory (`energy_production_today`, `_tomorrow`, `_d2`) mají atributy `watts` a `wh_period`: slovník `{"začátek hodiny (ISO)": hodnota}`. Protože je krok hodinový, jsou obě řady stejné (průměrný výkon ve W odpovídá energii v hodině ve Wh). Tyto atributy se neukládají do historie.

Pokud už máte nainstalovaný Forecast.Solar, dostanou entity této integrace příponu `_2`. Entity ID lze přejmenovat v UI.

### Příklad automatizace

Zapnout myčku ve 12:00, pokud se v příštích třech hodinách očekávají aspoň 2 kWh:

```yaml
triggers:
  - trigger: time
    at: "12:00:00"
conditions:
  - condition: template
    value_template: >
      {% set series = state_attr('sensor.energy_production_today', 'wh_period') %}
      {% set start = now().replace(minute=0, second=0, microsecond=0) %}
      {% set ns = namespace(wh=0) %}
      {% for t, wh in series.items() %}
        {% if start <= as_datetime(t) < start + timedelta(hours=3) %}
          {% set ns.wh = ns.wh + wh %}
        {% endif %}
      {% endfor %}
      {{ ns.wh >= 2000 }}
actions:
  - action: switch.turn_on
    target:
      entity_id: switch.mycka
```

## Jak výpočet funguje

1. **Data.** Integrace jednou za hodinu stáhne z Open-Meteo hodinové globální, přímé a difuzní záření a teplotu vzduchu. Po chybě to zkusí znovu za 10 minut.
2. **Časové zarovnání.** Open-Meteo udává záření jako průměr za předchozí hodinu. Poloha Slunce se proto počítá ve středu této hodiny a výsledek se přiřadí hodině podle jejího začátku, stejně jako hodinové statistiky v HA.
3. **Poloha Slunce.** Algoritmus NOAA s atmosférickou refrakcí podle NREL SPA.
4. **Záření na panel.** Perezův model difuzního záření (koeficienty *allsitescomposite1990*), přímá složka podle úhlu dopadu a odraz od země s albedem 0,25. Odpovídá výchozímu výpočtu v knihovně pvlib; shoda byla ověřena na celoročních datech.
5. **Teplota článku.** Model NOCT: `T_článku = T_vzduchu + POA / 800 · (NOCT − 20)`.
6. **Výkon.** `P = POA / 1000 · Wp · performance_ratio · (1 + temp_coefficient · (T_článku − t_ref))`, záporné hodnoty se nahradí nulou.

Senzory závislé na čase (teď, zbývá dnes, příští hodina) se přepočítávají každých 5 minut z uložených dat, bez dalšího dotazu na Open-Meteo.

## Omezení

- Model nezná stínění, omezení výkonu střídače ani skutečný stav panelů. Hodnotu `performance_ratio` je vhodné doladit podle porovnání předpovědi se skutečnou výrobou v energetickém panelu.
- Krok předpovědi je jedna hodina, takže krátkodobé výkyvy oblačnosti v ní nejsou.
- Přesnost je daná především přesností předpovědi oblačnosti z Open-Meteo.

## Data Open-Meteo

Předpověď používá bezplatné API Open-Meteo, které je určeno pro nekomerční použití a nevyžaduje klíč. Integrace pošle zhruba 24 dotazů denně, což je hluboko pod limity bezplatného API. Data Open-Meteo jsou poskytována pod licencí [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Podmínky použití najdete na [open-meteo.com](https://open-meteo.com).

## Vývoj a testy

Integrace sama žádné balíčky nepotřebuje. Soubor `requirements.txt` obsahuje závislosti pro spouštění testů (vyžaduje Python 3.13):

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

Testy spouštějí integraci v testovacím prostředí Home Assistantu s napodobenou odpovědí Open-Meteo. Ověřují senzory, data pro energetický panel, průběžnou aktualizaci a nastavení přes UI.

Struktura repozitáře:

```
custom_components/pv_forecast/
  __init__.py        nastavení integrace, plánování aktualizací
  config_flow.py     nastavení a možnosti v UI
  const.py           konstanty a výchozí konfigurace
  coordinator.py     stahování z Open-Meteo
  energy.py          předpověď pro energetický panel
  model.py           fyzikální model (bez závislostí)
  sensor.py          senzory
  manifest.json
  translations/      čeština a angličtina
tests/               testy (pytest)
```

## Licence

[MIT](LICENSE)
