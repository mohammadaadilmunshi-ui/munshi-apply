type RuntimeSlot = {
  dispose: () => void;
};

type RuntimeGlobal = typeof globalThis & {
  __munshiApplyContentRuntimeV1__?: RuntimeSlot;
};

function runtimeGlobal(): RuntimeGlobal {
  return globalThis as RuntimeGlobal;
}

export function disposePreviousContentRuntime(): void {
  const scope = runtimeGlobal();
  const previous = scope.__munshiApplyContentRuntimeV1__;
  if (!previous) return;
  delete scope.__munshiApplyContentRuntimeV1__;
  try {
    previous.dispose();
  } catch {
    // A previous content-script execution may belong to an invalidated extension
    // context. DOM cleanup is best-effort and a fresh runtime is still allowed.
  }
}

export function registerContentRuntime(dispose: () => void): () => void {
  disposePreviousContentRuntime();
  const scope = runtimeGlobal();
  let active = true;
  const slot: RuntimeSlot = {
    dispose: () => {
      if (!active) return;
      active = false;
      if (scope.__munshiApplyContentRuntimeV1__ === slot) {
        delete scope.__munshiApplyContentRuntimeV1__;
      }
      dispose();
    },
  };
  scope.__munshiApplyContentRuntimeV1__ = slot;
  return slot.dispose;
}
