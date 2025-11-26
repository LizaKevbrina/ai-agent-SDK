"""
LangChain Chains
Declarative composition of operations

Chains позволяют декларативно описать пайплайн обработки:
- Intent Classification Chain
- RAG Chain (с условной логикой)
- Response Generation Chain
- Full Pipeline Chain (композиция)

Usage:
    chain = create_full_pipeline_chain()
    result = await chain.ainvoke({"input": "Какие квартиры?"})
"""

from langchain.chains import LLMChain, SequentialChain
from langchain.prompts import ChatPromptTemplate, PromptTemplate
from langchain.schema import StrOutputParser
from langchain.schema.runnable import (
    RunnablePassthrough,
    RunnableLambda,
    RunnableBranch,
    RunnableParallel
)
from typing import Dict, Any, List
import logging

from llm.models import ChatYandexGPT
from tools.real_estate import search_documents
from rag.retrievers import get_real_estate_retriever
from config.prompts import get_prompt

logger = logging.getLogger(__name__)


# ========================================
# CHAIN 1: INTENT CLASSIFICATION
# ========================================

def create_intent_classification_chain(use_openai: bool = False):
    """
    Intent Classification Chain
    
    Определяет намерение пользователя:
    - real_estate: вопросы о недвижимости
    - general: общие вопросы
    
    Input: {"input": "текст"}
    Output: {"intent": "real_estate"}
    """
    if use_openai:
        from langchain.chat_models import ChatOpenAI
        llm = ChatOpenAI(model="gpt-4", temperature=0.1)
    else:
        llm = ChatYandexGPT(temperature=0.1, max_tokens=50)
    
    prompt = ChatPromptTemplate.from_template("""Классифицируй намерение пользователя.

Вопрос: {input}

Ответь ТОЛЬКО одним словом:
- "real_estate" - если вопрос о недвижимости (ЖК, квартиры, цены, локации)
- "general" - если общий вопрос (приветствие, small talk)

Ответ:""")
    
    chain = (
        prompt
        | llm
        | StrOutputParser()
        | RunnableLambda(lambda x: {"intent": x.strip().lower()})
    )
    
    return chain


# ========================================
# CHAIN 2: RAG RETRIEVAL
# ========================================

def create_rag_chain(use_openai: bool = False):
    """
    RAG Chain
    
    Извлекает контекст из базы знаний
    
    Input: {"query": "текст"}
    Output: {"context": "найденная информация"}
    """
    
    def retrieve_context(query: str) -> Dict[str, str]:
        """Извлечь контекст из RAG"""
        try:
            retriever = get_real_estate_retriever()
            docs = retriever.get_relevant_documents(query)
            
            if docs:
                context = "\n\n".join([doc.page_content for doc in docs])
                return {
                    "context": context,
                    "documents_found": len(docs),
                    "rag_used": True
                }
            else:
                return {
                    "context": "",
                    "documents_found": 0,
                    "rag_used": True
                }
        
        except Exception as e:
            logger.error(f"RAG chain error: {e}")
            return {
                "context": "",
                "documents_found": 0,
                "rag_used": False
            }
    
    chain = RunnableLambda(lambda x: retrieve_context(x["query"]))
    
    return chain


# ========================================
# CHAIN 3: RESPONSE GENERATION
# ========================================

def create_response_chain(use_openai: bool = False, prompt_version: str = "v1"):
    """
    Response Generation Chain
    
    Генерирует ответ на основе:
    - System prompt
    - Context (если есть)
    - User input
    
    Input: {"input": "...", "context": "...", "system_prompt": "..."}
    Output: {"response": "..."}
    """
    if use_openai:
        from langchain.chat_models import ChatOpenAI
        llm = ChatOpenAI(model="gpt-4", temperature=0.7, max_tokens=2000)
    else:
        llm = ChatYandexGPT(temperature=0.7, max_tokens=2000)
    
    # Получить system prompt
    system_prompt = get_prompt(prompt_version)
    
    # Промпт с условным контекстом
    prompt = ChatPromptTemplate.from_messages([
        ("system", "{system_prompt}"),
        ("user", """{input}

{context_section}""")
    ])
    
    def add_context_section(inputs: Dict) -> Dict:
        """Добавить секцию контекста если есть"""
        if inputs.get("context") and inputs["context"].strip():
            inputs["context_section"] = f"\n**Контекст из базы знаний:**\n{inputs['context']}"
        else:
            inputs["context_section"] = ""
        
        inputs["system_prompt"] = system_prompt
        
        return inputs
    
    chain = (
        RunnableLambda(add_context_section)
        | prompt
        | llm
        | StrOutputParser()
        | RunnableLambda(lambda x: {"response": x})
    )
    
    return chain


# ========================================
# FULL PIPELINE CHAIN
# ========================================

def create_full_pipeline_chain(use_openai: bool = False, prompt_version: str = "v1"):
    """
    Full Pipeline Chain - композиция всех цепочек
    
    Flow:
    1. Классификация намерения
    2. Условный RAG (только если real_estate)
    3. Генерация ответа
    
    Input: {"input": "текст пользователя"}
    Output: {
        "response": "ответ агента",
        "intent": "real_estate",
        "context_used": True,
        "documents_found": 3
    }
    """
    
    # Создать компоненты
    intent_chain = create_intent_classification_chain(use_openai)
    rag_chain = create_rag_chain(use_openai)
    response_chain = create_response_chain(use_openai, prompt_version)
    
    # Условная логика: RAG только для real_estate
    conditional_rag = RunnableBranch(
        # Condition 1: если intent = real_estate → вызвать RAG
        (
            lambda x: x.get("intent") == "real_estate",
            RunnableLambda(lambda x: {**x, "query": x["input"]}) | rag_chain
        ),
        # Else: пропустить RAG
        RunnableLambda(lambda x: {
            **x,
            "context": "",
            "documents_found": 0,
            "rag_used": False
        })
    )
    
    # Полная цепочка
    full_chain = (
        # Шаг 1: Классификация намерения
        RunnablePassthrough.assign(intent=intent_chain)
        
        # Шаг 2: Условный RAG
        | conditional_rag
        
        # Шаг 3: Генерация ответа
        | RunnablePassthrough.assign(response=response_chain)
        
        # Шаг 4: Финальная обработка (убрать промежуточные ключи)
        | RunnableLambda(lambda x: {
            "response": x["response"]["response"],
            "intent": x["intent"]["intent"],
            "context_used": x.get("rag_used", False),
            "documents_found": x.get("documents_found", 0)
        })
    )
    
    logger.info(f"Full pipeline chain created (use_openai={use_openai}, prompt_version={prompt_version})")
    
    return full_chain


# ========================================
# PARALLEL CHAINS (для A/B тестирования)
# ========================================

def create_ab_test_chain():
    """
    A/B Testing Chain - параллельное выполнение двух вариантов
    
    Полезно для сравнения:
    - YandexGPT vs OpenAI
    - Prompt v1 vs Prompt v2
    - С RAG vs Без RAG
    
    Input: {"input": "текст"}
    Output: {
        "variant_a": {"response": "...", ...},
        "variant_b": {"response": "...", ...}
    }
    """
    
    # Вариант A: YandexGPT + RAG
    variant_a = create_full_pipeline_chain(use_openai=False, prompt_version="v1")
    
    # Вариант B: OpenAI + RAG
    variant_b = create_full_pipeline_chain(use_openai=True, prompt_version="v1")
    
    # Параллельное выполнение
    parallel_chain = RunnableParallel(
        variant_a=variant_a,
        variant_b=variant_b
    )
    
    return parallel_chain


# ========================================
# STREAMING CHAIN (для real-time ответов)
# ========================================

def create_streaming_chain(use_openai: bool = False):
    """
    Streaming Chain - генерация ответа с потоковой передачей
    
    Полезно для UI: пользователь видит ответ по мере генерации
    
    Usage:
        chain = create_streaming_chain()
        async for chunk in chain.astream({"input": "..."}):
            print(chunk, end="", flush=True)
    """
    if use_openai:
        from langchain.chat_models import ChatOpenAI
        llm = ChatOpenAI(model="gpt-4", temperature=0.7, streaming=True)
    else:
        # YandexGPT не поддерживает streaming
        llm = ChatYandexGPT(temperature=0.7, max_tokens=2000)
    
    prompt = ChatPromptTemplate.from_template("""Ты — AI-ассистент по недвижимости.

Вопрос: {input}

Ответ:""")
    
    chain = prompt | llm | StrOutputParser()
    
    return chain


# ========================================
# HELPER: CHAIN WITH RETRY
# ========================================

def create_chain_with_retry(base_chain, max_retries: int = 3):
    """
    Обернуть цепочку в retry логику
    
    Полезно для устойчивости к временным сбоям
    """
    from tenacity import retry, stop_after_attempt, wait_exponential
    
    @retry(
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def execute_with_retry(inputs: Dict) -> Dict:
        """Выполнить цепочку с retry"""
        return await base_chain.ainvoke(inputs)
    
    return RunnableLambda(execute_with_retry)


# ========================================
# USAGE EXAMPLES
# ========================================

if __name__ == "__main__":
    """
    Примеры использования цепочек
    """
    import asyncio
    
    async def example_intent_classification():
        """Пример: классификация намерения"""
        chain = create_intent_classification_chain()
        
        result = await chain.ainvoke({"input": "Какие квартиры в ЖК Солнечный?"})
        print(f"Intent: {result['intent']}")  # real_estate
        
        result = await chain.ainvoke({"input": "Привет!"})
        print(f"Intent: {result['intent']}")  # general
    
    async def example_full_pipeline():
        """Пример: полный пайплайн"""
        chain = create_full_pipeline_chain()
        
        result = await chain.ainvoke({"input": "Какие квартиры есть?"})
        
        print(f"Response: {result['response']}")
        print(f"Intent: {result['intent']}")
        print(f"Context used: {result['context_used']}")
        print(f"Documents found: {result['documents_found']}")
    
    async def example_ab_test():
        """Пример: A/B тестирование"""
        chain = create_ab_test_chain()
        
        result = await chain.ainvoke({"input": "Посчитай ипотеку на 5 млн"})
        
        print("=== Variant A (YandexGPT) ===")
        print(result["variant_a"]["response"])
        
        print("\n=== Variant B (OpenAI) ===")
        print(result["variant_b"]["response"])
    
    async def example_streaming():
        """Пример: streaming ответ"""
        chain = create_streaming_chain(use_openai=True)
        
        print("Streaming response: ", end="", flush=True)
        
        async for chunk in chain.astream({"input": "Расскажи о ЖК"}):
            print(chunk, end="", flush=True)
        
        print()  # Newline
    
    # Запуск примеров
    asyncio.run(example_intent_classification())
    asyncio.run(example_full_pipeline())
    asyncio.run(example_ab_test())
    asyncio.run(example_streaming())
