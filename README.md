# Verifiable Medical MCQ Generator

## Problem
Medical training programs need small, trusted sets of multiple-choice questions where every correct answer links back to a verifiable source, but manual authoring is slow and prone to hallucinations when LLMs are used without guardrails.

## Solution
This app ingests PubMed IDs or PDFs, extracts schema-constrained triplets, and runs a Google ADK agent pipeline that drafts MCQs, enforces provenance, and produces an optimized visual prompt plus optional image. A Chainlit HITL UI lets reviewers iterate, approve, and store only those MCQs that meet the curation rules.

## Pipeline Snapshot
1. **Source Ingestion Agent** – pulls structured text and provenance tags from PubMed or uploads.  
2. **Fact Extraction Agent** – proposes subject-action-object triplets checked against the medical schema.  
3. **KB Management Agent** – deduplicates/queues triplets for human approval before persistence.  
4. **MCQ Generation + Critique Loop** – sequential writer + looped critic refine stems, options, and provenance to ≥50% confidence.  
5. **Visual Refiner + HITL** – produces an Optimized Visual Prompt, optional auto-generated image, and routes everything through the review UI for final approval/storage.
6. **Session Snapshot Store** – auto-saves ingestion sources and pending MCQs so reviewers can resume any session later.

## Agentic Pillars (Evaluation Focus)

| Idea | ADK Feature | Implementation | Impact |
|------|-------------|----------------|--------|
| Deterministic orchestration of the end-to-end flow | `SequentialAgent` pipeline (`app/agents/pipeline.py`) | Wires ingestion → fact extraction → KB → MCQ loop → visual refiner so provenance and triplet IDs survive every hop. | Ensures predictable data handoff and auditable provenance. |
| Quality gating before HITL | `LoopAgent` for MCQ refinement (`MCQRefinementLoop`) | Writer + critic iterate up to 3 times, calling provenance/confidence tools before reviewers see a draft. | Reduces HITL load and enforces the ≥0.5 confidence rule. |
| Tool-augmented reasoning | Custom `FunctionTool`s (schema validator, KB access, provenance guard) in `app/tools/` | Agents call deterministic utilities for triplet validation, storage, and scoring instead of relying on prompt-only behavior. | Keeps schema compliance, dedupe, and provenance checks consistent. |
| Session-aware HITL experience | `InMemorySessionService` + custom session store | The UI and pipeline share short-term state while a SQLite-backed snapshot store lets users resume ingestion/review later without re-uploading sources. | Preserves context across the multi-agent workflow and supports staged reviews. |

## Getting Started
1. Install dependencies: `uv pip install -r requirements.txt` (inside `.venv`).  
2. Set `CHATGPT_API_KEY` and/or `GEMINI_API_KEY` in `.env`.  
3. Launch the UI: `chainlit run chainlit_entry.py` (run from the repo root so the `app` package resolves correctly).

