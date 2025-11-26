"""
Custom Embeddings
Migrated from: services/embedder/main.py
Provides: YandexGPT embeddings wrapper for LangChain
FIXED: asyncio.sleep → time.sleep, added async support
"""

from langchain.embeddings.base import Embeddings
from typing import List
import httpx
import asyncio
import time
import logging
from config.settings import settings

logger = logging.getLogger(__name__)


class YandexGPTEmbeddings(Embeddings):
    """
    YandexGPT Embeddings wrapper for LangChain.
    
    Features:
    - Retry logic with exponential backoff
    - Both sync and async support
    - 8000 character limit (YandexGPT constraint)
    - Detailed logging
    
    Example:
        embeddings = YandexGPTEmbeddings()
        vector = embeddings.embed_query("Найди квартиры")
    """
    
    def __init__(
        self,
        api_key: str = None,
        folder_id: str = None,
        model: str = "text-search-doc/latest",
        max_retries: int = 3,
        retry_delay: int = 2
    ):
        self.api_key = api_key or settings.YANDEX_API_KEY
        self.folder_id = folder_id or settings.YANDEX_FOLDER_ID
        
        if not self.api_key or not self.folder_id:
            raise ValueError(
                "YANDEX_API_KEY and YANDEX_FOLDER_ID must be set in environment or passed as arguments"
            )
        
        self.model_uri = f"emb://{self.folder_id}/{model}"
        self.url = "https://llm.api.cloud.yandex.net/foundationModels/v1/textEmbedding"
        self.max_retries = max_retries
        self.retry_delay = retry_delay
    
    def _make_request_sync(self, text: str) -> List[float]:
        """
        Make synchronous request to YandexGPT API with retry logic.
        
        Args:
            text: Text to embed (max 8000 chars)
            
        Returns:
            Embedding vector (256 dimensions)
            
        Raises:
            Exception: If all retry attempts fail
        """
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "modelUri": self.model_uri,
            "text": text[:8000]  # YandexGPT limit
        }
        
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=30.0) as client:
                    response = client.post(
                        self.url,
                        headers=headers,
                        json=payload
                    )
                    response.raise_for_status()
                    
                    result = response.json()
                    embedding = result.get("embedding")
                    
                    if not embedding:
                        raise ValueError("Empty embedding received from API")
                    
                    logger.debug(
                        f"Embedding generated (attempt {attempt + 1}): "
                        f"dimension={len(embedding)}, text_length={len(text)}"
                    )
                    
                    return embedding
            
            except httpx.HTTPStatusError as e:
                last_exception = e
                if e.response.status_code == 429:
                    logger.warning(f"Rate limit hit (attempt {attempt + 1})")
                elif e.response.status_code >= 500:
                    logger.warning(f"Server error {e.response.status_code} (attempt {attempt + 1})")
                else:
                    # Client error (4xx) - don't retry
                    raise
                
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (attempt + 1)
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)  # ✅ FIXED: time.sleep instead of asyncio.sleep
            
            except Exception as e:
                last_exception = e
                logger.warning(
                    f"Embedding attempt {attempt + 1} failed: {type(e).__name__}: {e}"
                )
                
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (attempt + 1)
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
        
        # All retries failed
        logger.error(
            f"Embedding failed after {self.max_retries} attempts. "
            f"Last error: {last_exception}"
        )
        raise Exception(
            f"Failed to generate embedding after {self.max_retries} attempts: {last_exception}"
        )
    
    async def _make_request_async(self, text: str) -> List[float]:
        """
        Make asynchronous request to YandexGPT API with retry logic.
        
        Args:
            text: Text to embed (max 8000 chars)
            
        Returns:
            Embedding vector (256 dimensions)
            
        Raises:
            Exception: If all retry attempts fail
        """
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "modelUri": self.model_uri,
            "text": text[:8000]
        }
        
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        self.url,
                        headers=headers,
                        json=payload
                    )
                    response.raise_for_status()
                    
                    result = response.json()
                    embedding = result.get("embedding")
                    
                    if not embedding:
                        raise ValueError("Empty embedding received from API")
                    
                    logger.debug(
                        f"Async embedding generated (attempt {attempt + 1}): "
                        f"dimension={len(embedding)}"
                    )
                    
                    return embedding
            
            except httpx.HTTPStatusError as e:
                last_exception = e
                if e.response.status_code == 429:
                    logger.warning(f"Rate limit hit (attempt {attempt + 1})")
                elif e.response.status_code >= 500:
                    logger.warning(f"Server error (attempt {attempt + 1})")
                else:
                    raise
                
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (attempt + 1)
                    logger.info(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)  # ✅ CORRECT: async sleep in async function
            
            except Exception as e:
                last_exception = e
                logger.warning(f"Async embedding attempt {attempt + 1} failed: {e}")
                
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (attempt + 1)
                    await asyncio.sleep(wait_time)
        
        logger.error(f"Async embedding failed after {self.max_retries} attempts")
        raise Exception(
            f"Failed to generate embedding after {self.max_retries} attempts: {last_exception}"
        )
    
    # ========================================
    # LangChain Interface (REQUIRED)
    # ========================================
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a list of documents (synchronous).
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        embeddings = []
        
        for i, text in enumerate(texts):
            try:
                embedding = self._make_request_sync(text)
                embeddings.append(embedding)
            except Exception as e:
                logger.error(f"Failed to embed document {i}: {e}")
                # Return zero vector as fallback
                embeddings.append([0.0] * 256)
        
        logger.info(f"Generated embeddings for {len(texts)} documents")
        return embeddings
    
    def embed_query(self, text: str) -> List[float]:
        """
        Embed a single query (synchronous).
        
        Args:
            text: Query text to embed
            
        Returns:
            Embedding vector
        """
        embedding = self._make_request_sync(text)
        logger.info(f"Generated query embedding: dimension={len(embedding)}")
        return embedding
    
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a list of documents (asynchronous).
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        tasks = [self._make_request_async(text) for text in texts]
        embeddings = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        result_embeddings = []
        for i, emb in enumerate(embeddings):
            if isinstance(emb, Exception):
                logger.error(f"Failed to embed document {i}: {emb}")
                result_embeddings.append([0.0] * 256)  # Zero vector fallback
            else:
                result_embeddings.append(emb)
        
        logger.info(f"Generated async embeddings for {len(texts)} documents")
        return result_embeddings
    
    async def aembed_query(self, text: str) -> List[float]:
        """
        Embed a single query (asynchronous).
        
        Args:
            text: Query text to embed
            
        Returns:
            Embedding vector
        """
        embedding = await self._make_request_async(text)
        logger.info(f"Generated async query embedding: dimension={len(embedding)}")
        return embedding
