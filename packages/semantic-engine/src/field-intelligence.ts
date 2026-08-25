import type { SemanticType } from "@munshi-apply/contracts";
import {
  classifyQuestion as classifyBaseQuestion,
  type ClassificationResult,
} from "./index";

interface AliasRule {
  id: string;
  pattern: RegExp;
  semanticType: SemanticType;
  sensitive?: boolean;
  requiresReview?: boolean;
  confidence?: number;
}

const aliasRules: readonly AliasRule[] = [
  {
    id: "applicant-full-name",
    pattern:
      /^(?:applicant|candidate)(?: s)? (?:full |legal )?name$|^name of (?:the )?(?:applicant|candidate)$/,
    semanticType: "PERSONAL",
    sensitive: true,
    requiresReview: true,
  },
  {
    id: "legal-first-name",
    pattern: /^(?:legal )?(?:first|given) names?$|^forenames?$/,
    semanticType: "FIRST_NAME",
  },
  {
    id: "legal-middle-name",
    pattern: /^(?:legal )?middle (?:name|initial)s?$/,
    semanticType: "MIDDLE_NAME",
  },
  {
    id: "legal-last-name",
    pattern: /^(?:legal )?(?:last|family) names?$|^surnames?$/,
    semanticType: "LAST_NAME",
  },
  {
    id: "cell-phone",
    pattern:
      /^(?:cell|mobile|telephone|contact) (?:phone )?(?:number|no)$|^cell phone$/,
    semanticType: "PHONE",
  },
  {
    id: "website-url",
    pattern: /^(?:personal )?(?:site|website)(?: url| link)?$/,
    semanticType: "WEBSITE",
  },
  {
    id: "full-address",
    pattern:
      /^(?:full |complete )?(?:mailing|residential|home) address$|^full address$/,
    semanticType: "ADDRESS",
    sensitive: true,
    requiresReview: true,
  },
  {
    id: "role-title",
    pattern: /^(?:current |most recent )?role title$/,
    semanticType: "JOB_TITLE",
  },
  {
    id: "organization-name",
    pattern: /^(?:current |most recent )?organization name$/,
    semanticType: "EMPLOYER_NAME",
  },
];

const metadataRules: readonly AliasRule[] = [
  {
    id: "metadata-first-name",
    pattern: /\b(?:given name|givenname|first name|firstname)\b/,
    semanticType: "FIRST_NAME",
  },
  {
    id: "metadata-middle-name",
    pattern: /\b(?:additional name|additionalname|middle name|middlename)\b/,
    semanticType: "MIDDLE_NAME",
  },
  {
    id: "metadata-last-name",
    pattern: /\b(?:family name|familyname|last name|lastname|surname)\b/,
    semanticType: "LAST_NAME",
  },
  {
    id: "metadata-full-name",
    pattern: /\b(?:full name|fullname|legal name|candidate name|applicant name)\b/,
    semanticType: "PERSONAL",
    sensitive: true,
    requiresReview: true,
  },
  {
    id: "metadata-email",
    pattern: /\b(?:email|email address|emailaddress)\b/,
    semanticType: "EMAIL",
  },
  {
    id: "metadata-phone",
    pattern: /\b(?:tel|telephone|phone|mobile|cell phone|cellphone)\b/,
    semanticType: "PHONE",
  },
  {
    id: "metadata-address-line-1",
    pattern: /\b(?:street address|streetaddress|address line1|addressline1)\b/,
    semanticType: "STREET_ADDRESS",
  },
  {
    id: "metadata-address-line-2",
    pattern: /\b(?:address line2|addressline2)\b/,
    semanticType: "ADDRESS_LINE_2",
  },
  {
    id: "metadata-city",
    pattern: /\b(?:address level2|addresslevel2|locality)\b/,
    semanticType: "CITY",
  },
  {
    id: "metadata-state",
    pattern: /\b(?:address level1|addresslevel1|region)\b/,
    semanticType: "STATE_PROVINCE",
  },
  {
    id: "metadata-postal-code",
    pattern: /\b(?:postal code|postalcode|zipcode|zip code)\b/,
    semanticType: "POSTAL_CODE",
  },
  {
    id: "metadata-country",
    pattern: /\b(?:country name|countryname)\b/,
    semanticType: "COUNTRY",
  },
];

function normalize(value: string): string {
  return value
    .normalize("NFKC")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[’‘]/g, "'")
    .replace(/[_-]+/g, " ")
    .replace(/\s*\*+\s*$/g, "")
    .replace(/\s*\(?required\)?\s*$/i, "")
    .replace(/[?:]+$/g, "")
    .replace(/[^\p{L}\p{N}' ]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLocaleLowerCase("en-US");
}

function unwrapPrompt(value: string): string {
  let text = normalize(value);
  const prefixes = [
    /^(?:please )?(?:enter|provide|type|confirm|input) (?:your )?/,
    /^(?:what is|what's) (?:your )?/,
    /^(?:tell us|tell me) (?:your )?/,
    /^your /,
  ];
  for (const prefix of prefixes) {
    text = text.replace(prefix, "").trim();
  }
  return text;
}

function resultFor(rule: AliasRule): ClassificationResult {
  return {
    semanticType: rule.semanticType,
    confidence: rule.confidence ?? 0.93,
    sensitive: rule.sensitive ?? false,
    requiresReview: rule.requiresReview ?? false,
    matchedRule: rule.id,
  };
}

export function classifyQuestion(
  rawText: string,
  contextText = "",
): ClassificationResult {
  const direct = classifyBaseQuestion(rawText, contextText);
  if (direct.semanticType !== "UNKNOWN") return direct;

  const unwrapped = unwrapPrompt(rawText);
  if (unwrapped && unwrapped !== normalize(rawText)) {
    const unwrappedResult = classifyBaseQuestion(unwrapped, contextText);
    if (unwrappedResult.semanticType !== "UNKNOWN") {
      return {
        ...unwrappedResult,
        confidence: Math.max(unwrappedResult.confidence, 0.93),
        matchedRule: unwrappedResult.matchedRule
          ? `prompt-${unwrappedResult.matchedRule}`
          : "prompt-equivalence",
      };
    }
  }

  const text = normalize(rawText);
  const alias = aliasRules.find((candidate) => candidate.pattern.test(text));
  if (alias) return resultFor(alias);

  const metadata = normalize(contextText);
  const metadataRule = metadataRules.find((candidate) =>
    candidate.pattern.test(metadata),
  );
  if (metadataRule) return resultFor(metadataRule);

  return direct;
}

export type { ClassificationResult } from "./index";
