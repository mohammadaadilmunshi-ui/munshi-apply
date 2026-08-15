import test from "node:test";
import assert from "node:assert/strict";
import {
  isEligibleApplicationSnapshot,
  pendingReviewCount,
} from "../app/application-eligibility.ts";

function snapshot(overrides = {}) {
  return {
    pageId: "page-1",
    title: "Page",
    url: "https://example.test/",
    observedAt: "2026-08-14T20:00:00.000Z",
    questions: [],
    controls: [],
    applicationState: "QUESTIONS",
    navigationCandidates: [],
    finalSubmissionBoundary: false,
    atsFamily: "GENERIC",
    ...overrides,
  };
}

function question(questionId, semanticType, requiresReview = true) {
  return {
    questionId,
    controlId: `ctl-${questionId}`,
    rawText: questionId,
    semanticType,
    sensitive: false,
    requiresReview,
  };
}

test("owner queue hides ordinary help and portfolio snapshots", () => {
  assert.equal(
    isEligibleApplicationSnapshot(
      snapshot({
        title: "GPT-5.6 in ChatGPT | OpenAI Help Center",
        url: "https://help.openai.com/en/articles/123",
        questions: [question("q1", "UNKNOWN"), question("q2", "UNKNOWN")],
      }),
      "https://munshi-apply-mobile.mohammadaadilmunshi.chatgpt.site",
    ),
    false,
  );
  assert.equal(
    isEligibleApplicationSnapshot(
      snapshot({
        title: "Aadil Munshi | HR Operations & People Analytics",
        url: "https://munshi.systems/",
      }),
    ),
    false,
  );
});

test("owner queue always hides its own encrypted workspace origin", () => {
  const ownOrigin =
    "https://munshi-apply-mobile.mohammadaadilmunshi.chatgpt.site";
  assert.equal(
    isEligibleApplicationSnapshot(
      snapshot({
        title: "MUNSHI Apply",
        url: `${ownOrigin}/workspace`,
        questions: [
          question("q1", "FIRST_NAME"),
          question("q2", "EMAIL"),
          question("q3", "WORK_AUTHORIZATION_CURRENT"),
        ],
        atsFamily: "GENERIC",
      }),
      ownOrigin,
    ),
    false,
  );
});

test("owner queue keeps real generic and ATS application snapshots", () => {
  assert.equal(
    isEligibleApplicationSnapshot(
      snapshot({
        title: "Application",
        url: "https://careers.example.test/apply/123",
        questions: [
          question("q1", "FIRST_NAME", false),
          question("q2", "EMAIL", false),
        ],
      }),
    ),
    true,
  );
  assert.equal(
    isEligibleApplicationSnapshot(
      snapshot({
        title: "Candidate questions",
        url: "https://company.wd5.myworkdayjobs.com/job/123",
        questions: [question("q1", "WORK_AUTHORIZATION_CURRENT")],
        atsFamily: "WORKDAY",
      }),
    ),
    true,
  );
});

test("pending review count excludes questions already explicitly approved", () => {
  const application = snapshot({
    questions: [
      question("q1", "WORK_AUTHORIZATION_CURRENT", true),
      question("q2", "EMAIL", true),
      question("q3", "FIRST_NAME", false),
    ],
  });
  assert.equal(pendingReviewCount(application), 2);
  assert.equal(
    pendingReviewCount(application, {
      reviewId: "review-page-1",
      pageId: "page-1",
      resumeId: null,
      approvedAt: "2026-08-14T20:05:00.000Z",
      answers: [
        {
          questionId: "q1",
          controlId: "ctl-q1",
          value: "approved",
          approved: true,
          sensitive: true,
        },
        {
          questionId: "q2",
          controlId: "ctl-q2",
          value: "draft",
          approved: false,
          sensitive: false,
        },
      ],
    }),
    1,
  );
});
