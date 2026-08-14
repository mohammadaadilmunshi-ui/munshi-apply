import { describe, expect, it } from "vitest";
import { computeReviewBacklog } from "./review-backlog";

function page(pageId: string, count: number) {
  return {
    pageId,
    questions: Array.from({ length: count }, (_, index) => ({
      questionId: `${pageId}-q-${index + 1}`,
      rawText: `Question ${index + 1}`,
    })),
  };
}

describe("computeReviewBacklog", () => {
  it("does not label historical discovered questions as current review work", () => {
    const historical = page("historical", 99);
    const active = page("active", 2);
    const result = computeReviewBacklog({
      pages: [historical, active],
      reviews: [
        {
          pageId: "active",
          approvedAt: "2026-08-14T18:00:00.000Z",
          answers: [
            {
              questionId: "active-q-1",
              approved: true,
            },
          ],
        },
      ],
      activePageIds: ["active"],
    });

    expect(result.discoveredQuestionCount).toBe(101);
    expect(result.activeQuestionCount).toBe(2);
    expect(result.ignoredHistoricalQuestionCount).toBe(99);
    expect(result.approvedCount).toBe(1);
    expect(result.openCount).toBe(1);
    expect(result.items[0]).toMatchObject({
      pageId: "active",
      questionId: "active-q-2",
      reason: "MISSING_ANSWER",
    });
  });

  it("uses only the latest review for each active page", () => {
    const active = page("active", 1);
    const result = computeReviewBacklog({
      pages: [active],
      reviews: [
        {
          pageId: "active",
          approvedAt: "2026-08-14T17:00:00.000Z",
          answers: [{ questionId: "active-q-1", approved: false }],
        },
        {
          pageId: "active",
          approvedAt: "2026-08-14T18:00:00.000Z",
          answers: [{ questionId: "active-q-1", approved: true }],
        },
      ],
      activePageIds: ["active"],
    });

    expect(result.openCount).toBe(0);
    expect(result.approvedCount).toBe(1);
  });

  it("deduplicates repeated question identities within a page", () => {
    const result = computeReviewBacklog({
      pages: [
        {
          pageId: "active",
          questions: [
            { questionId: "q-1", rawText: "Question" },
            { questionId: "q-1", rawText: "Question" },
          ],
        },
      ],
      reviews: [],
      activePageIds: ["active"],
    });

    expect(result.activeQuestionCount).toBe(1);
    expect(result.openCount).toBe(1);
  });
});
