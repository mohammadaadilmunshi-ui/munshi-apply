from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one match in {path}, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def insert_before(path: str, marker: str, content: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if text.count(marker) != 1:
        raise SystemExit(f"expected one insertion marker in {path}: {marker[:120]!r}")
    target.write_text(text.replace(marker, content + marker, 1), encoding="utf-8")


# Preserve AI provenance through the fill instruction without changing the DOM fill payload semantics.
replace_once(
    "packages/contracts/src/index.ts",
    "  approved: z.boolean(),\n});",
    "  approved: z.boolean(),\n  sourceDraftId: z.string().min(1).optional(),\n});",
)
replace_once(
    "apps/extension/src/sidepanel/autopilot-plan.ts",
    "      sensitive: question.sensitive,\n      approved: true,\n    });",
    "      sensitive: question.sensitive,\n      approved: true,\n      sourceDraftId: answer.sourceDraftId ?? undefined,\n    });",
)

# Runtime state gains backward-compatible durable pause intent and pending AI-usage attribution.
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    "  navigationDispatchAttempted: boolean;\n};",
    "  navigationDispatchAttempted: boolean;\n"
    "  ownerPauseRequested: boolean;\n"
    "  ownerPauseReason: string | null;\n"
    "  pendingDraftUsageId: string | null;\n};",
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    "  actionDeadlineAt: string | null;\n};\n\nexport type AutoPilotStartInput",
    "  actionDeadlineAt: string | null;\n"
    "  ownerPauseRequested: boolean;\n"
    "  ownerPauseReason: string | null;\n"
    "  pendingDraftUsageId: string | null;\n"
    "};\n\nexport type AutoPilotStartInput",
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    "  getLatestCheckpoint: (\n    applicationId: string,\n  ) => Promise<AutoPilotCheckpoint | null>;\n",
    "  getLatestCheckpoint: (\n    applicationId: string,\n  ) => Promise<AutoPilotCheckpoint | null>;\n"
    "  markDraftUsed: (draftId: string) => Promise<void>;\n",
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    "      approved: candidate.approved,\n    };",
    "      approved: candidate.approved,\n"
    "      sourceDraftId:\n"
    "        candidate.sourceDraftId === undefined\n"
    "          ? undefined\n"
    '          : requiredString(candidate.sourceDraftId, "sourceDraftId"),\n'
    "    };",
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    "    navigationDispatchAttempted: candidate.navigationDispatchAttempted,\n  };",
    "    navigationDispatchAttempted: candidate.navigationDispatchAttempted,\n"
    "    ownerPauseRequested:\n"
    '      candidate.ownerPauseRequested === undefined\n'
    "        ? false\n"
    "        : Boolean(candidate.ownerPauseRequested),\n"
    "    ownerPauseReason:\n"
    "      candidate.ownerPauseReason === undefined\n"
    "        ? null\n"
    '        : nullableString(candidate.ownerPauseReason, "ownerPauseReason"),\n'
    "    pendingDraftUsageId:\n"
    "      candidate.pendingDraftUsageId === undefined\n"
    "        ? null\n"
    '        : nullableString(candidate.pendingDraftUsageId, "pendingDraftUsageId"),\n'
    "  };",
)

# Expose truthful queued-pause/audit state to the owner UI.
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    "      actionDeadlineAt: runtime.actionDeadlineAt,\n    };",
    "      actionDeadlineAt: runtime.actionDeadlineAt,\n"
    "      ownerPauseRequested: runtime.ownerPauseRequested,\n"
    "      ownerPauseReason: runtime.ownerPauseReason,\n"
    "      pendingDraftUsageId: runtime.pendingDraftUsageId,\n"
    "    };",
)

# Fail/stop/resume/persisted-pause clear queued pause intent. Pending usage is only cleared after
# native acknowledgement, so a worker restart can still reconcile it.
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    "      navigationDispatchAttempted: false,\n    });\n    await this.persist(failed);",
    "      navigationDispatchAttempted: false,\n"
    "      ownerPauseRequested: false,\n"
    "      ownerPauseReason: null,\n"
    "    });\n"
    "    await this.persist(failed);",
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    "        navigationDispatchAttempted: false,\n      });\n      await this.persist(paused);",
    "        navigationDispatchAttempted: false,\n"
    "        ownerPauseRequested: false,\n"
    "        ownerPauseReason: null,\n"
    "      });\n"
    "      await this.persist(paused);",
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    "      navigationDispatchAttempted: false,\n    });\n    const observation = observationFor(runtime, page);",
    "      navigationDispatchAttempted: false,\n"
    "      ownerPauseRequested: false,\n"
    "      ownerPauseReason: null,\n"
    "      pendingDraftUsageId: null,\n"
    "    });\n"
    "    const observation = observationFor(runtime, page);",
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    "        navigationDispatchAttempted: false,\n      });\n      await this.persist(runtime);\n      if (runtime.session.status === \"RUNNING\") {",
    "        navigationDispatchAttempted: false,\n"
    "        ownerPauseRequested: false,\n"
    "        ownerPauseReason: null,\n"
    "      });\n"
    "      await this.persist(runtime);\n"
    '      if (runtime.session.status === "RUNNING") {',
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    "        navigationDispatchAttempted: false,\n      });\n      await this.persist(stopped);",
    "        navigationDispatchAttempted: false,\n"
    "        ownerPauseRequested: false,\n"
    "        ownerPauseReason: null,\n"
    "      });\n"
    "      await this.persist(stopped);",
)

# Recoverable native usage settlement. It is safe to call repeatedly because native USED marking
# is made idempotent below.
insert_before(
    "apps/extension/src/background/autopilot-controller.ts",
    "  private async executeRunningStep(\n",
    '''  private async settlePendingDraftUsage(
    runtime: AutoPilotRuntimeState,
  ): Promise<AutoPilotRuntimeState> {
    if (!runtime.pendingDraftUsageId) return runtime;
    try {
      await this.dependencies.markDraftUsed(runtime.pendingDraftUsageId);
    } catch (error) {
      return this.fail(
        runtime,
        `AI draft usage attribution could not be persisted: ${
          error instanceof Error ? error.message : "unknown error"
        }`,
      );
    }
    const settled = parseAutoPilotRuntimeState({
      ...runtime,
      pendingDraftUsageId: null,
    });
    await this.persist(settled);
    return settled;
  }

''',
)

# Every new action first honors any queued owner pause. This means a pause requested while a fill
# or navigation is being verified takes effect before the following action.
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    "    if (runtime.session.status !== \"RUNNING\") return runtime;\n    if (canonicalUrl(page.url) !== canonicalUrl(runtime.lastUrl)) {",
    "    if (runtime.session.status !== \"RUNNING\") return runtime;\n"
    "    if (runtime.ownerPauseRequested) {\n"
    "      return this.persistPause(runtime, observationFor(runtime, page), {\n"
    '        type: "OWNER",\n'
    '        reason: runtime.ownerPauseReason ?? "Paused by owner",\n'
    "      });\n"
    "    }\n"
    "    if (canonicalUrl(page.url) !== canonicalUrl(runtime.lastUrl)) {",
)

# Arm the draft audit before DOM dispatch. Once DOM fill verifies, persist completed state first,
# then settle the draft usage before scheduling/continuing.
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    "          dispatchingFillControlId: plan.action.instruction.controlId,\n          actionDeadlineAt: this.deadline(FILL_TIMEOUT_MS),",
    "          dispatchingFillControlId: plan.action.instruction.controlId,\n"
    "          pendingDraftUsageId: plan.action.instruction.sourceDraftId ?? null,\n"
    "          actionDeadlineAt: this.deadline(FILL_TIMEOUT_MS),",
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    "        await this.persist(waiting);\n        this.scheduleDeadline(FILL_TIMEOUT_MS);\n        return waiting;",
    "        await this.persist(waiting);\n"
    "        const attributed = await this.settlePendingDraftUsage(waiting);\n"
    '        if (attributed.session.status === "PAUSED_ERROR") return attributed;\n'
    "        this.scheduleDeadline(FILL_TIMEOUT_MS);\n"
    "        return attributed;",
)

# Pause becomes a request when an action is in-flight instead of throwing at the owner. If the
# controller is idle between actions, it checkpoints and pauses immediately.
old_pause = '''  async pause(
    reason = "Paused by owner",
  ): Promise<AutoPilotControllerStatus | null> {
    return this.exclusive(async () => {
      const runtime = await this.load();
      if (!runtime) return null;
      if (runtime.session.status !== "RUNNING") {
        throw new Error(
          "AutoPilot can be owner-paused only between verified actions",
        );
      }
      const page = await this.dependencies.getPage(runtime.tabId);
      if (!page) throw new Error("No active application page is available");
      const paused = await this.persistPause(
        runtime,
        observationFor(runtime, page),
        { type: "OWNER", reason },
      );
      return this.statusFromRuntime(paused);
    });
  }
'''
new_pause = '''  async pause(
    reason = "Paused by owner",
  ): Promise<AutoPilotControllerStatus | null> {
    return this.exclusive(async () => {
      let runtime = await this.load();
      if (!runtime) return null;
      if (runtime.session.status === "PAUSED_OWNER") {
        return this.statusFromRuntime(runtime);
      }
      if (
        runtime.session.status === "WAITING_RESCAN" ||
        runtime.session.status === "WAITING_NAVIGATION" ||
        runtime.waitingFor !== null ||
        runtime.dispatchingFillControlId !== null
      ) {
        runtime = parseAutoPilotRuntimeState({
          ...runtime,
          ownerPauseRequested: true,
          ownerPauseReason: requiredString(reason, "reason"),
        });
        await this.persist(runtime);
        return this.statusFromRuntime(runtime);
      }
      if (runtime.session.status !== "RUNNING") {
        throw new Error("This AutoPilot state cannot accept an owner pause request");
      }
      const page = await this.dependencies.getPage(runtime.tabId);
      if (!page) throw new Error("No active application page is available");
      const paused = await this.persistPause(
        runtime,
        observationFor(runtime, page),
        { type: "OWNER", reason },
      );
      return this.statusFromRuntime(paused);
    });
  }
'''
replace_once(
    "apps/extension/src/background/autopilot-controller.ts", old_pause, new_pause
)

# Recovery reconciles pending AI usage before processing a rescan/navigation. If attribution fails,
# AutoPilot remains fail-closed with the already-completed DOM fill preserved in session history.
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    "    const page = await this.dependencies.getPage(runtime.tabId);\n    if (!page) {",
    "    const page = await this.dependencies.getPage(runtime.tabId);\n"
    "    if (runtime.pendingDraftUsageId) {\n"
    "      runtime = await this.settlePendingDraftUsage(runtime);\n"
    '      if (runtime.session.status === "PAUSED_ERROR") {\n'
    "        return this.statusFromRuntime(runtime);\n"
    "      }\n"
    "    }\n"
    "    if (!page) {",
)

# Service worker provides native usage acknowledgement to the controller.
replace_once(
    "apps/extension/src/background/service-worker.ts",
    "  getNativeHealth,\n  saveNativeApplicationCheckpoint,",
    "  getNativeHealth,\n  markAIDraftUsed,\n  saveNativeApplicationCheckpoint,",
)
replace_once(
    "apps/extension/src/background/service-worker.ts",
    "  getLatestCheckpoint: getLatestNativeApplicationCheckpoint,\n  scheduleTimeout:",
    "  getLatestCheckpoint: getLatestNativeApplicationCheckpoint,\n"
    "  markDraftUsed: async (draftId) => {\n"
    "    await markAIDraftUsed(draftId);\n"
    "  },\n"
    "  scheduleTimeout:",
)

# Side-panel client/status and cockpit expose queued pause and audit state truthfully.
replace_once(
    "apps/extension/src/messaging/client.ts",
    "  actionDeadlineAt: string | null;\n};",
    "  actionDeadlineAt: string | null;\n"
    "  ownerPauseRequested: boolean;\n"
    "  ownerPauseReason: string | null;\n"
    "  pendingDraftUsageId: string | null;\n"
    "};",
)
replace_once(
    "apps/extension/src/sidepanel/AutoPilotControlCenter.tsx",
    '  const pausable = status?.session.status === "RUNNING";',
    "  const pausable =\n"
    '    status?.session.status === "RUNNING" ||\n'
    '    status?.session.status === "WAITING_RESCAN" ||\n'
    '    status?.session.status === "WAITING_NAVIGATION";\n'
    "  const pauseQueued = status?.ownerPauseRequested === true;",
)
replace_once(
    "apps/extension/src/sidepanel/AutoPilotControlCenter.tsx",
    "            <span>Waiting for: {status?.waitingFor ?? \"none\"}</span>",
    "            <span>Waiting for: {status?.waitingFor ?? \"none\"}</span>\n"
    "            {pauseQueued && (\n"
    '              <span className="diagnostic-error">\n'
    "                Pause requested · current action will verify before AutoPilot stops\n"
    "              </span>\n"
    "            )}\n"
    "            {status?.pendingDraftUsageId && (\n"
    '              <span className="diagnostic-error">\n'
    "                Recording approved AI-answer usage before continuing\n"
    "              </span>\n"
    "            )}",
)
replace_once(
    "apps/extension/src/sidepanel/AutoPilotControlCenter.tsx",
    "              disabled={busy || !pausable}",
    "              disabled={busy || !pausable || pauseQueued}",
)
replace_once(
    "apps/extension/src/sidepanel/AutoPilotControlCenter.tsx",
    '                  "AutoPilot paused after a durable checkpoint.",',
    '                  "Pause requested. MUNSHI will finish verifying any in-flight action, persist a checkpoint, and stop before the next action.",',
)

# Avoid a STOPPED/stale runtime binding a newly viewed application to an old AI draft history.
insert_before(
    "apps/extension/src/sidepanel/App.tsx",
    "export function App() {\n",
    '''function sameOrigin(left: string, right: string): boolean {
  try {
    return new URL(left).origin === new URL(right).origin;
  } catch {
    return false;
  }
}

''',
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    "  const activeApplicationId =\n"
    '    autoPilotStatus?.session.applicationId ?? page?.pageId ?? "";',
    "  const runtimeOwnsCurrentPage = Boolean(\n"
    "    autoPilotStatus &&\n"
    "      page &&\n"
    '      autoPilotStatus.session.status !== "STOPPED" &&\n'
    "      sameOrigin(autoPilotStatus.lastUrl, page.url),\n"
    "  );\n"
    "  const activeApplicationId = runtimeOwnsCurrentPage\n"
    "    ? autoPilotStatus!.session.applicationId\n"
    '    : (page?.pageId ?? "");',
)

# Native USED transition is idempotent to make service-worker recovery safe.
replace_once(
    "apps/native-host/src/munshi_apply_native/ai_draft_store.py",
    '            if row["status"] != "APPROVED":\n'
    '                raise ValueError("Only an approved AI draft can be marked used")',
    '            if row["status"] == "USED":\n'
    "                connection.commit()\n"
    "                return self._wire(row)\n"
    '            if row["status"] != "APPROVED":\n'
    '                raise ValueError("Only an approved AI draft can be marked used")',
)

# Harness supports native usage tracking.
replace_once(
    "apps/extension/src/background/autopilot-controller.test.ts",
    "  let navigateCount = 0;\n  let id = 0;",
    "  let navigateCount = 0;\n  let draftUseCount = 0;\n  let id = 0;",
)
replace_once(
    "apps/extension/src/background/autopilot-controller.test.ts",
    "    getLatestCheckpoint: async () => latestCheckpoint,\n    now: () => {",
    "    getLatestCheckpoint: async () => latestCheckpoint,\n"
    "    markDraftUsed: async (draftId) => {\n"
    "      draftUseCount += 1;\n"
    "      events.push(`draft-used:${draftId}`);\n"
    "    },\n"
    "    now: () => {",
)
replace_once(
    "apps/extension/src/background/autopilot-controller.test.ts",
    "      return { fillCount, navigateCount, checkpointAttempts };",
    "      return { fillCount, navigateCount, checkpointAttempts, draftUseCount };",
)

# Tests: queued pause waits for fresh verification and prevents the second fill; AI provenance is
# carried into AutoPilot and usage is recorded exactly once.
controller_test = Path("apps/extension/src/background/autopilot-controller.test.ts")
text = controller_test.read_text(encoding="utf-8")
closing = "\n});\n"
if not text.endswith(closing):
    raise SystemExit("autopilot-controller.test.ts closing marker mismatch")
extra = '''

  it("queues an owner pause during a fill wait and pauses before the next action", async () => {
    const test = harness(page({ controls: ["first", "last"] }));
    const started = await test.controller.start(
      startInput([instruction("first"), instruction("last")]),
    );
    expect(started.session.status).toBe("WAITING_RESCAN");

    const requested = await test.controller.pause("Owner requested pause");
    expect(requested?.ownerPauseRequested).toBe(true);
    expect(requested?.waitingFor).toBe("FILL");

    const fresh = page({
      controls: ["first", "last"],
      observedAt: "2026-08-14T22:00:00.000Z",
    });
    test.setPage(fresh);
    const paused = await test.controller.onPageSnapshot(7, fresh);

    expect(paused?.session.status).toBe("PAUSED_OWNER");
    expect(paused?.ownerPauseRequested).toBe(false);
    expect(paused?.session.completedControlIds).toEqual(["first"]);
    expect(test.counts().fillCount).toBe(1);
    expect(test.counts().checkpointAttempts).toBeGreaterThan(0);
  });

  it("records approved AI draft usage exactly once after a verified AutoPilot fill", async () => {
    const test = harness(page({ controls: ["narrative"] }));
    const aiInstruction: FillInstruction = {
      ...instruction("narrative"),
      sourceDraftId: "draft-1",
    };

    const started = await test.controller.start(startInput([aiInstruction]));

    expect(started.session.status).toBe("WAITING_RESCAN");
    expect(started.pendingDraftUsageId).toBeNull();
    expect(test.counts().draftUseCount).toBe(1);
    expect(test.events).toContain("draft-used:draft-1");
  });
'''
controller_test.write_text(text[: -len(closing)] + extra + closing, encoding="utf-8")

plan_test = Path("apps/extension/src/sidepanel/autopilot-plan.test.ts")
text = plan_test.read_text(encoding="utf-8")
if not text.endswith(closing):
    raise SystemExit("autopilot-plan.test.ts closing marker mismatch")
extra = '''

  it("carries an approved AI draft identity into the AutoPilot fill instruction", () => {
    const current = page();
    current.controls = [current.controls[0]!];
    current.questions = [current.questions[0]!];
    const result = buildAutoPilotLaunchPlan(current, {
      "q-name": {
        value: "Evidence-backed answer",
        approved: true,
        sensitive: false,
        sourceDraftId: "draft-1",
      },
    });
    expect(result.fillInstructions[0]?.sourceDraftId).toBe("draft-1");
  });
'''
plan_test.write_text(text[: -len(closing)] + extra + closing, encoding="utf-8")

native_test = Path("apps/native-host/tests/test_ai_draft_store.py")
text = native_test.read_text(encoding="utf-8")
text += '''


def test_mark_used_is_idempotent_for_recovery(tmp_path: Path) -> None:
    store = AIDraftStore(database(tmp_path))
    created = store.create(record())
    approved = store.approve(created["draftId"], created["contentSha256"], NOW)
    first = store.mark_used(approved["draftId"], NOW)
    second = store.mark_used(approved["draftId"], NOW)
    assert first["status"] == "USED"
    assert second["status"] == "USED"
    assert second["usedAt"] == first["usedAt"]
'''
native_test.write_text(text, encoding="utf-8")
