// @vitest-environment jsdom

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DeveloperBadge } from "./developer-badge";

describe("DeveloperBadge", () => {
  afterEach(cleanup);

  it("renders Blue's attribution and circular avatar", () => {
    render(<DeveloperBadge />);

    expect(screen.getByText("Created by Blue")).toBeTruthy();
    const avatar = screen.getByAltText("Blue");
    expect(avatar.getAttribute("src")).toBe("/blue-avatar.png");
    expect(avatar.className).toContain("rounded-full");
  });

  it("is mounted exactly once by the global root layout", () => {
    const layout = readFileSync(
      resolve(process.cwd(), "src/app/layout.tsx"),
      "utf8",
    );

    expect(layout.match(/<DeveloperBadge\s*\/>/g)).toHaveLength(1);
  });
});
