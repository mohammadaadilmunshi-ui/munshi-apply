# MUNSHI Apply
## Universal Adaptive Job Application Agent
### Complete Master Architecture Plan

**Architecture Version:** 2.0
**Status:** Architecture Baseline
**Primary Browser:** Microsoft Edge
**Primary Environment:** macOS
**Primary Use:** Personal job-application intelligence and automation
**Architecture Philosophy:** Universal, evidence-grounded, progressively adaptive, local-first, provider-agnostic, verifiable, recoverable

---

# 1. PRODUCT DEFINITION

**MUNSHI Apply** is a universal adaptive job-application agent.

It is not:

- a basic browser autofill extension;
- a Workday automation script;
- a Greenhouse bot;
- a collection of ATS-specific selectors;
- an AI that blindly answers application questions;
- a bulk-application spam engine.

It is a coordinated browser and local intelligence system that can:

1. discover and understand job-application interfaces dynamically;
2. identify what each question or form field means;
3. resolve factual answers from a verified personal profile;
4. select or accept a tailored résumé for each application;
5. analyze the job, résumé, profile, and application together;
6. prepare the entire application before acting;
7. preview all important answers and actions;
8. create or detect application accounts;
9. navigate multi-step and dynamically changing applications;
10. fill conventional and unconventional interface controls;
11. verify that every meaningful action succeeded;
12. recover from failed interaction methods;
13. preserve application state during interruptions;
14. learn from every successful action;
15. learn from every failed action;
16. learn from user corrections;
17. reuse interaction knowledge across unrelated websites;
18. maintain a complete application ledger;
19. track application-specific portfolio engagement;
20. support résumé and written-response experiments;
21. export structured analytics;
22. integrate with n8n and broader automation systems.

---

# 2. CORE PRODUCT PROMISE

The architectural promise of MUNSHI Apply is:

> **No legitimate job-application website is rejected merely because its platform is unknown.**

The system does not begin by asking:

```text
Is this Workday?
Is this Greenhouse?
Is this Lever?
```

It begins by asking:

```text
What is visible?
What is interactive?
What does each element mean?
What information does this application request?
What information do we already know?
What requires reasoning?
What requires the user?
How can this interface be operated reliably?
```

Known ATS platforms may eventually receive optimization layers, but they never define compatibility.

---

# 3. DEFINITION OF UNIVERSAL

For this project, **Universal** means:

> Every legitimate browser-based job application enters the same universal discovery, understanding, planning, interaction, verification, recovery, and learning pipeline.

There is no architectural ATS allowlist.

Unknown systems become:

```text
PLATFORM: UNKNOWN
UNIVERSAL ENGINE: ACTIVE
```

not:

```text
UNSUPPORTED ATS
```

---

# 4. DEFINITION OF PROGRESSIVE

For this project, **Progressive** means:

> Every completed or attempted application should leave the system more informed than it was before.

Learning can include:

- new question wording;
- new semantic concepts;
- new field patterns;
- new interface components;
- successful interaction strategies;
- failed strategies;
- website-specific quirks;
- application workflow structures;
- user corrections;
- writing preferences;
- résumé-selection patterns;
- portfolio engagement;
- application outcomes.

Application #200 should therefore benefit from experience accumulated during applications #1–199.

---

# 5. DEFINITION OF SELF-LEARNING

Self-learning does **not** mean allowing uncontrolled AI to rewrite production code.

MUNSHI Apply learns through versioned structured knowledge:

```text
Semantic mappings
Interaction recipes
Component fingerprints
Site behavior
Question concepts
Failure-avoidance rules
User preferences
Confidence adjustments
Resume recommendations
Workflow patterns
```

Learned behavior must be:

```text
Versioned
Auditable
Reversible
Scope-aware
Confidence-scored
Evidence-backed
```

---

# 6. HIGH-LEVEL SYSTEM ARCHITECTURE

```text
┌──────────────────────────────────────────────────────────┐
│                     MUNSHI APPLY                         │
│          Universal Adaptive Application Agent            │
└──────────────────────────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
    EDGE EXTENSION   LOCAL COMPANION   INTELLIGENCE STORE
          │                │                │
          │                │                │
    Browser UI          Filesystem       Profiles
    Page Sensors        SQLite           Evidence
    Interaction         AI Gateway       Resumes
    AutoPilot           Retrieval        Applications
    Side Panel          Backups          Patterns
          │                │                │
          └────────────────┼────────────────┘
                           ▼
                 APPLICATION BRAIN
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
    UNDERSTAND           PLAN              EXECUTE
        │                  │                  │
        └──────────────────┼──────────────────┘
                           ▼
                         VERIFY
                           │
                           ▼
                         RECOVER
                           │
                           ▼
                          LEARN
```

---

# 7. PRIMARY SUBSYSTEMS

The complete system is divided into these major subsystems:

```text
01. Edge Extension Runtime
02. Persistent Side Panel
03. Universal Page Understanding Engine
04. Semantic Field & Question Engine
05. Interaction Integrity Engine
06. Application State Machine
07. Master Profile Vault
08. Master Resume System
09. Tailored Resume System
10. Evidence Graph
11. Retrieval & Context Engine
12. Provider-Agnostic AI Layer
13. Application Planner
14. Pre-Flight Preview
15. Adaptive AutoPilot
16. Interaction Escalation Engine
17. Account Orchestrator
18. Verification/Human Checkpoint Manager
19. Progressive Learning Core
20. Component Pattern Library
21. Site Memory
22. Teach-MUNSHI System
23. Job Signal Intelligence
24. Artifact Attribution Engine
25. Experiment Engine
26. Application Ledger
27. Outcome & Analytics Engine
28. n8n Event Bridge
29. Local Companion
30. Security & Privacy Layer
31. Diagnostics & Observability
32. Backup & Recovery
```

---

# 8. EDGE EXTENSION FOUNDATION

The browser component should use Microsoft Edge's Chromium extension model with **Manifest V3**.

Microsoft documents `manifest.json` as the extension blueprint, including permissions and extension metadata.

Recommended browser stack:

```text
Manifest V3
TypeScript
React
Vite
Zod / JSON Schema
Chrome/Edge Extension APIs
IndexedDB
Web Workers where appropriate
```

---

# 9. PERSISTENT SIDE PANEL

The primary MUNSHI Apply user interface should be a persistent side panel rather than a disappearing browser-action popup.

The current Chromium Side Panel API supports persistent extension experiences alongside normal browsing.

The panel becomes the command center.

Primary sections:

```text
CURRENT APPLICATION
PRE-FLIGHT
QUESTIONS
RESUME
AUTOPILOT
ACCOUNT
WARNINGS
LEARNING
ANALYTICS
APPLICATIONS
SETTINGS
DIAGNOSTICS
```

---

# 10. EXTENSION RUNTIME STRUCTURE

Recommended browser source layout:

```text
extension/
│
├── manifest.json
│
├── src/
│   │
│   ├── background/
│   │   ├── service-worker.ts
│   │   ├── event-router.ts
│   │   ├── native-bridge.ts
│   │   └── lifecycle.ts
│   │
│   ├── content/
│   │   ├── bootstrap.ts
│   │   ├── page-observer.ts
│   │   ├── dom-scanner.ts
│   │   ├── aria-scanner.ts
│   │   ├── field-discovery.ts
│   │   ├── question-extractor.ts
│   │   ├── control-fingerprint.ts
│   │   ├── interaction.ts
│   │   └── verifier.ts
│   │
│   ├── frames/
│   │   ├── frame-agent.ts
│   │   └── frame-coordinator.ts
│   │
│   ├── autopilot/
│   │   ├── planner.ts
│   │   ├── executor.ts
│   │   ├── navigation.ts
│   │   └── recovery.ts
│   │
│   ├── sidepanel/
│   │   ├── App.tsx
│   │   ├── Dashboard.tsx
│   │   ├── PreFlight.tsx
│   │   ├── ResumeSelector.tsx
│   │   ├── QuestionReview.tsx
│   │   ├── AutoPilotView.tsx
│   │   ├── Applications.tsx
│   │   ├── Analytics.tsx
│   │   └── Settings.tsx
│   │
│   ├── storage/
│   ├── messaging/
│   ├── schemas/
│   ├── types/
│   └── utilities/
│
└── tests/
```

---

# 11. SERVICE WORKER DESIGN

Manifest V3 extension background logic runs through service workers rather than persistent background pages.

Service workers should therefore be treated as **ephemeral coordinators**, not authoritative in-memory databases.

Chromium documents extension service-worker lifecycle behavior separately from traditional persistent pages, and IndexedDB is available from extension service workers.

Architectural rule:

```text
NO IMPORTANT STATE EXISTS ONLY IN MEMORY.
```

All durable state must be persisted.

---

# 12. UNIVERSAL PAGE OBSERVATION ENGINE

Every relevant browser document receives an observer.

The observer continuously monitors:

```text
DOM changes
SPA navigation
New controls
Removed controls
Conditional fields
Validation errors
Dialogs
Modals
Dynamic sections
File upload states
Button-state changes
Visibility changes
ARIA-state changes
Frame creation
Form completion
```

A `MutationObserver` should support incremental rescanning.

The engine must avoid repeatedly rescanning the entire document when only a small region changes.

---

# 13. MULTI-FRAME ARCHITECTURE

Content scripts can read and modify page DOM and communicate with the parent extension.

The architecture should treat each injectable frame as an independent sensor:

```text
TAB
│
├── FRAME 0
│   └── MUNSHI FRAME AGENT
│
├── FRAME 3
│   └── MUNSHI FRAME AGENT
│
└── FRAME 8
    └── MUNSHI FRAME AGENT
```

Each reports:

```text
tab_id
frame_id
document_id
origin
url
controls
questions
uploads
navigation
validation
```

to the service worker.

The Application Brain then constructs one unified application model.

---

# 14. UNIVERSAL PAGE UNDERSTANDING ENGINE

The engine transforms arbitrary application interfaces into semantic models.

Inputs:

```text
Visible text
DOM hierarchy
Input elements
ARIA attributes
Labels
Placeholders
Section headings
Nearby text
Control roles
Options
Navigation
Page URL
Page title
Frames
Shadow roots
Application context
```

Outputs:

```text
ApplicationPage
ApplicationSection[]
Question[]
Control[]
UploadTarget[]
NavigationAction[]
AuthenticationState
ValidationState
```

---

# 15. FIELD DISCOVERY LAYERS

Field understanding should progress through several independent signals.

## Layer A — Native semantics

```text
label
input
select
textarea
button
```

## Layer B — Accessibility semantics

```text
aria-label
aria-labelledby
aria-describedby
role
aria-expanded
aria-controls
```

## Layer C — Structural semantics

```text
nearest text block
section heading
sibling relationships
container grouping
```

## Layer D — Language understanding

Visible question text is classified semantically.

## Layer E — Historical knowledge

Previously learned component/question patterns are consulted.

## Layer F — Visual reasoning fallback

Only when conventional semantics remain insufficient.

---

# 16. SEMANTIC QUESTION ENGINE

Every application question receives a normalized semantic concept.

Example:

```json
{
  "raw_text": "Will you now or in the future require sponsorship?",
  "semantic_type": "SPONSORSHIP_FUTURE",
  "answer_type": "BOOLEAN",
  "confidence": 0.994,
  "answer_source": "VERIFIED_PROFILE"
}
```

---

# 17. INITIAL QUESTION ONTOLOGY

Initial concepts should include, but not be limited to:

```text
PERSONAL
CONTACT
ADDRESS
EMAIL
PHONE
LINKEDIN
PORTFOLIO
WEBSITE

EDUCATION
DEGREE
FIELD_OF_STUDY
GRADUATION_DATE
GPA

EMPLOYMENT
EMPLOYMENT_DATES
EMPLOYMENT_RESPONSIBILITIES

WORK_AUTHORIZATION_CURRENT
SPONSORSHIP_CURRENT
SPONSORSHIP_FUTURE
IMMIGRATION_ASSISTANCE

SALARY_EXPECTATION
START_DATE
NOTICE_PERIOD

RELOCATION
TRAVEL
REMOTE
HYBRID
ONSITE

SKILLS
CERTIFICATIONS
LICENSES
LANGUAGES
SECURITY_CLEARANCE

VETERAN_STATUS
PROTECTED_VETERAN_STATUS
DISABILITY_STATUS
GENDER
RACE_ETHNICITY
EEO_SELF_ID

REFERRAL
PREVIOUS_EMPLOYEE
PREVIOUS_APPLICATION
CONFLICT_OF_INTEREST
NON_COMPETE
BACKGROUND_CHECK
DRUG_SCREENING

WHY_COMPANY
WHY_ROLE
RELEVANT_EXPERIENCE
CAREER_GOALS
BEHAVIORAL_EXAMPLE

UNKNOWN
```

`UNKNOWN` is a valid temporary state, not a failure.

---

# 18. SELF-GROWING ONTOLOGY

When a genuinely new concept appears:

```text
UNKNOWN QUESTION
       ↓
Semantic reasoning
       ↓
User clarification
       ↓
New canonical concept
       ↓
Save mapping
       ↓
Reuse later
```

Example:

```text
POST_EMPLOYMENT_RESTRICTION
EXPORT_CONTROL_ELIGIBILITY
FIDUCIARY_RELATIONSHIP
```

can be introduced when encountered.

---

# 19. MASTER PROFILE VAULT

The Master Profile is the authoritative structured application identity.

Major sections:

```text
Identity
Contact
Address
Education
Employment
Projects
Skills
Certifications
Languages
Availability
Work Preferences
Relocation
Travel
Salary Preferences
Work Authorization
Sponsorship
Voluntary Demographics
Veteran Status
Disability Response
Saved Application Answers
Writing Preferences
```

---

# 20. FACT TRUST MODEL

Every profile value receives:

```text
fact_id
value
category
trust_level
source
confirmed_at
updated_at
protected
```

Trust levels:

```text
VERIFIED
USER_CONFIRMED
DOCUMENT_CONFIRMED
DERIVED
GENERATED
LEARNED
UNKNOWN
```

---

# 21. PROTECTED FACT MODEL

Sensitive or consequential facts may not be changed silently.

Examples:

```text
Legal name
Employment dates
Employer names
Education
Graduation
Work authorization
Sponsorship
Veteran response
Disability response
Gender response
Race/ethnicity response
```

Learning may improve **question recognition**.

Learning may not silently alter **the answer**.

---

# 22. MASTER RESUME SYSTEM

MUNSHI Apply maintains a canonical Master Resume.

Purpose:

```text
Evidence baseline
Experience source
Date reference
Skill reference
Metric reference
Resume consistency comparison
```

The Master Resume is not automatically submitted to employers.

---

# 23. TAILORED RESUME SYSTEM

Every application can choose:

```text
Use Master Resume
Choose Existing Tailored Resume
Upload New Tailored Resume
```

Example:

```text
MASTER
Aadil_Master_Resume.pdf

APPLICATION
ExampleCorp_People_Analytics.pdf
```

The selected application résumé becomes immutable application evidence after submission.

---

# 24. RESUME VERSIONING

Each résumé record should contain:

```text
resume_id
family
version
sha256
filename
created_at
source_path
role_family
active
```

Example:

```text
RES-PA-004
People Analytics
Version 4
```

The SHA-256 prevents a later modified file from being mistaken for the file originally submitted.

---

# 25. EVIDENCE GRAPH

Flat resume text is insufficient.

The Evidence Graph stores relationships.

Example:

```text
EMPLOYER
 Toyota
    │
    ├── ROLE
    │   HR Recruitment & Operations Intern
    │
    ├── DATES
    │
    ├── RESPONSIBILITY
    │   Candidate sourcing
    │
    ├── RESPONSIBILITY
    │   Onboarding
    │
    ├── SKILL
    │   Excel
    │
    └── ACHIEVEMENT
        Verified metric
```

---

# 26. EVIDENCE NODE STRUCTURE

```text
node_id
node_type
statement
source
source_version
confidence
verified
tags[]
relationships[]
embedding_reference
```

---

# 27. RETRIEVAL ENGINE

MUNSHI Apply should not send the complete profile and résumé to an LLM for every question.

Instead:

```text
QUESTION
    ↓
Semantic classification
    ↓
Evidence retrieval
    ↓
Top-K relevant nodes
    ↓
Context compression
    ↓
Model
```

Example:

```text
Question:
Describe your recruiting experience.

Retrieved:
Toyota recruiting evidence
Candidate sourcing evidence
Hiring metric evidence
Relevant tailored résumé bullet
```

Only these become model context.

---

# 28. VECTOR / SEMANTIC INDEX

The retrieval engine can maintain embeddings for:

```text
Profile facts
Resume bullets
Projects
Experience
Saved answers
Job requirements
Company context
```

The system should be designed so the vector implementation can change without affecting upstream modules.

Possible implementations:

```text
SQLite vector extension
Chroma
pgvector
FAISS
Other local index
```

No business logic should depend directly on one vector provider.

---

# 29. PROVIDER-AGNOSTIC AI LAYER

MUNSHI Apply must not depend on a single model provider.

Architecture:

```text
                INTELLIGENCE ROUTER
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
    OpenAI          Gemini         Anthropic
       │               │               │
       └───────────────┼───────────────┘
                       ▼
                    Ollama
```

Interface:

```text
AIProvider
  classify()
  generate()
  reason()
  embed()
  inspectImage()
```

---

# 30. MODEL ROUTER

Never use the strongest model automatically.

Routing:

```text
Can deterministic system answer?
        ↓ YES
        $0

NO
 ↓
Can saved knowledge answer?
        ↓ YES
        $0

NO
 ↓
Cheap classifier / small model
        ↓
Resolved?
        ↓ YES
        Continue

NO
 ↓
Stronger reasoning model
```

---

# 31. API BUDGET ENGINE

MUNSHI Apply should track:

```text
monthly_budget
soft_limit
hard_limit
spent
calls_by_provider
tokens_by_provider
estimated_cost
average_cost_per_application
```

Example:

```text
Monthly budget: $10
Soft warning: $5
Hard stop: $10
```

At hard limit:

```text
Paid inference disabled
        ↓
Fallback:
Local AI
Deterministic logic
Manual review
```

---

# 32. JOB CONTEXT ENGINE

Before completing an application, collect:

```text
Company
Role
Location
Work arrangement
Employment type
Compensation
Job description
Requirements
Preferred qualifications
Requisition ID
Application URL
Job URL
```

Unknown values remain unknown rather than invented.

---

# 33. JOB SIGNAL INTELLIGENCE

This module evaluates the job description without making unsupported claims about workplace toxicity.

Suggested dimensions:

```text
Role Ambiguity
Responsibility Breadth
Qualification Inflation
Workload Pressure
Schedule Intensity
Travel Burden
Compensation Clarity
Seniority Alignment
Role Stability Signals
Location Constraints
Work Authorization Risk
Application Friction
```

---

# 34. JOB SIGNAL OUTPUT

Example:

```json
{
  "overall_signal": "MODERATE",
  "dimensions": {
    "role_ambiguity": 72,
    "responsibility_breadth": 81,
    "compensation_clarity": 25
  },
  "signals": [
    {
      "type": "ROLE_BREADTH",
      "severity": "HIGH",
      "evidence": "Relevant excerpt",
      "explanation": "Responsibilities span several distinct functions."
    }
  ]
}
```

Every signal should expose evidence.

---

# 35. APPLICATION ANSWER RESOLUTION

Every field follows:

```text
QUESTION
   ↓
Semantic type
   ↓
Can Master Profile answer?
   ↓
Can saved answer answer?
   ↓
Can evidence resolve?
   ↓
Can tailored resume resolve?
   ↓
Does generation make sense?
   ↓
Generate + validate
   ↓
Otherwise manual review
```

---

# 36. ANSWER SOURCE HIERARCHY

Priority:

```text
1. Verified Profile
2. User-Confirmed Answer
3. Protected Fact
4. Master Resume
5. Tailored Resume
6. Evidence Graph
7. Job Description
8. Company Context
9. Learned Preference
10. AI Generation
11. Manual User Resolution
```

Higher-priority factual evidence cannot be overridden by a lower-priority generated answer.

---

# 37. SENSITIVE QUESTION ENGINE

Questions involving:

```text
Work authorization
Sponsorship
Veteran status
Disability
Gender
Race/Ethnicity
Voluntary self-identification
```

must resolve to explicitly saved choices.

Never infer these characteristics.

---

# 38. JOB-SPECIFIC WRITTEN RESPONSES

Examples:

```text
Why this company?
Why this position?
Tell us about yourself.
Describe relevant experience.
What makes you a strong candidate?
Describe your analytics experience.
```

Generation context:

```text
Relevant job requirements
+
Tailored résumé
+
Retrieved evidence
+
Verified profile
+
Company context
+
Writing preferences
```

---

# 39. WRITTEN RESPONSE VALIDATION

Every generated answer runs through:

```text
Evidence validation
Unsupported claim detection
Contradiction check
Word-limit check
Question relevance
Tone check
Duplicate phrase check
Resume consistency check
```

---

# 40. APPLICATION PLANNER

Before touching the webpage, construct an internal plan.

Example:

```text
APPLICATION

Fields discovered:        71
Verified answers:         46
Resume-derived:            8
Saved mappings:            6
Generated responses:       7
Needs review:              3
Unresolved:                1
```

---

# 41. PRE-FLIGHT PREVIEW

Pre-flight is mandatory before significant automation.

The panel displays:

```text
COMPANY
ROLE
JOB SIGNALS
RESUME
ACCOUNT ACTION
PERSONAL INFORMATION
EDUCATION
EMPLOYMENT
AUTHORIZATION
SPONSORSHIP
EEO
SALARY
CUSTOM QUESTIONS
KNOCKOUT QUESTIONS
WARNINGS
UNRESOLVED QUESTIONS
```

---

# 42. ANSWER BADGES

```text
VERIFIED
PROFILE
RESUME
USER SAVED
GENERATED
LEARNED
REVIEW
BLOCKED
```

---

# 43. KNOCKOUT QUESTION ENGINE

Higher-risk questions include:

```text
Work authorization
Sponsorship
Required degree
Required certification
Security clearance
Years of experience
Required location
Travel
Shift
Required license
```

These receive higher confidence requirements.

The system must never manipulate truthful answers merely to qualify.

---

# 44. SALARY POLICY ENGINE

Configurable options:

```text
Always review
Use exact saved target
Use saved range
Use posted range
Prefer negotiable
Leave unanswered when optional
```

---

# 45. APPLICATION STATE MACHINE

A universal workflow model:

```text
JOB_CONTEXT
       ↓
AUTH
       ↓
ACCOUNT_CREATE
       ↓
VERIFY_ACCOUNT
       ↓
PERSONAL
       ↓
EDUCATION
       ↓
EXPERIENCE
       ↓
RESUME
       ↓
QUESTIONS
       ↓
EEO
       ↓
DISCLOSURES
       ↓
REVIEW
       ↓
SUBMISSION
       ↓
CONFIRMATION
       ↓
COMPLETE
```

Not every application uses every state.

States are discovered dynamically.

---

# 46. ADAPTIVE AUTOPILOT

AutoPilot repeatedly performs:

```text
OBSERVE
   ↓
PLAN
   ↓
ACT
   ↓
VERIFY
   ↓
RESCAN
   ↓
CONTINUE
```

Never:

```text
fill()
clickNext()
hope()
```

---

# 47. INTERACTION INTEGRITY ENGINE

Before operating a control:

```text
Is it attached?
Is it visible?
Is it enabled?
Is it part of the application?
Is it semantically relevant?
Is it user-interactable?
```

Controls failing these tests are ignored or flagged.

The engine exists to prevent accidental interaction with hidden or irrelevant controls, not to defeat site security systems.

---

# 48. FRAMEWORK-COMPATIBLE INPUT

For controlled web components, the system should not assume:

```js
element.value = value
```

is sufficient.

Interaction may require:

```text
Focus
Native setter
Input event
Change event
Blur
Framework/state verification
```

If the site's internal state does not accept the value, the attempt fails even if the visible input appears correct.

---

# 49. STATE-BASED WAITS

Avoid arbitrary fixed delays whenever possible.

Prefer:

```text
Wait until element visible
Wait until enabled
Wait until options rendered
Wait until validation disappears
Wait until page state changes
Wait until upload completed
```

Timing is driven by UI state rather than attempts to imitate human behavior.

---

# 50. INTERACTION ESCALATION LADDER

```text
LEVEL 1
Native DOM interaction

        ↓

LEVEL 2
Keyboard/mouse semantics

        ↓

LEVEL 3
Custom component recipe

        ↓

LEVEL 4
Frame / Shadow DOM strategy

        ↓

LEVEL 5
Browser instrumentation

        ↓

LEVEL 6
Native companion assistance

        ↓

LEVEL 7
Visual reasoning

        ↓

LEVEL 8
Teach-MUNSHI
```

The `chrome.scripting` API supports runtime script injection, while extension/native communication is supported through Native Messaging.

---

# 51. SECURITY CHECKPOINT BOUNDARY

MUNSHI Apply does not attempt to defeat:

```text
CAPTCHA
MFA
OTP
Identity verification
Authentication protection
Anti-abuse controls
```

Instead:

```text
SECURITY CHECKPOINT
       ↓
Save application state
       ↓
Notify user
       ↓
User completes checkpoint
       ↓
Detect completion
       ↓
Resume application
```

---

# 52. CUSTOM COMPONENT LIBRARY

Initial component classes:

```text
Native input
Textarea
Native select
Radio
Checkbox
Searchable select
Combobox
Autocomplete
Date picker
Segmented date field
Multi-select
Tag selector
Drag/drop uploader
Custom uploader
Address autocomplete
Phone-country selector
Modal
Stepper
Accordion
Rich text field
```

---

# 53. COMPONENT FINGERPRINTING

Example:

```text
fingerprint_id: CFP-0042

type:
SEARCHABLE_COMBOBOX

signals:
role=combobox
aria-expanded=true/false
dynamic listbox
input-backed
portal-rendered menu
```

Matching components can reuse previous recipes even on different websites.

---

# 54. INTERACTION RECIPE MODEL

```text
recipe_id
fingerprint
preconditions
steps[]
verification
success_count
failure_count
confidence
version
scope
last_used
```

---

# 55. FAILURE MEMORY

Example:

```text
Component:
CFP-0042

Attempt:
Direct value setter

Observed:
Text visible

Validation:
Failed

Lesson:
Do not use direct setter

Preferred:
Recipe R-0038
```

A known failed approach should not repeatedly be retried when a successful alternative exists.

---

# 56. SUCCESS MEMORY

Successful interactions reinforce:

```text
Component fingerprint
Recipe
Website context
Question type
Verification result
```

---

# 57. GLOBAL MEMORY

Transferable across sites.

Examples:

```text
React combobox interaction
Date picker behavior
Resume drop-zone behavior
```

---

# 58. SITE MEMORY

Specific to a website or implementation.

Examples:

```text
Validation occurs only after blur
Resume parser overwrites employment fields
Continue button appears after animation
```

---

# 59. USER MEMORY

Examples:

```text
Preferred written-answer length
Salary review preference
Resume family preference
Preferred answer tone
```

---

# 60. APPLICATION MEMORY

Examples:

```text
Resume used
Salary answer
Generated why-company response
Temporary clarification
```

---

# 61. PROGRESSIVE LEARNING PIPELINE

```text
ACTION
   ↓
RESULT
   ↓
VERIFY
   ↓
LABEL
   ↓
CREATE LEARNING EVENT
   ↓
DETERMINE SCOPE
   ↓
UPDATE CONFIDENCE
   ↓
SAVE VERSION
```

---

# 62. QUESTION LEARNING

Novel question:

```text
Question classified: UNKNOWN
Confidence: 42%
```

User answers and may select:

```text
Remember:
○ This application
○ Similar questions
● Globally
```

If appropriate, a new canonical semantic mapping is created.

---

# 63. LEARNING FROM WRITING CORRECTIONS

Compare:

```text
Generated answer
versus
User-approved answer
```

Extract preferences such as:

```text
Preferred length
Opening style
Formality
Evidence density
Company emphasis
Role emphasis
Sentence complexity
Generic wording avoidance
```

Do not merely memorize the entire corrected answer.

Learn the underlying preference pattern.

---

# 64. TEACH-MUNSHI MODE

When the system cannot interact reliably:

```text
Capture BEFORE state
       ↓
Ask user to complete one interaction
       ↓
Capture AFTER state
       ↓
Compare
       ↓
Infer candidate recipe
       ↓
Test safely later
       ↓
Promote when validated
```

---

# 65. VERSIONED LEARNING

```text
R-0042 v1
R-0042 v2
R-0042 v3
```

Regression:

```text
v3 fails repeatedly
       ↓
Rollback to v2
```

---

# 66. SHADOW LEARNING

New learned strategies may initially run as predictions only.

```text
Production: R12
Candidate: R37

Would R37 have succeeded?

Observe over multiple cases.
```

Only then promote.

---

# 67. PROGRESSIVE AUTONOMY LEVELS

```text
LEVEL 0
Observe

LEVEL 1
Suggest

LEVEL 2
Auto-fill verified fields

LEVEL 3
AutoPilot known workflows

LEVEL 4
Adaptive AutoPilot

LEVEL 5
Trusted personal application agent
```

Autonomy increases from demonstrated reliability.

---

# 68. CONFIDENCE ENGINE

Every classification/action receives:

```text
base_confidence
historical_success
site_confidence
semantic_confidence
evidence_quality
risk_class
```

Suggested policy:

```text
95–100
Automatic

80–94
Automatic with prominent preview

60–79
Review required

0–59
Manual resolution
```

Sensitive categories can require stricter thresholds.

---

# 69. ACCOUNT ORCHESTRATOR

Authentication detection is generic.

Recognize concepts:

```text
Sign in
Register
Create account
New candidate
Forgot password
Verify account
```

Classify:

```text
AUTH_LOGIN
AUTH_CREATE
AUTH_RECOVERY
AUTH_VERIFY
```

---

# 70. ACCOUNT REGISTRY

Store:

```text
account_id
employer
domain
portal_url
email
exists
created_at
last_used
application_ids[]
```

Do not store ordinary plaintext passwords in the application ledger.

---

# 71. ACCOUNT CREATION

```text
Account required
      ↓
Existing account?
  YES       NO
   ↓         ↓
Login     Create
             ↓
       Fill identity
             ↓
       Generate password
             ↓
       Browser/credential manager
```

---

# 72. EMAIL/MFA VERIFICATION

V1:

```text
Verification required
       ↓
AutoPilot paused
       ↓
User completes email/MFA verification
       ↓
Extension rescans
       ↓
Continue
```

Mailbox automation remains optional.

---

# 73. LOCAL COMPANION

The Native Companion is the heavier local processing layer.

Edge Native Messaging allows an extension to exchange messages with an authorized native host using standard input/output and an allowed-extension manifest.

Recommended:

```text
Python 3
FastAPI where useful
SQLite
Pydantic
Local file system
Optional Ollama
Vector retrieval
Cryptography utilities
```

---

# 74. NATIVE COMPANION RESPONSIBILITIES

```text
Authoritative SQLite
Resume storage
Resume parsing
Evidence Graph
Vector index
AI gateway
API key handling
Model routing
Application history
Learning database
Diagnostics
Backups
Analytics exports
n8n bridge
```

---

# 75. STORAGE STRATEGY

## Early V1

```text
IndexedDB
→ structured browser state

OPFS / browser storage
→ temporary large blobs/cache

Encrypted exports
→ backup
```

IndexedDB is available in extension service workers.

## Mature architecture

```text
SQLite in Native Companion
→ authoritative persistence

IndexedDB
→ browser cache + active application state
```

---

# 76. DATABASE MODEL

Core tables:

```text
profiles
facts
evidence_nodes
evidence_edges
resumes
resume_versions
jobs
applications
application_pages
questions
answers
accounts
sites
components
recipes
interaction_attempts
learning_events
outcomes
portfolio_tokens
portfolio_events
experiments
experiment_variants
experiment_assignments
application_events
checkpoints
settings
api_usage
```

---

# 77. APPLICATION TABLE

Suggested fields:

```text
application_id
job_id
company
role
requisition_id
job_url
application_url
submitted_at
status
resume_id
account_id
job_signal_score
created_at
updated_at
```

---

# 78. APPLICATION EVENT MODEL

Do not continually add event-specific columns.

Use:

```text
application_events
```

with:

```text
event_id
application_id
event_type
timestamp
source
metadata_json
```

Possible events:

```text
APPLICATION_STARTED
ACCOUNT_CREATED
APPLICATION_PREPARED
APPLICATION_SUBMITTED
APPLICATION_CONFIRMED
PORTFOLIO_VISIT
ASSESSMENT_RECEIVED
INTERVIEW_RECEIVED
REJECTION_RECEIVED
FOLLOWUP_SENT
```

---

# 79. APPLICATION LEDGER

Each application retains:

```text
Company
Role
Job URL
Application URL
Requisition
Date
Resume
Resume hash
Account
Answers
Generated responses
Authorization responses
Salary response
Warnings
Manual interventions
Application ID
Confirmation
Outcome
Portfolio events
Learning generated
```

---

# 80. DUPLICATE DETECTION

Compare:

```text
company
role
requisition
job URL
application URL
historical applications
```

Warn before duplicating.

---

# 81. APPLICATION CHECKPOINTING

After meaningful transitions:

```text
Current state
Current page
Completed questions
Resume
Account state
Pending questions
Navigation history
```

is persisted.

Crash recovery:

```text
Previous Application Found

Progress: 73%

[Resume]
```

---

# 82. APPLICATION REPLAY

Maintain a sanitized trace:

```text
00:00 Application detected
00:01 57 controls found
00:02 54 classified
00:05 Resume selected
00:09 Account flow detected
00:18 Personal page complete
00:25 Upload complete
00:26 Upload verified
00:34 Conditional question appeared
...
```

Uses:

```text
Learning
Diagnostics
Recovery
Auditing
Performance analysis
```

---

# 83. ARTIFACT ATTRIBUTION ENGINE

Every application may receive an opaque portfolio attribution token.

Example:

```text
https://munshi.systems/?ma=7KQ2N9X4
```

Internally:

```text
7KQ2N9X4
      ↓
APP-002184
```

The public URL does not expose the résumé variant or requisition details.

---

# 84. PORTFOLIO TOKEN MODEL

```text
token
application_id
created_at
active
expires_at
```

---

# 85. PORTFOLIO EVENT TRACKING

Possible first-party events:

```text
PORTFOLIO_VISIT
RETURN_VISIT
PROJECT_OPENED
RESUME_VIEWED
RESUME_DOWNLOADED
CONTACT_CLICKED
LINKEDIN_CLICKED
```

Avoid labeling an anonymous visit:

```text
RECRUITER_VIEWED
```

unless identity is independently known.

Preferred:

```text
ATTRIBUTED_PORTFOLIO_VISIT
```

---

# 86. PORTFOLIO FEEDBACK LOOP

```text
Application submitted
        ↓
Unique token used
        ↓
Portfolio opened
        ↓
First-party event
        ↓
n8n
        ↓
Application Ledger
        ↓
Analytics
```

---

# 87. EXPERIMENT ENGINE

MUNSHI Apply can support structured job-search experiments.

Potential experiment targets:

```text
Resume layout
Resume emphasis
Written-response style
Portfolio landing strategy
Role-specific positioning
```

---

# 88. EXPERIMENT STRUCTURE

```text
experiment_id
hypothesis
population_definition
variant_a
variant_b
assignment_strategy
primary_metric
secondary_metrics
start_date
end_date
status
```

---

# 89. EXAMPLE RESUME EXPERIMENT

```text
Hypothesis:
Technical-first People Analytics resume
is associated with higher interview conversion.

Population:
People Analytics roles

Variant A:
Technical-first

Variant B:
Business-impact-first

Primary Metric:
Interview conversion

Secondary:
Assessment conversion
Portfolio attributed visit
Time to response
```

---

# 90. EXPERIMENT ASSIGNMENT

Prefer controlled assignment rather than choosing a résumé based on expectation and then calling the result an experiment.

Where practical:

```text
Eligible application
      ↓
Experiment active?
      ↓
Random assignment
      ↓
Variant
```

---

# 91. ANALYTICS INTERPRETATION

Application experiments are affected by:

```text
Company selectivity
Role seniority
Industry
Location
Timing
Applicant volume
Job fit
Economic conditions
```

Therefore analytics should distinguish:

```text
Association
```

from:

```text
Causation
```

---

# 92. OUTCOME TRACKING

Canonical outcomes:

```text
Applied
Assessment
Recruiter Screen
Interview
Final Interview
Rejected
Offer
Withdrawn
Ghosted / No Response
```

---

# 93. RESUME PERFORMANCE

Examples:

```text
Resume Version
Applications
Assessment Rate
Interview Rate
Offer Rate
Portfolio Visit Rate
Median Response Time
```

---

# 94. WRITTEN RESPONSE STRATEGIES

Define strategy IDs:

```text
WR-01 Evidence-first concise
WR-02 Story-driven
WR-03 Business-impact
WR-04 Analytical/technical
```

Store the strategy used for each generated response.

---

# 95. ANALYTICS EXPORT

Provide:

```text
Applications.csv
Application_Events.csv
Resume_Performance.csv
Experiments.csv
Portfolio_Attribution.csv
Job_Signals.csv
```

and:

```text
Complete Analytics Bundle
```

for Tableau/Power BI analysis.

---

# 96. N8N EVENT BRIDGE

MUNSHI Apply should emit internal events.

Architecture:

```text
MUNSHI APPLY
      ↓
LOCAL EVENT ROUTER
      │
      ├── Ledger
      ├── Learning
      ├── Analytics
      └── n8n
```

---

# 97. N8N EVENTS

Examples:

```text
APPLICATION_PREPARED
APPLICATION_SUBMITTED
APPLICATION_CONFIRMED
PORTFOLIO_VISIT_OBSERVED
INTERVIEW_RECEIVED
FOLLOWUP_DUE
STATUS_CHANGED
```

---

# 98. POSSIBLE N8N ACTIONS

```text
Update tracker
Send Telegram confirmation
Schedule follow-up
Prepare recruiter follow-up
Update dashboard
Create interview-prep task
Synchronize broader job pipeline
```

---

# 99. SECURITY PRINCIPLES

Core rules:

```text
Local-first
Least privilege
No plaintext secrets in extension code
Separate credentials from application data
Explicit sensitive fact confirmation
Audit sensitive changes
Encrypted backups
Redacted diagnostics
```

---

# 100. API KEY HANDLING

Cloud API credentials must remain outside publicly accessible browser JavaScript.

Preferred:

```text
Edge Extension
      ↓
Native Companion
      ↓
Provider API
```

The browser sends a model request to the companion.

The companion owns provider credentials.

---

# 101. PERMISSION STRATEGY

Potential permissions include:

```text
activeTab
scripting
storage
tabs
sidePanel
nativeMessaging
downloads
debugger
```

Microsoft documents `nativeMessaging` and `sidePanel` among extension permissions, while `chrome.scripting` provides runtime script injection.

Each permission must be separately justified.

---

# 102. DEBUGGER/CDP POLICY

Browser-level instrumentation can support difficult debugging and interaction scenarios.

It must be treated as:

```text
advanced compatibility layer
```

rather than:

```text
security-control bypass layer
```

---

# 103. DIAGNOSTIC REDACTION

Never include in diagnostic packages:

```text
Passwords
API keys
Authentication tokens
Cookies
Session secrets
Sensitive demographic answers unless essential
```

---

# 104. OBSERVABILITY DASHBOARD

Developer view:

```text
SYSTEM
Extension healthy
Native host connected
Database healthy
AI provider healthy

CURRENT PAGE
Controls: 67
Classified: 63
Review: 4

AUTOMATION
Successful: 51
Recovered: 7
Manual: 2

LEARNING
Patterns reinforced: 12
New patterns: 3
Failures learned: 2
```

---

# 105. STRUCTURED LOGGING

Every event:

```text
timestamp
level
component
application_id
page_id
event_type
message
metadata
```

Log levels:

```text
TRACE
DEBUG
INFO
WARN
ERROR
CRITICAL
```

---

# 106. DIAGNOSTIC BUNDLE

One action generates:

```text
System versions
Extension version
Page fingerprint
Question classifications
Interaction attempts
Validation failures
Recipe versions
Relevant sanitized logs
```

---

# 107. BACKUP SYSTEM

Back up:

```text
Profile
Evidence
Resume metadata
Applications
Learning
Experiments
Settings
```

Resume files may be backed up separately.

---

# 108. BACKUP VERSIONING

Example:

```text
backups/
├── 2026-08-13/
│   ├── database.sqlite
│   ├── manifest.json
│   └── checksums.sha256
```

---

# 109. DATABASE MIGRATIONS

Every schema change requires a numbered migration.

```text
001_initial.sql
002_evidence_graph.sql
003_learning.sql
004_experiments.sql
```

No direct ad hoc production schema editing.

---

# 110. RECIPE MIGRATIONS

Learned recipes should also have explicit versions.

Breaking recipe schema changes require conversion or migration.

---

# 111. REPOSITORY ARCHITECTURE

Recommended monorepo:

```text
munshi-apply/
│
├── apps/
│   ├── extension/
│   └── native-host/
│
├── packages/
│   ├── contracts/
│   ├── semantic-engine/
│   ├── application-model/
│   ├── evidence/
│   ├── learning/
│   ├── analytics/
│   └── shared/
│
├── tests/
│   ├── fixtures/
│   ├── synthetic-sites/
│   ├── integration/
│   └── e2e/
│
├── scripts/
│
├── migrations/
│
├── docs/
│
├── reports/
│
└── backups/
```

---

# 112. CORE CONTRACT PACKAGE

Shared schemas for:

```text
Application
Question
Answer
Control
ProfileFact
EvidenceNode
Resume
InteractionRecipe
LearningEvent
ApplicationEvent
Experiment
```

Both TypeScript and Python sides must agree on these contracts.

---

# 113. EVENT BUS

Canonical events:

```text
PAGE_DETECTED
APPLICATION_DETECTED
FIELD_DISCOVERED
QUESTION_CLASSIFIED
ANSWER_RESOLVED
ANSWER_REVIEW_REQUIRED
RESUME_SELECTED
RESUME_UPLOADED
UPLOAD_VERIFIED
ACCOUNT_REQUIRED
ACCOUNT_CREATED
APPLICATION_STATE_CHANGED
CHECKPOINT_REQUIRED
INTERACTION_FAILED
RECOVERY_SUCCEEDED
APPLICATION_READY
APPLICATION_SUBMITTED
APPLICATION_COMPLETED
LEARNING_EVENT_CREATED
```

---

# 114. TESTING STRATEGY

Testing layers:

```text
Unit
Component
Integration
Synthetic application
Browser E2E
Regression
Learning regression
Database migration
Security
Performance
```

---

# 115. SYNTHETIC APPLICATION LAB

Build local test applications reproducing:

```text
Plain HTML
React
Vue
Angular
Shadow DOM
Frames
Dynamic questions
Conditional fields
Custom selects
Date pickers
Resume upload
Account creation
EEO forms
Multi-page flows
Validation
SPA navigation
```

Universal behavior should be validated against patterns, not vendor names.

---

# 116. ADVERSARIAL UI TESTS

Synthetic tests should intentionally include:

```text
Random IDs
Missing labels
Broken ARIA
Delayed rendering
Multiple matching labels
Conditional fields
Duplicate questions
Shadow components
Nested frames
Dynamic validation
Resume parser
Disabled-until-valid buttons
```

---

# 117. LEARNING REGRESSION TESTS

Before promoting a learned recipe:

```text
Known success fixtures
Known failure fixtures
New candidate fixtures
```

must be checked.

---

# 118. PERFORMANCE TARGETS

Initial targets:

```text
Page scan:
< 1 second for normal application page

Incremental rescan:
< 250 ms where practical

Basic field resolution:
near instantaneous

Pre-flight:
few seconds excluding AI

Autofill verification:
per-control confirmation

UI:
never block browsing thread
```

Exact thresholds should be benchmarked rather than treated as promises.

---

# 119. PHASE 0 — ENGINEERING FOUNDATION

Build:

```text
Monorepo
Manifest V3 extension
Side panel
Service worker
Messaging
Contracts
Logging
Tests
CI
Backup framework
```

Deliverable:

> Extension loads and understands its own runtime reliably.

---

# 120. PHASE 1 — PROFILE & RESUME FOUNDATION

Build:

```text
Master Profile
Protected facts
Master Resume
Tailored Resume Vault
Resume versioning
Basic IndexedDB
```

Deliverable:

> User can configure all recurring application data once.

---

# 121. PHASE 2 — UNIVERSAL PAGE UNDERSTANDING

Build:

```text
DOM scanner
ARIA scanner
Frame sensors
Control discovery
Question extraction
Semantic classification
Dynamic observer
```

Deliverable:

> Unknown applications can be mapped into internal application objects.

---

# 122. PHASE 3 — EVIDENCE & RETRIEVAL

Build:

```text
Evidence Graph
Resume parser
Semantic retrieval
Context builder
```

Deliverable:

> Questions can retrieve only relevant evidence.

---

# 123. PHASE 4 — PRE-FLIGHT SYSTEM

Build:

```text
Application Planner
Answer Resolver
Confidence Engine
Sensitive Answer Engine
Resume selector
Question review
Pre-flight UI
```

Deliverable:

> Complete application is previewed before autofill.

---

# 124. PHASE 5 — UNIVERSAL AUTOFILL

Build:

```text
Text
Textarea
Radio
Checkbox
Select
Custom select
Dates
Autocomplete
Uploads
Verification
```

Deliverable:

> Most standard applications can be filled reliably.

---

# 125. PHASE 6 — MULTI-PAGE AUTOPILOT

Build:

```text
Application state machine
Navigation classification
Dynamic rescanning
Conditional questions
Checkpointing
Crash recovery
```

Deliverable:

> MUNSHI Apply progresses through complete application workflows.

---

# 126. PHASE 7 — ACCOUNT ORCHESTRATION

Build:

```text
Account detection
Account registry
Registration assistance
Credential-manager handoff
Verification pause/resume
```

---

# 127. PHASE 8 — PROVIDER-AGNOSTIC INTELLIGENCE

Build:

```text
AI Provider interface
Model Router
API Budget Engine
Cheap classifier
Strong-model escalation
Ollama fallback
```

---

# 128. PHASE 9 — JOB-SPECIFIC RESPONSES

Build:

```text
Why company
Why role
Experience answers
Truth checking
Evidence validation
Tone learning
```

---

# 129. PHASE 10 — INTERACTION ESCALATION

Build:

```text
Component fingerprints
Recipe library
Shadow DOM handling
Advanced frames
Browser instrumentation
Visual fallback
```

---

# 130. PHASE 11 — PROGRESSIVE LEARNING

Build:

```text
Success memory
Failure memory
Question learning
Site memory
Global pattern memory
User correction learning
Confidence adaptation
```

---

# 131. PHASE 12 — TEACH-MUNSHI

Build:

```text
Before/after capture
User demonstration
Candidate recipe generation
Testing
Versioning
Promotion
Rollback
```

---

# 132. PHASE 13 — JOB SIGNAL INTELLIGENCE

Build:

```text
Job signal ontology
Deterministic extractors
Classifier
Evidence-backed signals
Side-panel presentation
```

---

# 133. PHASE 14 — ARTIFACT ATTRIBUTION

Build:

```text
Opaque tokens
Portfolio event receiver
Application mapping
n8n bridge
Attribution analytics
```

---

# 134. PHASE 15 — EXPERIMENT & ANALYTICS ENGINE

Build:

```text
Experiment definitions
Variant assignment
Resume strategy tracking
Response strategy tracking
Outcome metrics
CSV exports
Tableau-ready datasets
```

---

# 135. PHASE 16 — N8N ORCHESTRATION

Build:

```text
Event router
Webhook interface
Application events
Follow-up events
Portfolio events
Outcome events
```

---

# 136. PHASE 17 — HARDENING

Perform:

```text
Security review
Permission review
Data migration testing
Learning regression testing
Crash recovery
Backup restore
Performance profiling
Accessibility
UI polish
```

---

# 137. V1 RELEASE DEFINITION

V1 should already contain:

```text
Master Profile
Protected facts
Master Resume
Tailored resume per application
Universal page scanning
Question classification
Pre-flight
Sensitive-answer handling
Basic generated answers
Generic autofill
Upload verification
Dynamic rescanning
Multi-step navigation
Account assistance
Security checkpoint pause
Application ledger
Basic learning
```

---

# 138. V2 RELEASE DEFINITION

Add:

```text
Evidence retrieval
Model routing
Advanced custom controls
Component fingerprints
Reusable interaction recipes
Failure memory
Site memory
Job Signal Intelligence
```

---

# 139. V3 RELEASE DEFINITION

Add:

```text
Native Companion maturity
Advanced browser instrumentation
Teach-MUNSHI
Artifact Attribution
Experiment Engine
n8n integration
Outcome learning
Progressive autonomy
```

---

# 140. SYSTEM SUCCESS METRICS

Track:

```text
Field classification accuracy
Autofill success
Verification success
Recovery success
Manual interventions/application
Unknown questions/application
Recipe reuse rate
Failure repetition rate
Application completion rate
Resume-upload accuracy
Generated-answer acceptance rate
Average AI cost/application
Average preparation time
Crash recovery success
```

---

# 141. LEARNING SUCCESS METRICS

```text
Question mappings reinforced
New concepts learned
Component recipes learned
Cross-site recipe reuse
User correction frequency
Manual intervention reduction
Known failure recurrence
Confidence calibration
```

The goal is not merely more stored knowledge.

The goal is:

> **measurably less manual effort with maintained or improved accuracy.**

---

# 142. NON-NEGOTIABLE RULES

MUNSHI Apply must never:

```text
Invent employment
Invent education
Invent skills
Invent certifications
Invent years of experience
Invent work authorization
Invent sponsorship answers
Infer protected characteristics
Modify verified facts silently
Silently substitute another resume
Submit a different document than previewed
Treat a visible value as proof the website accepted it
Lose application state after interruption
Repeatedly execute a known-bad interaction
Declare unknown platforms unsupported
Claim anonymous website traffic proves recruiter identity
Claim ordinary observational analytics prove causation
Store API keys directly in browser code
```

---

# 143. HUMAN CHECKPOINTS

Manual handoff remains appropriate for:

```text
CAPTCHA
MFA
OTP
Identity verification
Unknown consequential legal statements
Unknown personal facts
Material low-confidence knockout questions
Final submission when configured for approval
```

The system preserves progress and continues afterward.

---

# 144. FINAL OPERATING LOOP

The entire project ultimately operates as:

```text
                         JOB APPLICATION
                               │
                               ▼
                          DISCOVER
                               │
                               ▼
                         UNDERSTAND
                               │
                               ▼
                           RETRIEVE
                               │
                               ▼
                            RESOLVE
                               │
                               ▼
                             PLAN
                               │
                               ▼
                          PRE-FLIGHT
                               │
                               ▼
                         USER APPROVAL
                               │
                               ▼
                          AUTOPILOT
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
                  ACT                  VERIFY
                    │                     │
                    └──────────┬──────────┘
                               │
                           FAILURE?
                          /        \
                        NO          YES
                        │            │
                        │            ▼
                        │        RECOVER
                        │            │
                        └──────┬─────┘
                               ▼
                            CONTINUE
                               │
                               ▼
                         FINAL REVIEW
                               │
                               ▼
                           COMPLETE
                               │
               ┌───────────────┼────────────────┐
               ▼               ▼                ▼
             LEDGER          ANALYTICS         EVENTS
               │               │                │
               │               │                ▼
               │               │               n8n
               │               │
               └───────────────┼────────────────┐
                               ▼                │
                             LEARN              │
                               │                │
               ┌───────────────┼────────────┐   │
               ▼               ▼            ▼   │
            SUCCESS         FAILURE      CORRECTION
               │               │            │
               └───────────────┼────────────┘
                               ▼
                       VERSIONED MEMORY
                               │
                               ▼
                         NEXT APPLICATION
                               │
                               ▼
                             BETTER
```

---

# 145. FINAL ARCHITECTURAL PRINCIPLES

**Understand before acting.**

**Evidence before generation.**

**Meaning before selectors.**

**Universal behavior before platform-specific optimization.**

**Preview before automation.**

**Verify after every meaningful action.**

**State-driven interaction before arbitrary timing.**

**Recover before asking the user.**

**Ask rather than invent.**

**Remember successes.**

**Remember failures.**

**Learn from corrections.**

**Transfer reusable knowledge across websites.**

**Keep protected personal facts under user control.**

**Keep security checkpoints human-controlled.**

**Use deterministic logic before spending AI tokens.**

**Use retrieval before large-model context.**

**Keep AI providers replaceable.**

**Keep ATS vendors irrelevant to core compatibility.**

**Keep analytics statistically honest.**

**Keep portfolio attribution factual rather than speculative.**

**Keep automation recoverable and reversible.**

**Make every application improve the next one.**

---

# FINAL PROJECT IDENTITY

**Product:** MUNSHI Apply
**Category:** Universal Adaptive Job Application Agent
**Core Engine:** Universal Application Intelligence Engine
**Automation Layer:** Adaptive AutoPilot
**Knowledge Layer:** MUNSHI Intelligence Core
**Learning Layer:** Progressive Learning Engine
**Browser Interface:** MUNSHI Apply Side Panel
**Persistence Layer:** MUNSHI Application Vault
**Analytics Layer:** Experiment & Outcome Intelligence
**External Workflow Layer:** n8n Event Bridge

The final target is not an extension that knows how to fill particular websites.

The final target is a **personal application intelligence system capable of encountering unfamiliar application environments, understanding them, preparing truthful evidence-grounded responses, completing legitimate repetitive work, recovering from unfamiliar interfaces, retaining what it learns, and using that experience to make every subsequent application faster, more accurate, and more autonomous.**
