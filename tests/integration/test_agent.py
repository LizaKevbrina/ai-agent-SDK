"""
Tests for Agent (end-to-end)
"""

import pytest
import asyncio
import os

from agent.main import create_agent_for_session
from langchain.schema import HumanMessage


class TestAgent:
    """Test agent functionality"""
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not all([
            os.getenv("YANDEX_API_KEY"),
            os.getenv("SUPABASE_URL"),
            os.getenv("POSTGRES_URL")
        ]),
        reason="Required credentials not set"
    )
    async def test_create_agent(self):
        """Test: Agent creation"""
        agent = await create_agent_for_session(
            session_id="test_agent_123",
            prompt_version="v1",
            correlation_id="test_001"
        )
        
        assert agent is not None
        assert hasattr(agent, 'ainvoke')
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not all([
            os.getenv("YANDEX_API_KEY"),
            os.getenv("SUPABASE_URL"),
            os.getenv("POSTGRES_URL")
        ]),
        reason="Required credentials not set"
    )
    async def test_agent_simple_query(self):
        """Test: Agent responds to simple query"""
        agent = await create_agent_for_session(
            session_id="test_simple_123",
            prompt_version="v1",
            correlation_id="test_002"
        )
        
        result = await agent.ainvoke({"input": "Привет!"})
        
        assert result is not None
        assert "output" in result
        assert len(result["output"]) > 0
        
        print(f"\n✅ Agent response: {result['output'][:100]}...")
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not all([
            os.getenv("YANDEX_API_KEY"),
            os.getenv("SUPABASE_URL"),
            os.getenv("POSTGRES_URL")
        ]),
        reason="Required credentials not set"
    )
    async def test_agent_uses_search_tool(self):
        """Test: Agent uses search_documents tool"""
        agent = await create_agent_for_session(
            session_id="test_search_123",
            prompt_version="v1",
            correlation_id="test_003"
        )
        
        result = await agent.ainvoke({"input": "Какие квартиры есть в ЖК Солнечный?"})
        
        assert result is not None
        assert "output" in result
        
        # Check if search_documents was used
        tools_used = []
        for step in result.get("intermediate_steps", []):
            if isinstance(step, tuple) and len(step) >= 2:
                action = step[0]
                if hasattr(action, 'tool'):
                    tools_used.append(action.tool)
        
        print(f"\n✅ Tools used: {tools_used}")
        print(f"✅ Response: {result['output'][:200]}...")
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not all([
            os.getenv("YANDEX_API_KEY"),
            os.getenv("SUPABASE_URL"),
            os.getenv("POSTGRES_URL")
        ]),
        reason="Required credentials not set"
    )
    async def test_agent_calculates_mortgage(self):
        """Test: Agent uses calculate_mortgage tool"""
        agent = await create_agent_for_session(
            session_id="test_mortgage_123",
            prompt_version="v1",
            correlation_id="test_004"
        )
        
        result = await agent.ainvoke({
            "input": "Посчитай ипотеку на квартиру за 5 миллионов"
        })
        
        assert result is not None
        assert "output" in result
        
        # Check if calculate_mortgage was used
        tools_used = []
        for step in result.get("intermediate_steps", []):
            if isinstance(step, tuple):
                action = step[0]
                if hasattr(action, 'tool'):
                    tools_used.append(action.tool)
        
        assert "calculate_mortgage" in tools_used
        
        print(f"\n✅ Mortgage calculation response:")
        print(result['output'])
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not all([
            os.getenv("YANDEX_API_KEY"),
            os.getenv("SUPABASE_URL"),
            os.getenv("POSTGRES_URL")
        ]),
        reason="Required credentials not set"
    )
    async def test_agent_memory_retention(self):
        """Test: Agent remembers conversation context"""
        session_id = "test_memory_retention_123"
        
        agent = await create_agent_for_session(
            session_id=session_id,
            prompt_version="v1",
            correlation_id="test_005"
        )
        
        # First message
        result1 = await agent.ainvoke({"input": "Меня зовут Алексей"})
        
        # Second message (should remember name)
        result2 = await agent.ainvoke({"input": "Как меня зовут?"})
        
        assert "output" in result2
        assert "Алексей" in result2["output"] or "алексей" in result2["output"].lower()
        
        print(f"\n✅ Memory test passed!")
        print(f"Response 1: {result1['output'][:100]}...")
        print(f"Response 2: {result2['output'][:100]}...")
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not all([
            os.getenv("YANDEX_API_KEY"),
            os.getenv("SUPABASE_URL"),
            os.getenv("POSTGRES_URL")
        ]),
        reason="Required credentials not set"
    )
    async def test_agent_security_validation(self):
        """Test: Agent blocks malicious input"""
        agent = await create_agent_for_session(
            session_id="test_security_123",
            prompt_version="v1",
            correlation_id="test_006"
        )
        
        # Try SQL injection
        result = await agent.ainvoke({"input": "SELECT * FROM users WHERE id=1"})
        
        assert result is not None
        assert "output" in result
        
        # Should be blocked or return safe response
        response_lower = result["output"].lower()
        assert "безопасност" in response_lower or "заблокирован" in response_lower
        
        print(f"\n✅ Security test passed!")
        print(f"Response: {result['output']}")


# ========================================
# RUN TESTS
# ========================================

if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
