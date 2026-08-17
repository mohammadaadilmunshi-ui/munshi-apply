export type JobResponseIntent =
  | "WHY_COMPANY"
  | "WHY_ROLE"
  | "ROLE_UNDERSTANDING"
  | "RELEVANT_EXPERIENCE"
  | "CAREER_TRANSITION"
  | "MOTIVATION"
  | "BEHAVIORAL"
  | "OTHER_NARRATIVE";

export type JobResponsePlan = {
  intent: JobResponseIntent;
  modelLane: "CHEAP" | "STRONG";
  requiresJobContext: boolean;
  requiresCandidateEvidence: boolean;
  retrievalTerms: string[];
  defaultMaxWords: number;
};

const intentTerms: Record<JobResponseIntent, string[]> = {
  WHY_COMPANY: ["company", "mission", "culture", "values", "industry", "team"],
  WHY_ROLE: ["role", "position", "responsibilities", "skills", "experience"],
  ROLE_UNDERSTANDING: [
    "responsibilities",
    "duties",
    "requirements",
    "team",
    "role",
  ],
  RELEVANT_EXPERIENCE: [
    "experience",
    "responsibilities",
    "achievements",
    "skills",
    "results",
  ],
  CAREER_TRANSITION: [
    "career",
    "growth",
    "next",
    "opportunity",
    "goals",
    "experience",
  ],
  MOTIVATION: [
    "motivation",
    "interest",
    "role",
    "company",
    "experience",
    "goals",
  ],
  BEHAVIORAL: [
    "example",
    "situation",
    "action",
    "result",
    "challenge",
    "achievement",
  ],
  OTHER_NARRATIVE: ["experience", "role", "skills"],
};

export function classifyJobResponseIntent(
  question: string,
  semanticType: string,
): JobResponseIntent {
  const semantic = semanticType.toUpperCase();
  const text = question.toLowerCase().replace(/\s+/g, " ").trim();

  if (
    semantic === "WHY_COMPANY" ||
    /why .*?(work|join).*?(us|company|organization)/.test(text)
  ) {
    return "WHY_COMPANY";
  }
  if (semantic === "WHY_ROLE" || /why .*?(role|position)/.test(text)) {
    return "WHY_ROLE";
  }
  if (
    ["ROLE_RESPONSIBILITIES", "ROLE_UNDERSTANDING"].includes(semantic) ||
    /(?:understand|describe).*?(role|responsibilit)/.test(text)
  ) {
    return "ROLE_UNDERSTANDING";
  }
  if (
    semantic === "RELEVANT_EXPERIENCE" ||
    /(?:relevant|related|prior).*?experience|describe your experience/.test(
      text,
    )
  ) {
    return "RELEVANT_EXPERIENCE";
  }
  if (
    semantic === "CAREER_GOALS" ||
    /leave your current|career (?:goal|move|transition)|next opportunity/.test(
      text,
    )
  ) {
    return "CAREER_TRANSITION";
  }
  if (
    ["MOTIVATION", "RECRUITMENT_MOTIVATION"].includes(semantic) ||
    /what motivates|why recruitment|why sales|motivat/.test(text)
  ) {
    return "MOTIVATION";
  }
  if (
    semantic === "BEHAVIORAL_EXAMPLE" ||
    /tell .*? about a time|give .*? an example|describe a time/.test(text)
  ) {
    return "BEHAVIORAL";
  }

  return "OTHER_NARRATIVE";
}

export function planJobResponse(
  question: string,
  semanticType: string,
  requestedMaxWords?: number,
): JobResponsePlan {
  const intent = classifyJobResponseIntent(question, semanticType);
  const defaults: Record<JobResponseIntent, number> = {
    WHY_COMPANY: 140,
    WHY_ROLE: 160,
    ROLE_UNDERSTANDING: 160,
    RELEVANT_EXPERIENCE: 190,
    CAREER_TRANSITION: 130,
    MOTIVATION: 160,
    BEHAVIORAL: 240,
    OTHER_NARRATIVE: 180,
  };

  return {
    intent,
    modelLane: ["BEHAVIORAL", "CAREER_TRANSITION", "MOTIVATION"].includes(
      intent,
    )
      ? "STRONG"
      : "CHEAP",
    requiresJobContext: [
      "WHY_COMPANY",
      "WHY_ROLE",
      "ROLE_UNDERSTANDING",
      "MOTIVATION",
    ].includes(intent),
    requiresCandidateEvidence: [
      "WHY_ROLE",
      "RELEVANT_EXPERIENCE",
      "CAREER_TRANSITION",
      "MOTIVATION",
      "BEHAVIORAL",
    ].includes(intent),
    retrievalTerms: [...intentTerms[intent]],
    defaultMaxWords: requestedMaxWords ?? defaults[intent],
  };
}
