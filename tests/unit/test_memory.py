"""
Tests for Memory Service (VersionedChatHistory)
"""

import pytest
import asyncio
import os

from memory.history import VersionedChatHistory, get_or_create_history, check_version_conflict
from langchain.schema import HumanMessage, AIMessage


class TestVersionedChatHistory:
    """Test versioned chat history"""
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("POSTGRES_URL"),
        reason="POSTGRES_URL not set"
    )
    async def test_create_history(self):
        """Test: Create history instance"""
        history = VersionedChatHistory(
            session_id="test_create_123",
            prompt_version="v1"
        )
        
        assert history.session_id == "test_create_123"
        assert history.prompt_version == "v1"
        assert history.window_size == 40
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("POSTGRES_URL"),
        reason="POSTGRES_URL not set"
    )
    async def test_add_and_get_messages(self):
        """Test: Add messages and retrieve them"""
        history = VersionedChatHistory(
            session_id="test_add_get_123",
            prompt_version="v1"
        )
        
        # Clear first
        await history.aclear()
        
        # Add messages
        await history.aadd_user_message("Привет")
        await history.aadd_ai_message("Здравствуйте!")
        await history.aadd_user_message("Как дела?")
        # Get messages
    messages = await history.aget_messages()
    
    assert len(messages) == 3
    assert messages[0].content == "Привет"
    assert messages[1].content == "Здравствуйте!"
    assert messages[2].content == "Как дела?"
    
    # Cleanup
    await history.aclear()
    await history.close()

@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("POSTGRES_URL"),
    reason="POSTGRES_URL not set"
)
async def test_prompt_version_change_clears_history(self):
    """Test: Changing prompt version clears history"""
    session_id = "test_version_change_123"
    
    # Create with v1
    history_v1 = VersionedChatHistory(
        session_id=session_id,
        prompt_version="v1"
    )
    
    await history_v1.aclear()  # Start clean
    await history_v1.aadd_user_message("Message in v1")
    
    messages_v1 = await history_v1.aget_messages()
    assert len(messages_v1) == 1
    await history_v1.close()
    
    # Create with v2 (should clear history)
    history_v2 = VersionedChatHistory(
        session_id=session_id,
        prompt_version="v2"
    )
    
    messages_v2 = await history_v2.aget_messages()
    assert len(messages_v2) == 0  # History cleared!
    
    # Cleanup
    await history_v2.aclear()
    await history_v2.close()

@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("POSTGRES_URL"),
    reason="POSTGRES_URL not set"
)
async def test_sliding_window(self):
    """Test: Sliding window maintains max size"""
    history = VersionedChatHistory(
        session_id="test_sliding_123",
        prompt_version="v1",
        window_size=5  # Small window for testing
    )
    
    await history.aclear()
    
    # Add 10 messages
    for i in range(10):
        await history.aadd_user_message(f"Message {i}")
    
    messages = await history.aget_messages()
    
    # Should only have last 5
    assert len(messages) == 5
    assert messages[0].content == "Message 5"
    assert messages[4].content == "Message 9"
    
    # Cleanup
    await history.aclear()
    await history.close()

@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("POSTGRES_URL"),
    reason="POSTGRES_URL not set"
)
async def test_clear_history(self):
    """Test: Clear removes all messages"""
    history = VersionedChatHistory(
        session_id="test_clear_123",
        prompt_version="v1"
    )
    
    await history.aadd_user_message("Test message")
    messages_before = await history.aget_messages()
    assert len(messages_before) > 0
    
    await history.aclear()
    messages_after = await history.aget_messages()
    assert len(messages_after) == 0
    
    await history.close()

@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("POSTGRES_URL"),
    reason="POSTGRES_URL not set"
)
async def test_helper_get_or_create_history(self):
    """Test: Helper function works"""
    history = await get_or_create_history("test_helper_123", "v1")
    
    assert history is not None
    assert history.session_id == "test_helper_123"
    assert history.prompt_version == "v1"
    
    await history.close()

@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("POSTGRES_URL"),
    reason="POSTGRES_URL not set"
)
async def test_check_version_conflict(self):
    """Test: Version conflict detection"""
    session_id = "test_conflict_123"
    
    # Create with v1
    history = VersionedChatHistory(session_id=session_id, prompt_version="v1")
    await history.aclear()
    await history.aadd_user_message("test")
    await history.close()
    
    # Check for conflict with v2
    conflict, actual = await check_version_conflict(session_id, "v2")
    
    assert conflict == True
    assert actual == "v1"
    
    # Check for conflict with v1 (same version)
    conflict, actual = await check_version_conflict(session_id, "v1")
    
    assert conflict == False
    assert actual == "v1"

========================================

RUN TESTS

========================================


if name == "main":

    import sys
sys.exit(pytest.main([file, "-v", "-s"]))
