import { describe, expect, it } from "vitest";
import {
  applicationIdentityQuery,
  applicationUrlIdentityKey,
  sameApplicationUrlLocation,
} from "./application-url";

describe("application-aware URL identity", () => {
  it("ignores tracking and session-like query differences", () => {
    const first = "https://jobs.example.com/apply?utm_source=a&source=linkedin";
    const second = "https://jobs.example.com/apply?utm_source=b&source=direct";
    expect(applicationIdentityQuery(first)).toBe("");
    expect(sameApplicationUrlLocation(first, second)).toBe(true);
  });

  it("distinguishes jobs whose identity lives only in the query string", () => {
    const first = "https://jobs.example.com/apply?job=123";
    const second = "https://jobs.example.com/apply?job=456";
    expect(applicationUrlIdentityKey(first)).not.toBe(
      applicationUrlIdentityKey(second),
    );
    expect(sameApplicationUrlLocation(first, second)).toBe(false);
  });

  it("recognizes common ATS job and requisition query keys after normalization", () => {
    const cases = [
      "gh_jid=123",
      "jk=123",
      "requisitionId=123",
      "currentJobId=123",
      "jobPostingId=123",
      "position_id=123",
      "req-id=123",
    ];
    for (const query of cases) {
      expect(applicationIdentityQuery(`https://jobs.example.com/apply?${query}`)).not.toBe(
        "",
      );
    }
  });

  it("is stable across query order and unrelated tracking parameters", () => {
    const first =
      "https://jobs.example.com/apply/?utm_campaign=x&requisitionId=ABC-9&job=123";
    const second =
      "https://jobs.example.com/apply?job=123&utm_campaign=y&requisitionId=ABC-9";
    expect(applicationUrlIdentityKey(first)).toBe(
      applicationUrlIdentityKey(second),
    );
  });

  it("fails closed when one location has an explicit job identity and the other does not", () => {
    expect(
      sameApplicationUrlLocation(
        "https://jobs.example.com/apply?job=123",
        "https://jobs.example.com/apply",
      ),
    ).toBe(false);
  });
});
