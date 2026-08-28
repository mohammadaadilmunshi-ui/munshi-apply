import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  createResolutionTask,
  type ResolutionTask,
} from "@munshi-apply/application-model";
import { describe, expect, it } from "vitest";
import { ResolutionTaskQueueBody } from "./ResolutionTaskPanel";
import { buildResolutionTaskQueueView } from "./resolution-task-view";

function relocation(applicationId: string): ResolutionTask {
  return createResolutionTask({
    applicationId,
    question: "Are you willing to relocate?",
    semanticType: "RELOCATION",
    category: "MISSING_FACT",
    reason: "Relocation preference is not confirmed",
    createdAt: "2026-08-28T18:00:00.000Z",
  });
}

function sponsorship(applicationId: string): ResolutionTask {
  return createResolutionTask({
    applicationId,
    question: "Will you require employment sponsorship in the future?",
    semanticType: "SPONSORSHIP_FUTURE",
    category: "LEGAL_CONFIRMATION",
    reason: "The sponsorship answer needs explicit owner confirmation",
    createdAt: "2026-08-28T18:01:00.000Z",
  });
}

describe("Resolution Task queue presentation", () => {
  it("shows owner work, guarded candidates, and reusable scope without fake resolution controls", () => {
    const view = buildResolutionTaskQueueView(
      [
        sponsorship("application-a"),
        relocation("application-a"),
        relocation("application-b"),
      ],
      "application-a",
    );
    const html = renderToStaticMarkup(
      createElement(ResolutionTaskQueueBody, {
        view,
        loading: false,
        message: "",
        nativeAvailable: true,
      }),
    );

    expect(html).toContain("Owner action required");
    expect(html).toContain("Eligible for guarded resolution");
    expect(html).toContain("Reusable scope detected across 2 applications");
    expect(html).toContain("High-risk facts are never guessed");
    expect(html).not.toMatch(/>Resolve</i);
    expect(html).not.toMatch(/mark.+resolved/i);
  });

  it("explains why durable history is unavailable without the native companion", () => {
    const html = renderToStaticMarkup(
      createElement(ResolutionTaskQueueBody, {
        view: buildResolutionTaskQueueView([], "application-a"),
        loading: false,
        message: "",
        nativeAvailable: false,
      }),
    );

    expect(html).toContain("requires the native companion");
    expect(html).toContain("resume checkpoints remain durable");
  });
});
