"""
Multi-Agent Architecture
Supervisor + Specialized Agents

Архитектура:
- Supervisor Agent: принимает решения о делегировании
- Search Agent: специализируется на поиске недвижимости
- Calculation Agent: специализируется на расчётах
- Sales Agent: специализируется на продажах и работе с возражениями

Usage:
    result = await multi_agent_pipeline(
        user_input="Какие квартиры в ЖК Солнечный?",
        session_id="user_123"
    )
"""

import json
import logging
import time
from typing import Dict, List

from langchain.agents import create_openai_functions_agent, AgentExecutor
from langchain.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import SystemMessage, HumanMessage, AIMessage
from langchain.memory import ConversationBufferMemory

from llm.models import ChatYandexGPT
from tools.real_estate import search_documents, calculate_mortgage, get_property_details
from memory.history import get_or_create_history

logger = logging.getLogger(__name__)


# ========================================
# SUPERVISOR AGENT
# ========================================
class SupervisorAgent:
    """
    Supervisor Agent - принимает решения о делегировании
    
    Анализирует запрос пользователя и решает, какому агенту делегировать:
    - search_agent: вопросы о поиске недвижимости
    - calculation_agent: расчёты ипотеки, сравнение вариантов
    - sales_agent: работа с возражениями, закрытие сделки
    """
    
    def __init__(self, use_openai: bool = False):
        if use_openai:
            self.llm = ChatOpenAI(model="gpt-4", temperature=0.1)
        else:
            self.llm = ChatYandexGPT(temperature=0.1, max_tokens=500)
        
        self.system_prompt = """Ты — агент-супервизор в системе продажи недвижимости.

Твоя задача: проанализировать запрос пользователя и решить, какому специализированному агенту его делегировать.

Доступные агенты:
1. search_agent: для поиска информации о ЖК, квартирах, ценах, локациях, планировках
2. calculation_agent: для расчётов ипотеки, сравнения вариантов, финансовых вопросов
3. sales_agent: для работы с возражениями, закрытия сделки, общих вопросов

Верни ТОЛЬКО JSON (без markdown):
{
  "delegate_to": "search_agent",  // или calculation_agent, или sales_agent
  "reasoning": "краткое объяснение",
  "transformed_query": "переформулированный запрос для агента"
}

Правила:
- Если непонятно → делегируй sales_agent
- Если несколько категорий → выбери основную
- transformed_query должен быть чёткий и конкретный"""
    
    async def decide(self, user_input: str, conversation_history: List[Dict] = None) -> Dict:
        """Принять решение о делегировании"""
        messages = [SystemMessage(content=self.system_prompt)]
        
        if conversation_history:
            for msg in conversation_history[-3:]:  # Последние 3 сообщения
                if msg['role'] == 'user':
                    messages.append(HumanMessage(content=msg['content']))
                elif msg['role'] == 'assistant':
                    messages.append(AIMessage(content=msg['content']))
        
        messages.append(HumanMessage(content=user_input))
        
        try:
            response = await self.llm.ainvoke(messages)
            response_text = response.content.strip()
            
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
                response_text = response_text.strip()
            
            decision = json.loads(response_text)
            
            logger.info(
                f"Supervisor decision: delegate_to={decision['delegate_to']}, "
                f"reasoning={decision['reasoning']}"
            )
            
            return decision
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse supervisor decision: {e}")
            return {
                "delegate_to": "sales_agent",
                "reasoning": "Failed to parse decision, using fallback",
                "transformed_query": user_input
            }
        
        except Exception as e:
            logger.error(f"Supervisor decision failed: {e}")
            return {
                "delegate_to": "sales_agent",
                "reasoning": f"Error: {e}",
                "transformed_query": user_input
            }


# ========================================
# SPECIALIZED AGENTS
# ========================================
class SearchAgent:
    """Search Agent - специализируется на поиске недвижимости"""
    
    def __init__(self, use_openai: bool = False):
        self.llm = ChatOpenAI(model="gpt-4", temperature=0.7) if use_openai else ChatYandexGPT(temperature=0.7, max_tokens=2000)
        self.tools = [search_documents, get_property_details]
        self.system_prompt = """Ты — эксперт по поиску недвижимости.
Твоя задача: помочь клиенту найти подходящую недвижимость.
Используй search_documents и get_property_details.
Будь конкретен: указывай цены, площадь, этаж. Не выдумывай информацию."""
    
    async def execute(self, query: str, session_id: str, memory) -> str:
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=self.system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            HumanMessage(content="{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
        agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=prompt)
        executor = AgentExecutor(agent=agent, tools=self.tools, memory=memory, verbose=True, max_iterations=5, max_execution_time=60)
        result = await executor.ainvoke({"input": query})
        return result["output"]


class CalculationAgent:
    """Calculation Agent - специализируется на расчётах"""
    
    def __init__(self, use_openai: bool = False):
        self.llm = ChatOpenAI(model="gpt-4", temperature=0.3) if use_openai else ChatYandexGPT(temperature=0.3, max_tokens=1500)
        self.tools = [calculate_mortgage]
        self.system_prompt = """Ты — финансовый консультант по ипотеке.
Используй calculate_mortgage для точных расчётов.
Объясняй простым языком, давай советы по оптимизации."""
    
    async def execute(self, query: str, session_id: str, memory) -> str:
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=self.system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            HumanMessage(content="{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
        agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=prompt)
        executor = AgentExecutor(agent=agent, tools=self.tools, memory=memory, verbose=True, max_iterations=5, max_execution_time=60)
        result = await executor.ainvoke({"input": query})
        return result["output"]


class SalesAgent:
    """Sales Agent - специализируется на продажах"""
    
    def __init__(self, use_openai: bool = False):
        self.llm = ChatOpenAI(model="gpt-4", temperature=0.7) if use_openai else ChatYandexGPT(temperature=0.7, max_tokens=2000)
        from tools.real_estate import get_tools
        self.tools = get_tools()
        self.system_prompt = """Ты — профессиональный менеджер по продаже недвижимости.
Веди клиента через воронку продаж, используя доступные инструменты.
Стиль: дружелюбный, профессиональный, помогает принять решение."""
    
    async def execute(self, query: str, session_id: str, memory) -> str:
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=self.system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            HumanMessage(content="{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
        agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=prompt)
        executor = AgentExecutor(agent=agent, tools=self.tools, memory=memory, verbose=True, max_iterations=5, max_execution_time=60)
        result = await executor.ainvoke({"input": query})
        return result["output"]


# ========================================
# MULTI-AGENT PIPELINE
# ========================================
async def multi_agent_pipeline(
    user_input: str,
    session_id: str,
    prompt_version: str = "v1",
    use_openai: bool = False,
    correlation_id: str = None
) -> Dict:
    """Multi-agent pipeline с Supervisor"""
    
    start_time = time.time()
    
    # 1. Получить историю диалога
    chat_history = await get_or_create_history(session_id=session_id, prompt_version=prompt_version)
    history_messages = await chat_history.aget_messages()
    conversation_history = [
        {"role": "user" if msg.type == "human" else "assistant", "content": msg.content}
        for msg in history_messages
    ]
    
    # 2. Supervisor принимает решение
    supervisor = SupervisorAgent(use_openai=use_openai)
    decision = await supervisor.decide(user_input, conversation_history)
    
    # 3. Создать memory для агента
    memory = ConversationBufferMemory(chat_memory=chat_history, return_messages=True, memory_key="chat_history")
    
    # 4. Делегировать специализированному агенту
    agent_type = decision["delegate_to"]
    transformed_query = decision["transformed_query"]
    
    logger.info(
        f"[{correlation_id}] Multi-agent: delegating to {agent_type}, "
        f"query: {transformed_query[:50]}..."
    )
    
    if agent_type == "search_agent":
        agent = SearchAgent(use_openai=use_openai)
    elif agent_type == "calculation_agent":
        agent = CalculationAgent(use_openai=use_openai)
    else:
        agent = SalesAgent(use_openai=use_openai)
    
    # 5. Выполнить
    response = await agent.execute(transformed_query, session_id, memory)
    
    # 6. Сохранить в историю
    await chat_history.aadd_user_message(user_input)
    await chat_history.aadd_ai_message(response)
    await chat_history.close()
    
    duration_ms = int((time.time() - start_time) * 1000)
    
    logger.info(
        f"[{correlation_id}] Multi-agent completed: agent={agent_type}, "
        f"duration={duration_ms}ms"
    )
    
    return {
        "response": response,
        "delegated_to": agent_type,
        "reasoning": decision["reasoning"],
        "duration_ms": duration_ms,
        "session_id": session_id,
        "correlation_id": correlation_id
    }


# ========================================
# FACTORY FUNCTION
# ========================================
def create_multi_agent_system(use_openai: bool = False):
    """
    Factory для создания multi-agent системы
    Usage:
        system = create_multi_agent_system()
        result = await system.execute("Какие квартиры?", "user_123")
    """
    
    class MultiAgentSystem:
        def __init__(self, use_openai: bool = False):
            self.use_openai = use_openai
            self.supervisor = SupervisorAgent(use_openai)
            self.search_agent = SearchAgent(use_openai)
            self.calculation_agent = CalculationAgent(use_openai)
            self.sales_agent = SalesAgent(use_openai)
        
        async def execute(
            self,
            user_input: str,
            session_id: str,
            prompt_version: str = "v1",
            correlation_id: str = None
        ) -> Dict:
            return await multi_agent_pipeline(
                user_input=user_input,
                session_id=session_id,
                prompt_version=prompt_version,
                use_openai=self.use_openai,
                correlation_id=correlation_id
            )
    
    return MultiAgentSystem(use_openai=use_openai)
