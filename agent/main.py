"""
AI Agent Main Application - IMPROVED VERSION
FastAPI app with LangChain agent

IMPROVEMENTS:
✅ Simplified imports (cleaner structure)
✅ Simplified startup/shutdown (less verbose)
✅ Separate _track_business_metrics() function
✅ Compact extract_tools_and_context helper
✅ All original features preserved
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
import re
from datetime import datetime
from typing import List, Optional, Dict, Any

import asyncpg
import redis as redis_lib
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import Response
from pydantic import BaseModel
from prometheus_client import generate_latest
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# LangChain
from langchain.agents import create_openai_functions_agent, AgentExecutor
from langchain.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import SystemMessage, HumanMessage
from langchain.memory import ConversationBufferMemory
from langchain.cache import RedisCache
from langchain.globals import set_llm_cache

# Project modules
from config.settings import settings
from config.prompts import get_prompt
from tools.real_estate import get_tools
from tools.security import SecurityValidator
from llm.models import ChatYandexGPT
from memory.history import VersionedChatHistory
from logging.callbacks import SupabaseLoggingCallback, log_error_manually
from agent.executor import create_secure_executor
from agent.metrics import (
    track_agent_request,
    track_token_usage,
    agent_requests_total,
    funnel_step_reached,
    user_intent_distribution,
    conversation_turns,
    successful_closings
)

# ========================================
# SETUP
# ========================================

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="LangChain-based AI agent for real estate assistance"
)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Global resources
db_pool: Optional[asyncpg.Pool] = None
redis_client: Optional[redis_lib.Redis] = None

# ========================================
# MODELS
# ========================================

class ChatRequest(BaseModel):
    message: str
    session_id: str
    prompt_version: str = "v1"
    input_type: str = "text"
    use_openai: bool = False


class ChatResponse(BaseModel):
    response: str
    session_id: str
    tools_used: List[str]
    tokens_used: int
    response_time_ms: float
    context_used: bool
    documents_found: int
    timestamp: str
    correlation_id: str
    cached: bool = False


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str
    components: Dict[str, str]
    cache_stats: Optional[Dict[str, Any]] = None


# ========================================
# AGENT FACTORY
# ========================================

async def create_agent_for_session(
    session_id: str,
    prompt_version: str = "v1",
    input_type: str = "text",
    use_openai: bool = False,
    correlation_id: str = None
) -> AgentExecutor:
    """
    Create agent with all components configured.
    Uses shared DB pool for memory.
    """
    # 1. Get system prompt
    system_prompt = get_prompt(prompt_version)
    
    # 2. Initialize LLM
    if use_openai:
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not set")
        
        llm = ChatOpenAI(
            model=settings.DEFAULT_LLM_MODEL,
            temperature=settings.TEMPERATURE,
            max_tokens=settings.MAX_TOKENS
        )
        logger.info(f"[{correlation_id}] Using OpenAI: {settings.DEFAULT_LLM_MODEL}")
    else:
        llm = ChatYandexGPT(
            temperature=settings.TEMPERATURE,
            max_tokens=settings.MAX_TOKENS
        )
        logger.info(f"[{correlation_id}] Using YandexGPT")
    
    # 3. Get tools
    tools = get_tools()
    
    # 4. Create prompt template
    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=system_prompt),
        MessagesPlaceholder(variable_name="chat_history"),
        HumanMessage(content="{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad")
    ])
    
    # 5. Create agent
    agent = create_openai_functions_agent(
        llm=llm,
        tools=tools,
        prompt=prompt
    )
    
    # 6. Initialize memory (inject shared pool)
    chat_history = VersionedChatHistory(
        session_id=session_id,
        prompt_version=prompt_version,
        pool=db_pool  # Shared pool
    )
    await chat_history._initialize_version()
    
    memory = ConversationBufferMemory(
        chat_memory=chat_history,
        return_messages=True,
        memory_key="chat_history"
    )
    
    # 7. Create logging callback
    logging_callback = SupabaseLoggingCallback(
        session_id=session_id,
        input_type=input_type,
        correlation_id=correlation_id
    )
    
    # 8. Create executor
    executor = create_secure_executor(
        agent=agent,
        tools=tools,
        memory=memory,
        callbacks=[logging_callback],
        verbose=settings.ENVIRONMENT == "development",
        max_iterations=5,
        max_execution_time=60
    )
    
    logger.info(
        f"[{correlation_id}] Agent created: "
        f"session={session_id}, version={prompt_version}, tools={len(tools)}"
    )
    
    return executor


# ========================================
# HELPERS
# ========================================

def extract_tools_and_context(result: Dict[str, Any]) -> tuple[List[str], bool, int]:
    """
    Parse intermediate steps from agent result.
    Returns: (tools_used, context_used, documents_found)
    """
    tools_used = []
    context_used = False
    documents_found = 0
    
    for step in result.get("intermediate_steps", []):
        if isinstance(step, tuple) and len(step) >= 2:
            action, observation = step[0], step[1]
            
            # Extract tool name
            if hasattr(action, 'tool'):
                tools_used.append(action.tool)
                
                # Check if search_documents was used
                if action.tool == "search_documents":
                    context_used = True
                    # Try to extract document count from observation
                    if "Найдено документов:" in str(observation):
                        try:
                            count_str = str(observation).split("Найдено документов:")[1].split("\n")[0].strip()
                            documents_found = int(count_str)
                        except:
                            documents_found = 1
                    else:
                        documents_found = 1
    
    # Remove duplicates while preserving order
    tools_used = list(dict.fromkeys(tools_used))
    
    return tools_used, context_used, documents_found


def _track_business_metrics(
    request: ChatRequest,
    result: Dict[str, Any],
    tools_used: List[str]
):
    """
    Track business metrics (funnel, intent, conversions).
    
    Tracks:
    - Funnel progression (greeting → needs → presentation → closing)
    - Intent distribution (real_estate, general)
    - Successful closings (phone number collected)
    """
    try:
        message_lower = request.message.lower()
        response_lower = result.get("output", "").lower()
        
        # Track funnel steps
        if any(kw in message_lower for kw in ['привет', 'здравствуй']):
            funnel_step_reached.labels(step='greeting').inc()
        
        if any(kw in message_lower for kw in ['квартир', 'жк', 'цен', 'комнат']):
            funnel_step_reached.labels(step='needs_discovery').inc()
        
        if "search_documents" in tools_used:
            funnel_step_reached.labels(step='presentation').inc()
        
        if any(kw in message_lower for kw in ['имя', 'телефон', 'номер']):
            funnel_step_reached.labels(step='closing').inc()
            
            # Check if phone number provided
            if re.search(r'\+?\d[\d\s\-\(\)]{7,}', request.message):
                successful_closings.inc()
        
        # Track intent
        if "search_documents" in tools_used:
            user_intent_distribution.labels(intent_type='real_estate').inc()
        elif "calculate_mortgage" in tools_used:
            user_intent_distribution.labels(intent_type='pricing').inc()
        else:
            user_intent_distribution.labels(intent_type='general').inc()
        
        # Track conversation turns
        conversation_turns.observe(1)
        
    except Exception as e:
        logger.warning(f"Business metrics tracking failed: {e}")


# ========================================
# MIDDLEWARE
# ========================================

@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    """Add correlation ID to all requests"""
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    
    return response


# ========================================
# ENDPOINTS
# ========================================

@app.post("/chat", response_model=ChatResponse)
@track_agent_request
@limiter.limit("10/minute")
async def chat(
    request: ChatRequest,
    http_request: Request,
    background_tasks: BackgroundTasks
):
    """
    Main chat endpoint.
    
    Features:
    - Rate limiting (10 req/min)
    - LLM caching (Redis)
    - Business metrics tracking
    - Security validation
    """
    start_time = time.time()
    correlation_id = http_request.state.correlation_id
    
    logger.info(
        f"[{correlation_id}] Chat request: "
        f"session={request.session_id}, "
        f"message={request.message[:50]}..."
    )
    
    try:
        # 1. Validate input
        validator = SecurityValidator()
        try:
            sanitized_input = validator.validate(request.message)
        except ValueError as e:
            logger.warning(f"[{correlation_id}] Input blocked: {e}")
            
            return ChatResponse(
                response=f"🚫 {e}",
                session_id=request.session_id,
                tools_used=[],
                tokens_used=0,
                response_time_ms=round((time.time() - start_time) * 1000, 2),
                context_used=False,
                documents_found=0,
                timestamp=datetime.utcnow().isoformat(),
                correlation_id=correlation_id,
                cached=False
            )
        
        # 2. Create agent
        agent = await create_agent_for_session(
            session_id=request.session_id,
            prompt_version=request.prompt_version,
            input_type=request.input_type,
            use_openai=request.use_openai,
            correlation_id=correlation_id
        )
        
        # 3. Execute agent
        result = await agent.ainvoke({"input": sanitized_input})
        
        # 4. Extract metrics
        tools_used, context_used, documents_found = extract_tools_and_context(result)
        
        # 5. Get token usage
        tokens_used = 0
        if hasattr(agent, 'llm') and hasattr(agent.llm, 'get_num_tokens'):
            try:
                tokens_used = agent.llm.get_num_tokens(result["output"])
            except:
                tokens_used = 0
        
        track_token_usage(tokens_used)
        
        # 6. Track business metrics
        _track_business_metrics(request, result, tools_used)
        
        response_time_ms = round((time.time() - start_time) * 1000, 2)
        
        logger.info(
            f"[{correlation_id}] Chat completed: "
            f"duration={response_time_ms}ms, tools={tools_used}, "
            f"tokens={tokens_used}"
        )
        
        return ChatResponse(
            response=result["output"],
            session_id=request.session_id,
            tools_used=tools_used,
            tokens_used=tokens_used,
            response_time_ms=response_time_ms,
            context_used=context_used,
            documents_found=documents_found,
            timestamp=datetime.utcnow().isoformat(),
            correlation_id=correlation_id,
            cached=False
        )
    
    except RateLimitExceeded:
        raise
    except Exception as e:
        logger.error(
            f"[{correlation_id}] Chat error: {type(e).__name__}: {e}",
            exc_info=True
        )
        
        background_tasks.add_task(
            log_error_manually,
            session_id=request.session_id,
            error_message=str(e),
            error_code=500,
            node_name="Agent",
            severity="error",
            correlation_id=correlation_id
        )
        
        raise HTTPException(
            status_code=500,
            detail=(
                "Произошла ошибка при обработке запроса. "
                "Пожалуйста, попробуйте ещё раз или свяжитесь с менеджером."
            )
        )


@app.delete("/chat/{session_id}")
async def clear_history(session_id: str):
    """Clear chat history for session"""
    try:
        history = VersionedChatHistory(
            session_id=session_id,
            pool=db_pool
        )
        await history.aclear()
        await history.close()
        
        logger.info(f"Cleared history for session: {session_id}")
        
        return {
            "status": "cleared",
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Failed to clear history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint with cache stats"""
    components = {}
    
    # Check YandexGPT
    try:
        llm = ChatYandexGPT()
        components["yandex_gpt"] = "ok"
    except:
        components["yandex_gpt"] = "error"
    
    # Check Supabase
    try:
        from supabase import create_client
        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        supabase.table("logs").select("id").limit(1).execute()
        components["supabase"] = "ok"
    except:
        components["supabase"] = "error"
    
    # Check PostgreSQL
    try:
        if db_pool:
            async with db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            components["postgres"] = "ok"
        else:
            components["postgres"] = "not_initialized"
    except:
        components["postgres"] = "error"
    
    # Check Redis
    try:
        if redis_client:
            redis_client.ping()
            components["redis"] = "ok"
        else:
            components["redis"] = "not_initialized"
    except:
        components["redis"] = "error"
    
    # Get cache stats
    cache_stats = None
    try:
        from rag.retrievers import get_cache_info
        cache_stats = get_cache_info()
    except:
        pass
    
    status = "healthy" if all(v == "ok" for v in components.values()) else "degraded"
    
    return HealthResponse(
        status=status,
        service="ai-agent",
        version=settings.VERSION,
        timestamp=datetime.utcnow().isoformat(),
        components=components,
        cache_stats=cache_stats
    )


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), media_type="text/plain")


@app.get("/")
async def root():
    """API documentation"""
    return {
        "service": settings.APP_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "endpoints": {
            "POST /chat": "Send message to agent",
            "DELETE /chat/{session_id}": "Clear chat history",
            "GET /health": "Health check",
            "GET /metrics": "Prometheus metrics",
            "GET /docs": "OpenAPI documentation"
        },
        "features": [
            "Security validation",
            "Prompt versioning",
            "Memory with sliding window",
            "Tool calling (search, calculate, details)",
            "Logging to Supabase",
            "Prometheus metrics",
            "Circuit breaker",
            "Retry logic",
            "Rate limiting (10 req/min)",
            "LLM caching (Redis)",
            "Shared DB pool",
            "Business metrics"
        ]
    }


# ========================================
# STARTUP / SHUTDOWN
# ========================================

@app.on_event("startup")
async def startup_event():
    """Application startup"""
    global db_pool, redis_client
    
    logger.info(f"Starting {settings.APP_NAME} v{settings.VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Log level: {settings.LOG_LEVEL}")
    
    # Initialize shared DB pool
    try:
        db_pool = await asyncpg.create_pool(
            settings.POSTGRES_URL,
            min_size=10,
            max_size=50,
            command_timeout=60
        )
        logger.info("Database pool created (10-50 connections)")
    except Exception as e:
        logger.error(f"Failed to create DB pool: {e}")
        db_pool = None
    
    # Setup Redis LLM cache
    try:
        redis_client = redis_lib.Redis(
            host=settings.REDIS_URL.split("://")[1].split(":")[0],
            port=int(settings.REDIS_URL.split(":")[-1]),
            decode_responses=True
        )
        redis_client.ping()
        
        # Enable LangChain LLM caching
        set_llm_cache(RedisCache(redis_client))
        
        logger.info("Redis LLM cache enabled")
    except Exception as e:
        logger.error(f"Failed to setup Redis cache: {e}")
        redis_client = None
    
    # Log configuration
    logger.info(f"LLM Model: {settings.DEFAULT_LLM_MODEL}")
    logger.info(f"Temperature: {settings.TEMPERATURE}")
    logger.info(f"Similarity Threshold: {settings.SIMILARITY_THRESHOLD}")
    logger.info(f"Memory Window: {settings.MEMORY_WINDOW_SIZE}")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown"""
    logger.info("Shutting down agent application")
    
    # Close DB pool
    if db_pool:
        await db_pool.close()
        logger.info("Database pool closed")
    
    # Close Redis
    if redis_client:
        redis_client.close()
        logger.info("Redis connection closed")


# ========================================
# RUN SERVER
# ========================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level=settings.LOG_LEVEL.lower()
    )
