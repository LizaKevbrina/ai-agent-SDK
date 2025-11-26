"""
Logging Callbacks - ENHANCED VERSION
Migrated from: services/logging/main.py

NEW FEATURES:
✅ Tool execution breakdown tracking
✅ Rich error context for RCA
✅ Performance tracking per tool
"""

from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema import AgentAction, AgentFinish, LLMResult
from typing import Any, Dict, List, Optional
import time
import logging
from datetime import datetime
import json
import traceback
from supabase import create_client, Client

from config.settings import settings
from agent.metrics import tool_duration_seconds  # ✅ NEW: Prometheus metric

logger = logging.getLogger(__name__)


class SupabaseLoggingCallback(BaseCallbackHandler):
    """
    LangChain callback for logging to Supabase.
    
    NEW FEATURES:
    ✅ Tool execution tracking (breakdown by tool)
    ✅ Rich error context (agent state, conversation history)
    ✅ Performance metrics per tool
    
    Usage:
        callback = SupabaseLoggingCallback(
            session_id="user_123",
            input_type="text"
        )
        
        agent = AgentExecutor(
            agent=agent,
            tools=tools,
            callbacks=[callback]
        )
    """
    
    def __init__(
        self,
        session_id: str,
        input_type: str = "text",
        supabase_url: str = None,
        supabase_key: str = None,
        correlation_id: str = None
    ):
        super().__init__()
        
        self.session_id = session_id
        self.input_type = input_type
        self.correlation_id = correlation_id or f"{session_id}_{int(time.time())}"
        
        # Initialize Supabase client
        url = supabase_url or settings.SUPABASE_URL
        key = supabase_key or settings.SUPABASE_KEY
        self.supabase: Client = create_client(url, key)
        
        # Tracking state
        self.start_time = None
        self.question = None
        self.answer = None
        self.tools_used = []
        self.documents_found = 0
        self.context_used = False
        self.tokens_used = 0
        self.error_occurred = False
        
        # ✅ NEW: Tool execution tracking
        self.tool_start_time = None
        self.current_tool = None
        self.last_tool_output = None
        self.tool_executions = []  # List of {tool, duration, success}
        
        # ✅ NEW: Conversation history (for error context)
        self.history = []
    
    # ========================================
    # CHAIN CALLBACKS
    # ========================================
    
    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        **kwargs: Any
    ) -> None:
        """Called when chain starts"""
        self.start_time = time.time()
        self.question = inputs.get("input", inputs.get("question", ""))
        
        logger.debug(
            f"[{self.correlation_id}] Chain started: "
            f"session={self.session_id}, input_type={self.input_type}"
        )
    
    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        **kwargs: Any
    ) -> None:
        """
        Called when chain ends successfully.
        
        ✅ UPDATED: Now includes tool execution breakdown
        """
        duration_ms = int((time.time() - self.start_time) * 1000) if self.start_time else 0
        
        # Extract answer
        self.answer = outputs.get("output", outputs.get("answer", ""))
        
        # Extract tools used from intermediate steps
        intermediate_steps = outputs.get("intermediate_steps", [])
        self.tools_used = []
        
        for step in intermediate_steps:
            if isinstance(step, tuple) and len(step) >= 2:
                action, result = step[0], step[1]
                if hasattr(action, 'tool'):
                    self.tools_used.append(action.tool)
                    
                    # Check if search_documents was used
                    if action.tool == "search_documents" and result:
                        self.context_used = True
                        if "Найдено документов:" in result:
                            try:
                                count_str = result.split("Найдено документов:")[1].split("\n")[0].strip()
                                self.documents_found = int(count_str)
                            except:
                                self.documents_found = 1
        
        # Determine intent type
        intent_type = "real_estate" if self.context_used else "general"
        
        # ✅ NEW: Log tool executions to separate table
        try:
            for tool_exec in self.tool_executions:
                self.supabase.table("tool_executions").insert({
                    "session_id": self.session_id,
                    "tool_name": tool_exec["tool"],
                    "duration_ms": tool_exec["duration_ms"],
                    "success": tool_exec["success"],
                    "correlation_id": self.correlation_id,
                    "timestamp": datetime.utcnow().isoformat()
                }).execute()
        except Exception as e:
            logger.warning(f"[{self.correlation_id}] Failed to log tool executions: {e}")
        
        # Log interaction to Supabase
        try:
            log_data = {
                "session_id": self.session_id,
                "question": self.question,
                "answer": self.answer,
                "intent_type": intent_type,
                "cached": False,
                "response_time_ms": duration_ms,
                "context_used": self.context_used,
                "documents_found": self.documents_found,
                "input_type": self.input_type,
                "timestamp": datetime.utcnow().isoformat(),
                # ✅ NEW: Tool breakdown
                "tools_used": json.dumps(self.tools_used),
                "tool_count": len(self.tools_used),
                "tool_breakdown": json.dumps(self.tool_executions)
            }
            
            self.supabase.table("logs").insert(log_data).execute()
            
            logger.info(
                f"[{self.correlation_id}] Logged interaction: "
                f"duration={duration_ms}ms, tools={self.tools_used}, "
                f"docs={self.documents_found}"
            )
        
        except Exception as e:
            logger.error(f"[{self.correlation_id}] Failed to log interaction: {e}")
    
    def on_chain_error(
        self,
        error: Exception,
        **kwargs: Any
    ) -> None:
        """
        Called when chain errors.
        
        ✅ ENHANCED: Rich error context for RCA
        """
        self.error_occurred = True
        
        # Extract error details
        error_message = str(error)
        error_type = type(error).__name__
        stack_trace = traceback.format_exc()
        
        # Determine error code
        if "timeout" in error_message.lower():
            error_code = 408
        elif "rate limit" in error_message.lower():
            error_code = 429
        elif "temporarily unavailable" in error_message.lower():
            error_code = 503
        else:
            error_code = 500
        
        # Determine severity
        if error_code == 429 or error_code == 408:
            severity = "warning"
        elif error_code >= 500:
            severity = "error"
        else:
            severity = "critical"
        
        # ✅ NEW: Rich error context
        error_context = {
            "error_message": error_message,
            "error_type": error_type,
            "error_code": error_code,
            "stack_trace": stack_trace,
            
            # ✅ Agent state
            "tools_used": json.dumps(self.tools_used),
            "last_tool": self.tools_used[-1] if self.tools_used else None,
            "last_tool_output": self.last_tool_output[:500] if self.last_tool_output else None,
            "tool_executions": json.dumps(self.tool_executions),
            
            # ✅ Conversation context
            "question": self.question,
            "history_length": len(self.history),
            
            # ✅ System state
            "node_name": "Agent",
            "session_id": self.session_id,
            "correlation_id": self.correlation_id,
            "timestamp": datetime.utcnow().isoformat(),
            "input_type": self.input_type,
            "severity": severity,
            
            # ✅ Performance context
            "elapsed_ms": int((time.time() - self.start_time) * 1000) if self.start_time else 0,
        }
        
        # Log to Supabase
        try:
            self.supabase.table("errors").insert(error_context).execute()
            
            logger.error(
                f"[{self.correlation_id}] Logged error: "
                f"type={error_type}, code={error_code}, severity={severity}"
            )
        
        except Exception as e:
            logger.error(f"[{self.correlation_id}] Failed to log error: {e}")
    
    # ========================================
    # LLM CALLBACKS
    # ========================================
    
    def on_llm_end(
        self,
        response: LLMResult,
        **kwargs: Any
    ) -> None:
        """Track token usage from LLM"""
        if response.llm_output and "token_usage" in response.llm_output:
            tokens = response.llm_output["token_usage"].get("total_tokens", 0)
            self.tokens_used += tokens
            
            logger.debug(
                f"[{self.correlation_id}] LLM tokens: {tokens} "
                f"(total: {self.tokens_used})"
            )
    
    # ========================================
    # TOOL CALLBACKS (ENHANCED)
    # ========================================
    
    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any
    ) -> None:
        """
        Called when tool starts
        
        ✅ NEW: Track tool execution time
        """
        self.tool_start_time = time.time()
        self.current_tool = serialized.get("name", "unknown")
        
        logger.debug(
            f"[{self.correlation_id}] Tool started: {self.current_tool}, "
            f"input={input_str[:50]}..."
        )
    
    def on_tool_end(
        self,
        output: str,
        **kwargs: Any
    ) -> None:
        """
        Called when tool ends
        
        ✅ NEW: Track tool performance + Prometheus metric
        """
        if self.tool_start_time and self.current_tool:
            duration = time.time() - self.tool_start_time
            duration_ms = int(duration * 1000)
            
            # Store execution details
            self.tool_executions.append({
                "tool": self.current_tool,
                "duration_ms": duration_ms,
                "success": True
            })
            
            # Store output for error context
            self.last_tool_output = output
            
            # ✅ NEW: Prometheus metric
            tool_duration_seconds.labels(tool_name=self.current_tool).observe(duration)
            
            logger.debug(
                f"[{self.correlation_id}] Tool completed: {self.current_tool}, "
                f"duration={duration_ms}ms, output_length={len(output)}"
            )
    
    def on_tool_error(
        self,
        error: Exception,
        **kwargs: Any
    ) -> None:
        """
        Called when tool errors
        
        ✅ NEW: Track failed tool executions
        """
        if self.tool_start_time and self.current_tool:
            duration = time.time() - self.tool_start_time
            duration_ms = int(duration * 1000)
            
            # Store failed execution
            self.tool_executions.append({
                "tool": self.current_tool,
                "duration_ms": duration_ms,
                "success": False,
                "error": str(error)
            })
        
        logger.warning(
            f"[{self.correlation_id}] Tool error: {self.current_tool}, "
            f"error={error}"
        )
    
    # ========================================
    # AGENT CALLBACKS
    # ========================================
    
    def on_agent_action(
        self,
        action: AgentAction,
        **kwargs: Any
    ) -> None:
        """Called when agent takes action"""
        logger.debug(
            f"[{self.correlation_id}] Agent action: {action.tool}, "
            f"input={action.tool_input}"
        )
    
    def on_agent_finish(
        self,
        finish: AgentFinish,
        **kwargs: Any
    ) -> None:
        """Called when agent finishes"""
        logger.debug(
            f"[{self.correlation_id}] Agent finished: "
            f"output={finish.return_values.get('output', '')[:50]}..."
        )


# ========================================
# HELPER FUNCTIONS
# ========================================

def create_logging_callback(
    session_id: str,
    input_type: str = "text",
    correlation_id: str = None
) -> SupabaseLoggingCallback:
    """
    Factory function to create logging callback.
    
    Usage:
        callback = create_logging_callback("user_123", "text")
        agent = AgentExecutor(callbacks=[callback], ...)
    """
    return SupabaseLoggingCallback(
        session_id=session_id,
        input_type=input_type,
        correlation_id=correlation_id
    )


async def log_error_manually(
    session_id: str,
    error_message: str,
    error_code: int = 500,
    node_name: str = "Unknown",
    severity: str = "error",
    correlation_id: str = None
):
    """
    Manually log an error to Supabase.
    
    Use when error occurs outside agent execution.
    
    Usage:
        await log_error_manually(
            session_id="user_123",
            error_message="Database connection failed",
            error_code=503,
            severity="critical"
        )
    """
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    
    error_data = {
        "error_message": error_message,
        "error_code": error_code,
        "node_name": node_name,
        "session_id": session_id,
        "correlation_id": correlation_id or f"{session_id}_{int(time.time())}",
        "timestamp": datetime.utcnow().isoformat(),
        "severity": severity
    }
    
    try:
        supabase.table("errors").insert(error_data).execute()
        logger.info(f"Manually logged error: {error_message}")
    except Exception as e:
        logger.error(f"Failed to manually log error: {e}")


# ========================================
# NEW: Database Schema for tool_executions
# ========================================

"""
-- Add to init.sql:

CREATE TABLE IF NOT EXISTS tool_executions (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL,
    tool_name VARCHAR(100) NOT NULL,
    duration_ms INTEGER NOT NULL,
    success BOOLEAN DEFAULT TRUE,
    correlation_id VARCHAR(200),
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tool_executions_session 
    ON tool_executions(session_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_tool_executions_tool 
    ON tool_executions(tool_name, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_tool_executions_correlation 
    ON tool_executions(correlation_id);
"""
