"""
Custom Agent Executor
Provides: Security-enhanced AgentExecutor with metrics
"""

from langchain.agents import AgentExecutor
from langchain.schema import AgentAction, AgentFinish
from typing import Any, Dict, List, Optional, Union
import logging
import time

from tools.security import SecurityValidator
from agent.metrics import (
    track_agent_request,
    track_token_usage,
    agent_errors_total
)

logger = logging.getLogger(__name__)


class SecureAgentExecutor(AgentExecutor):
    """
    Custom AgentExecutor with security validation and enhanced error handling.
    
    Features:
    - Input validation before execution
    - Automatic metrics tracking
    - Enhanced error messages
    - Token usage tracking
    
    Usage:
        executor = SecureAgentExecutor(
            agent=agent,
            tools=tools,
            validate_input=True,
            verbose=True
        )
        
        result = await executor.ainvoke({"input": user_input})
    """
    
    validate_input: bool = True
    
    def _call(self, inputs: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        Override _call to add security validation.
        
        Validates input before passing to agent.
        """
        # Security validation
        if self.validate_input and "input" in inputs:
            try:
                validator = SecurityValidator()
                sanitized = validator.validate(inputs["input"])
                inputs["input"] = sanitized
                
                logger.debug(
                    f"Input validated: original_length={len(inputs['input'])}, "
                    f"sanitized_length={len(sanitized)}"
                )
            
            except ValueError as e:
                # Security threat detected
                logger.warning(f"Security validation failed: {e}")
                agent_errors_total.labels(error_type='security_block').inc()
                
                return {
                    "output": f"🚫 Ваш запрос заблокирован по соображениям безопасности: {e}",
                    "intermediate_steps": []
                }
        
        # Call parent
        try:
            result = super()._call(inputs, **kwargs)
            
            # Track token usage if available
            if "token_usage" in result:
                track_token_usage(result["token_usage"])
            
            return result
        
        except Exception as e:
            error_type = type(e).__name__
            agent_errors_total.labels(error_type=error_type).inc()
            
            logger.error(f"Agent execution failed: {error_type}: {e}")
            
            # Return user-friendly error message
            return {
                "output": self._format_error_message(e),
                "intermediate_steps": []
            }
    
    async def _acall(self, inputs: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        Override _acall to add security validation (async version).
        """
        # Security validation
        if self.validate_input and "input" in inputs:
            try:
                validator = SecurityValidator()
                sanitized = validator.validate(inputs["input"])
                inputs["input"] = sanitized
            
            except ValueError as e:
                logger.warning(f"Security validation failed: {e}")
                agent_errors_total.labels(error_type='security_block').inc()
                
                return {
                    "output": f"🚫 {e}",
                    "intermediate_steps": []
                }
        
        # Call parent
        try:
            result = await super()._acall(inputs, **kwargs)
            
            # Track token usage if available
            if "token_usage" in result:
                track_token_usage(result["token_usage"])
            
            return result
        
        except Exception as e:
            error_type = type(e).__name__
            agent_errors_total.labels(error_type=error_type).inc()
            
            logger.error(f"Agent execution failed: {error_type}: {e}")
            
            return {
                "output": self._format_error_message(e),
                "intermediate_steps": []
            }
    
    def _format_error_message(self, error: Exception) -> str:
        """
        Format error message for user.
        
        Converts technical errors to user-friendly messages.
        """
        error_str = str(error).lower()
        
        # Rate limit
        if "rate limit" in error_str or "429" in error_str:
            return (
                "⚠️ Извините, сейчас очень много запросов. "
                "Пожалуйста, попробуйте через минуту."
            )
        
        # Timeout
        if "timeout" in error_str or "408" in error_str:
            return (
                "⏱️ Запрос занял слишком много времени. "
                "Попробуйте переформулировать вопрос или повторите попытку."
            )
        
        # Service unavailable
        if "temporarily unavailable" in error_str or "503" in error_str:
            return (
                "🔧 Сервис временно недоступен. "
                "Пожалуйста, попробуйте через несколько минут."
            )
        
        # Circuit breaker open
        if "circuit breaker" in error_str:
            return (
                "⚠️ Система перегружена. "
                "Пожалуйста, подождите минуту и попробуйте снова."
            )
        
        # Generic error
        return (
            "❌ Произошла ошибка при обработке вашего запроса. "
            "Пожалуйста, попробуйте переформулировать вопрос или "
            "свяжитесь с менеджером: Лия, +7-999-000-12-12"
        )


def create_secure_executor(
    agent,
    tools: list,
    memory=None,
    callbacks: list = None,
    verbose: bool = False,
    max_iterations: int = 5,
    max_execution_time: int = 60
) -> SecureAgentExecutor:
    """
    Factory function to create SecureAgentExecutor.
    
    Args:
        agent: Agent instance
        tools: List of tools
        memory: Chat memory (optional)
        callbacks: List of callbacks (optional)
        verbose: Enable verbose logging
        max_iterations: Max agent iterations
        max_execution_time: Max execution time in seconds
        
    Returns:
        Configured SecureAgentExecutor
        
    Usage:
        executor = create_secure_executor(
            agent=agent,
            tools=tools,
            memory=memory,
            callbacks=[logging_callback],
            verbose=True
        )
    """
    return SecureAgentExecutor(
        agent=agent,
        tools=tools,
        memory=memory,
        callbacks=callbacks or [],
        verbose=verbose,
        max_iterations=max_iterations,
        max_execution_time=max_execution_time,
        validate_input=True,
        handle_parsing_errors=True,
        return_intermediate_steps=True,
        early_stopping_method="generate"
    )
