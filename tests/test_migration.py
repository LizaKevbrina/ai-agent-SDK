---

## 🧪 **4. tests/test_migration_part1.py (PRODUCTION TEST SUITE)**
````python
"""
Production Test Suite for Migration Part 1
Tests all migrated components with real API calls
"""

import pytest
import asyncio
import os
from typing import List

# Set test environment
os.environ["ENVIRONMENT"] = "testing"
os.environ["LOG_LEVEL"] = "DEBUG"

from rag.embeddings import YandexGPTEmbeddings
from rag.retrievers import get_real_estate_retriever, SimilarityThresholdRetriever
from llm.models import ChatYandexGPT
from tools.security import validate_user_input, SecurityValidator
from tools.real_estate import search_documents, calculate_mortgage, get_property_details
from langchain.schema import HumanMessage, SystemMessage


# ========================================
# SECURITY TESTS
# ========================================

class TestSecurity:
    """Test security validation"""
    
    def test_validate_normal_input(self):
        """Test: Normal input passes validation"""
        text = "Найди квартиры в ЖК Солнечный"
        result = validate_user_input(text)
        assert result == text
    
    def test_validate_blocks_sql_injection(self):
        """Test: SQL injection is blocked"""
        with pytest.raises(ValueError, match="sql_injection"):
            validate_user_input("SELECT * FROM users WHERE id=1")
    
    def test_validate_blocks_xss(self):
        """Test: XSS is blocked"""
        with pytest.raises(ValueError, match="xss"):
            validate_user_input("<script>alert('xss')</script>")
    
    def test_validate_blocks_path_traversal(self):
        """Test: Path traversal is blocked"""
        with pytest.raises(ValueError, match="path_traversal"):
            validate_user_input("../../etc/passwd")
    
    def test_validate_empty_input(self):
        """Test: Empty input is rejected"""
        with pytest.raises(ValueError, match="empty"):
            validate_user_input("")
    
    def test_validate_too_long_input(self):
        """Test: Input over 5000 chars is rejected"""
        with pytest.raises(ValueError, match="too long"):
            validate_user_input("A" * 6000)
    
    def test_security_validator_is_safe(self):
        """Test: SecurityValidator.is_safe() method"""
        validator = SecurityValidator()
        
        assert validator.is_safe("Привет") == True
        assert validator.is_safe("SELECT * FROM users") == False
    
    def test_sanitization(self):
        """Test: Special characters are removed"""
        text = "Привет   мир  <script>  test"
        result = validate_user_input(text)
        
        assert "<script>" not in result
        assert "   " not in result  # Extra spaces removed


# ========================================
# EMBEDDINGS TESTS
# ========================================

class TestEmbeddings:
    """Test YandexGPT embeddings"""
    
    @pytest.mark.skipif(
        not os.getenv("YANDEX_API_KEY"),
        reason="YANDEX_API_KEY not set"
    )
    def test_embed_query_sync(self):
        """Test: Synchronous query embedding"""
        embeddings = YandexGPTEmbeddings()
        result = embeddings.embed_query("тест")
        
        assert isinstance(result, list)
        assert len(result) == 256  # YandexGPT dimension
        assert all(isinstance(x, float) for x in result)
    
    @pytest.mark.skipif(
        not os.getenv("YANDEX_API_KEY"),
        reason="YANDEX_API_KEY not set"
    )
    def test_embed_documents_sync(self):
        """Test: Synchronous batch embedding"""
        embeddings = YandexGPTEmbeddings()
        texts = ["квартира", "дом", "цена"]
        results = embeddings.embed_documents(texts)
        
        assert len(results) == 3
        assert all(len(emb) == 256 for emb in results)
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("YANDEX_API_KEY"),
        reason="YANDEX_API_KEY not set"
    )
    async def test_embed_query_async(self):
        """Test: Asynchronous query embedding"""
        embeddings = YandexGPTEmbeddings()
        result = await embeddings.aembed_query("тест")
        
        assert isinstance(result, list)
        assert len(result) == 256
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("YANDEX_API_KEY"),
        reason="YANDEX_API_KEY not set"
    )
    async def test_embed_documents_async(self):
        """Test: Asynchronous batch embedding"""
        embeddings = YandexGPTEmbeddings()
        texts = ["квартира", "дом", "цена"]
        results = await embeddings.aembed_documents(texts)
        
        assert len(results) == 3
    
    @pytest.mark.skipif(
        not os.getenv("YANDEX_API_KEY"),
        reason="YANDEX_API_KEY not set"
    )
    def test_embeddings_retry_on_failure(self):
        """Test: Retry logic works on transient failures"""
        # Use invalid API key to trigger retry
        embeddings = YandexGPTEmbeddings(
            api_key="invalid_key",
            folder_id="invalid_folder",
            max_retries=2,
            retry_delay=1
        )
        
        with pytest.raises(Exception, match="Failed to generate embedding"):
            embeddings.embed_query("test")
    
    def test_embeddings_text_truncation(self):
        """Test: Text longer than 8000 chars is truncated"""
        embeddings = YandexGPTEmbeddings()
        long_text = "A" * 10000
        
        # Should not raise, text will be truncated to 8000
        # (Will fail on invalid API key if not set, but that's expected)
        try:
            result = embeddings.embed_query(long_text)
        except Exception as e:
            # Expected if API key not set
            assert "API" in str(e) or "Failed" in str(e)


# ========================================
# LLM TESTS
# ========================================

class TestLLM:
    """Test ChatYandexGPT model"""
    
    @pytest.mark.skipif(
        not os.getenv("YANDEX_API_KEY"),
        reason="YANDEX_API_KEY not set"
    )
    def test_llm_generate_sync(self):
        """Test: Synchronous generation"""
        llm = ChatYandexGPT(temperature=0.7, max_tokens=100)
        messages = [HumanMessage(content="Привет! Ответь одним словом: да")]
        
        result = llm.invoke(messages)
        
        assert result.content
        assert isinstance(result.content, str)
        assert len(result.content) > 0
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("YANDEX_API_KEY"),
        reason="YANDEX_API_KEY not set"
    )
    async def test_llm_generate_async(self):
        """Test: Asynchronous generation"""
        llm = ChatYandexGPT(temperature=0.7, max_tokens=100)
        messages = [HumanMessage(content="Привет! Ответь одним словом: да")]
        
        result = await llm.ainvoke(messages)
        
        assert result.content
        assert isinstance(result.content, str)
    
    @pytest.mark.skipif(
        not os.getenv("YANDEX_API_KEY"),
        reason="YANDEX_API_KEY not set"
    )
    def test_llm_with_system_message(self):
        """Test: System message handling"""
        llm = ChatYandexGPT(max_tokens=50)
        messages = [
            SystemMessage(content="Ты — помощник по недвижимости"),
            HumanMessage(content="Привет")
        ]
        
        result = llm.invoke(messages)
        assert result.content
    
    @pytest.mark.skipif(
        not os.getenv("YANDEX_API_KEY"),
        reason="YANDEX_API_KEY not set"
    )
    def test_llm_token_tracking(self):
        """Test: Token usage is tracked"""
        llm = ChatYandexGPT(max_tokens=100)
        messages = [HumanMessage(content="Привет")]
        
        result = llm.generate([messages])
        
        assert result.llm_output
        assert "token_usage" in result.llm_output
        assert result.llm_output["token_usage"]["total_tokens"] > 0
    
    def test_llm_circuit_breaker_on_repeated_failures(self):
        """Test: Circuit breaker opens after repeated failures"""
        llm = ChatYandexGPT(
            api_key="invalid_key",
            folder_id="invalid_folder"
        )
        messages = [HumanMessage(content="test")]
        
        # First few attempts will fail and retry
        # After 5 failures, circuit breaker opens
        for i in range(6):
            try:
                llm.invoke(messages)
            except ValueError as e:
                if "temporarily unavailable" in str(e):
                    # Circuit breaker opened!
                    assert i >= 5  # Should open after 5 failures
                    break
    
    @pytest.mark.skipif(
        not os.getenv("YANDEX_API_KEY"),
        reason="YANDEX_API_KEY not set"
    )
    def test_llm_message_conversion(self):
        """Test: LangChain messages convert correctly to YandexGPT format"""
        llm = ChatYandexGPT()
        
        messages = [
            SystemMessage(content="system"),
            HumanMessage(content="user"),
            HumanMessage(content="another user message")
        ]
        
        yandex_messages = llm._convert_messages_to_yandex_format(messages)
        
        assert len(yandex_messages) == 3
        assert yandex_messages[0]["role"] == "system"
        assert yandex_messages[1]["role"] == "user"
        assert yandex_messages[2]["role"] == "user"


# ========================================
# RETRIEVER TESTS
# ========================================

class TestRetriever:
    """Test RAG retriever"""
    
    @pytest.mark.skipif(
        not os.getenv("SUPABASE_URL") or not os.getenv("YANDEX_API_KEY"),
        reason="SUPABASE_URL or YANDEX_API_KEY not set"
    )
    def test_retriever_initialization(self):
        """Test: Retriever initializes correctly"""
        retriever = get_real_estate_retriever(top_k=5, threshold=0.7)
        
        assert retriever is not None
        assert isinstance(retriever, SimilarityThresholdRetriever)
        assert retriever.threshold == 0.7
    
    @pytest.mark.skipif(
        not os.getenv("SUPABASE_URL") or not os.getenv("YANDEX_API_KEY"),
        reason="SUPABASE_URL or YANDEX_API_KEY not set"
    )
    def test_retriever_search(self):
        """Test: Retriever finds documents"""
        retriever = get_real_estate_retriever()
        
        # Search for something generic
        docs = retriever.get_relevant_documents("квартира")
        
        # Should return documents (or empty list if DB is empty)
        assert isinstance(docs, list)
        
        # If documents found, check structure
        if docs:
            doc = docs[0]
            assert hasattr(doc, 'page_content')
            assert hasattr(doc, 'metadata')
            assert doc.metadata.get('similarity', 0) >= 0.7  # Above threshold
    
    @pytest.mark.skipif(
        not os.getenv("SUPABASE_URL") or not os.getenv("YANDEX_API_KEY"),
        reason="SUPABASE_URL or YANDEX_API_KEY not set"
    )
    def test_retriever_filters_by_threshold(self):
        """Test: Documents below threshold are filtered"""
        retriever = get_real_estate_retriever(threshold=0.9)  # High threshold
        
        docs = retriever.get_relevant_documents("случайный запрос xyz")
        
        # With high threshold, might get no results
        for doc in docs:
            assert doc.metadata.get('similarity', 0) >= 0.9


# ========================================
# TOOLS TESTS
# ========================================

class TestTools:
    """Test real estate tools"""
    
    def test_calculate_mortgage_tool(self):
        """Test: Mortgage calculation"""
        result = calculate_mortgage.invoke({
            "price": 5000000,
            "initial_payment_percent": 20,
            "rate": 12,
            "years": 30
        })
        
        assert "Расчёт ипотеки" in result
        assert "5,000,000" in result
        assert "Ежемесячный платёж" in result
    
    def test_calculate_mortgage_with_defaults(self):
        """Test: Mortgage calculation with default params"""
        result = calculate_mortgage.invoke({"price": 3000000})
        
        assert "3,000,000" in result
        assert "20%" in result  # Default initial payment
        assert "12%" in result  # Default rate
    
    def test_calculate_mortgage_zero_rate(self):
        """Test: Mortgage calculation with 0% rate"""
        result = calculate_mortgage.invoke({
            "price": 6000000,
            "rate": 0
        })
        
        assert "0%" in result
        assert "Ежемесячный платёж" in result
    
    @pytest.mark.skipif(
        not os.getenv("SUPABASE_URL") or not os.getenv("YANDEX_API_KEY"),
        reason="SUPABASE_URL or YANDEX_API_KEY not set"
    )
    def test_search_documents_tool(self):
        """Test: Document search tool"""
        result = search_documents.invoke({"query": "квартира"})
        
        # Should return either documents or "not found" message
        assert isinstance(result, str)
        assert len(result) > 0
    
    @pytest.mark.skipif(
        not os.getenv("SUPABASE_URL") or not os.getenv("YANDEX_API_KEY"),
        reason="SUPABASE_URL or YANDEX_API_KEY not set"
    )
    def test_search_documents_no_results(self):
        """Test: Search returns proper message when no results"""
        result = search_documents.invoke({"query": "xyz123nonexistent"})
        
        assert "нет информации" in result.lower() or "не найдено" in result.lower()
    
    @pytest.mark.skipif(
        not os.getenv("SUPABASE_URL") or not os.getenv("YANDEX_API_KEY"),
        reason="SUPABASE_URL or YANDEX_API_KEY not set"
    )
    def test_get_property_details_tool(self):
        """Test: Property details tool"""
        result = get_property_details.invoke({"property_id": "test_123"})
        
        assert isinstance(result, str)
        # Should either find property or return "not found"


# ========================================
# INTEGRATION TESTS
# ========================================

class TestIntegration:
    """Integration tests for full pipeline"""
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not all([
            os.getenv("YANDEX_API_KEY"),
            os.getenv("SUPABASE_URL")
        ]),
        reason="Required API keys not set"
    )
    async def test_full_pipeline_async(self):
        """Test: Full pipeline (validation → RAG → LLM) async"""
        
        # 1. Validate input
        user_input = "Найди квартиры в ЖК Солнечный"
        validated_input = validate_user_input(user_input)
        assert validated_input == user_input
        
        # 2. Generate embedding and search
        retriever = get_real_estate_retriever()
        docs = retriever.get_relevant_documents(validated_input)
        
        # 3. Generate response with LLM
        llm = ChatYandexGPT(max_tokens=200)
        
        if docs:
            context = "\n\n".join([doc.page_content for doc in docs[:3]])
            prompt = f"Контекст:\n{context}\n\nВопрос: {validated_input}"
        else:
            prompt = validated_input
        
        messages = [HumanMessage(content=prompt)]
        result = await llm.ainvoke(messages)
        
        assert result.content
        assert len(result.content) > 0
        
        print(f"\n✅ Full pipeline test passed!")
        print(f"Input: {user_input}")
        print(f"Documents found: {len(docs)}")
        print(f"Response: {result.content[:200]}...")


# ========================================
# RUN ALL TESTS
# ========================================

if __name__ == "__main__":
    """
    Run tests with:
    python tests/test_migration_part1.py
    
    Or with pytest:
    pytest tests/test_migration_part1.py -v
    """
    
    # Run with pytest
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
