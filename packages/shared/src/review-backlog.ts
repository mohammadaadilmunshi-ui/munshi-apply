export type ReviewQuestionLike = {
  questionId: string;
  rawText: string;
};

export type ReviewPageLike = {
  pageId: string;
  questions: readonly ReviewQuestionLike[];
};

export type ReviewAnswerLike = {
  questionId: string;
  approved: boolean;
};

export type ReviewRecordLike = {
  pageId: string;
  approvedAt: string;
  answers: readonly ReviewAnswerLike[];
};

export type ReviewBacklogItem = {
  pageId: string;
  questionId: string;
  rawText: string;
  reason: "MISSING_ANSWER" | "UNAPPROVED_ANSWER";
};

export type ReviewBacklogSummary = {
  openCount: number;
  approvedCount: number;
  activeQuestionCount: number;
  discoveredQuestionCount: number;
  ignoredHistoricalQuestionCount: number;
  items: readonly ReviewBacklogItem[];
};

function latestReviewByPage(
  reviews: readonly ReviewRecordLike[],
): Map<string, ReviewRecordLike> {
  const latest = new Map<string, ReviewRecordLike>();
  for (const review of reviews) {
    const existing = latest.get(review.pageId);
    if (!existing || review.approvedAt > existing.approvedAt) {
      latest.set(review.pageId, review);
    }
  }
  return latest;
}

function uniqueQuestionCount(pages: readonly ReviewPageLike[]): number {
  const identities = new Set<string>();
  for (const page of pages) {
    for (const question of page.questions) {
      identities.add(`${page.pageId}:${question.questionId}`);
    }
  }
  return identities.size;
}

export function computeReviewBacklog(input: {
  pages: readonly ReviewPageLike[];
  reviews: readonly ReviewRecordLike[];
  activePageIds: readonly string[];
}): ReviewBacklogSummary {
  const activeIds = new Set(input.activePageIds);
  const activePages = input.pages.filter((page) => activeIds.has(page.pageId));
  const discoveredQuestionCount = uniqueQuestionCount(input.pages);
  const activeQuestionCount = uniqueQuestionCount(activePages);
  const latestReviews = latestReviewByPage(input.reviews);
  const items: ReviewBacklogItem[] = [];
  let approvedCount = 0;

  for (const page of activePages) {
    const answerByQuestion = new Map(
      (latestReviews.get(page.pageId)?.answers ?? []).map((answer) => [
        answer.questionId,
        answer,
      ]),
    );
    const seen = new Set<string>();
    for (const question of page.questions) {
      if (seen.has(question.questionId)) continue;
      seen.add(question.questionId);
      const answer = answerByQuestion.get(question.questionId);
      if (!answer) {
        items.push({
          pageId: page.pageId,
          questionId: question.questionId,
          rawText: question.rawText,
          reason: "MISSING_ANSWER",
        });
      } else if (!answer.approved) {
        items.push({
          pageId: page.pageId,
          questionId: question.questionId,
          rawText: question.rawText,
          reason: "UNAPPROVED_ANSWER",
        });
      } else {
        approvedCount += 1;
      }
    }
  }

  return {
    openCount: items.length,
    approvedCount,
    activeQuestionCount,
    discoveredQuestionCount,
    ignoredHistoricalQuestionCount: Math.max(
      0,
      discoveredQuestionCount - activeQuestionCount,
    ),
    items,
  };
}
