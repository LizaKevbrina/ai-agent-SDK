"""
Quick smoke test - verify all components work
Run this FIRST before full test suite
"""

import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from rag.embeddings import YandexGPTEmbeddings
from rag.retrievers import get_real_estate_retriever
from llm.models import ChatYandexGPT
from tools.security import validate_user_input
from tools.real_estate import calculate_mortgage
from langchain.schema import HumanMessage


def check_env_variables():
    """Check that required env variables are set"""
    required = {
        "YANDEX_API_KEY": os.getenv("YANDEX_API_KEY"),
        "YANDEX_FOLDER_ID": os.getenv("YANDEX_FOLDER_ID"),
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_KEY": os.getenv("SUPABASE_KEY"),
    }
    
    missing = [k for k, v in required.items() if not v]
    
    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        print("\nSet them in .env file or export:")
        for var in missing:
            print(f"  export {var}=your_value_here")
        return False
    
    print("✅ All environment variables set")
    return True


async def test_embeddings():
    """Test embeddings generation"""
    print("\n🧪 Testing embeddings...")
    
    try:
        embeddings = YandexGPTEmbeddings()
        
        # Sync test
        result_sync = embeddings.embed_query("тест")
        assert len(result_sync) == 256
        print(f"  ✅ Sync embedding: dimension={len(result_sync)}")
        
        # Async test
        result_async = await embeddings.aembed_query("тест")
        assert len(result_async) == 256
        print(f"  ✅ Async embedding: dimension={len(result_async)}")
        
        return True
    
    except Exception as e:
        print(f"  ❌ Embeddings failed: {e}")
        return False


async def test_llm():
    """Test LLM generation"""
    print("\n🧪 Testing LLM...")
    
    try:
        llm = ChatYandexGPT(temperature=0.7, max_tokens=50)
        messages = [HumanMessage(content="Привет! Ответь одним словом: привет")]
        
        # Sync test
        result_sync = llm.invoke(messages)
        assert result_sync.content
        print(f"  ✅ Sync LLM: {result_sync.content[:50]}...")
        
        # Async test
        result_async = await llm.ainvoke(messages)
        assert result_async.content
        print(f"  ✅ Async LLM: {result_async.content[:50]}...")
        
        return True
    
    except Exception as e:
        print(f"  ❌ LLM failed: {e}")
        return False


def test_security():
    """Test security validation"""
    print("\n🧪 Testing security...")
    
    try:
        # Normal input
        result = validate_user_input("Найди квартиры")
        assert result == "Найди квартиры"
        print("  ✅ Normal input passed")
        
        # SQL injection
        try:
            validate_user_input("SELECT * FROM users")
            print("  ❌ SQL injection not blocked!")
            return False
        except ValueError:
            print("  ✅ SQL injection blocked")
        
        # XSS
        try:
            validate_user_input("<script>alert('xss')</script>")
            print("  ❌ XSS not blocked!")
            return False
        except ValueError:
            print("  ✅ XSS blocked")
        
        return True
    
    except Exception as e:
        print(f"  ❌ Security test failed: {e}")
        return False


def test_retriever():
    """Test retriever"""
    print("\n🧪 Testing retriever...")
    
    try:
        retriever = get_real_estate_retriever()
        docs = retriever.get_relevant_documents("квартира")
        
        print(f"  ✅ Retriever works: found {len(docs)} documents")
        
        if docs:
            doc = docs[0]
            similarity = doc.metadata.get('similarity', 0)
            print(f"  ✅ Top document similarity: {similarity:.3f}")
        
        return True
    
    except Exception as e:
        print(f"  ❌ Retriever failed: {e}")
        return False


def test_tools():
    """Test tools"""
    print("\n🧪 Testing tools...")
    
    try:
        # Mortgage calculator
        result = calculate_mortgage.invoke({
            "price": 5000000,
            "initial_payment_percent": 20,
            "rate": 12,
            "years": 30
        })
        
        assert "Расчёт ипотеки" in result
        assert "5,000,000" in result
        print("  ✅ Mortgage calculator works")
        
        return True
    
    except Exception as e:
        print(f"  ❌ Tools test failed: {e}")
        return False


async def main():
    """Run all quick tests"""
    print("=" * 60)
    print("🚀 QUICK SMOKE TEST - Migration Part 1")
    print("=" * 60)
    
    # Check environment
    if not check_env_variables():
        return False
    
    # Run tests
    results = []
    
    results.append(test_security())
    results.append(test_tools())
    results.append(await test_embeddings())
    results.append(test_retriever())
    results.append(await test_llm())
    
    # Summary
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"✅ ALL TESTS PASSED ({passed}/{total})")
        print("\n🎉 Migration Part 1 is READY!")
        print("\nNext steps:")
        print("  1. Run full test suite: pytest tests/test_migration_part1.py")
        print("  2. Proceed to Part 2: memory/, logging/, agent/")
        return True
    else:
        print(f"❌ SOME TESTS FAILED ({passed}/{total})")
        print("\n⚠️  Fix issues before proceeding to Part 2")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
