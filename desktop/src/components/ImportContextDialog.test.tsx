import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ImportContextDialog } from "./ImportContextDialog";
import type { ContextImportPreview } from "../ipc/client";

function preview(over: Partial<ContextImportPreview> = {}): ContextImportPreview {
  return {
    project_id: 1,
    project_name: "Alpha",
    handoff_project_name: "Alpha",
    name_matches: true,
    current_notes: "My own notes",
    block: "Imported handoff (2026-09-20) from Alpha\nStatus: Checkout done",
    proposed_notes_append: "My own notes\n\nImported handoff",
    fingerprint: "abc123",
    warnings: [],
    ignored_keys: [],
    fits: true,
    files_not_imported: 2,
    ...over,
  };
}

const noop = () => {};

describe("ImportContextDialog", () => {
  it("previews what will be saved and defaults to the non-destructive append", () => {
    const onConfirm = vi.fn();
    render(<ImportContextDialog preview={preview()} fileName="alpha.json" busy={false} error={null} onConfirm={onConfirm} onCancel={noop} />);
    expect(screen.getByText(/Imported handoff \(2026-09-20\) from Alpha/)).toBeInTheDocument();
    expect(screen.getByText("2 listed file name(s) are not imported.")).toBeInTheDocument();
    expect(screen.getByLabelText(/Add below my existing notes/)).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Import into project notes" }));
    expect(onConfirm).toHaveBeenCalledWith("append");
  });

  it("warns clearly before replacing existing notes and confirms with replace", () => {
    const onConfirm = vi.fn();
    render(<ImportContextDialog preview={preview()} fileName="a.json" busy={false} error={null} onConfirm={onConfirm} onCancel={noop} />);
    fireEvent.click(screen.getByLabelText(/Replace my existing notes/));
    expect(screen.getByRole("alert")).toHaveTextContent("replaces your current notes (12 characters)");
    fireEvent.click(screen.getByRole("button", { name: "Import into project notes" }));
    expect(onConfirm).toHaveBeenCalledWith("replace");
  });

  it("shows validation warnings and blocks an append that would overflow the notes limit", () => {
    render(
      <ImportContextDialog
        preview={preview({ fits: false, warnings: ["The file is for 'Other', not 'Alpha'."] })}
        fileName="a.json" busy={false} error={null} onConfirm={noop} onCancel={noop}
      />
    );
    expect(screen.getByText(/The file is for 'Other'/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import into project notes" })).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/Replace my existing notes/));
    expect(screen.getByRole("button", { name: "Import into project notes" })).not.toBeDisabled();
  });

  it("can be cancelled, shows errors, and locks while importing", () => {
    const onCancel = vi.fn();
    const { rerender } = render(
      <ImportContextDialog preview={preview()} fileName="a.json" busy={false} error="The project notes changed since the preview." onConfirm={noop} onCancel={onCancel} />
    );
    expect(screen.getByText(/notes changed since the preview/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalled();
    rerender(<ImportContextDialog preview={preview()} fileName="a.json" busy error={null} onConfirm={noop} onCancel={onCancel} />);
    expect(screen.getByRole("button", { name: "Importing…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  });

  it("renders nothing without a preview", () => {
    const { container } = render(<ImportContextDialog preview={null} fileName="" busy={false} error={null} onConfirm={noop} onCancel={noop} />);
    expect(container).toBeEmptyDOMElement();
  });
});
