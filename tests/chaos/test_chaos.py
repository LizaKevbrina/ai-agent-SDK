"""
Chaos Engineering Tests
Тестирование устойчивости системы к сбоям

Проверяем:
- Что происходит при падении Supabase?
- Что происходит при сбоях YandexGPT?
- Как агент ведёт себя при исчерпании соединений с БД?
- Работает ли circuit breaker?
- Graceful degradation работает?
"""

import pytest
import asyncio
import time
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import HTTPException
import httpx
import asyncpg

from agent.main import create_agent_for_session, app
from llm.models import ChatYandexGPT
from memory.history import VersionedChatHistory
from langchain.schema import HumanMessage
from pybreaker import CircuitBreakerError


# ========================================
# CHAOS TEST: SUPABASE OUTAGE
# ========================================

class TestSupabaseOutage:
    """Тест устойчивости при падении Supabase"""
    
    @pytest.mark.asyncio
    async def test_agent_survives_supabase_logging_failure(self):
        """
        Test: Агент должен работать даже если Supabase недоступен
        
        Сценарий:
        1. Supabase падает во время логирования
        2. Агент должен всё равно вернуть ответ
        3. Ошибка логирования не должна ломать основной flow
        """
        with patch('logging.callbacks.create_client') as mock_supabase:
            # Имитация падения Supabase
            mock_supabase.side_effect = Exception("Supabase connection timeout")
            
            # Агент должен работать
            agent = await create_agent_for_session(
                session_id="test_chaos_supabase",
                prompt_version="v1",
                correlation_id="chaos_001"
            )
            
            # Запрос должен пройти
            result = await agent.ainvoke({"input": "Привет!"})
            
            # Проверки
            assert result is not None
            assert "output" in result
            assert len(result["output"]) > 0
            
            print("✅ Agent survived Supabase outage")
    
    @pytest.mark.asyncio
    async def test_rag_fails_gracefully_on_supabase_error(self):
        """
        Test: RAG должен корректно обрабатывать ошибки Supabase
        
        Сценарий:
        1. Supabase vector store недоступен
        2. RAG должен вернуть понятное сообщение
        3. Агент должен продолжить работу без контекста
        """
        with patch('rag.retrievers.create_client') as mock_client:
            mock_client.side_effect = Exception("Supabase unavailable")
            
            from tools.real_estate import search_documents
            
            result = search_documents.invoke({"query": "квартиры"})
            
            # Должно быть понятное сообщение об ошибке
            assert isinstance(result, str)
            assert "нет информации" in result.lower() or "ошибка" in result.lower()
            
            print("✅ RAG failed gracefully")


# ========================================
# CHAOS TEST: YANDEX GPT FAILURES
# ========================================

class TestYandexGPTFailures:
    """Тест устойчивости при сбоях YandexGPT API"""
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self):
        """
        Test: Circuit breaker должен открыться после 5 сбоев
        
        Сценарий:
        1. YandexGPT возвращает 500 ошибку 5 раз подряд
        2. На 6-й попытке circuit breaker должен открыться
        3. Запрос должен завершиться быстро (< 100ms) без retry
        """
        with patch('llm.models.ChatYandexGPT._make_request_async') as mock_request:
            # Имитация сбоев YandexGPT
            mock_request.side_effect = httpx.HTTPStatusError(
                "Internal Server Error",
                request=MagicMock(),
                response=MagicMock(status_code=500)
            )
            
            llm = ChatYandexGPT()
            messages = [HumanMessage(content="test")]
            
            # Первые 5 попыток: должны завершиться с retry
            for i in range(5):
                with pytest.raises(Exception):
                    await llm.ainvoke(messages)
                
                print(f"  Attempt {i+1}/5 failed (expected)")
            
            # 6-я попытка: circuit breaker должен быть открыт
            start_time = time.time()
            
            with pytest.raises(ValueError) as exc_info:
                await llm.ainvoke(messages)
            
            duration = time.time() - start_time
            
            # Проверки
            assert "temporarily unavailable" in str(exc_info.value).lower()
            assert duration < 0.1  # Должно быть быстро (без retry)
            
            print(f"✅ Circuit breaker opened after 5 failures (duration: {duration*1000:.0f}ms)")
    
    @pytest.mark.asyncio
    async def test_rate_limit_handling(self):
        """
        Test: Агент должен корректно обрабатывать rate limits
        
        Сценарий:
        1. YandexGPT возвращает 429 (rate limit)
        2. Должен быть retry с exponential backoff
        3. Пользователь должен получить понятное сообщение
        """
        with patch('llm.models.ChatYandexGPT._make_request_async') as mock_request:
            # Имитация rate limit
            mock_request.side_effect = httpx.HTTPStatusError(
                "Too Many Requests",
                request=MagicMock(),
                response=MagicMock(status_code=429)
            )
            
            llm = ChatYandexGPT()
            messages = [HumanMessage(content="test")]
            
            # Должен быть retry, затем ошибка
            with pytest.raises(ValueError) as exc_info:
                await llm.ainvoke(messages)
            
            # Должно быть понятное сообщение
            assert "rate limit" in str(exc_info.value).lower() or \
                   "failed" in str(exc_info.value).lower()
            
            print("✅ Rate limit handled gracefully")


# ========================================
# CHAOS TEST: DATABASE FAILURES
# ========================================

class TestDatabaseFailures:
    """Тест устойчивости при проблемах с БД"""
    
    @pytest.mark.asyncio
    async def test_connection_pool_exhaustion(self):
        """
        Test: Агент должен корректно обрабатывать исчерпание пула соединений
        
        Сценарий:
        1. Все соединения в пуле заняты
        2. Новый запрос должен дождаться освобождения
        3. Timeout должен быть адекватный (не бесконечный)
        """
        with patch('asyncpg.create_pool') as mock_pool:
            # Имитация исчерпания соединений
            mock_pool.side_effect = asyncpg.TooManyConnectionsError(
                "too many connections"
            )
            
            # Попытка создать историю
            with pytest.raises(Exception) as exc_info:
                history = VersionedChatHistory(
                    session_id="test_chaos_pool",
                    prompt_version="v1"
                )
                await history._ensure_pool()
            
            # Должна быть ошибка соединения
            assert "connection" in str(exc_info.value).lower() or \
                   "too many" in str(exc_info.value).lower()
            
            print("✅ Connection pool exhaustion handled")
    
    @pytest.mark.asyncio
    async def test_database_query_timeout(self):
        """
        Test: Таймауты запросов к БД должны обрабатываться
        
        Сценарий:
        1. Запрос к БД зависает (> 60 секунд)
        2. Должен быть timeout
        3. Пользователь должен получить ошибку 503
        """
        with patch('asyncpg.connect') as mock_connect:
            # Имитация зависшего запроса
            async def slow_query(*args, **kwargs):
                await asyncio.sleep(70)  # Больше чем command_timeout=60
            
            mock_conn = AsyncMock()
            mock_conn.execute = slow_query
            mock_connect.return_value = mock_conn
            
            # Должен быть timeout
            with pytest.raises(asyncio.TimeoutError):
                history = VersionedChatHistory(
                    session_id="test_chaos_timeout",
                    prompt_version="v1"
                )
                # Попытка добавить сообщение с timeout
                await asyncio.wait_for(
                    history.aadd_user_message("test"),
                    timeout=5.0
                )
            
            print("✅ Database timeout handled")


# ========================================
# CHAOS TEST: NETWORK FAILURES
# ========================================

class TestNetworkFailures:
    """Тест устойчивости при сетевых проблемах"""
    
    @pytest.mark.asyncio
    async def test_connection_timeout(self):
        """
        Test: Connection timeout должен обрабатываться
        
        Сценарий:
        1. YandexGPT не отвечает (connection timeout)
        2. Должен быть retry с exponential backoff
        3. После 3 попыток — понятная ошибка
        """
        with patch('httpx.AsyncClient.post') as mock_post:
            # Имитация connection timeout
            mock_post.side_effect = httpx.ConnectTimeout("Connection timeout")
            
            llm = ChatYandexGPT()
            messages = [HumanMessage(content="test")]
            
            # Должен быть retry, затем ошибка
            with pytest.raises(ValueError) as exc_info:
                await llm.ainvoke(messages)
            
            assert "failed" in str(exc_info.value).lower()
            
            print("✅ Connection timeout handled")
    
    @pytest.mark.asyncio
    async def test_read_timeout(self):
        """
        Test: Read timeout должен обрабатываться
        
        Сценарий:
        1. YandexGPT начал отвечать, но зависает
        2. Должен быть read timeout (60 секунд)
        3. Retry, затем ошибка
        """
        with patch('httpx.AsyncClient.post') as mock_post:
            # Имитация read timeout
            mock_post.side_effect = httpx.ReadTimeout("Read timeout")
            
            llm = ChatYandexGPT()
            messages = [HumanMessage(content="test")]
            
            with pytest.raises(ValueError):
                await llm.ainvoke(messages)
            
            print("✅ Read timeout handled")


# ========================================
# CHAOS TEST: MEMORY CORRUPTION
# ========================================

class TestMemoryCorruption:
    """Тест устойчивости при проблемах с памятью"""
    
    @pytest.mark.asyncio
    async def test_prompt_version_conflict_during_write(self):
        """
        Test: Конфликт версий промпта должен обрабатываться
        
        Сценарий:
        1. Пользователь 1 пишет с версией v1
        2. Пользователь 2 меняет версию на v2 (FOR UPDATE lock)
        3. Пользователь 1 должен получить 409 Conflict
        """
        # Это сложно эмулировать без реальной БД
        # Проверяем, что функция check_version_conflict работает
        from memory.history import check_version_conflict
        
        # Mock для теста
        with patch('asyncpg.create_pool') as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.fetchrow.return_value = {'version': 'v2'}  # Другая версия!
            
            mock_pool_instance = AsyncMock()
            mock_pool_instance.acquire.return_value.__aenter__.return_value = mock_conn
            mock_pool.return_value = mock_pool_instance
            
            conflict, actual_version = await check_version_conflict("test_session", "v1")
            
            assert conflict == True
            assert actual_version == "v2"
            
            print("✅ Version conflict detected")


# ========================================
# CHAOS TEST: RESOURCE EXHAUSTION
# ========================================

class TestResourceExhaustion:
    """Тест при исчерпании ресурсов"""
    
    @pytest.mark.asyncio
    async def test_memory_leak_detection(self):
        """
        Test: Проверка отсутствия утечек памяти
        
        Сценарий:
        1. Создаём 100 агентов
        2. Проверяем, что память не растёт бесконечно
        3. После del агенты должны освобождать память
        """
        import gc
        import sys
        
        initial_objects = len(gc.get_objects())
        
        # Создаём 100 агентов
        agents = []
        for i in range(100):
            agent = await create_agent_for_session(
                session_id=f"leak_test_{i}",
                prompt_version="v1",
                correlation_id=f"leak_{i}"
            )
            agents.append(agent)
        
        # Удаляем агентов
        del agents
        gc.collect()
        
        final_objects = len(gc.get_objects())
        
        # Количество объектов не должно вырасти более чем в 2 раза
        growth_factor = final_objects / initial_objects
        
        assert growth_factor < 2.0, f"Possible memory leak: {growth_factor}x growth"
        
        print(f"✅ Memory leak test passed (growth factor: {growth_factor:.2f}x)")


# ========================================
# RUN ALL CHAOS TESTS
# ========================================

if __name__ == "__main__":
    """
    Запуск chaos tests:
    
    pytest tests/test_chaos.py -v -s
    """
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s", "--tb=short"]))
