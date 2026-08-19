import { describe, expect, it } from "vitest";
import type { ApplicationPage, SemanticType } from "@munshi-apply/contracts";
import { applicationPageEligibility } from "./application-detection";

function page(input: {
  url: string;
  title: string;
  semantics?: SemanticType[];
  atsFamily?: ApplicationPage["atsFamily"];
  applicationState?: ApplicationPage["applicationState"];
  finalSubmissionBoundary?: boolean;
  resume?: boolean;
  navigationLabel?: string;
}): ApplicationPage {
  const semantics = input.semantics ?? [];
  return {
    pageId: "page-test",
    tabId: 1,
    frameId: 0,
    documentId: "doc-test",
    url: input.url,
    title: input.title,
    observedAt: "2026-08-14T20:00:00.000Z",
    controls: [
      ...semantics.map((semanticType, index) => ({
        controlId: `ctl-${index}`,
        frameId: 0,
        kind: "TEXT" as const,
        tagName: "input",
        name: `field-${index}`,
        label: `Field ${index}`,
        placeholder: "",
        ariaLabel: "",
        required: true,
        disabled: false,
        visible: true,
        options: [],
        multiple: false,
        autocomplete: "",
        invalid: false,
        validationMessage: "",
      })),
      ...(input.resume
        ? [
            {
              controlId: "ctl-resume",
              frameId: 0,
              kind: "FILE" as const,
              tagName: "input",
              name: "resume",
              label: "Upload résumé",
              placeholder: "",
              ariaLabel: "",
              required: true,
              disabled: false,
              visible: true,
              options: [],
              multiple: false,
              autocomplete: "",
              invalid: false,
              validationMessage: "",
            },
          ]
        : []),
    ],
    questions: semantics.map((semanticType, index) => ({
      questionId: `q-${index}`,
      controlId: `ctl-${index}`,
      rawText: `Question ${index}`,
      semanticType,
      confidence: semanticType === "UNKNOWN" ? 0 : 0.95,
      sensitive: false,
      requiresReview: semanticType === "UNKNOWN",
    })),
    applicationState: input.applicationState ?? "QUESTIONS",
    pageFingerprint: "fp-test",
    securityCheckpoint: null,
    validationErrorCount: 0,
    navigationCandidates: input.navigationLabel
      ? [
          {
            controlId: "ctl-next",
            frameId: 0,
            action: "NEXT",
            label: input.navigationLabel,
            disabled: false,
          },
        ]
      : [],
    finalSubmissionBoundary: input.finalSubmissionBoundary ?? false,
    atsFamily: input.atsFamily ?? "GENERIC",
  };
}

describe("application page eligibility", () => {
  it("rejects ordinary help pages even when generic controls become questions", () => {
    const result = applicationPageEligibility(
      page({
        url: "https://help.openai.com/en/articles/123-gpt-help",
        title: "GPT help | OpenAI Help Center",
        semantics: ["UNKNOWN", "UNKNOWN"],
      }),
    );
    expect(result).toEqual({ eligible: false, reasons: [] });
  });

  it("rejects a LinkedIn profile page even when the scanner sees a language selector", () => {
    expect(
      applicationPageEligibility(
        page({
          url: "https://www.linkedin.com/in/aadil-munshi/",
          title: "Aadil Munshi | LinkedIn",
          semantics: ["LANGUAGES"],
        }),
      ).eligible,
    ).toBe(false);
  });

  it("rejects ordinary portfolio pages", () => {
    expect(
      applicationPageEligibility(
        page({
          url: "https://munshi.systems/",
          title: "Aadil Munshi | HR Operations & People Analytics",
        }),
      ).eligible,
    ).toBe(false);
  });

  it("rejects documentation about applying when it has no application form", () => {
    expect(
      applicationPageEligibility(
        page({
          url: "https://docs.example.test/how-to-apply",
          title: "How to apply",
          semantics: ["UNKNOWN", "UNKNOWN"],
        }),
      ).eligible,
    ).toBe(false);
  });

  it("accepts a generic application form with explicit intent and classified fields", () => {
    expect(
      applicationPageEligibility(
        page({
          url: "https://careers.example.test/apply/123",
          title: "Application",
          semantics: ["FIRST_NAME", "EMAIL"],
        }),
      ).eligible,
    ).toBe(true);
  });

  it("recognizes application intent carried by a URL fragment", () => {
    expect(
      applicationPageEligibility(
        page({
          url: "https://careers.example.test/jobs/role#apply",
          title: "Role details",
          resume: true,
        }),
      ).eligible,
    ).toBe(true);
  });

  it("accepts a generic embedded candidate form from strong structural evidence", () => {
    expect(
      applicationPageEligibility(
        page({
          url: "https://careers.example.test/jobs/role",
          title: "Role details",
          semantics: ["FIRST_NAME", "LAST_NAME", "EMAIL", "PHONE"],
          resume: true,
          navigationLabel: "Next",
        }),
      ).eligible,
    ).toBe(true);
  });

  it("tracks Bain-style careers job registration flows without requiring the word application", () => {
    const result = applicationPageEligibility(
      page({
        url: "https://careers.bain.com/jobs/Register?folderId=108235&source=Linked-In",
        title: "Coordinator, Consultant Recruiting",
        semantics: ["FIRST_NAME", "LAST_NAME", "PREFERRED_NAME"],
        navigationLabel: "Next",
      }),
    );
    expect(result.eligible).toBe(true);
    expect(result.reasons).toContain(
      "careers/job registration flow with progressive candidate fields",
    );
  });

  it("tracks a Bain job registration route even before field semantics are classified", () => {
    const candidate = page({
      url: "https://careers.bain.com/jobs/Register?folderId=108235&source=Linked-In",
      title: "Coordinator, Consultant Recruiting",
    });
    candidate.controls = [
      {
        controlId: "ctl-raw-1",
        frameId: 0,
        kind: "TEXT",
        tagName: "input",
        name: "first",
        label: "",
        placeholder: "",
        ariaLabel: "",
        required: true,
        disabled: false,
        visible: true,
        options: [],
        multiple: false,
        autocomplete: "",
        invalid: false,
        validationMessage: "",
      },
      {
        controlId: "ctl-raw-2",
        frameId: 0,
        kind: "TEXT",
        tagName: "input",
        name: "last",
        label: "",
        placeholder: "",
        ariaLabel: "",
        required: true,
        disabled: false,
        visible: true,
        options: [],
        multiple: false,
        autocomplete: "",
        invalid: false,
        validationMessage: "",
      },
    ];

    const result = applicationPageEligibility(candidate);
    expect(result.eligible).toBe(true);
    expect(result.reasons).toContain(
      "explicit careers job-registration route with candidate fields",
    );
  });

  it("keeps a Bain work-history step tracked even when its Next control is not currently scannable", () => {
    const result = applicationPageEligibility(
      page({
        url: "https://careers.bain.com/jobs/Register?folderId=108235&source=Linked-In",
        title: "Coordinator, Consultant Recruiting",
        semantics: ["EMPLOYER_NAME", "JOB_TITLE", "START_DATE"],
        applicationState: "EXPERIENCE",
      }),
    );
    expect(result.eligible).toBe(true);
    expect(result.reasons).toContain(
      "careers/job registration flow with candidate form evidence",
    );
  });

  it("does not loosen ordinary account registration pages into job applications", () => {
    expect(
      applicationPageEligibility(
        page({
          url: "https://accounts.example.test/Register",
          title: "Create account",
          semantics: ["FIRST_NAME", "LAST_NAME", "EMAIL"],
          navigationLabel: "Next",
        }),
      ).eligible,
    ).toBe(false);
  });

  it("does not treat a résumé/profile editor as an application without progression", () => {
    expect(
      applicationPageEligibility(
        page({
          url: "https://profile.example.test/documents",
          title: "Candidate profile",
          semantics: ["FIRST_NAME", "EMAIL"],
          resume: true,
        }),
      ).eligible,
    ).toBe(false);
  });

  it("accepts a known ATS page with application-specific questions", () => {
    expect(
      applicationPageEligibility(
        page({
          url: "https://company.wd5.myworkdayjobs.com/job/123",
          title: "Candidate questions",
          semantics: ["WORK_AUTHORIZATION_CURRENT"],
          atsFamily: "WORKDAY",
        }),
      ).eligible,
    ).toBe(true);
  });

  it("does not turn a candidate login into an application from one email field", () => {
    expect(
      applicationPageEligibility(
        page({
          url: "https://company.wd5.myworkdayjobs.com/candidate/login",
          title: "Candidate sign in",
          semantics: ["EMAIL"],
          atsFamily: "WORKDAY",
          applicationState: "AUTH",
        }),
      ).eligible,
    ).toBe(false);
  });

  it("accepts a résumé upload only inside application context", () => {
    expect(
      applicationPageEligibility(
        page({
          url: "https://careers.example.test/application/123",
          title: "Upload résumé",
          resume: true,
        }),
      ).eligible,
    ).toBe(true);
    expect(
      applicationPageEligibility(
        page({
          url: "https://files.example.test/profile",
          title: "Upload documents",
          resume: true,
        }),
      ).eligible,
    ).toBe(false);
  });

  it("accepts the verified final application boundary", () => {
    expect(
      applicationPageEligibility(
        page({
          url: "https://careers.example.test/step/7",
          title: "Final step",
          finalSubmissionBoundary: true,
        }),
      ).eligible,
    ).toBe(true);
  });

  it("does not crash on legacy snapshots that omit newer array fields", () => {
    const legacy = page({
      url: "https://help.openai.com/en/articles/legacy-help",
      title: "Legacy help page",
      semantics: ["UNKNOWN", "UNKNOWN"],
    }) as Partial<ApplicationPage>;
    delete legacy.controls;
    delete legacy.navigationCandidates;

    expect(applicationPageEligibility(legacy as ApplicationPage)).toEqual({
      eligible: false,
      reasons: [],
    });
  });
});
