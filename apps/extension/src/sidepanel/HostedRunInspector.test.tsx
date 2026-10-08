import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { HostedRunInspector } from "./HostedRunInspector";
import { isHostedApplicationSelected } from "./hosted-run-identity";

describe("Canonical hosted-run inspector", () => {
  it("renders as an observer, never an alternate submit engine", () => {
    const html = renderToStaticMarkup(
      createElement(HostedRunInspector, {
        nativeAvailable: true,
        onHostedRunFound: () => undefined,
      }),
    );
    expect(html).toContain("Netcup live application inspector");
    expect(html).toContain("Read-only");
    expect(html).toContain("exact hosted Apply session");
    expect(html).toContain("Refresh hosted run");
    expect(html).not.toContain("Approve exact answer");
    expect(html).not.toContain(">Submit<");
    expect(html).not.toContain(">Start AutoPilot<");
  });

  it("locks a selected hosted application even if monitoring is offline", () => {
    expect(
      isHostedApplicationSelected(
        "application-d072cde0bb58c62eb4178af0b4645814",
      ),
    ).toBe(true);
    expect(isHostedApplicationSelected("local-session-1")).toBe(false);
    expect(isHostedApplicationSelected("application-../escape")).toBe(false);
  });

  it("fails closed when the native companion cannot report the Netcup state", () => {
    const html = renderToStaticMarkup(
      createElement(HostedRunInspector, {
        nativeAvailable: false,
        onHostedRunFound: () => undefined,
      }),
    );
    expect(html).toContain("unavailable or outdated");
    expect(html).toContain("No hosted run evidence");
    expect(html).toContain("disabled");
  });
});
