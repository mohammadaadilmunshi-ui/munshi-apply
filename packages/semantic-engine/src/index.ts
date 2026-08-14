import type { SemanticType } from "@munshi-apply/contracts";

export interface ClassificationResult {
  semanticType: SemanticType;
  confidence: number;
  sensitive: boolean;
  requiresReview: boolean;
  matchedRule: string | null;
}

interface Rule {
  id: string;
  pattern: RegExp;
  semanticType: SemanticType;
  sensitive?: boolean;
  highRisk?: boolean;
}

const rules: readonly Rule[] = [
  { id: "email", pattern: /\b(e-?mail)\b/i, semanticType: "EMAIL" },
  {
    id: "phone",
    pattern: /\b(phone|mobile|telephone)\b/i,
    semanticType: "PHONE",
  },
  { id: "linkedin", pattern: /linkedin/i, semanticType: "LINKEDIN" },
  {
    id: "portfolio",
    pattern: /\b(portfolio|personal website)\b/i,
    semanticType: "PORTFOLIO",
  },
  { id: "gpa", pattern: /\bg\.?p\.?a\.?\b/i, semanticType: "GPA" },
  {
    id: "degree",
    pattern: /\b(degree|education level)\b/i,
    semanticType: "DEGREE",
  },
  {
    id: "field-of-study",
    pattern: /\b(field|major|area) of study\b/i,
    semanticType: "FIELD_OF_STUDY",
  },
  {
    id: "graduation",
    pattern: /\b(graduation|graduate|completion) (date|year)\b/i,
    semanticType: "GRADUATION_DATE",
  },
  {
    id: "authorization",
    pattern:
      /\b(legally authorized|authorization to work|authorized to work)\b/i,
    semanticType: "WORK_AUTHORIZATION_CURRENT",
    sensitive: true,
    highRisk: true,
  },
  {
    id: "future-sponsorship",
    pattern:
      /\b(now or in the future|in the future).{0,50}\b(sponsor|sponsorship)\b/i,
    semanticType: "SPONSORSHIP_FUTURE",
    sensitive: true,
    highRisk: true,
  },
  {
    id: "sponsorship",
    pattern: /\b(sponsor|sponsorship|visa assistance)\b/i,
    semanticType: "SPONSORSHIP_CURRENT",
    sensitive: true,
    highRisk: true,
  },
  {
    id: "salary",
    pattern: /\b(salary|compensation|pay expectation|desired pay)\b/i,
    semanticType: "SALARY_EXPECTATION",
    highRisk: true,
  },
  {
    id: "start-date",
    pattern: /\b(start|available) date\b/i,
    semanticType: "START_DATE",
  },
  {
    id: "relocation",
    pattern: /\b(relocat(e|ion|ing))\b/i,
    semanticType: "RELOCATION",
  },
  {
    id: "travel",
    pattern: /\b(willing(ness)? to travel|travel percentage)\b/i,
    semanticType: "TRAVEL",
  },
  {
    id: "veteran",
    pattern: /\b(protected veteran|veteran status|military status)\b/i,
    semanticType: "VETERAN_STATUS",
    sensitive: true,
    highRisk: true,
  },
  {
    id: "disability",
    pattern: /\b(disability|disabled)\b/i,
    semanticType: "DISABILITY_STATUS",
    sensitive: true,
    highRisk: true,
  },
  {
    id: "race-ethnicity",
    pattern: /\b(race|ethnicity|ethnic origin)\b/i,
    semanticType: "RACE_ETHNICITY",
    sensitive: true,
    highRisk: true,
  },
  {
    id: "gender",
    pattern: /\b(gender|sex)\b/i,
    semanticType: "GENDER",
    sensitive: true,
    highRisk: true,
  },
  {
    id: "why-company",
    pattern: /\bwhy (this|our) (company|organization)\b/i,
    semanticType: "WHY_COMPANY",
  },
  {
    id: "why-role",
    pattern: /\bwhy (this|the) (role|position|job)\b/i,
    semanticType: "WHY_ROLE",
  },
  {
    id: "experience",
    pattern: /\b(describe|summarize).{0,30}(relevant|your).{0,20}experience\b/i,
    semanticType: "RELEVANT_EXPERIENCE",
  },
];

function normalize(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

export function classifyQuestion(rawText: string): ClassificationResult {
  const text = normalize(rawText);
  if (!text) {
    return {
      semanticType: "UNKNOWN",
      confidence: 0,
      sensitive: false,
      requiresReview: true,
      matchedRule: null,
    };
  }

  const rule = rules.find((candidate) => candidate.pattern.test(text));
  if (!rule) {
    return {
      semanticType: "UNKNOWN",
      confidence: 0.35,
      sensitive: false,
      requiresReview: true,
      matchedRule: null,
    };
  }

  return {
    semanticType: rule.semanticType,
    confidence: rule.highRisk ? 0.9 : 0.94,
    sensitive: rule.sensitive ?? false,
    requiresReview: rule.highRisk ?? false,
    matchedRule: rule.id,
  };
}
