"""Integration test — verify the Decepticon Recon Agent uses the bash tool correctly.

Run with:
  pytest:  PYTHONPATH=. uv run pytest tests/integration/test_agent_bash.py -v -s
  script:  PYTHONPATH=. uv run python tests/integration/test_agent_bash.py

Requires:
  - docker compose up -d sandbox litellm postgres
  - Valid LITELLM_MASTER_KEY / ANTHROPIC_API_KEY in .env
"""

import os
import sys
import asyncio
import subprocess

from langchain_core.messages import HumanMessage

from decepticon.agents.recon import create_recon_agent
from decepticon.tools.bash.tool import TmuxSessionManager

from dotenv import load_dotenv
load_dotenv()

# Try importing pytest; allow running without it as a standalone script
try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False


def _reset_tmux_state():
    """Clear cached tmux session state AND kill tmux in sandbox so each test starts fresh."""
    TmuxSessionManager._initialized.clear()
    # Kill tmux server in the sandbox to ensure clean state
    try:
        subprocess.run(
            ["docker", "exec", "decepticon-sandbox",
             "tmux", "kill-server"],
            capture_output=True, text=True, timeout=5
        )
    except Exception:
        pass  # tmux server might not be running — that's fine


def _ensure_sandbox():
    """Check that the sandbox container is running."""
    result = subprocess.run(
        ["docker", "ps", "--filter", "name=decepticon-sandbox", "--format", "{{.Names}}"],
        capture_output=True, text=True, timeout=10
    )
    if "decepticon-sandbox" not in result.stdout:
        msg = "decepticon-sandbox container is not running. Run: docker compose up -d sandbox"
        if HAS_PYTEST:
            pytest.skip(msg)
        else:
            print(f"SKIP: {msg}")
            sys.exit(0)


async def _check_litellm():
    """Check if the LiteLLM Proxy is reachable."""
    from decepticon.llm.factory import LLMFactory
    from decepticon.llm.models import ProxyConfig
    factory = LLMFactory(ProxyConfig())
    healthy = await factory.health_check()
    if not healthy:
        msg = "LiteLLM Proxy is not running. Run: docker compose up -d litellm postgres"
        if HAS_PYTEST:
            pytest.skip(msg)
        else:
            print(f"SKIP: {msg}")
            sys.exit(0)


# ─── Test 1: Simple ls command ───────────────────────────────────────────

async def test_agent_ls():
    """Test: Agent runs 'ls' via the bash tool and returns its output."""
    _ensure_sandbox()
    await _check_litellm()
    _reset_tmux_state()

    print("\n" + "="*60)
    print("TEST: Agent LS Command")
    print("="*60)

    agent = create_recon_agent()
    prompt = "Run 'ls /home/decepticon_agent' and tell me exactly what files and directories are listed."
    config = {"configurable": {"thread_id": "test_agent_ls"}}

    print(f"[+] Prompt: {prompt}")
    response = await agent.ainvoke(
        {"messages": [HumanMessage(content=prompt)]},
        config=config,
    )

    final_output = response["messages"][-1].content
    print(f"\n[+] Agent response:\n{final_output}")

    # The agent should have used bash and returned some ls output
    assert any(keyword in final_output.lower() for keyword in ["workspace", "directory", "total", "ls", "home"]), \
        f"Agent response doesn't look like ls output: {final_output[:200]}"
    print("[✅] test_agent_ls PASSED")


# ─── Test 2: Interactive apt-get install ─────────────────────────────────

async def test_agent_apt_install():
    """Test: Agent installs 'tree' via apt-get with interactive Y/n prompt."""
    _ensure_sandbox()
    await _check_litellm()
    _reset_tmux_state()

    print("\n" + "="*60)
    print("TEST: Agent Interactive apt-get install")
    print("="*60)

    agent = create_recon_agent()
    prompt = (
        "Install the 'tree' package by running 'apt-get install tree' (without the -y flag). "
        "When it asks for confirmation [Y/n], send 'y' using is_input=True. "
        "After installation completes, run 'ls -l /usr/bin/tree' to verify and show me the output."
    )
    config = {"configurable": {"thread_id": "test_agent_apt"}}

    print(f"[+] Prompt: {prompt}")
    response = await agent.ainvoke(
        {"messages": [HumanMessage(content=prompt)]},
        config=config,
    )

    final_output = response["messages"][-1].content
    print(f"\n[+] Agent response:\n{final_output}")

    # Verify the agent mentions tree was installed or shows the ls output
    assert any(keyword in final_output.lower() for keyword in ["/usr/bin/tree", "tree", "installed"]), \
        f"Agent response doesn't mention tree installation: {final_output[:200]}"
    print("[✅] test_agent_apt_install PASSED")


# ─── Standalone runner ───────────────────────────────────────────────────

async def main():
    """Run all tests as a standalone script."""
    print("\n🔴 Decepticon — Agent Bash Integration Tests")
    print("="*60)

    passed = 0
    failed = 0

    for test_func in [test_agent_ls, test_agent_apt_install]:
        try:
            await test_func()
            passed += 1
        except Exception as e:
            print(f"\n[❌] {test_func.__name__} FAILED: {e}")
            failed += 1

    print("\n" + "="*60)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*60)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
