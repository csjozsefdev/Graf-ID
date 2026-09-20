import { beforeEach, describe, expect, it, vi } from "vitest";

const invokeMock = vi.fn();

vi.mock("@tauri-apps/api/core", () => ({
  invoke: (...args: unknown[]) => invokeMock(...args),
}));

import { saveAppSettings } from "./client";
import type { CodingAgentConfig } from "./types";

function agent(over: Partial<CodingAgentConfig>): CodingAgentConfig {
  return {
    id: "x",
    display_name: "X",
    executable: "x",
    args: [],
    built_in: false,
    available: true,
    ...over,
  };
}

describe("saveAppSettings — coding agent payloads", () => {
  beforeEach(() => {
    invokeMock.mockReset();
    invokeMock.mockResolvedValue({ ok: true, data: { message: "ok" } });
  });

  async function sentArgs(input: Parameters<typeof saveAppSettings>[0]) {
    await saveAppSettings(input);
    return invokeMock.mock.calls[0][1] as { codingAgents: string | null; builtinAgents: string | null };
  }

  const base = {
    default_project_opener: "system",
    usage_journal_enabled: false,
    debug_timing_enabled: false,
  };

  it("sends only custom agents in codingAgents and per-preset state in builtinAgents", async () => {
    const sent = await sentArgs({
      ...base,
      coding_agents: [
        agent({ id: "claude-code", built_in: true, executable: "C:\\T\\claude.cmd", executable_override: "C:\\T\\claude.cmd", args: ["-a"] }),
        agent({ id: "codex-cli", built_in: true, executable: "codex", executable_override: null }),
        agent({ id: "mine", display_name: "Mine", executable: "mine", args: ["--x"] }),
      ],
      removed_builtin_agents: [],
    });
    expect(JSON.parse(sent.codingAgents as string)).toEqual([
      { id: "mine", display_name: "Mine", executable: "mine", args: ["--x"] },
    ]);
    expect(JSON.parse(sent.builtinAgents as string)).toEqual({
      "claude-code": { executable: "C:\\T\\claude.cmd", args: ["-a"] },
      "codex-cli": { executable: null, args: [] },
    });
  });

  it("marks removed presets as hidden and never sends an override for them", async () => {
    const sent = await sentArgs({
      ...base,
      coding_agents: [agent({ id: "codex-cli", built_in: true, executable: "codex" })],
      removed_builtin_agents: [
        agent({ id: "claude-code", built_in: true, executable_override: "C:\\stale.cmd" }),
      ],
    });
    expect(JSON.parse(sent.builtinAgents as string)["claude-code"]).toEqual({ hidden: true });
  });

  it("leaves coding agent config untouched when the caller sends no agent data", async () => {
    const sent = await sentArgs(base);
    expect(sent.codingAgents).toBeNull();
    expect(sent.builtinAgents).toBeNull();
  });
});
