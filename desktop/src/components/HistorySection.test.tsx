import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HistorySection } from "./HistorySection";
import type { HistoryRow } from "../ipc/types";
import { healthyProject } from "../utils/grafiAdvisorTestFixtures";

const row: HistoryRow = {
  snapshot_id: 42,
  scanned_at: "2026-06-08T10:00:00+00:00",
  project_name: "demo",
  scanned_at_label: "2026-06-08",
  summary_preview: "Worked on tests.",
  changed_files_count: 3,
  session_duration_label: null,
  findings_count: 0,
  scanned_files_count: 12,
  duration_seconds: 1.2,
  git_branch: "main",
  git_dirty: false,
  is_git_repo: true,
  summary_source: "scan",
};

describe("HistorySection", () => {
  it("shows encouraging copy when only one snapshot exists", () => {
    render(
      <HistorySection
        project={healthyProject({ name: "demo" })}
        rows={[row]}
        loading={false}
        error={null}
      />
    );

    expect(screen.getByText(/One snapshot on record/i)).toBeInTheDocument();
    expect(screen.getByText(/Worked on tests/i)).toBeInTheDocument();
  });
});
