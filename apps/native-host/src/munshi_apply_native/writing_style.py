from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class WritingStyleProfile:
    samples: int = 0
    average_words: float = 0.0
    average_sentence_words: float = 0.0
    contraction_rate: float = 0.0
    first_person_rate: float = 0.0
    enthusiasm_rate: float = 0.0
    concise_preference: float = 0.5

    def instructions(self) -> str:
        if self.samples <= 0:
            return (
                "Use a concise, natural, professional first-person tone. Avoid generic filler, "
                "inflated claims, clichés, and robotic headings."
            )
        length = "concise" if self.concise_preference >= 0.6 else "moderately detailed"
        contractions = (
            "Natural contractions are acceptable when they improve conversational flow."
            if self.contraction_rate >= 0.08
            else "Prefer full professional phrasing over frequent contractions."
        )
        enthusiasm = (
            "Use measured positive energy without exaggeration."
            if self.enthusiasm_rate >= 0.02
            else "Keep enthusiasm understated and specific."
        )
        return (
            f"Match the owner's learned style: {length}, first-person, approximately "
            f"{max(8, round(self.average_sentence_words))} words per sentence. "
            f"{contractions} {enthusiasm} Avoid generic filler and preserve the owner's voice."
        )


_CONTRACTIONS = re.compile(r"\b(?:i'm|i've|i'd|i'll|don't|can't|won't|it's|that's|there's|we're|i’ve|i’m)\b", re.I)
_FIRST_PERSON = re.compile(r"\b(?:i|me|my|mine|i'm|i’ve|i'm)\b", re.I)


def _metrics(text: str) -> dict[str, float]:
    words = re.findall(r"\b[\w'’.-]+\b", text)
    sentences = [item for item in re.split(r"[.!?]+", text) if item.strip()]
    word_count = max(1, len(words))
    sentence_count = max(1, len(sentences))
    return {
        "words": float(len(words)),
        "sentence_words": len(words) / sentence_count,
        "contractions": len(_CONTRACTIONS.findall(text)) / word_count,
        "first_person": len(_FIRST_PERSON.findall(text)) / word_count,
        "enthusiasm": text.count("!") / sentence_count,
    }


class WritingStyleStore:
    def __init__(self, runtime_root: Path) -> None:
        self.path = runtime_root / "settings" / "writing-style.json"

    def load(self) -> WritingStyleProfile:
        if not self.path.exists():
            return WritingStyleProfile()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return WritingStyleProfile(**{key: raw[key] for key in asdict(WritingStyleProfile()) if key in raw})
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return WritingStyleProfile()

    def _save(self, profile: WritingStyleProfile) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.path.parent, prefix="style-", suffix=".tmp", delete=False
        ) as handle:
            json.dump(asdict(profile), handle, indent=2, sort_keys=True)
            handle.write("\n")
            temporary = Path(handle.name)
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)
        os.chmod(self.path, 0o600)

    def learn_from_approved_edit(self, generated: str, approved: str) -> WritingStyleProfile:
        approved = approved.strip()
        if not approved or approved == generated.strip():
            return self.load()
        metrics = _metrics(approved)
        current = self.load()
        previous = current.samples
        total = previous + 1

        def blend(old: float, new: float) -> float:
            return ((old * previous) + new) / total

        generated_words = max(1, len(re.findall(r"\b[\w'’.-]+\b", generated)))
        concise = min(1.0, max(0.0, 1.0 - (metrics["words"] / generated_words - 0.65)))
        next_profile = WritingStyleProfile(
            samples=total,
            average_words=blend(current.average_words, metrics["words"]),
            average_sentence_words=blend(current.average_sentence_words, metrics["sentence_words"]),
            contraction_rate=blend(current.contraction_rate, metrics["contractions"]),
            first_person_rate=blend(current.first_person_rate, metrics["first_person"]),
            enthusiasm_rate=blend(current.enthusiasm_rate, metrics["enthusiasm"]),
            concise_preference=blend(current.concise_preference, concise),
        )
        self._save(next_profile)
        return next_profile

    def status(self) -> dict[str, object]:
        profile = self.load()
        return {**asdict(profile), "instructions": profile.instructions()}
