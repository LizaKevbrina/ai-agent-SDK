"""
Versioned Chat History - OPTIMIZED VERSION
Migrated from: services/memory/main.py

CRITICAL FIX:
✅ Now uses shared DB pool (injected from agent/main.py)
✅ Prevents connection exhaustion (1000 → 50 connections)
"""

from langchain.memory.chat_message_histories import BaseChatMessageHistory
from langchain.schema import BaseMessage, HumanMessage, AIMessage, SystemMessage
from typing import List, Optional
import asyncpg
import logging
from datetime import datetime

from config.settings import settings

logger = logging.getLogger(__name__)


class VersionedChatHistory(BaseChatMessageHistory):
    """
    Chat history with prompt version control.
    
    Key Features:
    - Pessimistic locking (FOR UPDATE) to prevent race conditions
    - Automatic history clearing when prompt version changes
    - Sliding window (40 messages max)
    - PostgreSQL storage for persistence
    
    ✅ CRITICAL FIX: Now uses shared pool (injected dependency)
    
    Usage:
        # From agent/main.py:
        history = VersionedChatHistory(
            session_id="user_123",
            prompt_version="v1",
            pool=db_pool  # ✅ Inject shared pool
        )
    """
    
    def __init__(
        self,
        session_id: str,
        prompt_version: str = "v1",
        pool: Optional[asyncpg.Pool] = None,  # ✅ NEW: Injected pool
        connection_string: str = None,
        window_size: int = None
    ):
        self.session_id = session_id
        self.prompt_version = prompt_version
        self.window_size = window_size or settings.MEMORY_WINDOW_SIZE
        
        # ✅ CRITICAL FIX: Use injected pool
        if pool is not None:
            self._pool = pool
            self._owns_pool = False  # Don't close shared pool
            logger.debug(f"Using shared pool for session {session_id}")
        else:
            # Fallback: create own pool (for testing/standalone usage)
            self.connection_string = connection_string or settings.POSTGRES_URL
            self._pool = None
            self._owns_pool = True
            logger.warning(
                f"No pool injected for session {session_id}. "
                f"Will create own pool (not recommended for production)"
            )
        
        self._initialized = False
    
    async def _ensure_pool(self) -> asyncpg.Pool:
        """
        Ensure connection pool is initialized
        
        ✅ UPDATED: Only creates pool if not injected
        """
        if self._pool is None and self._owns_pool:
            self._pool = await asyncpg.create_pool(
                self.connection_string,
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            logger.debug(f"Created own pool for session {self.session_id}")
        
        return self._pool
    
    async def _initialize_version(self):
        """
        Initialize or check prompt version with pessimistic locking.
        
        This is the CORE feature from original Memory Service:
        - Uses FOR UPDATE to lock row during transaction
        - Clears history if version changed
        - Creates new version record if doesn't exist
        """
        if self._initialized:
            return
        
        pool = await self._ensure_pool()
        
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Pessimistic lock: SELECT ... FOR UPDATE
                row = await conn.fetchrow(
                    """
                    SELECT version FROM prompt_versions
                    WHERE session_id = $1
                    FOR UPDATE
                    """,
                    self.session_id
                )
                
                stored_version = row['version'] if row else None
                
                # Version changed → clear history
                if stored_version is not None and stored_version != self.prompt_version:
                    logger.info(
                        f"Prompt version changed for {self.session_id}: "
                        f"{stored_version} → {self.prompt_version}. Clearing history."
                    )
                    
                    # Clear old messages
                    await conn.execute(
                        "DELETE FROM chat_memory WHERE session_id = $1",
                        self.session_id
                    )
                    
                    # Update version
                    await conn.execute(
                        """
                        UPDATE prompt_versions
                        SET version = $2, updated_at = NOW()
                        WHERE session_id = $1
                        """,
                        self.session_id, self.prompt_version
                    )
                
                # No version record → create it
                elif stored_version is None:
                    await conn.execute(
                        """
                        INSERT INTO prompt_versions (session_id, version, updated_at)
                        VALUES ($1, $2, NOW())
                        ON CONFLICT (session_id) DO UPDATE
                        SET version = $2, updated_at = NOW()
                        """,
                        self.session_id, self.prompt_version
                    )
                    
                    logger.debug(f"Created version record: {self.session_id} → {self.prompt_version}")
        
        self._initialized = True
    
    # ========================================
    # LANGCHAIN INTERFACE (REQUIRED)
    # ========================================
    
    @property
    def messages(self) -> List[BaseMessage]:
        """
        Get chat history (last N messages based on window_size).
        
        Returns messages in chronological order (oldest first).
        Implements sliding window: only last `window_size` messages.
        """
        import asyncio
        
        loop = asyncio.get_event_loop()
        if loop.is_running():
            raise RuntimeError(
                "Cannot call .messages property from async context. "
                "Use await get_messages() instead."
            )
        
        return loop.run_until_complete(self.aget_messages())
    
    async def aget_messages(self) -> List[BaseMessage]:
        """Get chat history (async version)"""
        await self._initialize_version()
        
        pool = await self._ensure_pool()
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT role, content, created_at
                FROM chat_memory
                WHERE session_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                self.session_id,
                self.window_size
            )
            
            # Reverse to get chronological order
            messages = []
            for row in reversed(rows):
                role = row['role']
                content = row['content']
                
                if role == 'user':
                    messages.append(HumanMessage(content=content))
                elif role == 'assistant':
                    messages.append(AIMessage(content=content))
                elif role == 'system':
                    messages.append(SystemMessage(content=content))
                else:
                    logger.warning(f"Unknown role: {role}")
                    messages.append(HumanMessage(content=content))
            
            logger.debug(
                f"Retrieved {len(messages)} messages for {self.session_id} "
                f"(version: {self.prompt_version})"
            )
            
            return messages
    
    def add_message(self, message: BaseMessage) -> None:
        """Add a message to chat history"""
        import asyncio
        
        loop = asyncio.get_event_loop()
        if loop.is_running():
            raise RuntimeError(
                "Cannot call add_message from async context. "
                "Use await aadd_message() instead."
            )
        
        loop.run_until_complete(self.aadd_message(message))
    
    async def aadd_message(self, message: BaseMessage) -> None:
        """Add a message to chat history (async version)"""
        await self._initialize_version()
        
        # Determine role
        if isinstance(message, HumanMessage):
            role = 'user'
        elif isinstance(message, AIMessage):
            role = 'assistant'
        elif isinstance(message, SystemMessage):
            role = 'system'
        else:
            role = 'user'
            logger.warning(f"Unknown message type: {type(message)}, using 'user'")
        
        pool = await self._ensure_pool()
        
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Insert message
                await conn.execute(
                    """
                    INSERT INTO chat_memory (session_id, role, content, created_at)
                    VALUES ($1, $2, $3, NOW())
                    """,
                    self.session_id, role, message.content
                )
                
                # Maintain sliding window: delete old messages
                await conn.execute(
                    """
                    DELETE FROM chat_memory
                    WHERE session_id = $1
                    AND created_at < (
                        SELECT created_at FROM chat_memory
                        WHERE session_id = $1
                        ORDER BY created_at DESC
                        LIMIT 1 OFFSET $2
                    )
                    """,
                    self.session_id,
                    self.window_size
                )
        
        logger.debug(
            f"Added {role} message to {self.session_id}: "
            f"{message.content[:50]}..."
        )
    
    def add_user_message(self, message: str) -> None:
        """Add user message (convenience method)"""
        self.add_message(HumanMessage(content=message))
    
    def add_ai_message(self, message: str) -> None:
        """Add AI message (convenience method)"""
        self.add_message(AIMessage(content=message))
    
    async def aadd_user_message(self, message: str) -> None:
        """Add user message (async)"""
        await self.aadd_message(HumanMessage(content=message))
    
    async def aadd_ai_message(self, message: str) -> None:
        """Add AI message (async)"""
        await self.aadd_message(AIMessage(content=message))
    
    def clear(self) -> None:
        """Clear all messages for this session"""
        import asyncio
        
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.aclear())
    
    async def aclear(self) -> None:
        """Clear all messages (async)"""
        pool = await self._ensure_pool()
        
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM chat_memory WHERE session_id = $1",
                self.session_id
            )
        
        logger.info(f"Cleared history for {self.session_id}")
    
    async def close(self):
        """
        Close connection pool
        
        ✅ UPDATED: Only closes if we own the pool
        """
        if self._pool and self._owns_pool:
            await self._pool.close()
            self._pool = None
            logger.debug("Own pool closed")
        else:
            logger.debug("Skipping pool close (shared pool)")


# ========================================
# HELPER FUNCTIONS (UPDATED)
# ========================================

async def get_or_create_history(
    session_id: str,
    prompt_version: str = "v1",
    pool: Optional[asyncpg.Pool] = None  # ✅ NEW: Accept pool
) -> VersionedChatHistory:
    """
    Get or create chat history for a session.
    
    ✅ UPDATED: Accepts shared pool
    
    Usage:
        # From agent/main.py:
        history = await get_or_create_history("user_123", "v1", db_pool)
    """
    history = VersionedChatHistory(
        session_id=session_id,
        prompt_version=prompt_version,
        pool=pool  # ✅ Pass pool
    )
    
    await history._initialize_version()
    
    return history


async def check_version_conflict(
    session_id: str,
    expected_version: str,
    pool: Optional[asyncpg.Pool] = None  # ✅ NEW: Accept pool
) -> tuple[bool, Optional[str]]:
    """
    Check if prompt version matches expected version.
    
    ✅ UPDATED: Accepts shared pool
    
    Returns:
        (conflict_detected, actual_version)
    """
    if pool:
        _pool = pool
        close_pool = False
    else:
        _pool = await asyncpg.create_pool(settings.POSTGRES_URL, min_size=1, max_size=2)
        close_pool = True
    
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT version FROM prompt_versions WHERE session_id = $1",
                session_id
            )
            
            if not row:
                return False, None
            
            actual_version = row['version']
            conflict = actual_version != expected_version
            
            return conflict, actual_version
    
    finally:
        if close_pool:
            await _pool.close()
