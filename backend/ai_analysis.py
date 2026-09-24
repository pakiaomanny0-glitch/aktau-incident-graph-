"""
DeepSeek арқылы incident + correlation талдауы.

Мақсаты: districts + readings (температура, су сұранысы, су қысымы)
деректерін DeepSeek-ке жіберіп, LLM-нің өзіне:
  - қай аймақта қандай incident бар (типі, severity, түсініктеме)
  - incident-тер арасында қандай байланыс (correlation) бар
деп шештіру.

Backend тек нәтижені сұрайды және сақтайды — эвристикалық ереже
(if temp > 35...) ЕМЕС, шешімді толығымен модель қабылдайды.
"""

import os
import json
import httpx

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


class AIAnalysisError(Exception):
    """DeepSeek сұранысы немесе жауабы дұрыс болмаса көтеріледі."""
    pass


SYSTEM_PROMPT = """Сен - қалалық инфрақұрылымды талдайтын сарапшы AI жүйесісің.
Саған әр аймақ (district) бойынша сенсор деректері (температура, су сұранысы,
су қысымы, уақыт белгісі) беріледі. Сенің міндетің:

1. Деректерге қарап, қай аймақта қандай проблема (incident) туындауы мүмкін
   екенін анықтау. Мысалы: аномальды жоғары температура + судың сұранысы
   артуы + қысымның төмендеуі бір мезгілде болса, бұл су тапшылығы
   қаупін білдіруі мүмкін.
2. Әр incident үшін severity (low | medium | high) белгілеу.
3. Incident-тер арасындағы себеп-салдар немесе уақыттық байланысты
   (correlation) анықтау: қай incident қайсысына әсер еткен болуы мүмкін.

ТЕК төмендегі JSON форматында, басқа ешбір мәтінсіз, түсініктемесіз жауап бер:

{
  "incidents": [
    {
      "district_name": "<берілген district атауы дәл сол күйінде>",
      "type": "<қысқа ағылшынша snake_case, мыс. water_shortage, heat_spike, pressure_drop>",
      "severity": "low | medium | high",
      "description": "<қазақша қысқа түсініктеме, неге бұл incident деп танылды>",
      "triggered_at": "<берілген readings ішіндегі ең сай келетін timestamp, ISO 8601>"
    }
  ],
  "correlations": [
    {
      "source_index": <incidents массивіндегі 0-based индекс>,
      "target_index": <incidents массивіндегі 0-based индекс>,
      "weight": <0.0 - 1.0 аралығында, байланыс күші>,
      "relation_type": "causal | temporal | spatial",
      "explanation": "<қазақша қысқа түсініктеме>"
    }
  ]
}

Егер деректерде ешбір проблема көрінбесе, "incidents": [] және
"correlations": [] қайтар. Ойдан incident шығарма - тек берілген
сандарға сүйен."""


def _build_user_prompt(districts: list[dict], readings: list[dict]) -> str:
    payload = {
        "districts": districts,
        "readings": readings,
    }
    return (
        "Төмендегі деректерді талда және system prompt-та көрсетілген "
        "JSON форматында ғана жауап бер:\n\n"
        + json.dumps(payload, ensure_ascii=False, default=str)
    )


def analyze_districts(districts: list[dict], readings: list[dict]) -> dict:
    """
    DeepSeek chat completions API-ге сұраныс жасайды.

    districts: [{"name": str, "lat": float, "lng": float}, ...]
    readings:  [{"district_name": str, "timestamp": str, "temperature": float,
                 "water_demand": float, "water_pressure": float}, ...]

    Қайтарады: {"incidents": [...], "correlations": [...]} (жоғарыдағы форматта)
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise AIAnalysisError(
            "DEEPSEEK_API_KEY орнатылмаған. Railway → Variables бөліміне қосыңыз."
        )

    if not readings:
        # Талдайтын дерек жоқ болса, DeepSeek-ке сұраныс жасаудың мәні жоқ
        return {"incidents": [], "correlations": []}

    body = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(districts, readings)},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    try:
        response = httpx.post(
            DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=60.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise AIAnalysisError(
            f"DeepSeek API қатесі: {exc.response.status_code} - {exc.response.text}"
        ) from exc
    except httpx.RequestError as exc:
        raise AIAnalysisError(f"DeepSeek-ке қосыла алмады: {exc}") from exc

    data = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise AIAnalysisError(f"DeepSeek жауабының форматы күтпеген: {data}") from exc

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AIAnalysisError(
            f"DeepSeek JSON қайтармады. Жауап: {content[:500]}"
        ) from exc

    parsed.setdefault("incidents", [])
    parsed.setdefault("correlations", [])
    return parsed
