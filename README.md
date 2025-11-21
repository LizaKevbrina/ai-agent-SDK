<div align="center">

# AI Agent SDK

**Production-Ready LangChain Framework для интеллектуальных AI-агентов**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![LangChain](https://img.shields.io/badge/LangChain-0.1.20-green.svg)](https://langchain.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-teal.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

*Масштабируемый SDK для создания AI-агентов с RAG, версионируемой памятью и production-grade мониторингом*

[Быстрый старт](#-быстрый-старт) • [Архитектура](#-архитектура) • [API](#-api-reference) • [Production](#-production-deployment)

</div>

---

## О проекте

**AI Agent SDK** — production-ready фреймворк для создания интеллектуальных чат-ботов и AI-ассистентов на базе LangChain. Проект демонстрирует полный цикл разработки enterprise-grade AI-системы: от архитектуры до мониторинга.

### Ключевая проблема

Создание production AI-агента требует решения множества задач:
- Интеграция LLM с бизнес-логикой и инструментами
- Управление контекстом диалога с версионированием
- Безопасность (SQL injection, XSS, prompt injection)
- Надёжность (circuit breaker, retry, graceful degradation)
- Наблюдаемость (метрики, логирование, трейсинг)

### Решение

AI Agent SDK предоставляет готовую архитектуру со всеми компонентами:

```
Пользователь → FastAPI → Security → Agent → Tools/RAG/Memory → LLM → Ответ
                                      ↓
                              Logging + Metrics
```

### Демонстрируемые навыки

| Категория | Технологии |
|-----------|------------|
| **AI/ML** | LangChain, RAG, Vector Search, Embeddings, Prompt Engineering |
| **Backend** | FastAPI, asyncio, Pydantic, PostgreSQL, Redis |
| **DevOps** | Docker, Docker Compose, Prometheus, Grafana |
| **Quality** | pytest, k6, Chaos Engineering, CI/CD |
| **Architecture** | Microservices patterns, Circuit Breaker, CQRS |

---

##  Возможности

###  Core Features

| Feature | Описание |
|---------|----------|
| **LangChain Agent** | OpenAI Functions Agent с кастомными инструментами |
| **RAG Pipeline** | Supabase pgvector + YandexGPT Embeddings (256 dim) |
| **Versioned Memory** | Pessimistic locking, sliding window (40 сообщений) |
| **Multi-LLM** | YandexGPT (primary) + OpenAI (fallback) |
| **Security Layer** | SQL injection, XSS, path traversal protection |
| **Business Metrics** | Sales funnel tracking, intent distribution |

###  Доступные инструменты агента

```python
tools = [
    search_documents,      # Поиск в базе знаний (RAG)
    calculate_mortgage,    # Расчёт ипотеки
    get_property_details,  # Детали объекта
    check_availability,    # Проверка доступности
    book_viewing          # Запись на просмотр
]
```

###  Performance & Reliability

- **Circuit Breaker** — автоматическое отключение при сбоях LLM
- **Retry Logic** — exponential backoff для transient errors
- **LLM Caching** — Redis cache для повторных запросов
- **Singleton Pattern** — переиспользование embeddings/retriever (800ms → 300ms)
- **Connection Pooling** — shared DB pool (предотвращение exhaustion)

---

##  Быстрый старт

### Требования

- Python 3.11+
- Docker & Docker Compose
- API ключи: YandexGPT или OpenAI
- Supabase проект (бесплатный tier достаточен)

### Установка за 3 шага

```bash
# 1. Клонировать
git clone https://github.com/yourusername/ai-agent-sdk.git
cd ai-agent-sdk

# 2. Настроить окружение
cp .env.example .env
nano .env  # Добавить API ключи

# 3. Запустить
make dev
```

### Первый запрос

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Какие квартиры есть в продаже?",
    "session_id": "demo_user",
    "prompt_version": "v1"
  }'
```

**Ответ:**
```json
{
  "response": "Здравствуйте! Сейчас проверю базу...",
  "tools_used": ["search_documents"],
  "tokens_used": 234,
  "response_time_ms": 1423,
  "context_used": true,
  "documents_found": 3
}
```

---

##  Архитектура

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    FASTAPI APPLICATION                      │
│                     (agent/main.py)                         │
├─────────────────────────────────────────────────────────────┤
│  🔐 Security    →   🤖 Agent   →   📊 Logging              │
│  Validation         Executor        Callbacks               │
└─────────────────────────────────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│   TOOLS     │   │    RAG      │   │   MEMORY    │
├─────────────┤   ├─────────────┤   ├─────────────┤
│ search      │   │ Supabase    │   │ PostgreSQL  │
│ calculate   │   │ pgvector    │   │ Versioned   │
│ book        │   │ YandexGPT   │   │ Sliding     │
│ details     │   │ Embeddings  │   │ Window      │
└─────────────┘   └─────────────┘   └─────────────┘
         │                 │                 │
         └─────────────────┼─────────────────┘
                           ▼
              ┌─────────────────────┐
              │   LLM PROVIDERS     │
              ├─────────────────────┤
              │ YandexGPT (primary) │
              │ OpenAI (fallback)   │
              │ Circuit Breaker     │
              │ Retry Logic         │
              └─────────────────────┘
                           │
                           ▼
              ┌─────────────────────┐
              │   INFRASTRUCTURE    │
              ├─────────────────────┤
              │ Redis (LLM cache)   │
              │ Prometheus (metrics)│
              │ Grafana (dashboard) │
              └─────────────────────┘
```

### Структура проекта

```
ai-agent-sdk/
├── agent/                    # Core application
│   ├── main.py              # FastAPI app + endpoints
│   ├── executor.py          # SecureAgentExecutor
│   ├── metrics.py           # Prometheus metrics
│   ├── chains.py            # LangChain pipelines
│   └── multi_agent.py       # Multi-agent architecture
│
├── tools/                   # Agent tools
│   ├── security.py          # Input validation
│   └── real_estate.py       # Domain tools
│
├── rag/                     # RAG components
│   ├── retrievers.py        # Vector store retriever
│   └── embeddings.py        # YandexGPT embeddings
│
├── llm/                     # LLM integration
│   └── models.py            # ChatYandexGPT wrapper
│
├── memory/                  # Conversation memory
│   └── history.py           # VersionedChatHistory
│
├── logging/                 # Observability
│   └── callbacks.py         # Supabase logging
│
├── config/                  # Configuration
│   ├── settings.py          # Pydantic settings
│   └── prompts.py           # Versioned prompts
│
├── tests/                   # Test suite
│   ├── test_agent.py        # E2E tests
│   ├── test_memory.py       # Memory tests
│   ├── test_chaos.py        # Chaos engineering
│   └── load_test_sdk.js     # k6 load tests
│
├── monitoring/              # Monitoring
│   ├── prometheus.yml
│   ├── alerts.yml
│   └── grafana/
│
├── docker-compose.yml       # Development
├── Dockerfile
├── Makefile                 # CLI commands
├── init.sql                 # Database schema
└── requirements.txt
```

---

## API Reference

### POST `/chat` — Отправить сообщение

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Посчитай ипотеку на 5 млн",
    "session_id": "user_123",
    "prompt_version": "v1",
    "input_type": "text",
    "use_openai": false
  }'
```

**Response:**
```json
{
  "response": "Расчёт ипотеки:\n• Стоимость: 5,000,000 ₽\n• Первоначальный взнос (20%): 1,000,000 ₽\n• Ежемесячный платёж: 41,234 ₽",
  "session_id": "user_123",
  "tools_used": ["calculate_mortgage"],
  "tokens_used": 156,
  "response_time_ms": 892,
  "context_used": false,
  "documents_found": 0,
  "timestamp": "2025-01-27T15:30:00.123Z",
  "correlation_id": "req-abc-123",
  "cached": false
}
```

### DELETE `/chat/{session_id}` — Очистить историю

```bash
curl -X DELETE http://localhost:8000/chat/user_123
```

### GET `/health` — Health check

```json
{
  "status": "healthy",
  "service": "ai-agent",
  "version": "2.0.0",
  "components": {
    "yandex_gpt": "ok",
    "supabase": "ok",
    "postgres": "ok",
    "redis": "ok"
  },
  "cache_stats": {
    "retriever": {"hits": 45, "misses": 12},
    "embeddings": {"hits": 89, "misses": 3}
  }
}
```

### GET `/metrics` — Prometheus metrics

```
# HELP agent_requests_total Total agent requests
# TYPE agent_requests_total counter
agent_requests_total{status="success",tool_used="search_documents"} 234

# HELP agent_duration_seconds Agent request duration
# TYPE agent_duration_seconds histogram
agent_duration_seconds_bucket{le="2"} 189
```

---

## Конфигурация

### Environment Variables

```bash
# LLM Providers
YANDEX_API_KEY=your_key
YANDEX_FOLDER_ID=your_folder_id
OPENAI_API_KEY=sk-...              # Optional

# Database
POSTGRES_URL=postgresql://ai_user:pass@postgres:5432/ai_db
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your_key
REDIS_URL=redis://redis:6379

# Agent Configuration
TEMPERATURE=0.7
MAX_TOKENS=2000
SIMILARITY_THRESHOLD=0.7
RAG_TOP_K=5
MEMORY_WINDOW_SIZE=40

# Circuit Breaker
CIRCUIT_BREAKER_FAIL_MAX=5
CIRCUIT_BREAKER_TIMEOUT=60
```

### Versioned Prompts

```python
# config/prompts.py
PROMPT_VERSIONS = {
    "v1": """Роль: AI-менеджер по недвижимости...""",
    "v2": """Роль: Премиум-консультант (SPIN методология)..."""
}
```

---

## Production Deployment

### Docker Compose (VPS)

```bash
# 1. Настроить secrets
mkdir secrets
echo "YOUR_API_KEY" > secrets/yandex_api_key.txt
chmod 600 secrets/*

# 2. Проверить конфигурацию
make check-secrets

# 3. Деплой
make deploy
```

### Kubernetes

```bash
kubectl apply -f deployment/kubernetes/
kubectl get pods -n ai-agent
```

### Monitoring после деплоя

| Service | URL | Credentials |
|---------|-----|-------------|
| API Docs | http://host:8000/docs | — |
| Prometheus | http://host:9090 | — |
| Grafana | http://host:3000 | admin/admin |

---

## Тестирование

### Запуск тестов

```bash
# Все тесты
make test

# Unit тесты
make test-unit

# Integration тесты
make test-integration

# Load testing (k6)
make test-load

# Chaos engineering
make test-chaos
```

### Test Coverage

```
agent/main.py          85%
memory/history.py     100%
tools/security.py      95%
rag/retrievers.py      90%
llm/models.py          88%
─────────────────────────
TOTAL                  92%
```

---

## Мониторинг

### Ключевые метрики

```promql
# Request rate
sum(rate(agent_requests_total[5m]))

# P95 latency
histogram_quantile(0.95, rate(agent_duration_seconds_bucket[5m]))

# Error rate
sum(rate(agent_requests_total{status="error"}[5m])) / sum(rate(agent_requests_total[5m]))

# Token usage (hourly)
sum(increase(llm_tokens_used_sum[1h]))

# Conversion rate
sum(successful_closings_total) / sum(funnel_step_reached_total{step="greeting"})
```

### Grafana Dashboard

Dashboard включает панели:
- Request Rate & Latency
- Error Rate & Circuit Breaker
- Token Usage & Cost Estimation
- Sales Funnel Conversion
- Tool Usage Distribution
- Cache Hit Rate

---

## Показатели производительности

| Метрика | Значение |
|---------|----------|
| P95 Latency | < 2s |
| Error Rate | < 1% |
| Throughput | 50 RPS |
| Cache Hit Rate | > 70% |
| Circuit Breaker Recovery | 60s |

---

## Roadmap

- [x] Core agent implementation
- [x] RAG with similarity filtering
- [x] Versioned memory with locking
- [x] Security validation layer
- [x] Prometheus + Grafana monitoring
- [x] Chaos engineering tests
- [ ] OpenTelemetry tracing
- [ ] Voice input/output
- [ ] Multi-tenant support
- [ ] A/B testing framework

---

## 👩‍💻 Автор

<div align="center">

**Елизавета Кевбрина**

*AI/ML Engineer • LangChain Developer*

[![Email](https://img.shields.io/badge/Email-elisa.kevbrina%40yandex.ru-red?style=flat-square&logo=gmail)](mailto:elisa.kevbrina@yandex.ru)
[![GitHub](https://img.shields.io/badge/GitHub-%40LizaKevbrina-black?style=flat-square&logo=github)](https://github.com/LizaKevbrina)

</div>

---

## 📄 Лицензия

MIT License — см. [LICENSE](LICENSE)

---

<div align="center">

**⭐ Если проект полезен, поставьте звёздочку!**

</div>
