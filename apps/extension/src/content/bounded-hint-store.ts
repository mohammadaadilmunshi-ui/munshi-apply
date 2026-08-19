export const DEFAULT_CONTROL_HINT_LIMIT = 1_024;

export type BoundedHintStore<T> = {
  get(key: string): T | undefined;
  set(key: string, value: T): void;
  size(): number;
};

export function createBoundedHintStore<T>(
  maxEntries = DEFAULT_CONTROL_HINT_LIMIT,
): BoundedHintStore<T> {
  const limit = Math.max(1, Math.floor(maxEntries));
  const values = new Map<string, T>();

  function touch(key: string, value: T): void {
    values.delete(key);
    values.set(key, value);
  }

  function prune(): void {
    while (values.size > limit) {
      const oldest = values.keys().next().value as string | undefined;
      if (oldest === undefined) return;
      values.delete(oldest);
    }
  }

  return {
    get(key) {
      const value = values.get(key);
      if (value === undefined) return undefined;
      touch(key, value);
      return value;
    },
    set(key, value) {
      touch(key, value);
      prune();
    },
    size() {
      return values.size;
    },
  };
}
