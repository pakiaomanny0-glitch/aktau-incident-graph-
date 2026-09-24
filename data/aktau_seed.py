#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AKTAU INCIDENT GRAPH — генератор синтетических данных и загрузчик на бэкенд.

Порядок работы (строго по правилу бэкенда):
  Шаг 1. POST /ingest  -> districts + readings + incidents (correlations = [])
  Шаг 2. GET  /incidents -> получаем реальные id созданных инцидентов
  Шаг 3. Формируем correlations по id
  Шаг 4. POST /ingest  -> только correlations

Запуск:
  pip install requests
  python aktau_seed.py                      # полный цикл (шаги 1-4)
  python aktau_seed.py --dry-run            # только сгенерировать и проверить данные, ничего не отправлять
  python aktau_seed.py --only-correlations  # шаги 2-4 (если шаг 1 уже выполнялся, чтобы не плодить дубли)

Сценарий каскада (24 сентября 2026):
  11:00 HIGH_HEAT (>38 °C) -> 13:00 WATER_DEMAND_SURGE (>130 %) ->
  15:00 LOW_WATER_PRESSURE -> 17:00 CRITICAL_FACILITY_RISK (областная больница).
Основная цепочка: 14 мкр -> 26 мкр -> Мангистауская областная больница.

ВАЖНО: координаты приблизительные (точность порядка сотен метров), данные синтетические.
"""

import argparse
import json
import math
import random
import sys
import time
from datetime import datetime, timedelta

import requests

# ----------------------------------------------------------------------------
# НАСТРОЙКИ
# ----------------------------------------------------------------------------
BASE_URL = "https://aktau-incident-graph-production.up.railway.app"
INGEST_URL = f"{BASE_URL}/ingest"
INCIDENTS_URL = f"{BASE_URL}/incidents"

REQUEST_TIMEOUT = 60      # сек; Railway может "просыпаться" на первом запросе
MAX_RETRIES = 3
RANDOM_SEED = 2026        # фиксированный seed -> одинаковые данные при каждом запуске

ISO_FMT = "%Y-%m-%dT%H:%M:%S"
SCENARIO_DAY = datetime(2026, 9, 24)            # день каскадной аварии
START_TS = SCENARIO_DAY - timedelta(days=2)     # история: 22.09 00:00 ... 24.09 23:00

# Типы инцидентов (если бэкенд ждёт другой регистр/названия — меняются только здесь)
T_HEAT = "HIGH_HEAT"
T_SURGE = "WATER_DEMAND_SURGE"
T_PRESSURE = "LOW_WATER_PRESSURE"
T_CRITICAL = "CRITICAL_FACILITY_RISK"

# ----------------------------------------------------------------------------
# ГЕОГРАФИЯ: 15 микрорайонов + 3 объекта инфраструктуры (координаты приблизительные)
# ----------------------------------------------------------------------------
HOSPITAL = "Мангистауская областная больница (26 мкр)"
PORT = "Морской порт Актау"
INDUSTRIAL = "Промзона 1"

DISTRICTS = [
    ("1 мкр", 43.6510, 51.1580),
    ("3Б мкр", 43.6470, 51.1530),
    ("4 мкр", 43.6440, 51.1600),
    ("5 мкр", 43.6420, 51.1510),
    ("8 мкр", 43.6380, 51.1460),
    ("9 мкр", 43.6350, 51.1540),
    ("11 мкр", 43.6300, 51.1430),
    ("12 мкр", 43.6270, 51.1390),
    ("14 мкр", 43.6240, 51.1340),
    ("15 мкр", 43.6210, 51.1290),
    ("24 мкр", 43.6180, 51.1240),
    ("26 мкр", 43.6130, 51.1200),
    ("27 мкр", 43.6090, 51.1150),
    ("28 мкр", 43.6050, 51.1100),
    ("32A мкр", 43.5990, 51.1030),
    (HOSPITAL, 43.6120, 51.1215),
    (PORT, 43.6180, 51.2270),
    (INDUSTRIAL, 43.6560, 51.2050),
]

# ----------------------------------------------------------------------------
# ПАРАМЕТРЫ СЦЕНАРИЯ (кто в зоне жары / всплеска спроса)
# ----------------------------------------------------------------------------
HEAT_AFFECTED = {"12 мкр", "14 мкр", "15 мкр", "26 мкр", "27 мкр", HOSPITAL, PORT, INDUSTRIAL}

# Температура (°C) по часам в день аварии для зоны жары
HEAT_PROFILE = {
    0: 24.0, 1: 23.5, 2: 23.0, 3: 22.5, 4: 22.5, 5: 23.5, 6: 26.0, 7: 28.5,
    8: 31.0, 9: 34.0, 10: 37.0, 11: 39.4, 12: 40.2, 13: 40.9, 14: 41.5, 15: 41.2,
    16: 40.4, 17: 39.4, 18: 38.2, 19: 36.5, 20: 34.5, 21: 33.0, 22: 31.5, 23: 30.0,
}
NON_AFFECTED_HEAT_SHIFT = 5.0  # остальные районы на 5 °C прохладнее -> ниже порога 38 °C

# Дополнительный спрос на воду (в п.п. к норме) по часам в день аварии
SURGE_PROFILE = {
    11: 4, 12: 18, 13: 42, 14: 54, 15: 50, 16: 44, 17: 38, 18: 32, 19: 24, 20: 14, 21: 7,
}
SURGE_INTENSITY = {
    "14 мкр": 1.00, "26 мкр": 1.05, "15 мкр": 0.95, "12 мкр": 0.90,
    "27 мкр": 0.90, INDUSTRIAL: 0.90, HOSPITAL: 0.50,
}
SURGE_DELAY_H = {"27 мкр": 1, INDUSTRIAL: 1}  # эти зоны реагируют на час позже

HEAT_THRESHOLD = 38.0
SURGE_THRESHOLD = 130.0


# ----------------------------------------------------------------------------
# ГЕНЕРАЦИЯ ПОКАЗАНИЙ
# ----------------------------------------------------------------------------
def gauss(x, mu, sigma):
    return math.exp(-((x - mu) ** 2) / (2 * sigma ** 2))


def normal_temp(ts):
    """Обычная сентябрьская температура с лёгким потеплением по дням."""
    day_shift = (ts.date() - START_TS.date()).days * 0.8
    daylight = max(0.0, math.sin(math.pi * (ts.hour - 7) / 13))
    return 21.0 + 8.0 * daylight + day_shift


def base_demand(hour):
    """Суточная кривая водопотребления в % от нормы (утренний и вечерний пики)."""
    return (
        78
        + 16 * gauss(hour, 7.5, 1.6)
        + 14 * gauss(hour, 19.5, 2.0)
        + 8 * gauss(hour, 13.0, 3.0)
        - 10 * gauss(hour, 3.0, 2.5)
    )


def clipped_noise(rng, sigma, limit):
    return max(-limit, min(limit, rng.gauss(0, sigma)))


def build_readings(rng):
    readings = []
    temp_offset = {name: rng.uniform(-0.3, 0.3) for name, _, _ in DISTRICTS}
    demand_scale = {name: rng.uniform(0.96, 1.04) for name, _, _ in DISTRICTS}

    total_hours = 3 * 24
    for name, _, _ in DISTRICTS:
        for i in range(total_hours):
            ts = START_TS + timedelta(hours=i)
            is_scenario_day = ts.date() == SCENARIO_DAY.date()

            # --- температура ---
            if is_scenario_day:
                profile_t = HEAT_PROFILE[ts.hour]
                if name in HEAT_AFFECTED:
                    temp = profile_t
                else:
                    temp = max(normal_temp(ts), profile_t - NON_AFFECTED_HEAT_SHIFT)
            else:
                temp = normal_temp(ts)
            temp += temp_offset[name] + clipped_noise(rng, 0.15, 0.3)

            # --- спрос на воду (% от нормы) ---
            demand = base_demand(ts.hour) * demand_scale[name]
            demand += 0.9 * max(0.0, temp - 27.0)  # жарче -> больше поливают/моются
            if is_scenario_day and name in SURGE_INTENSITY:
                shifted_hour = ts.hour - SURGE_DELAY_H.get(name, 0)
                demand += SURGE_PROFILE.get(shifted_hour, 0) * SURGE_INTENSITY[name]
            demand += clipped_noise(rng, 1.0, 2.0)

            readings.append({
                "district_name": name,
                "timestamp": ts.strftime(ISO_FMT),
                "temperature": round(temp, 1),
                "water_demand": round(demand, 1),
            })
    return readings


# ----------------------------------------------------------------------------
# ИНЦИДЕНТЫ
# ----------------------------------------------------------------------------
def build_incidents():
    def at(hour, minute=0):
        return (SCENARIO_DAY + timedelta(hours=hour, minutes=minute)).strftime(ISO_FMT)

    heat_desc = "Аномальная жара: температура воздуха превысила 38 °C, прогноз до 41 °C к 15:00."
    surge_desc = "Всплеск водопотребления: спрос превысил 130 % от нормы на фоне аномальной жары."

    # (район, тип, severity, время, описание)
    specs = [
        # --- Шаг 1: HIGH_HEAT ---
        ("12 мкр", T_HEAT, "high", at(11), heat_desc),
        ("14 мкр", T_HEAT, "high", at(11), heat_desc),
        ("15 мкр", T_HEAT, "high", at(11), heat_desc),
        ("26 мкр", T_HEAT, "high", at(11), heat_desc),
        ("27 мкр", T_HEAT, "high", at(11), heat_desc),
        (PORT, T_HEAT, "high", at(12),
         "Аномальная жара на территории порта: свыше 38 °C, работа грузовых терминалов затруднена."),
        (INDUSTRIAL, T_HEAT, "high", at(12),
         "Аномальная жара в промзоне: свыше 38 °C, рост нагрузки на системы промышленного охлаждения."),

        # --- Шаг 2: WATER_DEMAND_SURGE ---
        ("12 мкр", T_SURGE, "medium", at(13), surge_desc + " Пик около 134 %."),
        ("14 мкр", T_SURGE, "high", at(13), surge_desc + " Пик около 150 %."),
        ("15 мкр", T_SURGE, "high", at(13), surge_desc + " Пик около 145 %."),
        ("26 мкр", T_SURGE, "high", at(13), surge_desc + " Пик около 155 %."),
        ("27 мкр", T_SURGE, "medium", at(14), surge_desc + " Пик около 138 %."),
        (INDUSTRIAL, T_SURGE, "medium", at(14),
         "Рост водозабора промзоной на охлаждение оборудования: спрос свыше 130 % от нормы."),

        # --- Шаг 3: LOW_WATER_PRESSURE ---
        ("14 мкр", T_PRESSURE, "high", at(15),
         "Падение давления в распределительной сети до 1,9 атм (норма 3,5–4,5 атм), "
         "жалобы жителей на отсутствие воды на верхних этажах."),
        ("15 мкр", T_PRESSURE, "medium", at(15),
         "Снижение давления в сети до 2,4 атм (норма 3,5–4,5 атм), перебои на верхних этажах."),
        ("26 мкр", T_PRESSURE, "high", at(15, 30),
         "Падение давления в сети до 1,7 атм (норма 3,5–4,5 атм) на магистрали, питающей 26 мкр."),

        # --- Шаг 4: CRITICAL_FACILITY_RISK ---
        (HOSPITAL, T_CRITICAL, "critical", at(17),
         "Угроза водоснабжению Мангистауской областной больницы: давление на вводе ниже допустимого, "
         "запас воды в резервных ёмкостях около 6 часов; риск для хирургии, реанимации и пищеблока."),
    ]

    return [
        {
            "district_name": district,
            "type": inc_type,
            "severity": severity,
            "triggered_at": triggered_at,
            "description": description,
        }
        for district, inc_type, severity, triggered_at, description in specs
    ]


# ----------------------------------------------------------------------------
# КОРРЕЛЯЦИИ (связи между инцидентами). Ключ инцидента = (район, тип)
# ----------------------------------------------------------------------------
CORRELATION_SPECS = [
    # --- Основная цепочка: 14 мкр ---
    (("14 мкр", T_HEAT), ("14 мкр", T_SURGE), 0.92,
     "Аномальная жара (>38 °C) резко повысила расход воды на полив, душ и охлаждение: спрос в 14 мкр вырос выше 130 % от нормы."),
    (("14 мкр", T_SURGE), ("14 мкр", T_PRESSURE), 0.90,
     "Пиковый водозабор превысил пропускную способность сети 14 мкр, из-за чего давление упало до 1,9 атм."),

    # --- Основная цепочка: 26 мкр ---
    (("26 мкр", T_HEAT), ("26 мкр", T_SURGE), 0.91,
     "Жара свыше 38 °C вызвала лавинообразный рост водопотребления в 26 мкр (свыше 150 % от нормы)."),
    (("26 мкр", T_SURGE), ("26 мкр", T_PRESSURE), 0.88,
     "Рост расхода воды в 26 мкр превысил ёмкость магистрали и снизил давление до 1,7 атм."),

    # --- Каскад между районами ---
    (("14 мкр", T_PRESSURE), ("26 мкр", T_PRESSURE), 0.80,
     "26 мкр находится ниже по течению общей магистрали: просадка давления в 14 мкр перераспределила нагрузку и усилила дефицит в 26 мкр."),
    (("15 мкр", T_PRESSURE), ("26 мкр", T_PRESSURE), 0.74,
     "Падение давления в 15 мкр на том же питающем кольце добавило нагрузки на соседний участок и ухудшило ситуацию в 26 мкр."),
    ((INDUSTRIAL, T_SURGE), ("14 мкр", T_PRESSURE), 0.71,
     "Промзона забирает воду из общего магистрального водовода, повышенный водозабор усугубил падение давления в 14 мкр."),

    # --- Угроза критическому объекту ---
    (("26 мкр", T_PRESSURE), (HOSPITAL, T_CRITICAL), 0.95,
     "Больница подключена к сети 26 мкр: давление на вводе упало ниже допустимого, риск потери водоснабжения хирургии и реанимации."),
    (("26 мкр", T_SURGE), (HOSPITAL, T_CRITICAL), 0.82,
     "Конкуренция жилого сектора и больницы за ограниченный ресурс воды в 26 мкр во время пика спроса снижает запас воды в резервных ёмкостях больницы."),

    # --- Дополнительные ветви для наглядности графа ---
    (("12 мкр", T_HEAT), ("12 мкр", T_SURGE), 0.82,
     "Жара свыше 38 °C привела к росту водопотребления в 12 мкр выше 130 % от нормы."),
    (("15 мкр", T_HEAT), ("15 мкр", T_SURGE), 0.88,
     "Аномальная жара в 15 мкр спровоцировала всплеск спроса на воду (около 145 % от нормы)."),
    (("15 мкр", T_SURGE), ("15 мкр", T_PRESSURE), 0.79,
     "Пиковый расход воды в 15 мкр вызвал снижение давления в сети до 2,4 атм."),
    (("27 мкр", T_HEAT), ("27 мкр", T_SURGE), 0.80,
     "Жара свыше 38 °C привела к росту спроса на воду в 27 мкр с задержкой около часа."),
    ((INDUSTRIAL, T_HEAT), (INDUSTRIAL, T_SURGE), 0.75,
     "Жара увеличила нагрузку на системы охлаждения в промзоне, что подняло водозабор выше 130 % от нормы."),
]


# ----------------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ----------------------------------------------------------------------------
def log(msg=""):
    print(msg, flush=True)


def short(text, limit=600):
    text = str(text)
    return text if len(text) <= limit else text[:limit] + f"... [обрезано, всего {len(text)} символов]"


def request_with_retry(method, url, **kwargs):
    """HTTP-запрос с повторами на сетевые ошибки и 5xx (Railway может просыпаться)."""
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
            if response.status_code >= 500 and attempt < MAX_RETRIES:
                log(f"   ! Сервер вернул {response.status_code}, повтор {attempt}/{MAX_RETRIES - 1}...")
                time.sleep(2 ** attempt)
                continue
            return response
        except requests.RequestException as exc:
            last_error = exc
            log(f"   ! Ошибка сети ({exc.__class__.__name__}: {exc}), попытка {attempt}/{MAX_RETRIES}")
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Не удалось выполнить {method} {url}: {last_error}")


def post_ingest(payload, label):
    log(f"-> POST {INGEST_URL}  [{label}]")
    response = request_with_retry("POST", INGEST_URL, json=payload,
                                  headers={"Content-Type": "application/json"})
    log(f"<- Статус-код: {response.status_code}")
    log(f"<- Ответ сервера: {short(response.text)}")
    if not response.ok:
        log("XX Бэкенд отклонил запрос, останавливаюсь.")
        sys.exit(1)
    return response


def get_incidents():
    log(f"-> GET {INCIDENTS_URL}")
    response = request_with_retry("GET", INCIDENTS_URL)
    log(f"<- Статус-код: {response.status_code}")
    if not response.ok:
        log("XX Не удалось получить список инцидентов, останавливаюсь.")
        log(f"<- Ответ сервера: {short(response.text)}")
        sys.exit(1)
    return response.json()


def extract_incident_list(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("incidents", "items", "data", "results"):
            if isinstance(data.get(key), list):
                return data[key]
    raise ValueError(f"Неожиданный формат ответа GET /incidents: {short(json.dumps(data, ensure_ascii=False))}")


def incident_district_name(item):
    if item.get("district_name"):
        return item["district_name"]
    district = item.get("district")
    if isinstance(district, dict):
        return district.get("name")
    if isinstance(district, str):
        return district
    return None


def norm(value):
    return str(value).strip().lower() if value is not None else ""


def build_incident_index(server_items):
    """
    Индексы серверных инцидентов. При повторных запусках в БД могут лежать дубли —
    берём инцидент с наибольшим id (самый свежий).
    """
    by_name, by_desc = {}, {}
    for item in sorted(server_items, key=lambda x: x.get("id") or 0):
        incident_id = item.get("id")
        if incident_id is None:
            continue
        name = incident_district_name(item)
        if name:
            by_name[(norm(name), norm(item.get("type")))] = incident_id
        by_desc[(norm(item.get("type")), norm(item.get("description")))] = incident_id
    return by_name, by_desc


def resolve_id(key, local_incidents, by_name, by_desc):
    district, inc_type = key
    found = by_name.get((norm(district), norm(inc_type)))
    if found is not None:
        return found
    local = local_incidents.get(key)
    if local:
        return by_desc.get((norm(inc_type), norm(local["description"])))
    return None


def validate_scenario(readings, incidents, correlation_specs):
    """Проверяет, что данные реально соответствуют порогам сценария и требованиям по весам."""
    by_reading = {(r["district_name"], r["timestamp"]): r for r in readings}
    errors = []
    for inc in incidents:
        hour_ts = datetime.strptime(inc["triggered_at"], ISO_FMT).replace(minute=0)
        reading = by_reading.get((inc["district_name"], hour_ts.strftime(ISO_FMT)))
        if reading is None:
            errors.append(f"Нет показаний для {inc['district_name']} на {hour_ts}")
            continue
        if inc["type"] == T_HEAT and not reading["temperature"] > HEAT_THRESHOLD:
            errors.append(f"{inc['district_name']}: HIGH_HEAT, но temperature={reading['temperature']}")
        if inc["type"] == T_SURGE and not reading["water_demand"] > SURGE_THRESHOLD:
            errors.append(f"{inc['district_name']}: WATER_DEMAND_SURGE, но water_demand={reading['water_demand']}")

    keys = {(i["district_name"], i["type"]) for i in incidents}
    for src, dst, weight, _ in correlation_specs:
        if not 0.7 <= weight <= 0.95:
            errors.append(f"Вес {weight} вне диапазона 0.7–0.95 ({src} -> {dst})")
        if src not in keys or dst not in keys:
            errors.append(f"Корреляция ссылается на несуществующий инцидент: {src} -> {dst}")

    # Не-затронутые районы не должны превышать порог жары (чтобы граф был "чистым")
    for r in readings:
        if r["district_name"] not in HEAT_AFFECTED and r["temperature"] > HEAT_THRESHOLD:
            errors.append(f"{r['district_name']} неожиданно >38 °C: {r['timestamp']}")

    if errors:
        log("XX Проверка данных не пройдена:")
        for e in errors:
            log(f"   - {e}")
        sys.exit(1)
    log("OK Проверка данных пройдена: пороги (>38 °C, >130 %) и веса (0.7–0.95) соблюдены.")


# ----------------------------------------------------------------------------
# ШАГИ 2-4: разрешение id и отправка корреляций
# ----------------------------------------------------------------------------
def run_correlations_step(local_incidents):
    log("\n[ШАГ 2] Получение реальных id созданных инцидентов (GET /incidents)")
    server_data = get_incidents()
    server_items = extract_incident_list(server_data)
    log(f"   Получено {len(server_items)} инцидентов с сервера.")

    by_name, by_desc = build_incident_index(server_items)

    log("\n[ШАГ 3] Сопоставление локальных инцидентов с id на сервере")
    unresolved = []
    correlations_payload = []

    for src_key, dst_key, weight, explanation in CORRELATION_SPECS:
        src_id = resolve_id(src_key, local_incidents, by_name, by_desc)
        dst_id = resolve_id(dst_key, local_incidents, by_name, by_desc)

        if src_id is None:
            unresolved.append(src_key)
            continue
        if dst_id is None:
            unresolved.append(dst_key)
            continue

        correlations_payload.append({
            "source_incident_id": src_id,
            "target_incident_id": dst_id,
            "weight": weight,
            "relation_type": "causal",
            "explanation": explanation,
        })

    if unresolved:
        log("XX Не удалось найти id для следующих инцидентов на сервере:")
        for key in unresolved:
            log(f"   - район={key[0]!r}, тип={key[1]!r}")
        log("   Проверьте, что ШАГ 1 выполнялся и district_name/type совпадают дословно.")
        sys.exit(1)

    log(f"   Все {len(correlations_payload)} корреляций сопоставлены с реальными id.")

    log("\n[ШАГ 4] Отправка correlations (POST /ingest)")
    payload = {"correlations": correlations_payload}
    post_ingest(payload, "correlations only")

    log("\nOK Готово: districts + readings + incidents + correlations загружены на бэкенд.")
    log(f"   Проверить результат: {BASE_URL}/graph?min_weight=0")


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="AKTAU INCIDENT GRAPH: загрузка синтетических данных")
    parser.add_argument("--dry-run", action="store_true",
                        help="только сгенерировать и проверить данные, сохранить aktau_payload_preview.json")
    parser.add_argument("--only-correlations", action="store_true",
                        help="пропустить шаг 1 (данные уже загружены) и выполнить шаги 2-4")
    args = parser.parse_args()

    rng = random.Random(RANDOM_SEED)

    districts = [{"name": n, "lat": lat, "lng": lng} for n, lat, lng in DISTRICTS]
    readings = build_readings(rng)
    incidents = build_incidents()
    local_incidents = {(i["district_name"], i["type"]): i for i in incidents}

    log("=" * 70)
    log("AKTAU INCIDENT GRAPH — загрузка данных")
    log("=" * 70)
    log(f"Сгенерировано: районов={len(districts)}, readings={len(readings)}, "
        f"incidents={len(incidents)}, планируемых correlations={len(CORRELATION_SPECS)}")
    validate_scenario(readings, incidents, CORRELATION_SPECS)

    if args.dry_run:
        preview = {
            "districts": districts,
            "readings": readings,
            "incidents": incidents,
            "correlations_plan": [
                {"source": list(s), "target": list(t), "weight": w, "explanation": e}
                for s, t, w, e in CORRELATION_SPECS
            ],
        }
        with open("aktau_payload_preview.json", "w", encoding="utf-8") as f:
            json.dump(preview, f, ensure_ascii=False, indent=2)
        log("Dry-run: ничего не отправлено. Данные сохранены в aktau_payload_preview.json")
        return

    # ---------------- ШАГ 1 ----------------
    if args.only_correlations:
        log("\n[ШАГ 1] Пропущен (--only-correlations)")
    else:
        log("\n[ШАГ 1] Отправка districts + readings + incidents (correlations = [])")
        payload = {"districts": districts, "readings": readings, "incidents": incidents, "correlations": []}
        post_ingest(payload, "districts + readings + incidents")

    # ---------------- ШАГИ 2-4 ----------------
    run_correlations_step(local_incidents)


if __name__ == "__main__":
    main()
