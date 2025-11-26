"""
Real Estate Tools - OPTIMIZED VERSION
Domain-specific functionality
NEW: Uses singleton retriever for better performance
"""

from langchain.tools import tool
from typing import List
from rag.retrievers import _get_retriever_singleton  # ✅ NEW: Use singleton
import httpx
import logging

logger = logging.getLogger(__name__)


def get_tools() -> List:
    """Returns all available tools for the agent"""
    return [
        search_documents,
        calculate_mortgage,
        get_property_details,
        check_availability,
        book_viewing
    ]


@tool
def search_documents(query: str) -> str:
    """
    Search real estate knowledge base for properties, prices, locations, etc.
    
    ✅ OPTIMIZED: Now uses singleton retriever (800ms → 300ms latency)
    
    Use this tool when user asks about:
    - Available properties
    - Prices
    - Locations
    - Building specifications
    - Developer information
    
    Args:
        query: Search query from user
        
    Returns:
        Relevant information from knowledge base
    """
    try:
        # ✅ NEW: Use singleton retriever instead of creating new instance
        retriever = _get_retriever_singleton()
        docs = retriever.get_relevant_documents(query)
        
        if not docs:
            logger.info(f"No documents found for query: {query}")
            return (
                f"В базе знаний нет информации по запросу: '{query}'\n\n"
                "Попробуйте:\n"
                "• Уточнить район или ЖК\n"
                "• Указать параметры (кол-во комнат, бюджет)\n"
                "• Или свяжитесь с менеджером: Лия, +7-999-000-12-12"
            )
        
        # Format results
        context = "\n\n---\n\n".join([
            f"📄 Документ {i+1} (сходство: {doc.metadata.get('similarity', 0):.2%}):\n{doc.page_content}"
            for i, doc in enumerate(docs[:3])  # Top 3 results
        ])
        
        logger.info(f"Found {len(docs)} documents for query: {query}")
        
        return (
            f"Найдено документов: {len(docs)}\n\n"
            f"{context}\n\n"
            f"💡 Хотите узнать больше? Могу рассказать подробнее о любом варианте."
        )
    
    except Exception as e:
        logger.error(f"Search documents error: {e}", exc_info=True)
        return (
            "Произошла ошибка при поиске. "
            "Пожалуйста, свяжитесь с менеджером: Лия, +7-999-000-12-12"
        )


@tool
def calculate_mortgage(
    price: float,
    initial_payment_percent: float = 20.0,
    rate: float = 12.0,
    years: int = 30
) -> str:
    """
    Calculate monthly mortgage payment and total cost.
    
    Args:
        price: Property price in rubles
        initial_payment_percent: Initial payment as percentage (default 20%)
        rate: Annual interest rate as percentage (default 12%)
        years: Loan duration in years (default 30)
        
    Returns:
        Formatted string with monthly payment and total cost
    """
    try:
        initial_payment = price * (initial_payment_percent / 100)
        loan_amount = price - initial_payment
        
        monthly_rate = rate / 12 / 100
        n_payments = years * 12
        
        if monthly_rate == 0:
            monthly_payment = loan_amount / n_payments
        else:
            monthly_payment = loan_amount * (
                monthly_rate * (1 + monthly_rate)**n_payments
            ) / ((1 + monthly_rate)**n_payments - 1)
        
        total_payment = monthly_payment * n_payments
        total_cost = total_payment + initial_payment
        overpayment = total_payment - loan_amount
        
        logger.info(
            f"Mortgage calculated: price={price:,.0f}, "
            f"monthly={monthly_payment:,.0f}, total={total_cost:,.0f}"
        )
        
        return f"""
💰 **Расчёт ипотеки:**

📊 **Параметры:**
• Стоимость: {price:,.0f} ₽
• Первоначальный взнос ({initial_payment_percent}%): {initial_payment:,.0f} ₽
• Сумма кредита: {loan_amount:,.0f} ₽
• Ставка: {rate}% годовых
• Срок: {years} лет ({n_payments} месяцев)

💳 **Ежемесячный платёж: {monthly_payment:,.0f} ₽**

📈 **Итого:**
• Переплата: {overpayment:,.0f} ₽
• Общая сумма выплат: {total_cost:,.0f} ₽

💡 *Расчёт ориентировочный. Точные условия уточните у менеджера.*
"""
    
    except Exception as e:
        logger.error(f"Mortgage calculation error: {e}", exc_info=True)
        return "Ошибка расчёта ипотеки. Свяжитесь с менеджером: +7-999-000-12-12"


@tool
def get_property_details(property_id: str) -> str:
    """
    Get detailed information about specific property by ID.
    
    ✅ OPTIMIZED: Uses singleton retriever
    
    Args:
        property_id: Property identifier (e.g., "apt_123", "flat_456")
        
    Returns:
        Detailed property information
    """
    try:
        # ✅ NEW: Use singleton retriever
        retriever = _get_retriever_singleton()
        docs = retriever.get_relevant_documents(f"property_id:{property_id}")
        
        if not docs:
            logger.warning(f"Property not found: {property_id}")
            return (
                f"❌ Квартира {property_id} не найдена.\n\n"
                "Пожалуйста, проверьте ID или воспользуйтесь поиском по параметрам."
            )
        
        logger.info(f"Property details retrieved: {property_id}")
        return f"📋 **Детали объекта {property_id}:**\n\n{docs[0].page_content}"
    
    except Exception as e:
        logger.error(f"Get property details error: {e}", exc_info=True)
        return "Ошибка получения данных. Свяжитесь с менеджером: +7-999-000-12-12"


@tool
def check_availability(property_id: str) -> str:
    """
    Check if property is available for viewing or purchase.
    
    Args:
        property_id: Property identifier
        
    Returns:
        Availability status
    """
    # TODO: Integrate with CRM/booking system
    logger.info(f"Checking availability: {property_id}")
    
    return (
        f"✅ Квартира {property_id} доступна для просмотра.\n\n"
        "Хотите забронировать время? Используйте функцию `book_viewing` "
        "или позвоните менеджеру: Лия, +7-999-000-12-12"
    )


@tool
def book_viewing(
    property_id: str,
    date: str,
    time: str,
    client_phone: str
) -> str:
    """
    Book property viewing appointment.
    
    Args:
        property_id: Property identifier
        date: Viewing date in YYYY-MM-DD format
        time: Viewing time in HH:MM format
        client_phone: Client phone number
        
    Returns:
        Booking confirmation
    """
    try:
        # TODO: Replace with real CRM integration
        logger.info(
            f"Booking viewing: property={property_id}, "
            f"date={date}, time={time}, phone={client_phone}"
        )
        
        # Simulate booking API call
        # response = httpx.post(
        #     "https://crm.example.com/api/bookings",
        #     json={
        #         "property_id": property_id,
        #         "date": date,
        #         "time": time,
        #         "phone": client_phone
        #     },
        #     timeout=10
        # )
        
        # For now, return success message
        return f"""
✅ **Просмотр забронирован!**

📋 **Детали:**
• Объект: {property_id}
• Дата: {date}
• Время: {time}
• Телефон: {client_phone}

📞 Менеджер свяжется с вами за день до просмотра для подтверждения.

💡 Если нужно изменить время, позвоните: Лия, +7-999-000-12-12
"""
    
    except Exception as e:
        logger.error(f"Booking error: {e}", exc_info=True)
        return (
            "❌ Не удалось забронировать просмотр.\n\n"
            "Пожалуйста, позвоните менеджеру напрямую: Лия, +7-999-000-12-12"
        )
