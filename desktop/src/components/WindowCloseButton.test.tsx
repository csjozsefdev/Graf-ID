import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WindowCloseButton } from "./WindowCloseButton";

vi.mock("../utils/mainWindowClose", () => ({
  requestMainWindowClose: vi.fn(),
}));

describe("WindowCloseButton", () => {
  it("renders a fixed close control with an accessible label", () => {
    render(<WindowCloseButton />);
    expect(screen.getByRole("button", { name: "Close Graf-ID" })).toHaveClass(
      "window-close-button"
    );
  });
});
