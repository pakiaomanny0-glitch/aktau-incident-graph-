# Aktau City Intelligence — Incident Correlation Graph

Ақтау қаласындағы қалалық инфрақұрылым оқиғаларының (жылу, су тапшылығы, қысым құлдырауы, критикалық нысан қаупі) арасындағы себеп-салдар байланысын анықтайтын AI-негізделген backend + frontend жүйе.

Дербес сигналдар (аномальды жылу, су сұранысының секірісі, қысымның төмендеуі) көбіне бір-бірінен бөлек көрінеді. Бұл жүйе оларды граф түрінде біріктіріп, каскадты авария қалай өрбитінін — мысалы, жылу қалай ауруханадағы су тапшылығы қаупіне дейін апаратынын — алдын ала көрсетеді.

## Демо сценарий

24 қыркүйек 2026, каскадты авария (синтетикалық деректер):

```
11:00  HIGH_HEAT              (12, 14, 15, 26, 27 мкр, порт, өнеркәсіп)
  ↓
13:00  WATER_DEMAND_SURGE     (сұраныс нормадан >130%)
  ↓
15:00  LOW_WATER_PRESSURE     (су желісінде қысым құлдырауы)
  ↓
17:00  CRITICAL_FACILITY_RISK (Маңғыстау облыстық ауруханасы)
```

Негізгі тізбек: **14 мкр → 26 мкр → облыстық аурухана**. Барлық correlation салмақтары 0.70–0.95 аралығында расталған.

## Архитектура

```
data/aktau_seed.py  →  POST /ingest  →  backend (FastAPI + SQLAlchemy)
                                              │
                                    POST /analyze/run
                                              │
                                      DeepSeek Chat API
                                   (incidents + correlations)
                                              │
                                       GET /graph, /incidents
                                              │
                                    frontend (React, Vite)
```

Backend деректерге ешбір эвристикалық ереже (`if temp > 35...`) қолданбайды — incident пен correlation анықтауды толығымен LLM (DeepSeek) шешеді. Бэкенд тек нәтижені сақтайды және API арқылы қайтарады.

## Технологиялар

| Қабат | Стек |
|---|---|
| Backend | FastAPI, SQLAlchemy, Python |
| AI | DeepSeek Chat API (`response_format: json_object`) |
| Frontend | React, Vite |
| Деректер | Синтетикалық генератор (`data/aktau_seed.py`) |
| Deploy | Railway (backend), Vercel (frontend) |

## Жоба құрылымы

```
backend/
  main.py              # FastAPI app, роутерлерді қосу
  models.py            # District, Reading, Incident, Correlation
  schemas.py           # Pydantic схемалар
  database.py          # SQLAlchemy engine/session
  ai_analysis.py       # DeepSeek-ке сұраныс, JSON парсинг
  routers/
    ingest.py          # POST /ingest — districts/readings/incidents/correlations жүктеу
    incidents.py       # GET/POST /incidents — тізім, сүзгі, бір оқиға
    graph.py           # GET /graph — nodes/edges граф форматы
    analyze.py         # POST /analyze/run — DeepSeek арқылы авто-талдау
data/
  aktau_seed.py         # 18 аудан/нысан, 72 сағаттық readings, демо сценарий генераторы
frontend/
  src/App.jsx            # Overview / Incident map / Correlation graph беттері
```

## API

| Endpoint | Сипаттама |
|---|---|
| `POST /ingest` | districts, readings, incidents, correlations жүктеу (барлығы optional) |
| `GET /incidents` | Оқиғалар тізімі; `district`, `severity`, `type` сүзгілерімен |
| `GET /incidents/{id}` | Бір оқиға |
| `POST /incidents` | Қолмен оқиға құру (демо үшін) |
| `GET /graph?min_weight=0` | Граф: `nodes` = incidents, `edges` = correlations |
| `POST /analyze/run?since_hours=24&district=...` | DeepSeek арқылы автоматты incident/correlation анықтау |
| `GET /health` | Сервис статусы |

## Іске қосу

### Backend

```bash
cd backend
pip install -r requirements.txt
export DEEPSEEK_API_KEY=<сенің кілтің>
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_URL орнату
npm run dev
```

### Демо деректерді жүктеу

```bash
cd data
pip install requests
python aktau_seed.py --dry-run   # алдымен тексеру (aktau_payload_preview.json)
python aktau_seed.py             # districts + readings + incidents + correlations жіберу
```

Нәтижені тексеру: `GET /graph?min_weight=0`

## Ескерту

Координаттар мен барлық сенсор деректері **синтетикалық** (шамамен, дәлдігі жүздеген метр реттес) — нақты өлшем құралдарынан алынбаған. Хакатон демонстрациясы үшін жасалған сценарий, production-ready дерек көзі емес.
