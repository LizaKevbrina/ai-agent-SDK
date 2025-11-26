# ========================================
# AI Agent SDK - Makefile (VPS Ubuntu + Docker)
# Автор: AI Agent SDK Team
# Окружение: VPS Ubuntu 20.04+, Docker, Docker Compose
# ========================================

.PHONY: help build start stop restart logs health test deploy clean

# Цвета для вывода
RED    := \033[0;31m
GREEN  := \033[0;32m
YELLOW := \033[0;33m
BLUE   := \033[0;34m
NC     := \033[0m # No Color

# Переменные окружения
ENV_FILE := .env
COMPOSE_FILE := docker-compose.yml
COMPOSE_PROD_FILE := deployment/docker-compose.prod.yml

# Проверка наличия .env
check-env:
	@if [ ! -f $(ENV_FILE) ]; then \
		echo "$(RED)❌ Файл .env не найден!$(NC)"; \
		echo "$(YELLOW)Создайте его из .env.example:$(NC)"; \
		echo "  cp .env.example .env"; \
		echo "  nano .env"; \
		exit 1; \
	fi

# ========================================
# HELP - Справка по командам
# ========================================

help: ## Показать справку по всем командам
	@echo "$(GREEN)╔════════════════════════════════════════════════════════╗$(NC)"
	@echo "$(GREEN)║        AI Agent SDK - Makefile Commands               ║$(NC)"
	@echo "$(GREEN)╚════════════════════════════════════════════════════════╝$(NC)"
	@echo ""
	@echo "$(BLUE)🚀 ОСНОВНЫЕ КОМАНДЫ:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BLUE)📚 ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ:$(NC)"
	@echo "  $(GREEN)make dev$(NC)           # Запуск для разработки"
	@echo "  $(GREEN)make test$(NC)          # Запуск всех тестов"
	@echo "  $(GREEN)make deploy$(NC)        # Деплой в production на VPS"
	@echo "  $(GREEN)make logs-agent$(NC)    # Просмотр логов агента"
	@echo "  $(GREEN)make backup$(NC)        # Резервная копия БД"

# ========================================
# РАЗРАБОТКА (Development)
# ========================================

dev: check-env ## Запуск для локальной разработки (hot reload)
	@echo "$(GREEN)🚀 Запуск в режиме разработки...$(NC)"
	@echo "$(YELLOW)📝 Логи будут выводиться в консоль$(NC)"
	docker-compose up --build
	@echo "$(GREEN)✅ Разработка запущена!$(NC)"
	@echo "$(BLUE)🌐 API: http://localhost:8000$(NC)"
	@echo "$(BLUE)📊 Metrics: http://localhost:8000/metrics$(NC)"
	@echo "$(BLUE)📖 Docs: http://localhost:8000/docs$(NC)"

dev-detached: check-env ## Запуск для разработки (фоновый режим)
	@echo "$(GREEN)🚀 Запуск в фоновом режиме...$(NC)"
	docker-compose up -d --build
	@make health
	@echo "$(GREEN)✅ Разработка запущена в фоне!$(NC)"

# ========================================
# PRODUCTION (Deployment на VPS)
# ========================================

deploy: check-env ## Деплой в production на VPS
	@echo "$(RED)⚠️  ВНИМАНИЕ: Деплой в PRODUCTION!$(NC)"
	@read -p "Вы уверены? (yes/no): " confirm && [ "$$confirm" = "yes" ]
	@echo "$(GREEN)🚀 Запуск production deployment...$(NC)"
	
	# 1. Проверка secrets
	@make check-secrets
	
	# 2. Pull последних изменений
	@echo "$(BLUE)📥 Pulling latest changes...$(NC)"
	git pull origin main
	
	# 3. Build образов
	@echo "$(BLUE)🏗️  Building Docker images...$(NC)"
	docker-compose -f $(COMPOSE_PROD_FILE) build --no-cache
	
	# 4. Остановка старой версии
	@echo "$(YELLOW)🛑 Stopping old version...$(NC)"
	docker-compose -f $(COMPOSE_PROD_FILE) down
	
	# 5. Запуск новой версии
	@echo "$(GREEN)🚀 Starting new version...$(NC)"
	docker-compose -f $(COMPOSE_PROD_FILE) up -d
	
	# 6. Health check
	@sleep 15
	@make health
	
	# 7. Backup после успешного деплоя
	@make backup
	
	@echo "$(GREEN)✅ Production deployment completed!$(NC)"
	@echo "$(BLUE)🌐 Check status: make ps$(NC)"
	@echo "$(BLUE)📊 View logs: make logs$(NC)"

check-secrets: ## Проверка наличия всех secrets
	@echo "$(BLUE)🔐 Проверка secrets...$(NC)"
	@if [ ! -f secrets/yandex_api_key.txt ]; then echo "$(RED)❌ yandex_api_key.txt missing$(NC)"; exit 1; fi
	@if [ ! -f secrets/yandex_folder_id.txt ]; then echo "$(RED)❌ yandex_folder_id.txt missing$(NC)"; exit 1; fi
	@if [ ! -f secrets/supabase_url.txt ]; then echo "$(RED)❌ supabase_url.txt missing$(NC)"; exit 1; fi
	@if [ ! -f secrets/supabase_key.txt ]; then echo "$(RED)❌ supabase_key.txt missing$(NC)"; exit 1; fi
	@if [ ! -f secrets/postgres_password.txt ]; then echo "$(RED)❌ postgres_password.txt missing$(NC)"; exit 1; fi
	@echo "$(GREEN)✅ All secrets configured$(NC)"

# ========================================
# УПРАВЛЕНИЕ КОНТЕЙНЕРАМИ
# ========================================

build: check-env ## Сборка всех Docker образов
	@echo "$(GREEN)🏗️  Building Docker images...$(NC)"
	docker-compose build

start: check-env ## Запуск всех сервисов
	@echo "$(GREEN)🚀 Starting services...$(NC)"
	docker-compose up -d
	@sleep 5
	@make health

stop: ## Остановка всех сервисов
	@echo "$(YELLOW)🛑 Stopping services...$(NC)"
	docker-compose down

restart: ## Перезапуск всех сервисов
	@echo "$(YELLOW)🔄 Restarting services...$(NC)"
	@make stop
	@sleep 2
	@make start

restart-agent: ## Перезапуск только агента (без инфраструктуры)
	@echo "$(YELLOW)🔄 Restarting agent...$(NC)"
	docker-compose restart agent
	@sleep 5
	@make health

# ========================================
# ЛОГИ И МОНИТОРИНГ
# ========================================

logs: ## Просмотр логов всех сервисов
	docker-compose logs -f

logs-agent: ## Просмотр логов только агента
	docker-compose logs -f agent

logs-errors: ## Показать только ERROR логи
	docker-compose logs -f | grep -i error

ps: ## Показать статус всех контейнеров
	docker-compose ps

stats: ## Показать использование ресурсов контейнерами
	docker stats --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"

health: ## Проверка здоровья всех сервисов
	@echo "$(GREEN)🏥 Health Check...$(NC)"
	@curl -s http://localhost:8000/health | jq '.' || echo "$(RED)❌ Agent unhealthy$(NC)"
	@echo ""
	@echo "$(BLUE)📊 Prometheus: http://localhost:9090$(NC)"
	@echo "$(BLUE)📈 Grafana: http://localhost:3000 (admin/admin)$(NC)"

# ========================================
# ТЕСТИРОВАНИЕ
# ========================================

test: ## Запуск всех тестов
	@echo "$(GREEN)🧪 Running all tests...$(NC)"
	pytest tests/ -v --cov=agent --cov=tools --cov=rag --cov=llm --cov=memory --cov-report=html --cov-report=term-missing

test-quick: ## Быстрый smoke test (только основные проверки)
	@echo "$(GREEN)🧪 Running quick tests...$(NC)"
	python tests/test_quick.py

test-unit: ## Только unit-тесты (без integration)
	@echo "$(GREEN)🧪 Running unit tests...$(NC)"
	pytest tests/ -v -k "not integration" --cov=agent --cov-report=term-missing

test-integration: ## Только integration тесты
	@echo "$(GREEN)🧪 Running integration tests...$(NC)"
	@make start
	@sleep 10
	pytest tests/test_agent.py tests/test_memory.py -v

test-load: ## Load testing с k6
	@echo "$(RED)⚠️  Running load test...$(NC)"
	k6 run tests/load_test_sdk.js --out json=load_test_results.json

test-chaos: ## Chaos engineering тесты
	@echo "$(RED)💥 Running chaos tests...$(NC)"
	pytest tests/test_chaos.py -v -s

# ========================================
# БАЗА ДАННЫХ
# ========================================

db-shell: ## Открыть PostgreSQL shell
	docker-compose exec postgres psql -U ai_user -d ai_db

db-migrate: ## Применить init.sql (создание таблиц)
	@echo "$(BLUE)📊 Running database migrations...$(NC)"
	docker-compose exec -T postgres psql -U ai_user -d ai_db < init.sql
	@echo "$(GREEN)✅ Database migrated$(NC)"

db-backup: ## Создать backup базы данных
	@echo "$(BLUE)💾 Creating database backup...$(NC)"
	@mkdir -p backups
	docker-compose exec -T postgres pg_dump -U ai_user ai_db > backups/backup_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "$(GREEN)✅ Backup created: backups/backup_$(shell date +%Y%m%d_%H%M%S).sql$(NC)"

db-restore: ## Восстановить backup (укажите: make db-restore FILE=backup.sql)
	@if [ -z "$(FILE)" ]; then echo "$(RED)❌ Укажите файл: make db-restore FILE=backup.sql$(NC)"; exit 1; fi
	@echo "$(YELLOW)⚠️  Восстановление базы из $(FILE)...$(NC)"
	@read -p "Все данные будут удалены! Продолжить? (yes/no): " confirm && [ "$$confirm" = "yes" ]
	docker-compose exec -T postgres psql -U ai_user ai_db < $(FILE)
	@echo "$(GREEN)✅ Database restored$(NC)"

db-clean: ## Очистить старые данные (chat history >30 дней)
	@echo "$(YELLOW)🧹 Cleaning old data...$(NC)"
	docker-compose exec postgres psql -U ai_user -d ai_db -c "SELECT clean_old_chat_history();"
	docker-compose exec postgres psql -U ai_user -d ai_db -c "SELECT clean_old_logs();"
	docker-compose exec postgres psql -U ai_user -d ai_db -c "SELECT clean_old_errors();"
	@echo "$(GREEN)✅ Old data cleaned$(NC)"

# ========================================
# REDIS CACHE
# ========================================

cache-flush: ## Очистить весь Redis cache
	@echo "$(YELLOW)🗑️  Flushing Redis cache...$(NC)"
	docker-compose exec redis redis-cli FLUSHALL
	@echo "$(GREEN)✅ Cache flushed$(NC)"

cache-stats: ## Показать статистику Redis
	docker-compose exec redis redis-cli INFO stats

cache-shell: ## Открыть Redis CLI
	docker-compose exec redis redis-cli

# ========================================
# ОЧИСТКА
# ========================================

clean: ## Остановить и удалить контейнеры, сети
	@echo "$(RED)🗑️  Cleaning up...$(NC)"
	docker-compose down
	@echo "$(GREEN)✅ Cleanup complete$(NC)"

clean-all: ## Полная очистка (контейнеры, volumes, images)
	@echo "$(RED)⚠️  WARNING: This will delete ALL data!$(NC)"
	@read -p "Are you sure? (yes/no): " confirm && [ "$$confirm" = "yes" ]
	docker-compose down -v --rmi all
	@echo "$(GREEN)✅ Full cleanup complete$(NC)"

clean-logs: ## Удалить старые log файлы
	@echo "$(YELLOW)🗑️  Cleaning log files...$(NC)"
	find . -name "*.log" -type f -delete
	@echo "$(GREEN)✅ Logs cleaned$(NC)"

# ========================================
# DEVELOPMENT UTILITIES
# ========================================

lint: ## Проверка кода (flake8, black, isort)
	@echo "$(BLUE)🔍 Running linters...$(NC)"
	flake8 agent/ tools/ rag/ llm/ memory/ logging/ --max-line-length=127
	black --check agent/ tools/ rag/ llm/ memory/ logging/
	isort --check-only agent/ tools/ rag/ llm/ memory/ logging/

format: ## Форматирование кода
	@echo "$(BLUE)✨ Formatting code...$(NC)"
	black agent/ tools/ rag/ llm/ memory/ logging/
	isort agent/ tools/ rag/ llm/ memory/ logging/
	@echo "$(GREEN)✅ Code formatted$(NC)"

install-dev: ## Установить зависимости для разработки
	pip install -r requirements.txt
	pip install flake8 black isort mypy pytest pytest-cov pytest-asyncio

shell-agent: ## Открыть shell внутри контейнера агента
	docker-compose exec agent /bin/sh

# ========================================
# MONITORING
# ========================================

metrics: ## Открыть Prometheus metrics
	@echo "$(BLUE)📊 Prometheus Metrics:$(NC)"
	@echo "  http://localhost:9090"
	@echo ""
	@echo "$(BLUE)📈 Grafana Dashboard:$(NC)"
	@echo "  http://localhost:3000"
	@echo "  Login: admin / admin"

grafana-import: ## Импортировать Grafana dashboard
	@echo "$(BLUE)📊 Importing Grafana dashboard...$(NC)"
	@echo "1. Откройте http://localhost:3000"
	@echo "2. Login: admin / admin"
	@echo "3. Dashboards → Import"
	@echo "4. Upload JSON: monitoring/grafana/dashboards/agent.json"

prometheus-reload: ## Перезагрузить конфигурацию Prometheus
	docker-compose exec prometheus kill -HUP 1
	@echo "$(GREEN)✅ Prometheus config reloaded$(NC)"

# ========================================
# BACKUP & RESTORE
# ========================================

backup: ## Полный backup (БД + secrets + .env)
	@echo "$(BLUE)💾 Creating full backup...$(NC)"
	@mkdir -p backups/full_$(shell date +%Y%m%d_%H%M%S)
	@make db-backup
	@cp -r secrets backups/full_$(shell date +%Y%m%d_%H%M%S)/
	@cp .env backups/full_$(shell date +%Y%m%d_%H%M%S)/
	@tar -czf backups/full_$(shell date +%Y%m%d_%H%M%S).tar.gz backups/full_$(shell date +%Y%m%d_%H%M%S)
	@rm -rf backups/full_$(shell date +%Y%m%d_%H%M%S)
	@echo "$(GREEN)✅ Full backup created: backups/full_$(shell date +%Y%m%d_%H%M%S).tar.gz$(NC)"

# ========================================
# CI/CD
# ========================================

ci: ## Запуск CI pipeline локально (lint → test → build)
	@echo "$(GREEN)🔄 Running CI pipeline...$(NC)"
	@make lint
	@make test-quick
	@make build
	@echo "$(GREEN)✅ CI pipeline completed$(NC)"

version: ## Показать версии всех компонентов
	@echo "$(GREEN)📦 Component Versions:$(NC)"
	@echo "  Agent SDK: $(shell grep 'VERSION' config/settings.py | head -1 | cut -d'"' -f2)"
	@docker-compose exec agent python --version
	@docker-compose exec postgres psql --version
	@docker-compose exec redis redis-cli --version

# ========================================
# PRODUCTION UTILITIES
# ========================================

update: ## Обновление до последней версии (для production)
	@echo "$(YELLOW)🔄 Updating to latest version...$(NC)"
	git pull origin main
	@make deploy

rollback: ## Откатиться к предыдущему backup
	@echo "$(RED)⚠️  Rolling back to previous version...$(NC)"
	@ls -t backups/*.sql | head -1
	@read -p "Use this backup? (yes/no): " confirm && [ "$$confirm" = "yes" ]
	@make db-restore FILE=$(shell ls -t backups/*.sql | head -1)

# ========================================
# TROUBLESHOOTING
# ========================================

debug: ## Показать отладочную информацию
	@echo "$(BLUE)🐛 Debug Information:$(NC)"
	@echo ""
	@echo "$(YELLOW)=== Docker Containers ===$(NC)"
	@make ps
	@echo ""
	@echo "$(YELLOW)=== Resource Usage ===$(NC)"
	@make stats
	@echo ""
	@echo "$(YELLOW)=== Health Status ===$(NC)"
	@make health
	@echo ""
	@echo "$(YELLOW)=== Recent Errors ===$(NC)"
	@docker-compose logs --tail=50 | grep -i error | tail -10

fix-permissions: ## Исправить права доступа к файлам
	@echo "$(BLUE)🔧 Fixing file permissions...$(NC)"
	sudo chown -R $(USER):$(USER) .
	chmod +x scripts/*.sh
	@echo "$(GREEN)✅ Permissions fixed$(NC)"

# ========================================
# DEFAULT TARGET
# ========================================

.DEFAULT_GOAL := help
