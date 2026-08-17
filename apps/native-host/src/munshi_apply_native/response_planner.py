from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class JobResponsePlan:
    intent: str
    model_lane: str
    requires_job_context: bool
    requires_candidate_evidence: bool
    retrieval_terms: tuple[str, ...]
    default_max_words: int


_INTENT_TERMS: dict[str, tuple[str, ...]] = {
    "WHY_COMPANY": (
        "company",
        "organization",
        "mission",
        "culture",
        "values",
        "industry",
        "team",
    ),
    "WHY_ROLE": (
        "role",
        "position",
        "responsibilities",
        "opportunity",
        "skills",
        "experience",
    ),
    "ROLE_UNDERSTANDING": (
        "responsibilities",
        "duties",
        "role",
        "position",
        "requirements",
        "team",
    ),
    "RELEVANT_EXPERIENCE": (
        "experience",
        "responsibilities",
        "achievements",
        "skills",
        "results",
        "project",
    ),
    "CAREER_TRANSITION": (
        "career",
        "growth",
        "next",
        "opportunity",
        "goals",
        "experience",
    ),
    "MOTIVATION": (
        "motivation",
        "interest",
        "role",
        "company",
        "experience",
        "goals",
    ),
    "BEHAVIORAL": (
        "example",
        "situation",
        "action",
        "result",
        "challenge",
        "achievement",
        "team",
    ),
    "OTHER_NARRATIVE": ("experience", "role", "skills"),
}


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def classify_response_intent(question: str, semantic_type: str) -> str:
    semantic = semantic_type.strip().upper()
    text = _normalized(question)
    if semantic == "WHY_COMPANY" or re.search(
        r"why (?:do you want to (?:work|join)|are you interested in) "
        r"(?:us|our|this company|the company)",
        text,
    ):
        return "WHY_COMPANY"
    if semantic == "WHY_ROLE" or re.search(
        r"why (?:this|the) (?:role|position)|why are you interested in "
        r"(?:this|the) (?:role|position)",
        text,
    ):
        return "WHY_ROLE"
    if semantic in {"ROLE_RESPONSIBILITIES", "ROLE_UNDERSTANDING"} or re.search(
        r"what (?:does|do you understand about).*(?:role|position)|describe "
        r"(?:the )?(?:role|responsibilities)",
        text,
    ):
        return "ROLE_UNDERSTANDING"
    if semantic == "RELEVANT_EXPERIENCE" or re.search(
        r"(?:relevant|related|prior) experience|tell us about your experience|"
        r"describe your experience",
        text,
    ):
        return "RELEVANT_EXPERIENCE"
    if semantic == "CAREER_GOALS" or re.search(
        r"(?:leave|leaving) your current|career (?:goal|move|transition)|looking for next",
        text,
    ):
        return "CAREER_TRANSITION"
    if semantic in {"MOTIVATION", "RECRUITMENT_MOTIVATION"} or re.search(
        r"what motivates|why recruitment|why sales|motivat(?:e|ion)|what interests you",
        text,
    ):
        return "MOTIVATION"
    if semantic == "BEHAVIORAL_EXAMPLE" or re.search(
        r"tell (?:me|us) about a time|give (?:me|us) an example|describe a time|situation where",
        text,
    ):
        return "BEHAVIORAL"
    return "OTHER_NARRATIVE"


def plan_job_response(
    question: str,
    semantic_type: str,
    requested_max_words: int | None = None,
) -> JobResponsePlan:
    intent = classify_response_intent(question, semantic_type)
    requires_job = intent in {
        "WHY_COMPANY",
        "WHY_ROLE",
        "ROLE_UNDERSTANDING",
        "MOTIVATION",
    }
    requires_candidate = intent in {
        "WHY_ROLE",
        "RELEVANT_EXPERIENCE",
        "CAREER_TRANSITION",
        "MOTIVATION",
        "BEHAVIORAL",
    }
    model_lane = (
        "STRONG" if intent in {"BEHAVIORAL", "CAREER_TRANSITION", "MOTIVATION"} else "CHEAP"
    )
    defaults = {
        "WHY_COMPANY": 140,
        "WHY_ROLE": 160,
        "ROLE_UNDERSTANDING": 160,
        "RELEVANT_EXPERIENCE": 190,
        "CAREER_TRANSITION": 130,
        "MOTIVATION": 160,
        "BEHAVIORAL": 240,
        "OTHER_NARRATIVE": 180,
    }
    default_max_words = requested_max_words or defaults[intent]
    return JobResponsePlan(
        intent=intent,
        model_lane=model_lane,
        requires_job_context=requires_job,
        requires_candidate_evidence=requires_candidate,
        retrieval_terms=_INTENT_TERMS[intent],
        default_max_words=default_max_words,
    )
