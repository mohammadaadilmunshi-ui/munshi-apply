from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Guard failed for {path}: expected 1 match, found {count}")
    target.write_text(text.replace(old, new, 1))


def replace_between(path: str, start: str, end: str, new: str) -> None:
    target = Path(path)
    text = target.read_text()
    left = text.find(start)
    if left < 0:
        raise SystemExit(f"Guard failed for {path}: start marker not found")
    right = text.find(end, left)
    if right < 0:
        raise SystemExit(f"Guard failed for {path}: end marker not found")
    target.write_text(text[:left] + new + text[right:])


replace_once(
    "apps/extension/src/messaging/client.ts",
    '''export type TeachMunshiStart = {
  sessionId: string;
  controlId: string;
  label: string;
  componentFingerprint: string;
  startedAt: string;
};''',
    '''export type TeachMunshiStart = {
  sessionId: string;
  frameId: number;
  controlId: string;
  label: string;
  componentFingerprint: string;
  startedAt: string;
};''',
)
replace_once(
    "apps/extension/src/messaging/client.ts",
    '''export type TeachMunshiResult = {
  sessionId: string;
  controlId: string;
  changed: boolean;''',
    '''export type TeachMunshiResult = {
  sessionId: string;
  controlId: string;
  resolvedControlId?: string;
  changed: boolean;''',
)
replace_once(
    "apps/extension/src/messaging/client.ts",
    '''export async function beginTeachMunshi(
  frameId: number,
  controlId: string,
  applicationId: string,
): Promise<TeachMunshiStart> {
  return (await send({
    type: "TEACH_BEGIN",
    payload: { frameId, controlId, applicationId },
  })) as TeachMunshiStart;
}''',
    '''export async function beginTeachMunshi(
  frameId: number,
  controlId: string,
  applicationId: string,
): Promise<TeachMunshiStart> {
  const started = (await send({
    type: "TEACH_BEGIN",
    payload: { frameId, controlId, applicationId },
  })) as Omit<TeachMunshiStart, "frameId">;
  return { ...started, frameId };
}''',
)

replace_once(
    "apps/extension/src/sidepanel/TeachMunshiPanel.tsx",
    '''  const selectedLabel = active
    ? labelFor(active.controlId)
    : selected
      ? labelFor(selected)
      : "";''',
    '''  const selectedLabel = active
    ? active.label || labelFor(active.controlId)
    : selected
      ? labelFor(selected)
      : "";''',
)
replace_between(
    "apps/extension/src/sidepanel/TeachMunshiPanel.tsx",
    "  async function finish(): Promise<void> {\n",
    "  async function cancel(): Promise<void> {\n",
    '''  async function finish(): Promise<void> {
    if (!active) return;
    setBusy(true);
    setMessage("");
    setResultTone(null);
    try {
      const learned = await finishTeachMunshi(
        active.frameId,
        active.sessionId,
        applicationId,
      );
      setActive(null);

      if (!learned.reusable || !learned.recipe) {
        const quality = learned.quality
          ? Math.round(learned.quality.score * 100)
          : null;
        if (quality === 0) {
          setResultTone("error");
          setMessage(
            "I did not see the interaction, so nothing was learned. Start again, wait until MUNSHI says Watching, then complete only that field on the employer page before returning here.",
          );
        } else {
          setResultTone("warning");
          setMessage(
            quality === null
              ? "I saw the interaction, but not enough of it to save a safe lesson. Nothing was learned; you can continue the application manually."
              : `I saw part of the interaction (${quality}% confidence), but not enough to save a safe lesson. Retry once, starting before you touch the field.`,
          );
        }
        return;
      }

      const quality = learned.quality
        ? Math.round(learned.quality.score * 100)
        : null;
      setResultTone("success");
      setMessage(
        `Lesson captured${quality === null ? "" : ` with ${quality}% confidence`}. MUNSHI saved it in testing mode and will trust it only after a future matching control is completed and verified successfully.`,
      );
    } catch (error) {
      setResultTone("error");
      setMessage(
        error instanceof Error
          ? error.message
          : "MUNSHI could not finish learning this interaction.",
      );
    } finally {
      setBusy(false);
    }
  }

''',
)
replace_between(
    "apps/extension/src/sidepanel/TeachMunshiPanel.tsx",
    "  async function cancel(): Promise<void> {\n",
    "  return (\n",
    '''  async function cancel(): Promise<void> {
    if (!active) return;
    setBusy(true);
    try {
      await cancelTeachMunshi(active.frameId, active.sessionId);
    } finally {
      setActive(null);
      setResultTone("warning");
      setMessage(
        "Teaching cancelled. Nothing from this demonstration was saved.",
      );
      setBusy(false);
    }
  }

''',
)

replace_once(
    "apps/extension/src/background/service-worker.ts",
    '''          sessionId: string;
          controlId: string;
          componentFingerprint: string;
          changed: boolean;''',
    '''          sessionId: string;
          controlId: string;
          resolvedControlId?: string;
          componentFingerprint: string;
          changed: boolean;''',
)
replace_once(
    "apps/extension/src/background/service-worker.ts",
    '''  const control = page.controls.find(
    (item) => item.controlId === capture.controlId,
  );
  const question = page.questions.find(
    (item) => item.controlId === capture.controlId,
  );
  if (!control || !control.componentFingerprint) {
    throw new Error(
      "The demonstrated control changed before its recipe could be saved",
    );
  }
  await ensureNativeApplication(applicationId, page.observedAt);
  const recipe = await teachInteractionRecipe({
    attemptId: `demo-${crypto.randomUUID()}`,
    applicationId,
    siteOrigin: new URL(page.url).origin,
    componentFingerprint: control.componentFingerprint,
    semanticType: question?.semanticType ?? "UNKNOWN",
    actions: capture.actions,
  });''',
    '''  const resolvedControlId = capture.resolvedControlId ?? capture.controlId;
  const control = page.controls.find(
    (item) => item.controlId === resolvedControlId,
  );
  const question = page.questions.find(
    (item) => item.controlId === (control?.controlId ?? resolvedControlId),
  );
  const componentFingerprint =
    control?.componentFingerprint || capture.componentFingerprint;
  if (!componentFingerprint) {
    throw new Error(
      "The demonstrated control changed before its recipe could be saved",
    );
  }
  await ensureNativeApplication(applicationId, page.observedAt);
  const recipe = await teachInteractionRecipe({
    attemptId: `demo-${crypto.randomUUID()}`,
    applicationId,
    siteOrigin: new URL(page.url).origin,
    componentFingerprint,
    semanticType: question?.semanticType ?? "UNKNOWN",
    actions: capture.actions,
  });''',
)

replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    'import { ResumeVaultPanel } from "./ResumeVaultPanel";',
    '''import { ResumeVaultPanel } from "./ResumeVaultPanel";
import {
  canAutoApproveRememberedAnswer,
  getRememberedAnswer,
  saveRememberedAnswer,
} from "../storage/answer-memory";''',
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''type AnswerDraft = {
  value: string;
  approved: boolean;
  sensitive: boolean;
  sourceDraftId?: string | null;
  ownerEdited?: boolean;
};''',
    '''type AnswerDraft = {
  value: string;
  approved: boolean;
  sensitive: boolean;
  sourceDraftId?: string | null;
  ownerEdited?: boolean;
  remembered?: boolean;
};''',
)

anchor = '''  const selectedResume = useMemo(
'''
insert = '''  useEffect(() => {
    let cancelled = false;
    if (!page) return () => undefined;

    void Promise.all(
      page.questions.map(async (question) => [
        question.questionId,
        await getRememberedAnswer(question.rawText).catch(() => null),
      ] as const),
    ).then((entries) => {
      if (cancelled) return;
      const memories = new Map(entries);
      setAnswers((current) => {
        const next = { ...current };
        for (const question of page.questions) {
          const existing = next[question.questionId];
          if (existing?.ownerEdited || existing?.value.trim()) continue;
          const remembered = memories.get(question.questionId);
          if (!remembered?.value.trim()) continue;
          const control = page.controls.find(
            (candidate) => candidate.controlId === question.controlId,
          );
          next[question.questionId] = {
            value: remembered.value,
            approved: canAutoApproveRememberedAnswer({
              semanticType: question.semanticType,
              controlKind: control?.kind,
              value: remembered.value,
            }),
            sensitive: Boolean(question.sensitive || remembered.sensitive),
            remembered: true,
          };
        }
        return next;
      });
    });

    return () => {
      cancelled = true;
    };
  }, [page]);

  useEffect(() => {
    if (!page) return;
    for (const question of page.questions) {
      const answer = answers[question.questionId];
      if (
        !answer?.ownerEdited ||
        !answer.approved ||
        !answer.value.trim()
      ) {
        continue;
      }
      void saveRememberedAnswer({
        question: question.rawText,
        semanticType: question.semanticType,
        value: answer.value,
        sensitive: Boolean(question.sensitive || answer.sensitive),
      }).catch((error: unknown) => {
        setNotice(
          error instanceof Error
            ? `Answer memory unavailable: ${error.message}`
            : "Answer memory is temporarily unavailable.",
        );
      });
    }
  }, [answers, page]);

'''
replace_once("apps/extension/src/sidepanel/App.tsx", anchor, insert + anchor)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    "Approved for this application",
    "Approved · remember for matching questions",
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''                      </label>
                      <AIDraftReview''',
    '''                      </label>
                      {answer.remembered && (
                        <span className="answer-memory-note">
                          Remembered from a previous approved answer.
                        </span>
                      )}
                      <AIDraftReview''',
)

new_fill = '''  async function fillApprovedFields(): Promise<void> {
    if (!page) return;
    setFilling(true);
    try {
      const workingAnswers: Record<string, AnswerDraft> = { ...answers };
      const attemptedControlIds = new Set<string>();
      const allResults: Awaited<ReturnType<typeof applyFillPlan>> = [];
      const usedDraftIds = new Set<string>();
      let currentPage: ApplicationPage = page;
      let dynamicRounds = 0;

      const connection = await getCloudConnection();
      if (
        connection &&
        cloud.status === "connected" &&
        cloud.data.encryptionReady
      ) {
        const selectedResume = cloudSnapshot?.resumes.find(
          (resume) => resume.resumeId === selectedResumeId,
        );
        const review: ApplicationReview = {
          reviewId: `review-${page.pageId}`,
          pageId: page.pageId,
          resumeId: selectedResumeId || null,
          resumeSha256: selectedResume?.sha256 ?? null,
          approvedAt: now(),
          answers: page.questions.map((question) => {
            const answer = workingAnswers[question.questionId] ?? {
              value: "",
              approved: false,
              sensitive: question.sensitive,
            };
            return {
              questionId: question.questionId,
              controlId: question.controlId,
              value: answer.value,
              approved: answer.approved,
              sensitive: question.sensitive,
            };
          }),
        };
        await publishApplicationReview(connection, review);
      }

      for (let round = 0; round < 4; round += 1) {
        const controls = new Map(
          currentPage.controls.map((control) => [control.controlId, control]),
        );
        const memories = await Promise.all(
          currentPage.questions.map(async (question) => [
            question.questionId,
            await getRememberedAnswer(question.rawText).catch(() => null),
          ] as const),
        );
        const memoryByQuestion = new Map(memories);

        for (const question of currentPage.questions) {
          const existing = workingAnswers[question.questionId];
          if (existing?.value.trim()) continue;
          const resolution = resolveProfileAnswer(question, profile);
          if (resolution.value != null && String(resolution.value).trim()) {
            workingAnswers[question.questionId] = {
              value: String(resolution.value),
              approved: resolution.state === "READY",
              sensitive: resolution.sensitive,
            };
            continue;
          }
          const remembered = memoryByQuestion.get(question.questionId);
          if (!remembered?.value.trim()) continue;
          const control = controls.get(question.controlId);
          workingAnswers[question.questionId] = {
            value: remembered.value,
            approved: canAutoApproveRememberedAnswer({
              semanticType: question.semanticType,
              controlKind: control?.kind,
              value: remembered.value,
            }),
            sensitive: Boolean(question.sensitive || remembered.sensitive),
            remembered: true,
          };
        }

        setAnswers((current) => ({ ...current, ...workingAnswers }));

        const instructions: FillInstruction[] = currentPage.questions
          .map((question) => {
            const answer = workingAnswers[question.questionId];
            const control = controls.get(question.controlId);
            if (
              !answer ||
              !control ||
              !answer.value.trim() ||
              !answer.approved ||
              attemptedControlIds.has(question.controlId)
            ) {
              return null;
            }
            return {
              controlId: question.controlId,
              frameId: control.frameId,
              value: answer.value,
              sensitive: question.sensitive,
              approved: true,
            };
          })
          .filter(
            (instruction): instruction is FillInstruction => instruction !== null,
          );

        if (instructions.length === 0) break;
        instructions.forEach((instruction) =>
          attemptedControlIds.add(instruction.controlId),
        );

        const results = await applyFillPlan({
          pageId: currentPage.pageId,
          instructions,
        });
        allResults.push(...results);
        for (const result of results) {
          if (result.status !== "FILLED") continue;
          const question = currentPage.questions.find(
            (candidate) => candidate.controlId === result.controlId,
          );
          const draftId = question
            ? workingAnswers[question.questionId]?.sourceDraftId
            : null;
          if (draftId) usedDraftIds.add(draftId);
        }

        await new Promise((resolve) => window.setTimeout(resolve, 450));
        const latest = await getActivePage();
        if (!latest || !sameOrigin(latest.url, currentPage.url)) break;
        const previousQuestionIds = new Set(
          currentPage.questions.map((question) => question.questionId),
        );
        const revealed = latest.questions.filter(
          (question) => !previousQuestionIds.has(question.questionId),
        ).length;
        if (revealed > 0) dynamicRounds += 1;
        currentPage = latest;
      }

      await Promise.allSettled(
        [...usedDraftIds].map((draftId) => markAIDraftUsed(draftId)),
      );
      const filled = allResults.filter(
        (result) => result.status === "FILLED",
      ).length;
      const skipped = allResults.length - filled;
      if (allResults.length === 0) {
        setNotice("No approved answers are ready to fill.");
        return;
      }
      setNotice(
        `${filled} field${filled === 1 ? "" : "s"} filled and verified${dynamicRounds ? ` across ${dynamicRounds + 1} dynamic form passes` : ""}${skipped ? `; ${skipped} require manual interaction` : ""}. Newly revealed unresolved questions stay visible for your review. Final submission remains manual.`,
      );
    } catch (error) {
      setNotice(
        error instanceof Error ? error.message : "Verified fill failed",
      );
    } finally {
      setFilling(false);
    }
  }

'''
replace_between(
    "apps/extension/src/sidepanel/App.tsx",
    "  async function fillApprovedFields(): Promise<void> {\n",
    "  async function storeApiKey(): Promise<void> {\n",
    new_fill,
)

print("Guarded dynamic Teach + Answer Memory + iterative fill patch applied")
