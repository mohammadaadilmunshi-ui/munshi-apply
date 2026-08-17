const applicationIdentityQueryKeys = new Set([
  "currentjobid",
  "ghjid",
  "jid",
  "jk",
  "job",
  "jobid",
  "jobpostingid",
  "jobrequisitionid",
  "jobreqid",
  "openingid",
  "positionid",
  "postingid",
  "reqid",
  "requisition",
  "requisitionid",
  "requisitionnumber",
  "vacancyid",
]);

function normalizedQueryKey(value: string): string {
  return value.toLocaleLowerCase("en-US").replace(/[^a-z0-9]/g, "");
}

function normalizedPathname(pathname: string): string {
  const withoutTrailingSlash = pathname.replace(/\/+$/, "");
  return withoutTrailingSlash || "/";
}

function identityQueryPairs(url: URL): Array<[string, string]> {
  const pairs: Array<[string, string]> = [];
  for (const [rawKey, rawValue] of url.searchParams.entries()) {
    const key = normalizedQueryKey(rawKey);
    const value = rawValue.trim();
    if (!applicationIdentityQueryKeys.has(key) || !value) continue;
    pairs.push([key, value]);
  }
  return pairs.sort(([leftKey, leftValue], [rightKey, rightValue]) => {
    const byKey = leftKey.localeCompare(rightKey);
    return byKey || leftValue.localeCompare(rightValue);
  });
}

export function applicationIdentityQuery(value: string): string {
  const url = new URL(value);
  return identityQueryPairs(url)
    .map(
      ([key, item]) => `${encodeURIComponent(key)}=${encodeURIComponent(item)}`,
    )
    .join("&");
}

export function applicationUrlIdentityKey(value: string): string {
  const url = new URL(value);
  const query = applicationIdentityQuery(url.href);
  const location = `${url.origin.toLocaleLowerCase("en-US")}${normalizedPathname(url.pathname)}`;
  return query ? `${location}?${query}` : location;
}

export function sameApplicationUrlLocation(
  leftValue: string,
  rightValue: string,
): boolean {
  return applicationUrlIdentityKey(leftValue) === applicationUrlIdentityKey(rightValue);
}

export function sameExplicitApplicationIdentity(
  leftValue: string,
  rightValue: string,
): boolean {
  const left = new URL(leftValue);
  const right = new URL(rightValue);
  if (left.origin !== right.origin) return false;

  const leftIdentity = applicationIdentityQuery(left.href);
  const rightIdentity = applicationIdentityQuery(right.href);
  if (!leftIdentity && !rightIdentity) return true;
  return Boolean(leftIdentity && rightIdentity && leftIdentity === rightIdentity);
}
