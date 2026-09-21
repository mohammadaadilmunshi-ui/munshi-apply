import { describe, expect, it } from "vitest";

import { ApplicationPageSchema } from "@munshi-apply/contracts";

import { detectAtsFamily } from "./adaptive";

describe("ATS provider bundle", () => {
  it("keeps the extended ATS enum accepted by the shared application-page contract", () => {
    for (const family of [
      "RIPPLING",
      "ICIMS",
      "BRASSRING",
      "JAZZHR",
      "JOBVITE",
      "BREEZYHR",
      "ORACLE_RECRUITING",
      "PAYLOCITY",
      "UKG_ULTIPRO",
      "ZOHO_RECRUIT",
      "ADP",
      "DOVER",
      "GEM",
      "SAP_SUCCESSFACTORS",
      "TEAMTAILOR",
      "PHENOM",
      "DAYFORCE",
      "CAREERPLUG",
      "HIREOLOGY",
    ]) {
      expect(
        ApplicationPageSchema.shape.atsFamily.safeParse(family).success,
      ).toBe(true);
    }
  });

  it("exports the detector used by the shared browser scanner", () => {
    expect(typeof detectAtsFamily).toBe("function");
  });
});
