import pytest
from decepticon.agents.recon import create_recon_agent
from decepticon.tools.registry import get_tools

def test_agent_initialization():
    """Verify that the Recon agent can be built without errors from deepagents."""
    agent = create_recon_agent()
    # Deepagents returns a CompiledGraph, we just check if it's not None
    assert agent is not None
    assert hasattr(agent, "stream")

def test_tool_registry():
    """Verify tool loading from registry."""
    tools = get_tools(["nmap_scan", "dns_lookup", "whois_lookup"])
    assert len(tools) == 3
    tool_names = [t.name for t in tools]
    assert "nmap_scan" in tool_names
    
def test_missing_tool_registry():
    """Verify tool registry raises error for missing tools."""
    with pytest.raises(ValueError):
        get_tools(["invalid_tool_name"])
