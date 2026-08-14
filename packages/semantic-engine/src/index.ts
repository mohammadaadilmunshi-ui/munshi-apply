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
  {
    id: "preferred-name",
    pattern: /^preferred (first )?name$/i,
    semanticType: "PREFERRED_NAME",
  },
  {
    id: "first-name",
    pattern: /^(first|given) name$/i,
    semanticType: "FIRST_NAME",
  },
  {
    id: "middle-name",
    pattern: /^middle (name|initial)$/i,
    semanticType: "MIDDLE_NAME",
  },
  {
    id: "last-name",
    pattern: /^(last name|family name|surname)$/i,
    semanticType: "LAST_NAME",
  },
  {
    id: "full-name",
    pattern: /^(full legal name|legal name|full name)$/i,
    semanticType: "PERSONAL",
    highRisk: true,
  },
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
  {
    id: "address-line-2",
    pattern:
      /^(address line 2|address 2|apartment|apt\.?|suite|unit)( number| #)?$/i,
    semanticType: "ADDRESS_LINE_2",
  },
  {
    id: "street-address",
    pattern: /^(street address|address line 1|address 1|home address)$/i,
    semanticType: "STREET_ADDRESS",
  },
  { id: "city", pattern: /^(city|town)$/i, semanticType: "CITY" },
  {
    id: "state-province",
    pattern: /^(state|province|state\/province|region)$/i,
    semanticType: "STATE_PROVINCE",
  },
  {
    id: "postal-code",
    pattern: /^(zip|zip code|postal code|postcode)$/i,
    semanticType: "POSTAL_CODE",
  },
  { id: "country", pattern: /^country$/i, semanticType: "COUNTRY" },
  {
    id: "school-name",
    pattern:
      /^(school|school name|university|university name|college|college name|institution|institution name)$/i,
    semanticType: "SCHOOL_NAME",
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
    id: "employer-name",
    pattern:
      /^(employer|employer name|company name|current employer|most recent employer)$/i,
    semanticType: "EMPLOYER_NAME",
  },
  {
    id: "job-title",
    pattern: /^(job title|position title|current title|most recent title)$/i,
    semanticType: "JOB_TITLE",
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
    id: "immigration-assistance",
    pattern: /\b(immigration|visa) (assistance|support)\b/i,
    semanticType: "IMMIGRATION_ASSISTANCE",
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
    id: "notice-period",
    pattern: /\b(notice period|how soon can you start)\b/i,
    semanticType: "NOTICE_PERIOD",
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
    id: "skills",
    pattern: /^(skills|key skills|relevant skills)$/i,
    semanticType: "SKILLS",
  },
  {
    id: "certifications",
    pattern: /\b(certification|certifications|certificate|certificates)\b/i,
    semanticType: "CERTIFICATIONS",
  },
  {
    id: "languages",
    pattern: /^(languages|languages spoken|language proficiency)$/i,
    semanticType: "LANGUAGES",
  },
  {
    id: "referral",
    pattern: /\b(how did you hear|referral source|referred by)\b/i,
    semanticType: "REFERRAL",
  },
  {
    id: "previous-employee",
    pattern:
      /\b(previously|ever).{0,30}\b(worked|employed).{0,30}\b(company|organization|us|here)\b/i,
    semanticType: "PREVIOUS_EMPLOYEE",
    highRisk: true,
  },
  {
    id: "previous-application",
    pattern:
      /\b(previously|ever).{0,30}\b(applied|application).{0,30}\b(company|organization|us|here|position|role)\b/i,
    semanticType: "PREVIOUS_APPLICATION",
    highRisk: true,
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
    sensitive: rule.sensitive ?? rule.highRisk ?? false,
    requiresReview: rule.highRisk ?? false,
    matchedRule: rule.id,
  };
}
