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
    id: "pronouns",
    pattern: /^(preferred )?pronouns?$/i,
    semanticType: "PRONOUNS",
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
    id: "highest-education-level",
    pattern:
      /^(highest )?(level of education|education level|degree level)( obtained| completed| in progress| obtained or in progress)?$/i,
    semanticType: "DEGREE",
  },
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
    pattern:
      /(?:\b(?:graduation|completion)\s+(?:date|year)\b|\banticipated\s+graduation\b|\b(?:when|what)\b.{0,60}\bgraduat(?:e|ing|ed)\b|\bgraduat(?:e|ing|ed)\b.{0,45}\b(?:university|college|school)\b)/i,
    semanticType: "GRADUATION_DATE",
  },
  {
    id: "employer-name",
    pattern:
      /^(employer|employer name|company|company name|current employer|most recent employer)$/i,
    semanticType: "EMPLOYER_NAME",
  },
  {
    id: "job-title",
    pattern:
      /^(title|job title|position title|current title|most recent title)$/i,
    semanticType: "JOB_TITLE",
  },
  {
    id: "company-industry",
    pattern: /^(company|employer|organization) industry$|^industry$/i,
    semanticType: "COMPANY_INDUSTRY",
  },
  {
    id: "position-function",
    pattern:
      /^(position|job|role) function$|^functional area$|^function(\/area)?$/i,
    semanticType: "POSITION_FUNCTION",
  },
  {
    id: "employment-type",
    pattern:
      /^(employment|job|position) type$|^(full[- ]time|part[- ]time) status$/i,
    semanticType: "EMPLOYMENT_TYPE",
  },
  {
    id: "currently-employed",
    pattern:
      /\b(currently employed|current position|currently work(?:ing)? (?:here|there|for)|still employed)\b/i,
    semanticType: "CURRENTLY_EMPLOYED",
  },
  {
    id: "certification-issuer",
    pattern:
      /^(issuing organization|issuing authority|certificate issuer|certification issuer)$/i,
    semanticType: "CERTIFICATION_ISSUER",
  },
  {
    id: "certification-issue-date",
    pattern: /^(issue|issued|certification issue) date$/i,
    semanticType: "CERTIFICATION_ISSUE_DATE",
  },
  {
    id: "certification-expiration-date",
    pattern: /^(expiration|expiry|expires|certification expiration) date$/i,
    semanticType: "CERTIFICATION_EXPIRATION_DATE",
  },
  {
    id: "credential-id",
    pattern: /^(credential|certificate|certification) id$/i,
    semanticType: "CREDENTIAL_ID",
  },
  {
    id: "credential-url",
    pattern: /^(credential|certificate|certification) (url|link)$/i,
    semanticType: "CREDENTIAL_URL",
  },
  {
    id: "language-proficiency",
    pattern: /^(language )?(proficiency|fluency|level)$/i,
    semanticType: "LANGUAGE_PROFICIENCY",
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
      /(?:\b(?:now or in the future|in the future)\b.{0,90}\b(?:sponsor|sponsorship)\b|\b(?:sponsor|sponsorship)\b.{0,90}\b(?:now or in the future|in the future)\b)/i,
    semanticType: "SPONSORSHIP_FUTURE",
    sensitive: true,
    highRisk: true,
  },
  {
    id: "current-sponsorship",
    pattern:
      /\b(currently|at this time|right now).{0,40}\b(require|need).{0,30}\b(sponsor|sponsorship)\b|\b(require|need).{0,30}\b(sponsor|sponsorship).{0,40}\b(currently|at this time|right now)\b/i,
    semanticType: "SPONSORSHIP_CURRENT",
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
    semanticType: "UNKNOWN",
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
    pattern:
      /\b(available date|earliest (?:possible )?start date|available to start|when (?:would|can|could|are) you (?:be )?available to start|desired start date)\b/i,
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
    id: "remote-preference",
    pattern: /\b(remote work|work remotely|remote preference)\b/i,
    semanticType: "REMOTE",
  },
  {
    id: "hybrid-preference",
    pattern: /\b(hybrid work|hybrid preference)\b/i,
    semanticType: "HYBRID",
  },
  {
    id: "onsite-preference",
    pattern: /\b(on[- ]?site work|work on[- ]?site|onsite preference)\b/i,
    semanticType: "ONSITE",
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
    pattern: /^(languages|languages spoken|language)$/i,
    semanticType: "LANGUAGES",
  },
  {
    id: "security-clearance",
    pattern: /\b(security clearance|clearance level|active clearance)\b/i,
    semanticType: "SECURITY_CLEARANCE",
    sensitive: true,
    highRisk: true,
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
    id: "protected-veteran",
    pattern: /\bprotected veteran(?: status)?\b/i,
    semanticType: "PROTECTED_VETERAN_STATUS",
    sensitive: true,
    highRisk: true,
  },
  {
    id: "veteran",
    pattern: /\b(veteran status|military status)\b/i,
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
    id: "eeo-self-id",
    pattern:
      /\b(equal employment opportunity|voluntary self[- ]identification|eeo self[- ]identification)\b/i,
    semanticType: "EEO_SELF_ID",
    sensitive: true,
    highRisk: true,
  },
  {
    id: "conflict-of-interest",
    pattern: /\b(conflict of interest|potential conflict)\b/i,
    semanticType: "CONFLICT_OF_INTEREST",
    sensitive: true,
    highRisk: true,
  },
  {
    id: "non-compete",
    pattern: /\b(non[- ]compete|noncompete|restrictive covenant)\b/i,
    semanticType: "NON_COMPETE",
    sensitive: true,
    highRisk: true,
  },
  {
    id: "background-check",
    pattern: /\b(background check|background screening)\b/i,
    semanticType: "BACKGROUND_CHECK",
    sensitive: true,
    highRisk: true,
  },
  {
    id: "drug-screening",
    pattern: /\b(drug (test|screen|screening)|substance screening)\b/i,
    semanticType: "DRUG_SCREENING",
    sensitive: true,
    highRisk: true,
  },
  {
    id: "why-company",
    pattern: /\bwhy (this|our) (company|organization)\b/i,
    semanticType: "WHY_COMPANY",
  },
  {
    id: "role-understanding",
    pattern:
      /(?:\bhow would you describe\b.{0,80}\b(?:role|position|recruitment|sales)\b.{0,80}\b(?:responsibilit|duties)\w*\b|\bwhat are the key responsibilit\w*\b.{0,80}\b(?:role|position|recruitment|sales)\b)/i,
    semanticType: "WHY_ROLE",
  },
  {
    id: "career-motivation",
    pattern:
      /\bwhat motivates you\b.{0,100}\b(?:career|recruitment|recruiting|sales|talent acquisition)\b/i,
    semanticType: "CAREER_GOALS",
  },
  {
    id: "leave-current-employer",
    pattern:
      /\b(?:why are you|why do you|what makes you)\b.{0,70}\b(?:leave|leaving|looking to leave|move on from|change from)\b.{0,60}\b(?:current )?(?:employer|company|role|job|position)\b/i,
    semanticType: "CAREER_GOALS",
  },
  {
    id: "first-recruitment-role",
    pattern:
      /(?:\bfirst experience\b.{0,100}\b(?:professional )?(?:recruitment|recruiting|recruiter|talent acquisition)\b|\bfirst\b.{0,80}\bprofessional recruitment role\b)/i,
    semanticType: "RELEVANT_EXPERIENCE",
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

const contextualRules: readonly Rule[] = [
  {
    id: "education-start-date-context",
    pattern:
      /\b(education|academic|school|college|university)\b.{0,160}\b(start|from)\s*(date|month|year)?\b/i,
    semanticType: "EDUCATION_START_DATE",
  },
  {
    id: "education-location-context",
    pattern:
      /\b(education|academic|school|college|university)\b.{0,160}\b(location|city|country)\b/i,
    semanticType: "EDUCATION_LOCATION",
  },
  {
    id: "employment-start-date-context",
    pattern:
      /\b(work history|employment|experience|employer|company)\b.{0,160}\b(start|from)\s*(date|month|year)?\b/i,
    semanticType: "EMPLOYMENT_START_DATE",
  },
  {
    id: "employment-end-date-context",
    pattern:
      /\b(work history|employment|experience|employer|company)\b.{0,160}\b(end|to)\s*(date|month|year)?\b/i,
    semanticType: "EMPLOYMENT_END_DATE",
  },
  {
    id: "employment-location-context",
    pattern:
      /\b(work history|employment|experience|employer|company)\b.{0,160}\b(location|city|country)\b/i,
    semanticType: "EMPLOYMENT_LOCATION",
  },
  {
    id: "certification-issue-context",
    pattern:
      /\b(certification|certificate|credential|license)\b.{0,160}\b(issue|issued) date\b/i,
    semanticType: "CERTIFICATION_ISSUE_DATE",
  },
  {
    id: "certification-expiration-context",
    pattern:
      /\b(certification|certificate|credential|license)\b.{0,160}\b(expiration|expiry|expires) date\b/i,
    semanticType: "CERTIFICATION_EXPIRATION_DATE",
  },
  {
    id: "language-proficiency-context",
    pattern: /\blanguage\b.{0,120}\b(proficiency|fluency|level)\b/i,
    semanticType: "LANGUAGE_PROFICIENCY",
  },
];

function normalize(text: string): string {
  return text
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\s*\*+\s*$/, "")
    .replace(/\s*\(?required\)?\s*$/i, "")
    .replace(/\s*:\s*$/, "")
    .trim();
}

function resultFor(rule: Rule): ClassificationResult {
  return {
    semanticType: rule.semanticType,
    confidence: rule.highRisk ? 0.9 : 0.94,
    sensitive: rule.sensitive ?? rule.highRisk ?? false,
    requiresReview: rule.highRisk ?? false,
    matchedRule: rule.id,
  };
}

export function classifyQuestion(
  rawText: string,
  contextText = "",
): ClassificationResult {
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

  const directRule = rules.find((candidate) => candidate.pattern.test(text));
  if (directRule) return resultFor(directRule);

  const context = normalize(`${contextText} ${text}`);
  const contextualRule = contextualRules.find((candidate) =>
    candidate.pattern.test(context),
  );
  if (contextualRule) return resultFor(contextualRule);

  return {
    semanticType: "UNKNOWN",
    confidence: 0.35,
    sensitive: false,
    requiresReview: true,
    matchedRule: null,
  };
}
