"""Integration test — verify actual LLM response through LiteLLM Proxy.

Run with: uv run python tests/integration/test_llm_live.py
Requires: docker compose up -d litellm postgres
"""

import asyncio
import sys
import os

# Load .env
from dotenv import load_dotenv
load_dotenv()

from decepticon.llm.factory import LLMFactory
from decepticon.llm.models import LLMModelMapping, ModelAssignment, ProxyConfig


async def test_health():
    """Test 1: LiteLLM Proxy health check."""
    print("=" * 60)
    print("Test 1: Health Check")
    print("=" * 60)

    factory = LLMFactory(ProxyConfig())
    healthy = await factory.health_check()
    print(f"  Proxy healthy: {healthy}")

    if not healthy:
        print("  ❌ LiteLLM Proxy is not running!")
        print("  Run: docker compose up -d litellm postgres")
        return False

    print("  ✅ Proxy is healthy")
    return True


async def test_list_models():
    """Test 2: List available models on the proxy."""
    print("\n" + "=" * 60)
    print("Test 2: List Models")
    print("=" * 60)

    factory = LLMFactory(ProxyConfig())
    try:
        models = await factory.list_available_models()
        print(f"  Available models ({len(models)}):")
        for m in models:
            print(f"    - {m}")
        print("  ✅ Models listed")
        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


async def test_anthropic_response():
    """Test 3: Get actual LLM response from Anthropic via LiteLLM Proxy."""
    print("\n" + "=" * 60)
    print("Test 3: Anthropic LLM Response (via LiteLLM Proxy)")
    print("=" * 60)

    proxy = ProxyConfig(
        url="http://localhost:4000",
        api_key=os.getenv("LITELLM_MASTER_KEY", "sk-decepticon-master"),
    )

    # Map "recon" role to the recon-model (which maps to claude-sonnet in litellm.yaml)
    mapping = LLMModelMapping(
        recon=ModelAssignment(primary="recon-model", temperature=0.3),
    )

    factory = LLMFactory(proxy, mapping)
    model = factory.get_model("recon")

    print(f"  Model: {model.model_name}")
    print(f"  Proxy: {proxy.url}")
    print("  Sending test prompt...")

    try:
        response = model.invoke("Say 'Hello from Decepticon!' and nothing else.")
        print(f"  Response: {response.content}")
        print("  ✅ LLM response received!")
        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


async def main():
    print("\n🔴 Decepticon 2.0 — LLM Integration Test")
    print("=" * 60)

    results = []

    # Test 1: Health check
    results.append(await test_health())
    if not results[-1]:
        print("\n⚠️ Proxy not running. Aborting remaining tests.")
        sys.exit(1)

    # Test 2: List models
    results.append(await test_list_models())

    # Test 3: Actual LLM response
    results.append(await test_anthropic_response())

    # Summary
    passed = sum(results)
    total = len(results)
    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} passed")
    print("=" * 60)

    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    asyncio.run(main())
