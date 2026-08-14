export * from "./workspace-status";

const secretKeys = /password|secret|token|api[_-]?key|cookie|authorization/i;

export function redactMetadata(
  value: Record<string, unknown>,
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => {
      if (secretKeys.test(key)) return [key, "[REDACTED]"];
      if (item && typeof item === "object" && !Array.isArray(item)) {
        return [key, redactMetadata(item as Record<string, unknown>)];
      }
      return [key, item];
    }),
  );
}

export function createId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}
