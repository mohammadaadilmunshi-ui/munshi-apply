import { describe, expect, it } from "vitest";
import type { ApplicationPage } from "@munshi-apply/contracts";
import { shouldPublishApplicationSnapshot } from "./cloud";

function applicationPage(url: string, title = "Application"): ApplicationPage {
  return {
    pageId: "page-application",
    tabId: 1,
    frameId: 0,
    documentId: "doc-application",
    url,
    title,
    observedAt: "2026-08-14T20:00:00.000Z",
    controls: [
      {
        controlId: "ctl-first",
        frameId: 0,
        kind: "TEXT",
        tagName: "input",
        name: "first_name",
        label: "First name",
        placeholder: "",
        ariaLabel: "",
        required: true,
        disabled: false,
        visible: true,
        options: [],
        multiple: false,
        autocomplete: "given-name",
        invalid: false,
        validationMessage: "",
      },
      {
        controlId: "ctl-email",
        frameId: 0,
        kind: "EMAIL",
        tagName: "input",
        name: "email",
        label: "Email",
        placeholder: "",
        ariaLabel: "",
        required: true,
        disabled: false,
        visible: true,
        options: [],
        multiple: false,
        autocomplete: "email",
        invalid: false,
        validationMessage: "",
      },
    ],
    questions: [
      {
        questionId: "q-first",
        controlId: "ctl-first",
        rawText: "First name",
        semanticType: "FIRST_NAME",
        confidence: 0.99,
        sensitive: false,
        requiresReview: false,
      },
      {
        questionId: "q-email",
        controlId: "ctl-email",
        rawText: "Email",
        semanticType: "EMAIL",
        confidence: 0.99,
        sensitive: false,
        requiresReview: false,
      },
    ],
    applicationState: "PERSONAL",
    pageFingerprint: "fp-application",
    securityCheckpoint: null,
    validationErrorCount: 0,
    navigationCandidates: [],
    finalSubmissionBoundary: false,
    atsFamily: "GENERIC",
  };
}

const connection = {
  baseUrl: "https://munshi-apply-mobile.mohammadaadilmunshi.chatgpt.site",
  deviceId: "device-test",
  credential: "credential-test",
  platform: "macos-edge",
  connectedAt: "2026-08-14T19:00:00.000Z",
};

describe("cloud application publication boundary", () => {
  it("never publishes the owner workspace itself even if its UI looks application-like", () => {
    expect(
      shouldPublishApplicationSnapshot(
        connection,
        applicationPage(`${connection.baseUrl}/workspace`, "MUNSHI Apply"),
      ),
    ).toBe(false);
  });

  it("publishes a real application form on a different origin", () => {
    expect(
      shouldPublishApplicationSnapshot(
        connection,
        applicationPage("https://careers.example.test/apply/123"),
      ),
    ).toBe(true);
  });
});
