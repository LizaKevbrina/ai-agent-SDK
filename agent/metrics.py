"""
Agent Metrics - ENHANCED VERSION
Provides: Prometheus metrics for agent operations

NEW FEATURES:
 Business metrics (funnel, intent, conversions)
 Tool performance tracking
 Conversation quality metrics
"""

from prometheus_client import Counter, Histogram, Gauge, Summary
import time
import logging
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger(__name__)

# ========================================
# EXISTING AGENT METRICS
# ========================================

agent_requests_total = Counter(
    'agent_requests_total',
    'Total agent requests',
    ['status', 'tool_used']
)

agent_duration_seconds = Histogram(
    'agent_duration_seconds',
    'Agent request duration',
    ['status'],
    buckets=[0.5, 1, 2, 5, 10, 30, 60, 120]
)

agent_tokens_used = Histogram(
    'agent_tokens_used',
    'Tokens used per agent request',
    buckets=[100, 500, 1000, 2000, 5000, 10000, 20000]
)

tool_calls_total = Counter(
    'tool_calls_total',
    'Tool invocations',
    ['tool_name', 'status']
)

tool_duration_seconds = Histogram(
    'tool_duration_seconds',
    'Tool execution duration',
    ['tool_name'],
    buckets=[0.1, 0.5, 1, 2, 5, 10]
)

active_sessions = Gauge(
    'active_sessions',
    'Number of active chat sessions'
)

agent_errors_total = Counter(
    'agent_errors_total',
    'Total agent errors',
    ['error_type']
)

# Memory metrics
memory_operations_total = Counter(
    'memory_operations_total',
    'Memory operations',
    ['operation', 'status']
)

memory_window_size = Gauge(
    'memory_window_size',
    'Current memory window size',
    ['session_id']
)

memory_version_changes = Counter(
    'memory_version_changes_total',
    'Prompt version changes',
    ['from_version', 'to_version']
)

# ========================================
# NEW: BUSINESS METRICS
# ========================================

# Funnel tracking
funnel_step_reached = Counter(
    'funnel_step_reached_total',
    'Users reaching each funnel step',
    ['step']  # greeting, needs_discovery, presentation, objection_handling, closing
)

# Intent distribution
user_intent_distribution = Counter(
    'user_intent_total',
    'Distribution of user intents',
    ['intent_type']  # real_estate, general, pricing, location, scheduling
)

# Conversation quality
conversation_turns = Histogram(
    'conversation_turns',
    'Number of turns in conversation',
    buckets=[1, 3, 5, 10, 15, 20, 30, 50]
)

conversation_duration_seconds = Histogram(
    'conversation_duration_seconds',
    'Total conversation duration',
    buckets=[60, 300, 600, 1800, 3600, 7200]  # 1min to 2hrs
)

# Success metrics
successful_closings = Counter(
    'successful_closings_total',
    'Number of successful closings (phone number collected)'
)

viewing_bookings = Counter(
    'viewing_bookings_total',
    'Number of viewing bookings made'
)

# User engagement
messages_per_session = Histogram(
    'messages_per_session',
    'Number of messages per session',
    buckets=[1, 5, 10, 20, 50, 100]
)

active_users_gauge = Gauge(
    'active_users',
    'Currently active users'
)

# Response quality
user_satisfaction = Counter(
    'user_satisfaction_total',
    'User satisfaction signals',
    ['signal']  # positive, negative, neutral
)

# ========================================
# NEW: CACHE METRICS
# ========================================

cache_operations_total = Counter(
    'cache_operations_total',
    'Cache operations',
    ['operation', 'cache_type']  # hit/miss for llm/retriever
)

cache_hit_rate = Gauge(
    'cache_hit_rate',
    'Cache hit rate',
    ['cache_type']
)

# ========================================
# DECORATORS
# ========================================

def track_agent_request(func: Callable) -> Callable:
    """
    Decorator to track agent request metrics.
    
    Usage:
        @track_agent_request
        async def handle_chat(request):
            ...
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        active_sessions.inc()
        active_users_gauge.inc()
        
        status = "success"
        tool_used = "none"
        
        try:
            result = await func(*args, **kwargs)
            
            # Extract tool usage if available
            if isinstance(result, dict) and "tools_used" in result:
                tool_used = ",".join(result["tools_used"]) or "none"
            
            return result
        
        except Exception as e:
            status = "error"
            error_type = type(e).__name__
            agent_errors_total.labels(error_type=error_type).inc()
            raise
        
        finally:
            duration = time.time() - start_time
            
            agent_requests_total.labels(
                status=status,
                tool_used=tool_used
            ).inc()
            
            agent_duration_seconds.labels(status=status).observe(duration)
            active_sessions.dec()
            active_users_gauge.dec()
    
    return wrapper


def track_tool_call(tool_name: str):
    """
    Decorator to track tool execution.
    
    Usage:
        @track_tool_call("search_documents")
        def search_documents(query):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            
            try:
                result = func(*args, **kwargs)
                return result
            
            except Exception as e:
                status = "error"
                raise
            
            finally:
                duration = time.time() - start_time
                tool_calls_total.labels(tool_name=tool_name, status=status).inc()
                tool_duration_seconds.labels(tool_name=tool_name).observe(duration)
        
        return wrapper
    
    return decorator


# ========================================
# HELPER FUNCTIONS
# ========================================

def track_token_usage(tokens: int):
    """Track token usage"""
    agent_tokens_used.observe(tokens)


def track_memory_operation(operation: str, status: str = "success"):
    """
    Track memory operations.
    
    Args:
        operation: get, add, clear
        status: success, error
    """
    memory_operations_total.labels(
        operation=operation,
        status=status
    ).inc()


def track_version_change(from_version: str, to_version: str):
    """Track prompt version change"""
    memory_version_changes.labels(
        from_version=from_version,
        to_version=to_version
    ).inc()


def update_memory_window_size(session_id: str, size: int):
    """Update memory window size gauge"""
    memory_window_size.labels(session_id=session_id).set(size)


# ========================================
# NEW: BUSINESS METRICS HELPERS
# ========================================

def track_funnel_step(step: str):
    """
    Track funnel progression
    
    Args:
        step: greeting, needs_discovery, presentation, objection_handling, closing
    """
    funnel_step_reached.labels(step=step).inc()


def track_user_intent(intent_type: str):
    """
    Track user intent
    
    Args:
        intent_type: real_estate, general, pricing, location, scheduling
    """
    user_intent_distribution.labels(intent_type=intent_type).inc()


def track_conversation_turns(turns: int):
    """Track number of conversation turns"""
    conversation_turns.observe(turns)


def track_conversation_duration(duration_seconds: float):
    """Track total conversation duration"""
    conversation_duration_seconds.observe(duration_seconds)


def track_successful_closing():
    """Track successful closing (phone number collected)"""
    successful_closings.inc()


def track_viewing_booking():
    """Track viewing booking"""
    viewing_bookings.inc()


def track_user_satisfaction(signal: str):
    """
    Track user satisfaction signals
    
    Args:
        signal: positive, negative, neutral
    """
    user_satisfaction.labels(signal=signal).inc()


def track_cache_operation(operation: str, cache_type: str):
    """
    Track cache operations
    
    Args:
        operation: hit, miss
        cache_type: llm, retriever, embeddings
    """
    cache_operations_total.labels(
        operation=operation,
        cache_type=cache_type
    ).inc()


def update_cache_hit_rate(cache_type: str, hit_rate: float):
    """
    Update cache hit rate gauge
    
    Args:
        cache_type: llm, retriever, embeddings
        hit_rate: 0.0 to 1.0
    """
    cache_hit_rate.labels(cache_type=cache_type).set(hit_rate)


def get_metrics_summary() -> dict:
    """
    Get summary of current metrics.
    
    Returns:
        Dictionary with metric values
        
    Usage:
        summary = get_metrics_summary()
        print(f"Active sessions: {summary['active_sessions']}")
    """
    return {
        "active_sessions": active_sessions._value._value,
        "total_requests": agent_requests_total._value.get(),
        "total_errors": agent_errors_total._value.get(),
        "total_tool_calls": tool_calls_total._value.get(),
        "successful_closings": successful_closings._value._value,
        "viewing_bookings": viewing_bookings._value._value,
        "active_users": active_users_gauge._value._value
    }


# ========================================
# NEW: ANALYTICS HELPERS
# ========================================

def calculate_conversion_rate() -> float:
    """
    Calculate conversion rate (closings / total sessions)
    
    Returns:
        Conversion rate as percentage
    """
    try:
        total = agent_requests_total._value.get()
        closings = successful_closings._value._value
        
        if total == 0:
            return 0.0
        
        return (closings / total) * 100
    
    except:
        return 0.0


def get_funnel_metrics() -> dict:
    """
    Get funnel metrics breakdown
    
    Returns:
        Dictionary with counts per funnel step
    """
    try:
        # Access internal Prometheus data
        funnel_data = funnel_step_reached._value._value
        
        return {
            step: count
            for step, count in funnel_data.items()
        }
    
    except:
        return {}


def get_intent_distribution() -> dict:
    """
    Get intent distribution
    
    Returns:
        Dictionary with counts per intent type
    """
    try:
        intent_data = user_intent_distribution._value._value
        
        return {
            intent: count
            for intent, count in intent_data.items()
        }
    
    except:
        return {}
