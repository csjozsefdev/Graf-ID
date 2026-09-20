import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BuildCacheCard } from "./BuildCacheCard";

const detectBuildCachesMock = vi.fn();
const cleanBuildCacheMock = vi.fn();

vi.mock("../ipc/client", () => ({
  detectBuildCaches: (...args: unknown[]) => detectBuildCachesMock(...args),
  cleanBuildCache: (...args: unknown[]) => cleanBuildCacheMock(...args),
  getUserErrorMessage: (err: unknown) => (err instanceof Error ? err.message : String(err)),
}));

const cache = {
  kind: "cargo",
  manifest_path: "desktop/src-tauri/Cargo.toml",
  target_path: "desktop/src-tauri/target",
  size_bytes: 3_400_000_000,
};

beforeEach(() => {
  detectBuildCachesMock.mockReset();
  cleanBuildCacheMock.mockReset();
});

describe("BuildCacheCard", () => {
  it("renders nothing for a project with no detected build cache", async () => {
    detectBuildCachesMock.mockResolvedValue({ caches: [] });
    const { container } = render(<BuildCacheCard projectId={1} projectPath="C:/proj" />);

    await waitFor(() => expect(detectBuildCachesMock).toHaveBeenCalledWith(1));
    expect(container.firstChild).toBeNull();
  });

  it("shows the detected cache with a formatted size", async () => {
    detectBuildCachesMock.mockResolvedValue({ caches: [cache] });
    render(<BuildCacheCard projectId={1} projectPath="C:/proj" />);

    expect(await screen.findByText(/Build cache detected: desktop\/src-tauri\/target/)).toBeInTheDocument();
    expect(screen.getByText(/Estimated size: 3\.2 GB/)).toBeInTheDocument();
  });

  it("opens a confirmation dialog before cleaning, and cancel does not clean", async () => {
    detectBuildCachesMock.mockResolvedValue({ caches: [cache] });
    render(<BuildCacheCard projectId={1} projectPath="C:/proj" />);

    fireEvent.click(await screen.findByRole("button", { name: /clean build cache/i }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/Delete Rust build cache/i)).toBeInTheDocument();
    expect(screen.getByText(/cargo clean/i)).toBeInTheDocument();
    expect(screen.getByText(/C:\/proj\/desktop\/src-tauri/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(cleanBuildCacheMock).not.toHaveBeenCalled();
  });

  it("cleans the cache, shows a freed-space notice, and removes the row", async () => {
    detectBuildCachesMock.mockResolvedValue({ caches: [cache] });
    cleanBuildCacheMock.mockResolvedValue({
      cache: { ...cache, size_bytes: 3_400_000_000 },
    });
    render(<BuildCacheCard projectId={7} projectPath="C:/proj" />);

    fireEvent.click(await screen.findByRole("button", { name: /clean build cache/i }));
    fireEvent.click(screen.getByRole("button", { name: /clean now/i }));

    await waitFor(() =>
      expect(cleanBuildCacheMock).toHaveBeenCalledWith(7, "desktop/src-tauri/Cargo.toml")
    );
    expect(await screen.findByText(/Freed 3\.2 GB/)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /clean build cache/i })).not.toBeInTheDocument();
  });

  it("shows an error in the dialog and keeps it open when cleaning fails", async () => {
    detectBuildCachesMock.mockResolvedValue({ caches: [cache] });
    cleanBuildCacheMock.mockRejectedValue(new Error("cargo not found"));
    render(<BuildCacheCard projectId={1} projectPath="C:/proj" />);

    fireEvent.click(await screen.findByRole("button", { name: /clean build cache/i }));
    fireEvent.click(screen.getByRole("button", { name: /clean now/i }));

    expect(await screen.findByText("cargo not found")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("does not apply a stale clean result after switching to a different project mid-clean (M9)", async () => {
    detectBuildCachesMock.mockImplementation((projectId: number) =>
      Promise.resolve({ caches: projectId === 1 ? [cache] : [] })
    );
    let resolveClean!: (value: { cache: typeof cache }) => void;
    cleanBuildCacheMock.mockReturnValue(
      new Promise((resolve) => {
        resolveClean = resolve;
      })
    );

    const { rerender } = render(<BuildCacheCard projectId={1} projectPath="C:/proj-a" />);
    fireEvent.click(await screen.findByRole("button", { name: /clean build cache/i }));
    fireEvent.click(screen.getByRole("button", { name: /clean now/i }));
    await waitFor(() => expect(cleanBuildCacheMock).toHaveBeenCalledWith(1, cache.manifest_path));

    // Switch to project B while project A's cargo clean is still running.
    rerender(<BuildCacheCard projectId={2} projectPath="C:/proj-b" />);
    await waitFor(() => expect(detectBuildCachesMock).toHaveBeenCalledWith(2));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    // A's clean now finishes — its result must not surface on B's screen.
    resolveClean({ cache: { ...cache, size_bytes: 3_400_000_000 } });
    await Promise.resolve();
    await Promise.resolve();

    expect(screen.queryByText(/Freed/)).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("re-detects when the selected project changes", async () => {
    detectBuildCachesMock.mockResolvedValue({ caches: [] });
    const { rerender } = render(<BuildCacheCard projectId={1} projectPath="C:/proj-a" />);
    await waitFor(() => expect(detectBuildCachesMock).toHaveBeenCalledWith(1));

    rerender(<BuildCacheCard projectId={2} projectPath="C:/proj-b" />);
    await waitFor(() => expect(detectBuildCachesMock).toHaveBeenCalledWith(2));
  });
});
