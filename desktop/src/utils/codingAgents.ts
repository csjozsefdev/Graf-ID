/**
 * Coding Agent opener-value helpers — mirrors
 * grafid/config/coding_agents.py's opener_value_for_agent /
 * agent_id_from_opener_value / is_agent_opener_value exactly, so the
 * frontend and backend agree on the "agent:<id>" namespacing without
 * needing a dynamic round trip just to tell an agent opener apart from an
 * editor token.
 */

const AGENT_OPENER_PREFIX = "agent:";

export function openerValueForAgent(agentId: string): string {
  return `${AGENT_OPENER_PREFIX}${agentId}`;
}

export function agentIdFromOpenerValue(value: string | null | undefined): string | null {
  if (!value || !value.startsWith(AGENT_OPENER_PREFIX)) {
    return null;
  }
  const id = value.slice(AGENT_OPENER_PREFIX.length);
  return id || null;
}

export function isAgentOpenerValue(value: string | null | undefined): boolean {
  return agentIdFromOpenerValue(value) !== null;
}

