# Verifiable Medical MCQ Generator (V1 Prototype)

This document outlines the project's Goal, Scope, Architecture, and Technical Requirements for development.

## 1. Project Overview (Section A)

| Field | Description |
| :--- | :--- |
| **Project Name** | Verifiable Medical MCQ Generator (V1) |
| **Primary Goal** | Generate high-quality, clinical-style Multiple Choice Questions (MCQs) for medical education. |
| **Critical Innovation** | Ensure the **correct answer is 100% traceable (verifiable)** to a specific source (Pubmed/PDF), thereby mitigating LLM hallucination. |
| **Target Output** | A Clinical Stem/Scenario, one Question, five Options (one correct), and Provenance Tag for the correct answer. |
| **Success Criteria** | Successful generation of ≤20 demo MCQs where the correct answer is factually accurate and linked to the source ID. |

---

## 2. Architecture and Agentic Pipeline (Section B)

The system will use the **Google Ask Agentic Framework** for orchestration and a lower-cost LLM (Gemini 2.5 or GPT-4o Mini) for generation and extraction tasks.

### 2.1. Data Flow and Ingestion

* **Source Input:** User provides either a **Pubmed ID** or uploads a **PDF file**.
* **Agent: Source Ingestion Agent**
    * Retrieves abstract text (Pubmed) or parses text/metadata (PDF).
    * Stores the unique identifier: **Pubmed ID** or **File Name**.

### 2.2. Knowledge Base (KB) Management

* **Agent: Fact Extraction Agent**
    * Uses an LLM to generate candidate **Subject-Action-Object triplets** from the ingested source text.
* **Agent: KB Management Agent (Triplets)**
    * Compares new triplets against the **Approved Triplet KB**.
    * If a triplet is new, it is presented to the user for **Approval/Rejection only**. (Refer to `objectives_extra` for editing rules.)
* **Storage:** Approved triplets are added to the persistent **Approved Triplet KB** (Simple DB structure: `Subject`, `Action`, `Object`, `Source_ID`).

### 2.3. MCQ Generation and Validation (Human-in-the-Loop)

#### Agent: MCQ Generation Agent
1.  **Generates Question:** Uses the approved source text and approved triplets to construct the question and stem based on the user's selected mode (**Recall** or **Reasoning**).
2.  **Generates Correct Answer:** Uses the approved triplet directly as the basis for the correct answer.
3.  **Generates Distractors:** Uses knowledge for approximation/negation based on the subject/topic (distractors are **not verified facts**). (See `objectives_extra` for distractor logic.)
4.  **Visual Kernel Draft (VKD):** Also outputs a **Visual Kernel Draft (VKD)** in JSON format, constrained to concepts suitable for reliable generation (imaging, histopathology, diagrams). The VKD includes a reference to the question/MCQ ID.
5.  **Provenance Tag:** Ensures the final MCQ links the correct answer back to the **Source ID** (Pubmed ID or File Name).

#### New Agent: Visual Refiner Agent
* **Input:** Accepts the **VKD** and the corresponding **C-TRIPLET** (Correct Answer Triplet).
* **Refinement:** Refines the VKD into an **Optimized Visual Prompt (OVP)** for image generation.
* **Verification:** Generates a **Visual Triplet** (Subject-Action-Object) corresponding to the OVP, ensuring the visual concept is factually aligned with the approved KB. (See `objectives_extra` for details.)

#### HITL Validation Workflow (Updated)
The generated MCQ, OVP, and Visual Triplet are presented to the user for review:

* **Approve:** MCQ is stored, and its associated triplets are **automatically added** to the Approved Triplet KB.
* **Amend/Edit:** The user can edit the final MCQ text directly. **The user also reviews and can edit the Optimized Visual Prompt (OVP) and the Visual Triplet** during this step. If amended, the user must re-Approve for storage.
* **Re-prompt:** The user can request the generation agent to try again.

#### New Service: Image Generation Service
* The final, approved **Optimized Visual Prompt (OVP)** is used by an external service for image generation **only upon explicit user request** (via a separate UI button/icon).
* The resulting **Image URL** is stored.

#### Storage Update
The Approved MCQ Repository structure is updated to store:
* MCQ text
* Correct Triplet
* Source ID
* **Optimized Visual Prompt (OVP)**
* **Image URL** (if generated)

---

### 2.4 Selected Framework Features (Section B.4)

To operationalize the agentic pipeline, we commit to the following Google Ask Framework features (see `framework/agent_examples.txt` for implementation patterns):

1. **SequentialAgent Orchestration** — wraps Source Ingestion → Fact Extraction → KB Management → MCQ Generation → Visual Refiner → HITL, guaranteeing deterministic hand-off of source identifiers and approved triplets.
2. **LoopAgent QA Wrapper** — encloses the MCQ Generation Agent with an internal critic loop so drafts iterate until the critic returns an “APPROVED” signal or max iterations are reached before presenting to the human reviewer.
3. **Custom Tooling Layer** — schema validator, triplet dedupe checker, KB writer, and provenance enricher are exposed as custom function tools callable by agents to keep deterministic logic outside the LLM prompts.
4. **Session Memory Service** — `InMemorySessionService` maintains per-user context (selected model, ingestion source list, approval state) across UI interactions so agents can resume work without re-uploading artifacts.

These features satisfy the “select 4 features from framework.txt” requirement while directly supporting the MCQ pipeline’s reliability goals.

---

## 3. Technical Requirements and Constraints (Section C)

| Component | Specification |
| :--- | :--- |
| **Framework** | Google Ask Framework |
| **Front-End** | Chainlit UI (One section for search/upload, one for KB search/MCQ generation) |
| **Persistent Storage** | Required for: 1) Approved Triplet KB (Simple DB), 2) Approved MCQ Repository. |
| **LLM Choice** | Low-cost model, allowing for user selection between **Gemini 2.5** and **GPT-4o Mini**. |
| **Identifiers** | **Pubmed ID** (for searches) or **File Name** (for PDFs). Must persist with the final stored MCQ and its triplets. |
| **Key Constraint** | User can edit triplets only within the interactive approval editor defined in `objectives_extra`; once a triplet is stored in the Approved Triplet KB, it is read-only. |