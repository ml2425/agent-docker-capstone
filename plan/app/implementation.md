# Implementation Decisions

## Schema & Knowledge Base
- Preload every triplet from `schema_examples.md`, adapting entity text as needed to fit the DB schema.
- Store all triplets (schema or LLM-derived) as `subject`, `action`, `object`, `source_id`, plus typed entity labels when available.
- Source ID is either the PubMed ID or uploaded filename; if none, treat as invalid provenance.
- Preserve LLM history/session context alongside triplets for auditability.
- Include placeholder metadata columns (string + float) for future use.

## UI (Chainlit)
- Use a navigation panel to separate the Source Search/Upload page from the MCQ Review page; prefer dark mode if Chainlit supports it.
- **Search/Upload page:** PubMed ID search bar, file uploader, list of ingested sources (show 5 at a time) with titles and IDs linking into review.
- **MCQ Review page:** Always display the selected triplet, MCQ stem/options, provenance (PubMed ID + article title or filename), and an Optimized Visual Prompt section at the bottom for manual image generation. Highlight provenance to reinforce anti-hallucination goals.

## Validation & Critique Loop
- Hard gate: MCQs lacking a verified source ID or filename are rejected as hallucinated and sent back automatically.
- Critique agent emits structured scores (provenance, schema compliance, distractor plausibility, clarity) plus a weighted `overall_confidence`. Any score < 0.5 or hard failure triggers revision.
- MCQ writer + critic loop allows up to 2 retries; feedback from the critic is fed back into the writer prompts.

## Dev Workflow
- Continue all work on the existing `mock-run` branch until explicitly told otherwise; merges to `main` happen manually at project end.
- Add `pytest` for automated checks; initial test suite focuses on <10 high-value cases (e.g., MCQ provenance validation, schema validator integrity). Additional tests can be added later but should stay lean.
- Choose a lint/format stack (e.g., `ruff` + `black`) once and keep it consistent throughout the project.
- Maintain architectural decisions in two places: `plan/app/implementation.md` (this file) and the architecture log in `/docs` whenever major design changes occur.
- Keep `.env` out of version control; add `.env.example` later if onboarding needs it.

