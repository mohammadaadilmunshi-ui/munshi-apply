export const jobSignalDimensions = [
  "ROLE_AMBIGUITY",
  "RESPONSIBILITY_BREADTH",
  "QUALIFICATION_INFLATION",
  "WORKLOAD_PRESSURE",
  "SCHEDULE_INTENSITY",
  "TRAVEL_BURDEN",
  "COMPENSATION_CLARITY",
  "SENIORITY_ALIGNMENT",
  "ROLE_STABILITY",
  "LOCATION_CONSTRAINTS",
  "WORK_AUTHORIZATION_RISK",
  "APPLICATION_FRICTION",
] as const;

export type JobSignalDimension = (typeof jobSignalDimensions)[number];
export type JobSignalSeverity = "LOW" | "MODERATE" | "HIGH";
export type OverallJobSignal =
  "LOW" | "MODERATE" | "HIGH" | "INSUFFICIENT_DATA";

export type JobSignalInput = {
  company?: string | null;
  role?: string | null;
  location?: string | null;
  workArrangement?: string | null;
  employmentType?: string | null;
  compensation?: string | null;
  description?: string | null;
  requirements?: string | null;
  preferredQualifications?: string | null;
  applicationFriction?: {
    accountRequired?: boolean;
    manualRequiredControls?: number;
    validationErrors?: number;
  } | null;
};

export type JobSignalEvidence = {
  signalId: string;
  dimension: JobSignalDimension;
  severity: JobSignalSeverity;
  evidence: string;
  explanation: string;
};

export type JobSignalDimensionResult = {
  dimension: JobSignalDimension;
  score: number | null;
  confidence: number;
  evidenceIds: readonly string[];
};

export type JobSignalReport = {
  overallSignal: OverallJobSignal;
  overallScore: number | null;
  dimensions: Record<JobSignalDimension, JobSignalDimensionResult>;
  signals: readonly JobSignalEvidence[];
  disclaimer: string;
};

type DimensionAccumulator = {
  score: number | null;
  confidence: number;
  evidenceIds: string[];
};

const functionalPatterns = [
  /\brecruit(?:ing|ment|er)?\b/i,
  /\b(?:data|people|workforce|business) analytics?\b/i,
  /\bhris\b|\bhuman resources information system\b/i,
  /\bpayroll\b/i,
  /\bemployee relations?\b/i,
  /\bbenefits?\b/i,
  /\bcompensation\b/i,
  /\bcompliance\b/i,
  /\bproject management\b/i,
  /\boperations?\b/i,
  /\bsales\b|\bbusiness development\b/i,
  /\bmarketing\b/i,
  /\bfinance\b|\baccounting\b/i,
  /\blegal\b/i,
  /\bcustomer success\b|\bcustomer support\b/i,
  /\bsoftware\b|\bengineering\b|\bdevelopment\b/i,
] as const;

function compact(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function bounded(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function excerpt(value: string): string {
  const normalized = compact(value);
  return normalized.length <= 220
    ? normalized
    : `${normalized.slice(0, 217).trimEnd()}...`;
}

function severity(score: number): JobSignalSeverity {
  if (score >= 65) return "HIGH";
  if (score >= 33) return "MODERATE";
  return "LOW";
}

function allText(input: JobSignalInput): string {
  return [
    input.role,
    input.location,
    input.workArrangement,
    input.employmentType,
    input.compensation,
    input.description,
    input.requirements,
    input.preferredQualifications,
  ]
    .map(compact)
    .filter(Boolean)
    .join("\n");
}

function accumulator(): DimensionAccumulator {
  return { score: null, confidence: 0, evidenceIds: [] };
}

function emptyDimensions(): Record<JobSignalDimension, DimensionAccumulator> {
  return {
    ROLE_AMBIGUITY: accumulator(),
    RESPONSIBILITY_BREADTH: accumulator(),
    QUALIFICATION_INFLATION: accumulator(),
    WORKLOAD_PRESSURE: accumulator(),
    SCHEDULE_INTENSITY: accumulator(),
    TRAVEL_BURDEN: accumulator(),
    COMPENSATION_CLARITY: accumulator(),
    SENIORITY_ALIGNMENT: accumulator(),
    ROLE_STABILITY: accumulator(),
    LOCATION_CONSTRAINTS: accumulator(),
    WORK_AUTHORIZATION_RISK: accumulator(),
    APPLICATION_FRICTION: accumulator(),
  };
}

function setDimension(
  dimensions: Record<JobSignalDimension, DimensionAccumulator>,
  dimension: JobSignalDimension,
  score: number,
  confidence: number,
): void {
  dimensions[dimension].score = bounded(score);
  dimensions[dimension].confidence = Math.max(
    dimensions[dimension].confidence,
    Math.max(0, Math.min(1, confidence)),
  );
}

function addSignal(
  signals: JobSignalEvidence[],
  dimensions: Record<JobSignalDimension, DimensionAccumulator>,
  dimension: JobSignalDimension,
  score: number,
  evidence: string,
  explanation: string,
  confidence = 0.9,
): void {
  const signalId = `job-signal-${dimension.toLocaleLowerCase("en-US")}-${signals.length + 1}`;
  signals.push({
    signalId,
    dimension,
    severity: severity(score),
    evidence: excerpt(evidence),
    explanation,
  });
  dimensions[dimension].evidenceIds.push(signalId);
  const current = dimensions[dimension].score;
  setDimension(
    dimensions,
    dimension,
    current === null ? score : Math.max(current, score),
    confidence,
  );
}

function numericYears(text: string): number[] {
  return Array.from(
    text.matchAll(/\b(\d+(?:\.\d+)?)\+?\s+years?\b/gi),
    (match) => Number(match[1]),
  ).filter(Number.isFinite);
}

function analyzeRoleAmbiguity(
  text: string,
  signals: JobSignalEvidence[],
  dimensions: Record<JobSignalDimension, DimensionAccumulator>,
): void {
  const patterns: readonly [RegExp, number, string][] = [
    [
      /\bother duties as assigned\b/i,
      38,
      "The role reserves responsibility outside the listed duties.",
    ],
    [
      /\bwear many hats\b/i,
      72,
      "The posting explicitly describes a broadly shifting role boundary.",
    ],
    [
      /\b(?:evolving|changing) responsibilities\b/i,
      62,
      "The posting says responsibilities may materially change.",
    ],
    [
      /\bwhatever it takes\b/i,
      78,
      "The posting uses unusually open-ended responsibility language.",
    ],
  ];
  for (const [pattern, score, explanation] of patterns) {
    const match = text.match(pattern);
    if (match) {
      addSignal(
        signals,
        dimensions,
        "ROLE_AMBIGUITY",
        score,
        match[0],
        explanation,
      );
    }
  }
}

function analyzeResponsibilityBreadth(
  text: string,
  signals: JobSignalEvidence[],
  dimensions: Record<JobSignalDimension, DimensionAccumulator>,
): void {
  const domains = functionalPatterns.filter((pattern) =>
    pattern.test(text),
  ).length;
  if (domains < 4) return;
  const score = Math.min(88, 35 + (domains - 3) * 9);
  addSignal(
    signals,
    dimensions,
    "RESPONSIBILITY_BREADTH",
    score,
    `${domains} distinct functional domains detected in the supplied job text`,
    "The posting spans several distinct functional areas. Breadth is reported as scope, not as a claim about employer quality.",
    0.78,
  );
}

function analyzeQualificationInflation(
  input: JobSignalInput,
  text: string,
  signals: JobSignalEvidence[],
  dimensions: Record<JobSignalDimension, DimensionAccumulator>,
): void {
  const role = compact(input.role).toLocaleLowerCase("en-US");
  const juniorRole =
    /\b(intern|entry|assistant|coordinator|associate|junior)\b/.test(role);
  if (!juniorRole) return;
  const years = numericYears(text);
  const maximum = years.length ? Math.max(...years) : 0;
  if (maximum < 3) return;
  const score = maximum >= 5 ? 88 : 68;
  addSignal(
    signals,
    dimensions,
    "QUALIFICATION_INFLATION",
    score,
    `${compact(input.role)} paired with an explicit ${maximum}-year experience threshold`,
    "A junior-position title is paired with a comparatively high explicit experience threshold.",
    0.86,
  );
}

function analyzeWorkloadPressure(
  text: string,
  signals: JobSignalEvidence[],
  dimensions: Record<JobSignalDimension, DimensionAccumulator>,
): void {
  const patterns: readonly [RegExp, number, string][] = [
    [
      /\bhigh[- ]volume\b/i,
      58,
      "The posting explicitly describes the work as high-volume.",
    ],
    [
      /\b(?:tight|aggressive) deadlines?\b/i,
      64,
      "The posting explicitly calls out tight or aggressive deadlines.",
    ],
    [
      /\bmultiple competing priorities\b/i,
      52,
      "The posting explicitly expects management of competing priorities.",
    ],
    [
      /\bwork (?:well )?under pressure\b/i,
      66,
      "The posting explicitly expects work under pressure.",
    ],
  ];
  for (const [pattern, score, explanation] of patterns) {
    const match = text.match(pattern);
    if (match) {
      addSignal(
        signals,
        dimensions,
        "WORKLOAD_PRESSURE",
        score,
        match[0],
        explanation,
      );
    }
  }
}

function analyzeScheduleIntensity(
  text: string,
  signals: JobSignalEvidence[],
  dimensions: Record<JobSignalDimension, DimensionAccumulator>,
): void {
  const patterns: readonly [RegExp, number, string][] = [
    [
      /\b(?:evenings?|nights?) and weekends?\b/i,
      72,
      "The posting explicitly requires evening/night and weekend availability.",
    ],
    [
      /\bweekend(?:s| work)?(?: (?:is|are))? (?:required|as needed|as necessary)\b/i,
      62,
      "The posting explicitly requires or may require weekend work.",
    ],
    [/\bon[- ]call\b/i, 74, "The posting includes an on-call expectation."],
    [
      /\bmandatory overtime\b/i,
      88,
      "The posting explicitly states mandatory overtime.",
    ],
    [
      /\brotating shifts?\b/i,
      68,
      "The posting explicitly requires rotating shifts.",
    ],
  ];
  for (const [pattern, score, explanation] of patterns) {
    const match = text.match(pattern);
    if (match) {
      addSignal(
        signals,
        dimensions,
        "SCHEDULE_INTENSITY",
        score,
        match[0],
        explanation,
      );
    }
  }
}

function analyzeTravel(
  text: string,
  signals: JobSignalEvidence[],
  dimensions: Record<JobSignalDimension, DimensionAccumulator>,
): void {
  const percentage = text.match(/\b(?:up to )?(\d{1,3})%\s+travel\b/i);
  if (percentage) {
    const amount = Math.min(100, Number(percentage[1]));
    const score =
      amount <= 10 ? 20 : amount <= 25 ? 45 : amount <= 50 ? 70 : 90;
    addSignal(
      signals,
      dimensions,
      "TRAVEL_BURDEN",
      score,
      percentage[0],
      `The posting states a travel expectation of ${amount}%.`,
      0.98,
    );
    return;
  }
  const frequent = text.match(/\bfrequent travel\b/i);
  if (frequent) {
    addSignal(
      signals,
      dimensions,
      "TRAVEL_BURDEN",
      65,
      frequent[0],
      "The posting explicitly describes travel as frequent but gives no percentage.",
      0.8,
    );
  }
}

function analyzeCompensation(
  input: JobSignalInput,
  text: string,
  signals: JobSignalEvidence[],
  dimensions: Record<JobSignalDimension, DimensionAccumulator>,
): void {
  const compensation = compact(input.compensation);
  const source = compensation || text;
  const range = source.match(
    /(?:\$|USD\s*)\s*\d[\d,.]*(?:\s*(?:-|–|to)\s*(?:\$|USD\s*)?\s*\d[\d,.]*)?/i,
  );
  if (range) {
    setDimension(dimensions, "COMPENSATION_CLARITY", 92, 0.97);
    addSignal(
      signals,
      dimensions,
      "COMPENSATION_CLARITY",
      92,
      range[0],
      "The supplied job context includes explicit numeric compensation information.",
      0.97,
    );
    return;
  }
  const vague = source.match(/\bcompetitive (?:salary|pay|compensation)\b/i);
  if (vague) {
    setDimension(dimensions, "COMPENSATION_CLARITY", 28, 0.88);
    addSignal(
      signals,
      dimensions,
      "COMPENSATION_CLARITY",
      28,
      vague[0],
      "Compensation is described qualitatively without a numeric amount or range.",
      0.88,
    );
  }
}

function analyzeSeniorityAlignment(
  input: JobSignalInput,
  text: string,
  signals: JobSignalEvidence[],
  dimensions: Record<JobSignalDimension, DimensionAccumulator>,
): void {
  const role = compact(input.role).toLocaleLowerCase("en-US");
  if (!role) return;
  const years = numericYears(text);
  if (!years.length) return;
  const maximum = Math.max(...years);
  const junior =
    /\b(intern|entry|assistant|coordinator|associate|junior)\b/.test(role);
  const senior =
    /\b(senior|lead|principal|director|head|vice president|vp)\b/.test(role);
  if (junior && maximum >= 4) {
    setDimension(dimensions, "SENIORITY_ALIGNMENT", 30, 0.82);
    addSignal(
      signals,
      dimensions,
      "SENIORITY_ALIGNMENT",
      30,
      `${compact(input.role)} with a ${maximum}-year experience threshold`,
      "The title signals a junior level while the explicit experience threshold signals greater seniority.",
      0.82,
    );
  } else if (senior && maximum >= 5) {
    setDimension(dimensions, "SENIORITY_ALIGNMENT", 85, 0.76);
  }
}

function analyzeRoleStability(
  input: JobSignalInput,
  text: string,
  signals: JobSignalEvidence[],
  dimensions: Record<JobSignalDimension, DimensionAccumulator>,
): void {
  const source = `${compact(input.employmentType)} ${text}`;
  const temporary = source.match(
    /\b(?:temporary|temp|fixed[- ]term|contract role|contract position|seasonal)\b/i,
  );
  if (temporary) {
    setDimension(dimensions, "ROLE_STABILITY", 28, 0.9);
    addSignal(
      signals,
      dimensions,
      "ROLE_STABILITY",
      28,
      temporary[0],
      "The supplied job context explicitly describes a temporary, contract, fixed-term, or seasonal arrangement.",
      0.9,
    );
    return;
  }
  const permanent = source.match(/\b(?:permanent|regular full[- ]time)\b/i);
  if (permanent) {
    setDimension(dimensions, "ROLE_STABILITY", 88, 0.88);
  }
}

function analyzeLocationConstraints(
  input: JobSignalInput,
  text: string,
  signals: JobSignalEvidence[],
  dimensions: Record<JobSignalDimension, DimensionAccumulator>,
): void {
  const source = `${compact(input.workArrangement)} ${compact(input.location)} ${text}`;
  const relocation = source.match(/\b(?:must|required to) relocate\b/i);
  if (relocation) {
    addSignal(
      signals,
      dimensions,
      "LOCATION_CONSTRAINTS",
      82,
      relocation[0],
      "The posting explicitly requires relocation.",
      0.95,
    );
    return;
  }
  const onsite = source.match(
    /\b(?:onsite|on-site|in office)\b.{0,45}\b(?:required|mandatory|must)\b/i,
  );
  if (onsite) {
    addSignal(
      signals,
      dimensions,
      "LOCATION_CONSTRAINTS",
      62,
      onsite[0],
      "The posting explicitly requires onsite or in-office attendance.",
      0.92,
    );
  }
}

function analyzeWorkAuthorization(
  text: string,
  signals: JobSignalEvidence[],
  dimensions: Record<JobSignalDimension, DimensionAccumulator>,
): void {
  const noSponsorship = text.match(
    /\b(?:no|not|cannot|can't|unable to|will not|won't)\b.{0,45}\b(?:visa )?sponsor(?:ship|ing)?\b/i,
  );
  if (noSponsorship) {
    addSignal(
      signals,
      dimensions,
      "WORK_AUTHORIZATION_RISK",
      92,
      noSponsorship[0],
      "The posting explicitly states that sponsorship is unavailable. Eligibility is evaluated separately by employer pre-flight rules.",
      0.97,
    );
  }
  const citizenship = text.match(
    /\b(?:must be|requires?|required)\b.{0,30}\bU\.?S\.? citizen(?:ship)?\b/i,
  );
  if (citizenship) {
    addSignal(
      signals,
      dimensions,
      "WORK_AUTHORIZATION_RISK",
      96,
      citizenship[0],
      "The posting explicitly includes a U.S.-citizenship requirement. Eligibility is evaluated separately by employer pre-flight rules.",
      0.98,
    );
  }
}

function analyzeApplicationFriction(
  input: JobSignalInput,
  signals: JobSignalEvidence[],
  dimensions: Record<JobSignalDimension, DimensionAccumulator>,
): void {
  const friction = input.applicationFriction;
  if (!friction) return;
  const manual = Math.max(0, friction.manualRequiredControls ?? 0);
  const validation = Math.max(0, friction.validationErrors ?? 0);
  const account = friction.accountRequired === true;
  if (!account && manual === 0 && validation === 0) {
    setDimension(dimensions, "APPLICATION_FRICTION", 0, 0.95);
    return;
  }
  const score = Math.min(
    100,
    (account ? 18 : 0) +
      Math.min(50, manual * 10) +
      Math.min(40, validation * 8),
  );
  addSignal(
    signals,
    dimensions,
    "APPLICATION_FRICTION",
    score,
    `account_required=${account}; manual_required_controls=${manual}; validation_errors=${validation}`,
    "Application friction is calculated from observed workflow requirements, not inferred from employer quality.",
    0.96,
  );
}

function concernScore(result: JobSignalDimensionResult): number | null {
  if (result.score === null) return null;
  if (
    result.dimension === "COMPENSATION_CLARITY" ||
    result.dimension === "SENIORITY_ALIGNMENT" ||
    result.dimension === "ROLE_STABILITY"
  ) {
    return 100 - result.score;
  }
  return result.score;
}

function finalizeDimension(
  dimension: JobSignalDimension,
  dimensions: Record<JobSignalDimension, DimensionAccumulator>,
): JobSignalDimensionResult {
  return {
    dimension,
    score: dimensions[dimension].score,
    confidence: dimensions[dimension].confidence,
    evidenceIds: [...dimensions[dimension].evidenceIds],
  };
}

function finalizeDimensions(
  dimensions: Record<JobSignalDimension, DimensionAccumulator>,
): Record<JobSignalDimension, JobSignalDimensionResult> {
  return {
    ROLE_AMBIGUITY: finalizeDimension("ROLE_AMBIGUITY", dimensions),
    RESPONSIBILITY_BREADTH: finalizeDimension(
      "RESPONSIBILITY_BREADTH",
      dimensions,
    ),
    QUALIFICATION_INFLATION: finalizeDimension(
      "QUALIFICATION_INFLATION",
      dimensions,
    ),
    WORKLOAD_PRESSURE: finalizeDimension("WORKLOAD_PRESSURE", dimensions),
    SCHEDULE_INTENSITY: finalizeDimension("SCHEDULE_INTENSITY", dimensions),
    TRAVEL_BURDEN: finalizeDimension("TRAVEL_BURDEN", dimensions),
    COMPENSATION_CLARITY: finalizeDimension("COMPENSATION_CLARITY", dimensions),
    SENIORITY_ALIGNMENT: finalizeDimension("SENIORITY_ALIGNMENT", dimensions),
    ROLE_STABILITY: finalizeDimension("ROLE_STABILITY", dimensions),
    LOCATION_CONSTRAINTS: finalizeDimension("LOCATION_CONSTRAINTS", dimensions),
    WORK_AUTHORIZATION_RISK: finalizeDimension(
      "WORK_AUTHORIZATION_RISK",
      dimensions,
    ),
    APPLICATION_FRICTION: finalizeDimension("APPLICATION_FRICTION", dimensions),
  };
}

export function analyzeJobSignals(input: JobSignalInput): JobSignalReport {
  const text = allText(input);
  const dimensions = emptyDimensions();
  const signals: JobSignalEvidence[] = [];

  if (text) {
    analyzeRoleAmbiguity(text, signals, dimensions);
    analyzeResponsibilityBreadth(text, signals, dimensions);
    analyzeQualificationInflation(input, text, signals, dimensions);
    analyzeWorkloadPressure(text, signals, dimensions);
    analyzeScheduleIntensity(text, signals, dimensions);
    analyzeTravel(text, signals, dimensions);
    analyzeCompensation(input, text, signals, dimensions);
    analyzeSeniorityAlignment(input, text, signals, dimensions);
    analyzeRoleStability(input, text, signals, dimensions);
    analyzeLocationConstraints(input, text, signals, dimensions);
    analyzeWorkAuthorization(text, signals, dimensions);
  }
  analyzeApplicationFriction(input, signals, dimensions);

  const finalized = finalizeDimensions(dimensions);
  const concerns = jobSignalDimensions
    .map((dimension) => concernScore(finalized[dimension]))
    .filter((score): score is number => score !== null);
  const overallScore = concerns.length
    ? bounded(concerns.reduce((sum, score) => sum + score, 0) / concerns.length)
    : null;
  const overallSignal: OverallJobSignal =
    overallScore === null
      ? "INSUFFICIENT_DATA"
      : overallScore >= 65
        ? "HIGH"
        : overallScore >= 33
          ? "MODERATE"
          : "LOW";

  return {
    overallSignal,
    overallScore,
    dimensions: finalized,
    signals,
    disclaimer:
      "Job signals describe evidence found in the supplied job/application context. They do not diagnose employer culture, toxicity, intent, or future workplace conditions.",
  };
}
