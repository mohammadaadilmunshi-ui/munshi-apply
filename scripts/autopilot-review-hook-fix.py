from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one match in {path}, found {count}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "apps/extension/src/sidepanel/AIDraftReview.tsx",
    'import { useCallback, useEffect, useState } from "react";',
    'import { useCallback, useEffect, useMemo, useState } from "react";',
)
replace_once(
    "apps/extension/src/sidepanel/AIDraftReview.tsx",
    '''  const request = {
    applicationId,
    pageId,
    questionId: question.questionId,
    controlId: question.controlId,
    question: question.rawText,
    semanticType: question.semanticType,
    correlationId: `draft-${question.questionId}`,
    maxWords: 250,
    maxOutputTokens: 768,
  };
''',
    '''  const request = useMemo(
    () => ({
      applicationId,
      pageId,
      questionId: question.questionId,
      controlId: question.controlId,
      question: question.rawText,
      semanticType: question.semanticType,
      correlationId: `draft-${question.questionId}`,
      maxWords: 250,
      maxOutputTokens: 768,
    }),
    [
      applicationId,
      pageId,
      question.controlId,
      question.questionId,
      question.rawText,
      question.semanticType,
    ],
  );
''',
)
replace_once(
    "apps/extension/src/sidepanel/AIDraftReview.tsx",
    '  }, [applicationId, nativeAvailable, pageId, question.controlId, question.questionId, question.semanticType, question.rawText]);',
    '  }, [applicationId, nativeAvailable, pageId, question.controlId, question.questionId, question.semanticType, request]);',
)

replace_once(
    "apps/extension/src/sidepanel/AutoPilotControlCenter.tsx",
    'import { useEffect, useMemo, useState } from "react";',
    'import { useCallback, useEffect, useMemo, useState } from "react";',
)
replace_once(
    "apps/extension/src/sidepanel/AutoPilotControlCenter.tsx",
    '''  async function refresh(): Promise<void> {
    const next = await getAutoPilotStatus();
    setStatus(next);
    onStatusChange?.(next);
  }

  useEffect(() => {
    void refresh().catch(() => undefined);
    const timer = window.setInterval(() => {
      void refresh().catch(() => undefined);
    }, 900);
    return () => window.clearInterval(timer);
  }, []);
''',
    '''  const refresh = useCallback(async (): Promise<void> => {
    const next = await getAutoPilotStatus();
    setStatus(next);
    onStatusChange?.(next);
  }, [onStatusChange]);

  useEffect(() => {
    void refresh().catch(() => undefined);
    const timer = window.setInterval(() => {
      void refresh().catch(() => undefined);
    }, 900);
    return () => window.clearInterval(timer);
  }, [refresh]);
''',
)
