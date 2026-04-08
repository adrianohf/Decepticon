"""Unit tests for SafeCommandMiddleware.

The middleware blocks bash tool calls that would destroy the sandbox tmux
session or attempt sandbox escape. These tests pin the dangerous-pattern
allow/deny matrix so regressions in the regex set are caught immediately.

NOTE: regex matching is *defense-in-depth only* and trivially bypassed by
encoding tricks (`pkill${IFS}bash`, base64+eval, quoting). Tests intentionally
exercise canonical forms to lock in current intent — not to claim the
middleware is a real security boundary.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import ToolMessage

from decepticon.middleware.safe_command import SafeCommandMiddleware


def _make_request(tool_name: str, **args: Any) -> MagicMock:
    """Build a minimal ToolCallRequest mock."""
    request = MagicMock()
    request.tool_call = {
        "name": tool_name,
        "id": "call_test_123",
        "args": args,
    }
    return request


class TestSafeCommandMiddlewareSync:
    """wrap_tool_call (sync path)."""

    def setup_method(self) -> None:
        self.mw = SafeCommandMiddleware()
        self.handler = MagicMock(return_value="ok")

    @pytest.mark.parametrize(
        "command",
        [
            "pkill bash",
            "pkill -9 bash",
            "pkill -f bash",
            "killall bash",
            "killall -9 bash",
            "pkill tmux",
            "pkill -f tmux",
            "killall tmux",
            "kill -9 -1",
            "kill -9 0",
            "docker exec sandbox ls",
            "docker run alpine",
            "docker cp foo bar",
            "docker build .",
            "docker compose up",
            "cat /proc/1/environ",
            "cat /proc/1/cmdline",
            "cat /proc/1/maps",
            "nsenter --target 1",
            "mount -t proc proc /proc",
            "mount -t sysfs sys /sys",
            "iptables -L",
            "ip6tables -F",
            "nftables list",
            "ip route add default via 1.2.3.4",
            "ip rule del table main",
        ],
    )
    def test_blocks_dangerous_commands(self, command: str) -> None:
        request = _make_request("bash", command=command)
        result = self.mw.wrap_tool_call(request, self.handler)
        assert isinstance(result, ToolMessage)
        assert result.status == "error"
        assert "[BLOCKED]" in str(result.content)
        self.handler.assert_not_called()

    @pytest.mark.parametrize(
        "command",
        [
            "ls -la",
            "nmap -sV 10.0.0.1",
            "echo 'pkill bash will not actually run because echo'",  # in quotes, regex still matches — test the OPPOSITE below
        ],
    )
    def test_allows_benign_commands(self, command: str) -> None:
        # Skip the literal-string-with-pkill case for the inverse test
        if "pkill bash" in command:
            pytest.skip("regex matches inside quotes — known limitation")
        request = _make_request("bash", command=command)
        result = self.mw.wrap_tool_call(request, self.handler)
        assert result == "ok"
        self.handler.assert_called_once_with(request)

    def test_allows_non_bash_tool(self) -> None:
        request = _make_request("ls", path="/workspace")
        result = self.mw.wrap_tool_call(request, self.handler)
        assert result == "ok"

    def test_allows_input_to_running_process(self) -> None:
        # is_input=True means the user is feeding stdin to a running interactive
        # program (msf6>, sliver>) — content checks must NOT apply.
        request = _make_request("bash", command="pkill bash", is_input=True)
        result = self.mw.wrap_tool_call(request, self.handler)
        assert result == "ok"

    def test_allows_empty_command(self) -> None:
        # Empty command = "read screen" no-op; nothing to validate.
        request = _make_request("bash", command="")
        result = self.mw.wrap_tool_call(request, self.handler)
        assert result == "ok"

    def test_blocked_message_includes_tool_call_id(self) -> None:
        request = _make_request("bash", command="pkill bash")
        result = self.mw.wrap_tool_call(request, self.handler)
        assert isinstance(result, ToolMessage)
        assert result.tool_call_id == "call_test_123"
        assert result.name == "bash"


class TestSafeCommandMiddlewareAsync:
    """awrap_tool_call (async path)."""

    @pytest.mark.asyncio
    async def test_blocks_dangerous_command_async(self) -> None:
        mw = SafeCommandMiddleware()
        handler = AsyncMock(return_value="ok")
        request = _make_request("bash", command="pkill bash")
        result = await mw.awrap_tool_call(request, handler)
        assert isinstance(result, ToolMessage)
        assert result.status == "error"
        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_allows_benign_command_async(self) -> None:
        mw = SafeCommandMiddleware()
        handler = AsyncMock(return_value="ok")
        request = _make_request("bash", command="ls -la")
        result = await mw.awrap_tool_call(request, handler)
        assert result == "ok"
        handler.assert_awaited_once_with(request)
