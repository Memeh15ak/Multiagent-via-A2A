# multi_agent_system/agents/mcp_tools/tool_registry.py

# Similar to tool_manager.py, this file would be for a centralized registry of
# tools that are not necessarily A2A agents themselves, but perhaps local
# utility functions or integrations with external APIs that aren't exposed
# as full A2A services.

# Given our setup, the primary "tool registry" for the orchestrator is
# the collection of ADK FunctionTools derived from the A2A AgentCards
# by the a2a_protocol_handler and managed by the orchestrator_agent itself.

# This file can remain empty or contain very generic, non-agent-specific utility functions.