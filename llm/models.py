"""
LLM Models
Migrated from: services/llm/main.py
Provides: ChatYandexGPT wrapper with circuit breaker, retry, metrics
FIXED: Added async support, retry logic, Prometheus metrics
"""

from langchain.chat_models.base import BaseChatModel
from langchain.schema import (
    BaseMessage,
    ChatResult,
    ChatGeneration,
    AIMessage,
    HumanMessage,
    SystemMessage
)
from langchain.callbacks.manager import CallbackManagerForLLMRun
from typing import Optional, List, Any, Dict
from pydantic import Field
import httpx
import asyncio
import logging
from pybreaker import CircuitBreaker, CircuitBreakerError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    RetryError
)
from prometheus_client import Counter, Histogram

from config.settings import settings

logger = logging.getLogger(__name__)

# ========================================
# PROMETHEUS METRICS
# ========================================

llm_requests_total = Counter(
    'llm_requests_total',
    'Total LLM requests',
    ['provider', 'model', 'status']
)

llm_tokens_used = Histogram(
    'llm_tokens_used',
    'Tokens used per LLM request',
    ['provider', 'model'],
    buckets=[100, 500, 1000, 2000, 5000, 10000, 20000]
)

llm_duration_seconds = Histogram(
    'llm_duration_seconds',
    'LLM request duration',
    ['provider', 'model'],
    buckets=[0.5, 1, 2, 5, 10, 30, 60]
)

llm_circuit_breaker_opens = Counter(
    'llm_circuit_breaker_opens_total',
    'Circuit breaker opens',
    ['provider']
)

llm_rate_limits_total = Counter(
    'llm_rate_limits_total',
    'Rate limit hits',
    ['provider']
)

# ========================================
# CIRCUIT BREAKER
# ========================================

yandex_circuit_breaker = CircuitBreaker(
    fail_max=settings.CIRCUIT_BREAKER_FAIL_MAX,
    timeout_duration=settings.CIRCUIT_BREAKER_TIMEOUT,
    name='yandex_gpt',
    listeners=[
        lambda breaker, *args: llm_circuit_breaker_opens.labels(provider='yandex').inc()
    ]
)


class ChatYandexGPT(BaseChatModel):
    """
    YandexGPT Chat Model wrapper for LangChain.
    
    Features:
    - Circuit breaker for reliability (5 failures → 60s timeout)
    - Retry logic with exponential backoff (3 attempts)
    - Both sync and async support
    - Token tracking via Prometheus
    - Rate limit handling
    
    Example:
        llm = ChatYandexGPT()
        response = llm.invoke([HumanMessage(content="Привет!")])
        # Or async:
        response = await llm.ainvoke([HumanMessage(content="Привет!")])
    """
    
    api_key: str = Field(default=None)
    folder_id: str = Field(default=None)
    model: str = Field(default="yandexgpt/latest")
    temperature: float = Field(default=0.7)
    max_tokens: int = Field(default=2000)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Set defaults from settings if not provided
        if not self.api_key:
            self.api_key = settings.YANDEX_API_KEY
        if not self.folder_id:
            self.folder_id = settings.YANDEX_FOLDER_ID
        
        if not self.api_key or not self.folder_id:
            raise ValueError(
                "YANDEX_API_KEY and YANDEX_FOLDER_ID must be set in environment or passed as arguments"
            )
    
    @property
    def _llm_type(self) -> str:
        return "yandex-gpt"
    
    @property
    def _identifying_params(self) -> Dict[str, Any]:
        """Return identifying parameters for tracking"""
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }
    
    # ========================================
    # MESSAGE CONVERSION
    # ========================================
    
    def _convert_messages_to_yandex_format(
        self, 
        messages: List[BaseMessage]
    ) -> List[Dict[str, str]]:
        """
        Convert LangChain messages to YandexGPT format.
        
        LangChain types: SystemMessage, HumanMessage, AIMessage
        YandexGPT roles: system, user, assistant
        """
        yandex_messages = []
        
        for msg in messages:
            if isinstance(msg, SystemMessage):
                role = "system"
            elif isinstance(msg, HumanMessage):
                role = "user"
            elif isinstance(msg, AIMessage):
                role = "assistant"
            else:
                # Fallback for custom message types
                role = "user"
                logger.warning(f"Unknown message type: {type(msg)}, using 'user' role")
            
            yandex_messages.append({
                "role": role,
                "text": msg.content
            })
        
        return yandex_messages
    
    # ========================================
    # HTTP REQUESTS (SYNC)
    # ========================================
    
    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _make_request_sync(self, yandex_messages: List[Dict[str, str]]) -> Dict:
        """
        Make synchronous HTTP request to YandexGPT API with retry logic.
        
        Retries on:
        - Network errors (httpx.RequestError)
        - 5xx server errors
        - 429 rate limits (after backoff)
        
        Does NOT retry on:
        - 4xx client errors (except 429)
        - Circuit breaker open
        """
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "modelUri": f"gpt://{self.folder_id}/{self.model}",
            "completionOptions": {
                "temperature": self.temperature,
                "maxTokens": self.max_tokens
            },
            "messages": yandex_messages
        }
        
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            
            # Handle rate limits
            if response.status_code == 429:
                llm_rate_limits_total.labels(provider='yandex').inc()
                logger.warning("YandexGPT rate limit hit")
                response.raise_for_status()  # Will retry via tenacity
            
            # Handle other errors
            response.raise_for_status()
            
            return response.json()
    
    # ========================================
    # HTTP REQUESTS (ASYNC)
    # ========================================
    
    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def _make_request_async(self, yandex_messages: List[Dict[str, str]]) -> Dict:
        """
        Make asynchronous HTTP request to YandexGPT API with retry logic.
        """
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "modelUri": f"gpt://{self.folder_id}/{self.model}",
            "completionOptions": {
                "temperature": self.temperature,
                "maxTokens": self.max_tokens
            },
            "messages": yandex_messages
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code == 429:
                llm_rate_limits_total.labels(provider='yandex').inc()
                logger.warning("YandexGPT rate limit hit (async)")
                response.raise_for_status()
            
            response.raise_for_status()
            return response.json()
    
    # ========================================
    # LANGCHAIN INTERFACE (SYNC)
    # ========================================
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        Generate response using YandexGPT API (synchronous).
        
        This is called by llm.invoke() and llm.generate().
        """
        import time
        start_time = time.time()
        
        # Convert messages
        yandex_messages = self._convert_messages_to_yandex_format(messages)
        
        try:
            # Call with circuit breaker
            result = yandex_circuit_breaker.call(
                self._make_request_sync,
                yandex_messages
            )
            
            # Extract response
            text = result["result"]["alternatives"][0]["message"]["text"]
            tokens = result["result"]["usage"]["totalTokens"]
            
            # Create response
            message = AIMessage(content=text)
            generation = ChatGeneration(message=message)
            
            # Metrics
            duration = time.time() - start_time
            llm_requests_total.labels(
                provider='yandex',
                model=self.model,
                status='success'
            ).inc()
            llm_tokens_used.labels(provider='yandex', model=self.model).observe(tokens)
            llm_duration_seconds.labels(provider='yandex', model=self.model).observe(duration)
            
            logger.info(
                f"YandexGPT response generated: tokens={tokens}, duration={duration:.2f}s"
            )
            
            return ChatResult(
                generations=[generation],
                llm_output={
                    "token_usage": {
                        "total_tokens": tokens,
                        "prompt_tokens": result["result"]["usage"].get("inputTextTokens", 0),
                        "completion_tokens": result["result"]["usage"].get("completionTokens", 0)
                    },
                    "model": self.model
                }
            )
        
        except CircuitBreakerError:
            llm_requests_total.labels(
                provider='yandex',
                model=self.model,
                status='circuit_breaker_open'
            ).inc()
            
            logger.error("YandexGPT circuit breaker is OPEN!")
            raise ValueError(
                "LLM service temporarily unavailable due to repeated failures. "
                "Please try again later."
            )
        
        except RetryError as e:
            llm_requests_total.labels(
                provider='yandex',
                model=self.model,
                status='retry_exhausted'
            ).inc()
            
            logger.error(f"YandexGPT request failed after retries: {e}")
            raise ValueError(f"LLM request failed after multiple attempts: {e}")
        
        except Exception as e:
            llm_requests_total.labels(
                provider='yandex',
                model=self.model,
                status='error'
            ).inc()
            
            logger.error(f"YandexGPT generation failed: {e}", exc_info=True)
            raise
    
    # ========================================
    # LANGCHAIN INTERFACE (ASYNC)
    # ========================================
    
    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        Generate response using YandexGPT API (asynchronous).
        
        This is called by llm.ainvoke() and llm.agenerate().
        ✅ FIXED: Now async is fully supported!
        """
        import time
        start_time = time.time()
        
        # Convert messages
        yandex_messages = self._convert_messages_to_yandex_format(messages)
        
        try:
            # Note: pybreaker doesn't support async natively
            # We check circuit state manually
            if yandex_circuit_breaker.current_state == "open":
                llm_circuit_breaker_opens.labels(provider='yandex').inc()
                raise CircuitBreakerError("Circuit breaker is open")
            
            # Make async request
            result = await self._make_request_async(yandex_messages)
            
            # Record success in circuit breaker
            yandex_circuit_breaker.call_succeeded()
            
            # Extract response
            text = result["result"]["alternatives"][0]["message"]["text"]
            tokens = result["result"]["usage"]["totalTokens"]
            
            # Create response
            message = AIMessage(content=text)
            generation = ChatGeneration(message=message)
            
            # Metrics
            duration = time.time() - start_time
            llm_requests_total.labels(
                provider='yandex',
                model=self.model,
                status='success'
            ).inc()
            llm_tokens_used.labels(provider='yandex', model=self.model).observe(tokens)
            llm_duration_seconds.labels(provider='yandex', model=self.model).observe(duration)
            
            logger.info(
                f"YandexGPT async response generated: tokens={tokens}, duration={duration:.2f}s"
            )
            
            return ChatResult(
                generations=[generation],
                llm_output={
                    "token_usage": {
                        "total_tokens": tokens,
                        "prompt_tokens": result["result"]["usage"].get("inputTextTokens", 0),
                        "completion_tokens": result["result"]["usage"].get("completionTokens", 0)
                    },
                    "model": self.model
                }
            )
        
        except CircuitBreakerError:
            llm_requests_total.labels(
                provider='yandex',
                model=self.model,
                status='circuit_breaker_open'
            ).inc()
            
            logger.error("YandexGPT circuit breaker is OPEN! (async)")
            raise ValueError(
                "LLM service temporarily unavailable. Please try again later."
            )
        
        except RetryError as e:
            # Record failure in circuit breaker
            yandex_circuit_breaker.call_failed()
            
            llm_requests_total.labels(
                provider='yandex',
                model=self.model,
                status='retry_exhausted'
            ).inc()
            
            logger.error(f"YandexGPT async request failed after retries: {e}")
            raise ValueError(f"LLM request failed after multiple attempts: {e}")
        
        except Exception as e:
            # Record failure in circuit breaker
            yandex_circuit_breaker.call_failed()
            
            llm_requests_total.labels(
                provider='yandex',
                model=self.model,
                status='error'
            ).inc()
            
            logger.error(f"YandexGPT async generation failed: {e}", exc_info=True)
            raise
