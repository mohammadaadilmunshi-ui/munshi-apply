# MUNSHI Apply — Phase 3, Phase 8, Phase 9 + Teach-MUNSHI strengthening

**Build mode:** source/CI only; owner-side deployment intentionally deferred.

## Phase 3 — Evidence & Retrieval

- Durable Evidence Graph remains the authority.
- Added PDF/DOCX/TXT/MD résumé parsing with explicit refusal for legacy `.doc` and image-only/no-text files rather than false parsing.
- Added resumable, SHA-256-verified Native Messaging document ingestion so original résumé bytes can be indexed without putting large documents into a single native message.
- Résumé evidence is chunked, source-bound, `DOCUMENT_CONFIRMED`, non-protected by default, and replaces older indexed chunks for the same résumé identity.
- Added hybrid semantic retrieval planning with trust, evidence kind, semantic intent, query overlap, source diversity, duplicate suppression, and contradiction avoidance.
- Job-specific context assembly expands retrieval using the response intent rather than only literal question words.

## Phase 8 — Provider-Agnostic Intelligence

- OpenAI remains supported through the Responses API adapter.
- Added a provider interface and local Ollama structured-output adapter using a loopback-only endpoint.
- Added cheap/strong model lanes and response-intent routing.
- Added `auto`, `openai`, and `ollama` provider policies with optional local fallback.
- Paid OpenAI routes retain pricing/budget reservation enforcement; local Ollama routes have zero provider API cost and do not consume the paid budget.
- A blocked paid route can select configured local fallback rather than making the application question unusable.

## Phase 9 — Job-Specific Responses

- Added intent planning for Why Company, Why Role, role understanding, relevant experience, career transition, motivation, behavioral, and other narrative questions.
- Intent controls evidence requirements, retrieval vocabulary, default answer length, and cheap/strong model lane.
- Job/company-dependent answers require captured job context instead of generic guessing.
- Existing claim-to-evidence validation, contradiction checking, exact owner approval, and word limits remain enforced.
- Added writing-style learning from owner-edited answers only when the exact edit is approved. Rejected or untouched generated drafts do not train the preference profile.

## Teach-MUNSHI strengthening

- Demonstrations now capture structured before/after control state, a bounded event sequence, targeted-event evidence, commit evidence, and a capture quality score.
- Unrelated page clicks no longer make a demonstration reusable.
- A recipe requires a real control-state change plus commit evidence and high capture quality before it is saved.
- Existing value-free recipes, SHADOW testing, promotion, versioning, verification, fallback, and rollback remain intact.

## Practical principle

Truth/security boundaries remain hard boundaries. Missing job context, unsupported document formats, unverified provider output, and low-quality demonstrations are surfaced clearly. Routine application work should otherwise keep moving through deterministic retrieval, local/cloud model routing, owner review, and recoverable teaching.
