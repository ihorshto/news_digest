import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DigestMarkdown } from "./markdown";
import { runStatusLabel, scheduleLabel, statusTone } from "./format";
import type { Topic } from "./api";

const SAMPLE = `# Crypto
_08.10.2026 09:00_

### Bitcoin \\[BTC\\] hits record
Price rose 5\\% \\*today\\*.
[Forbes](https://news.google.com/rss/articles/abc?oc=5) · [Evil](javascript:alert(1))
`;

describe("DigestMarkdown", () => {
  it("renders headings, escapes and safe links only", () => {
    const { container } = render(<DigestMarkdown source={SAMPLE} />);
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(
      "Bitcoin [BTC] hits record",
    );
    expect(screen.queryByText("Crypto")).toBeNull(); // title shown by the page
    expect(screen.getByText("08.10.2026 09:00")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Forbes" });
    expect(link).toHaveAttribute("href", "https://news.google.com/rss/articles/abc?oc=5");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.queryByRole("link", { name: "Evil" })).toBeNull();
    expect(container.innerHTML).not.toContain("javascript:");
    expect(container.textContent).toContain("*today*");
  });

  it("never renders raw HTML", () => {
    const { container } = render(<DigestMarkdown source={"<img src=x onerror=alert(1)>"} />);
    expect(container.querySelector("img")).toBeNull();
  });
});

describe("format helpers", () => {
  const topic = { frequency: "weekly", send_hour: 7, weekday: 2 } as Topic;

  it("labels schedules", () => {
    expect(scheduleLabel(topic)).toBe("Щотижня, Середа о 07:00");
    expect(scheduleLabel({ ...topic, frequency: "daily" })).toBe("Щодня о 07:00");
    expect(scheduleLabel({ ...topic, frequency: "hourly" })).toBe("Щогодини");
  });

  it("maps statuses", () => {
    expect(statusTone("fake_sent")).toBe("success");
    expect(statusTone("error: boom")).toBe("danger");
    expect(runStatusLabel("error: boom")).toBe("помилка обробки");
    expect(runStatusLabel("empty")).toBe("нових новин немає");
  });
});
