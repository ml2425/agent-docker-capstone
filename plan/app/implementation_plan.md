# Implementation Plan: Verifiable Medical MCQ Generator

## Purpose
This document provides a complete implementation roadmap for building the Verifiable Medical MCQ Generator from scratch. It consolidates all planning decisions, identifies gaps, and provides step-by-step implementation guidance.

---

## Project Overview

**Goal:** Generate high-quality, clinical-style MCQs where the correct answer is 100% traceable to a specific source (PubMed/PDF), mitigating LLM hallucination.

**Key Innovation:** Provenance verification through context sentences (2-4 verbatim sentences from source) that prove triplets came from source material, not LLM imagination.

**Target Output:** Clinical stem, question, 5 options (1 correct), provenance tag, optimized visual prompt, and optional image.

---

## Implementation

### ✅ PAST ATTEMP -- we are now starting from scratch.

1. **MCQ Generation Pipeline** (`app/agents/pipeline.py`)
   - SequentialAgent orchestration
   - MCQGenerationAgent with visual_kernel_draft
   - CritiqueAgent + RefinerAgent with LoopAgent (max 3 iterations)
   - VisualRefinerAgent with schema validation
   - SourceIngestionAgent (handles PubMed ID fetch and file registration)

2. **MCQ Review UI** (`app/ui/chainlit_app.py`)
   - MCQ display with provenance, triplet, visual prompt
   - HITL actions: Edit, Regenerate, Reject, Approve
   - Status tracking (Pending/Approved)
   - Image generation integration

3. **Database Models** (`app/db/models.py`)
   - Triplet model (subject, action, object, relation, source_id, source_title)
   - MCQRecord model (stem, options, correct_option, source_id, triplet_id, visual_prompt, image_url, status)

4. **Source Ingestion** (`app/services/ingestion_service.py`)
   - PubMed fetch by ID (uses Entrez API)
   - PDF upload registration (uses filename as source_id)
   - ⚠️ PDF text extraction missing (assumes text already decoded)

5. **KB Service** (`app/services/kb_service.py`)
   - Triplet storage and retrieval
   - Upsert functionality

---

## Critical Gaps & Issues

### **GAP 1: PubMed Keyword Search - NOT IMPLEMENTED**

**Current State:**
- `app/ui/chainlit_app.py` line 159: Asks user to enter PubMed ID directly
- Users must know PubMed ID in advance (bad UX)

**Required:**
- User enters keywords (e.g., "diabetes treatment")
- System searches PubMed API and returns list of articles
- User selects article (sees title, authors, year - NOT PubMed ID)
- System uses PubMed ID internally as metadata

**Missing Components:**
- `app/services/pubmed_service.py`: `search_pubmed(keywords: str)` function
- `app/tools/pubmed_tools.py`: Function tool wrapper
- UI: Search input box + "Search PubMed" button
- Article selection UI (clickable cards/buttons)

---

### **GAP 2: Context Sentences (Provenance Proof) - NOT IMPLEMENTED**

**Current State:**
- `app/agents/pipeline.py` line 40-55: FactExtractionAgent does NOT return context sentences
- Agent output: `subject, action, object, relation, source_id, source_title` only
- No `context_sentences` field in database or services

**Required:**
- FactExtractionAgent must extract 2-4 verbatim sentences from source text
- These sentences prove triplet came from source, not hallucinated
- Store context_sentences permanently with triplet

**Missing Components:**
- Update FactExtractionAgent instruction to require context sentences
- Update agent output JSON to include `context_sentences` array
- Add `context_sentences` field to Triplet model
- Update TripletDTO and upsert_triplet to handle context_sentences
- Add validation that context sentences appear in source text

**Impact:** **CRITICAL** - Cannot verify provenance without this.

---

### **GAP 3: Triplet Review UI - NOT IMPLEMENTED**

**Current State:**
- `app/agents/pipeline.py` line 57-66: KBManagementAgent directly upserts triplets to KB
- No human approval step exists
- No triplet review UI

**Required:**
- After extraction, display triplets with context sentences
- User reviews each triplet and Accepts/Rejects
- Only accepted triplets stored in KB

**Missing Components:**
- New UI page/section for triplet review
- Display: subject, action, object, relation, context_sentences, schema validation status
- Accept/Reject buttons per triplet
- Route to review UI after extraction
- Store only accepted triplets

**Impact:** No quality control - triplets go directly to KB.

---

### **GAP 4: Database Schema - Missing Provenance Fields**

**Current State:**
- Triplet model missing: `context_sentences`, `article_authors`, `publication_year`

**Required:**
- Add `context_sentences` (Text/JSON field)
- Add `article_authors` (String, optional)
- Add `publication_year` (Integer, optional)

**Missing Components:**
- Database migration or schema update
- Update Triplet model
- Update TripletDTO
- Update all services that create/read triplets

---

### **GAP 5: PDF Text Extraction - NOT IMPLEMENTED**

**Current State:**
- `app/services/ingestion_service.py` line 57-76: Decodes bytes as UTF-8 text
- No PDF parsing library used
- Assumes file is already text

**Required:**
- Extract text from PDF bytes using PDF parsing library
- Handle extraction errors gracefully

**Missing Components:**
- Add PDF library (`pypdf` or `pdfplumber`) to requirements.txt
- Update `register_upload` to detect PDF and extract text
- Error handling for corrupted/unreadable PDFs

---

### **GAP 6: Automatic Triplet Extraction Trigger - NOT IMPLEMENTED**

**Current State:**
- Source intake stores source but doesn't trigger extraction
- Extraction only happens when user clicks "Generate MCQ"
- No automatic extraction after article selection or PDF upload

**Required:**
- After article selection OR PDF upload → automatically extract triplets
- Display extraction results → route to triplet review UI

**Missing Components:**
- Trigger FactExtractionAgent after source ingestion
- Display extraction progress/status
- Route to triplet review UI automatically

**Impact:** Workflow is disconnected.

---

### **GAP 7: Workflow Disconnection**

**Current State:**
- Pipeline expects `source_payload` JSON
- UI stores sources in session but doesn't format for pipeline
- Extraction only triggered during MCQ generation

**Required:**
- Connect: Source ingestion → Automatic extraction → Review UI → KB storage → MCQ generation

**Missing Components:**
- Ensure source_payload format matches pipeline expectations
- Connect ingestion → extraction → review flow
- Separate extraction flow from MCQ generation flow

---

## Complete Workflow (Target State)

```
1. User searches PubMed by keywords OR uploads PDF
   ↓
2. User selects article (PubMed) OR PDF text extracted automatically
   ↓
3. SourceIngestionAgent: Creates source_payload with content
   ↓
4. FactExtractionAgent: Extracts triplets WITH context sentences
   ↓
5. [NEW] Triplet Review UI: User reviews each triplet with context sentences
   ↓
6. [NEW] User Accepts/Rejects triplets (only accepted stored)
   ↓
7. KBManagementAgent: Stores ONLY accepted triplets (or bypass, store from UI)
   ↓
8. MCQGenerationAgent: Creates MCQ from approved triplets
   ↓
9. CritiqueAgent + RefinerAgent (Loop): Refines MCQ
   ↓
10. VisualRefinerAgent: Optimizes visual prompt
   ↓
11. Returns final_payload with MCQ + visual_payload
```

---

## Implementation Roadmap

### **PHASE 1: Critical for Provenance (Must Have)**

#### **Task 1.1: Add Context Sentences to Database Schema**
**Priority:** CRITICAL

**Files to Modify:**
- `app/db/models.py`: Add `context_sentences` field to Triplet model
- `app/services/kb_service.py`: Update TripletDTO and upsert_triplet

**Implementation:**
1. Add `context_sentences: Mapped[str | None] = mapped_column(Text)` to Triplet model
2. Add `context_sentences: Optional[str]` to TripletDTO
3. Update `upsert_triplet` to accept and store context_sentences
4. Decide format: JSON array (stored as string) or concatenated text
5. Handle database migration (or schema update on init)

**Testing:**
- Verify field is added to database
- Test storing and retrieving context_sentences
- Verify existing triplets still work (null context_sentences)

**Estimated Effort:** 1-2 hours

---

#### **Task 1.2: Update FactExtractionAgent to Return Context Sentences**
**Priority:** CRITICAL

**Files to Modify:**
- `app/agents/pipeline.py`: Update FactExtractionAgent instruction and output format

**Implementation:**
1. Update instruction (line 43-48) to require:
   - "For each triplet, extract 2-4 verbatim sentences from the source text that support the triplet."
   - "These context sentences must appear in the original source text."
   - "Return JSON with fields: subject, action, object, relation, source_id, source_title, context_sentences (array of strings)."
2. Update output_key format expectation
3. Consider adding validation tool to check if context sentences appear in source

**Testing:**
- Verify agent returns context_sentences in output
- Test with various source texts
- Verify context sentences are verbatim or near-verbatim from source

**Estimated Effort:** 2-3 hours

---

#### **Task 1.3: Create Triplet Review UI**
**Priority:** CRITICAL

**Files to Create/Modify:**
- `app/ui/chainlit_app.py`: Add new action callback and UI functions

**Implementation:**
1. Create `render_triplet_review_page()` function
2. Display each triplet with:
   - Subject, Action, Object, Relation
   - Context sentences (formatted nicely, maybe in a quote block)
   - Schema validation status (✅ Valid / ⚠️ Needs Review)
   - Source metadata (title, authors, year if available)
3. Add Accept/Reject buttons per triplet (Chainlit Actions)
4. Store only accepted triplets via `kb_service.upsert_triplet()`
5. Route to review UI after extraction completes
6. Show progress/status during extraction

**UI Design:**
```
Triplet: Metformin → treats → Type 2 Diabetes (TREATS)
✅ Schema Valid

Provenance Evidence (from source):
"Metformin is the first-line treatment for type 2 diabetes mellitus.
It works by reducing hepatic glucose production and improving insulin sensitivity.
Clinical trials have shown significant HbA1c reduction with metformin therapy."

Source: PubMed ID 12345678 | "Metformin in Type 2 Diabetes..." (2023)
Authors: Smith J, et al.

[Accept] [Reject]
```

**Testing:**
- Verify triplets display correctly
- Test Accept/Reject buttons
- Verify only accepted triplets stored
- Test routing from extraction to review

**Estimated Effort:** 3-4 hours

---

### **PHASE 2: User Experience (Should Have)**

#### **Task 2.1: Implement PubMed Keyword Search**
**Priority:** HIGH

**Files to Create:**
- `app/services/pubmed_service.py`: New service with `search_pubmed(keywords: str)` function
- `app/tools/pubmed_tools.py`: Function tool wrapper

**Files to Modify:**
- `requirements.txt`: Add `biopython` dependency
- `app/ui/chainlit_app.py`: Replace PubMed ID input with keyword search UI

**Implementation:**
1. Install `biopython` package
2. Create `PubmedService` class with `search_pubmed(keywords: str)` method
3. Use `biopython.Entrez` to search PubMed:
   - `Entrez.esearch()` to get PubMed IDs
   - `Entrez.efetch()` to get article details
4. Return list of articles with: PubMed ID, title, authors, year, abstract
5. Create function tool `search_pubmed_articles(keywords: str)` for agents
6. Update UI:
   - Replace `cl.AskUserMessage` for PubMed ID with search input box
   - Add "Search PubMed" button
   - Display results as clickable cards/buttons (show title, authors, year - NOT PubMed ID)
   - User clicks article → store article metadata → trigger extraction

**Testing:**
- Test keyword search returns articles
- Verify article metadata is correct
- Test article selection stores data correctly
- Verify PubMed ID is stored internally (not shown to user)

**Estimated Effort:** 4-5 hours

---

#### **Task 2.2: Add PDF Text Extraction**
**Priority:** HIGH

**Files to Modify:**
- `requirements.txt`: Add `pypdf` or `pdfplumber`
- `app/services/ingestion_service.py`: Update `register_upload` to extract PDF text

**Implementation:**
1. Install PDF parsing library (`pypdf` recommended for simplicity)
2. Update `register_upload` method:
   - Detect if file is PDF (check `media_type` or file extension)
   - Use PDF library to extract text from bytes
   - Handle errors (corrupted PDF, password-protected, etc.)
   - Fall back to text decoding if extraction fails
3. Store extracted text in `content` field

**Testing:**
- Test PDF upload extracts text correctly
- Test with various PDF formats
- Test error handling (corrupted PDF, password-protected)
- Verify text extraction quality

**Estimated Effort:** 2-3 hours

---

#### **Task 2.3: Connect Automatic Extraction Trigger**
**Priority:** HIGH

**Files to Modify:**
- `app/ui/chainlit_app.py`: Update source intake to trigger extraction
- `app/ui/pipeline_client.py`: May need to add extraction-only function

**Implementation:**
1. After article selection or PDF upload:
   - Format source as `source_payload` JSON
   - Call FactExtractionAgent (extraction-only, not full MCQ pipeline)
   - Display extraction progress/status
2. When extraction completes:
   - Parse agent output for triplets with context sentences
   - Route to triplet review UI automatically
3. Handle extraction errors gracefully

**Testing:**
- Verify extraction triggers automatically
- Test extraction progress display
- Verify routing to review UI
- Test error handling

**Estimated Effort:** 2-3 hours

---

### **PHASE 3: Enhancement (Nice to Have)**

#### **Task 3.1: Add Article Metadata Fields**
**Priority:** MEDIUM

**Files to Modify:**
- `app/db/models.py`: Add `article_authors` and `publication_year` fields
- `app/services/kb_service.py`: Update TripletDTO
- `app/services/ingestion_service.py`: Extract and store authors/year from PubMed

**Implementation:**
1. Add fields to Triplet model (both optional)
2. Update TripletDTO
3. Extract authors/year from PubMed API responses
4. Store with triplets

**Estimated Effort:** 1-2 hours

---

#### **Task 3.2: Add Context Sentence Validation**
**Priority:** MEDIUM

**Files to Create/Modify:**
- `app/services/validation.py`: Add function to check if context sentences appear in source
- `app/ui/chainlit_app.py`: Display warnings if validation fails

**Implementation:**
1. Create validation function:
   - Check if context sentences (or close matches) appear in source text
   - Use fuzzy matching or substring search
2. Flag triplets where validation fails
3. Display warning in review UI

**Estimated Effort:** 2-3 hours

---

#### **Task 3.3: Improve Error Handling**
**Priority:** MEDIUM

**Files to Modify:**
- All UI functions: Add better error messages
- Pipeline: Add error handling for extraction failures

**Estimated Effort:** 1-2 hours

---

## Dependencies

### New Python Packages
```txt
biopython>=1.81          # For PubMed Entrez API keyword search
pypdf>=3.17.0            # For PDF text extraction (or pdfplumber>=0.10.0)
```

### Update `requirements.txt`
Add the above packages to existing requirements.

---

## Database Schema Changes

### Triplet Model Updates
```python
# Add to app/db/models.py Triplet class:
context_sentences: Mapped[str | None] = mapped_column(Text)  # JSON array or concatenated text
article_authors: Mapped[str | None] = mapped_column(String(512))  # Optional
publication_year: Mapped[int | None] = mapped_column(Integer)  # Optional
```

### Migration Strategy
- Option 1: Handle schema update on database init (check if columns exist, add if missing)
- Option 2: Create migration script using Alembic (if using migrations)
- Option 3: Drop and recreate database (acceptable for prototype)

---

## Testing Strategy

### Unit Tests
- Test context_sentences storage and retrieval
- Test FactExtractionAgent output format
- Test PDF text extraction
- Test PubMed search functionality

### Integration Tests
- Test full workflow: Search → Extract → Review → Store
- Test Accept/Reject functionality
- Test MCQ generation with approved triplets

### Manual Testing Checklist
- [ ] PubMed keyword search returns articles
- [ ] Article selection stores metadata correctly
- [ ] PDF upload extracts text correctly
- [ ] Triplet extraction includes context sentences
- [ ] Context sentences appear in source text (validation)
- [ ] Triplet review UI displays all data correctly
- [ ] Accept/Reject buttons work and only store accepted
- [ ] MCQ generation uses only approved triplets
- [ ] Database schema supports all new fields
- [ ] Error handling works for edge cases

---

## Estimated Total Effort

- **Phase 1 (Critical):** 6-9 hours
- **Phase 2 (UX):** 8-11 hours
- **Phase 3 (Enhancement):** 4-7 hours
- **Total:** 18-27 hours

---

## Implementation Order

1. **Start with Phase 1** - Critical for provenance verification
2. **Complete Task 1.1** - Database schema (foundation)
3. **Complete Task 1.2** - Agent updates (core functionality)
4. **Complete Task 1.3** - Review UI (user interaction)
5. **Test Phase 1** - Verify provenance workflow works
6. **Move to Phase 2** - Improve user experience
7. **Phase 3** - Enhancements (optional)

---

## Key Design Decisions

1. **Context Sentences Format:** Store as JSON string (array of sentences) for flexibility
2. **Triplet Review:** Separate UI page, not inline in MCQ generation
3. **PubMed ID:** Never shown to user, only used internally as metadata
4. **PDF Extraction:** Use `pypdf` for simplicity (lightweight, good enough for text)
5. **Automatic Extraction:** Trigger immediately after source ingestion, before MCQ generation

---

## Notes for Implementation

- Keep existing MCQ generation pipeline intact (it works)
- Add new features incrementally
- Test after each task
- Document any deviations from this plan
- Update this plan if major design changes occur

---

## Success Criteria

Phase 1 is complete when:
- ✅ Users can review triplets with context sentences
- ✅ Only accepted triplets are stored in KB
- ✅ Context sentences prove provenance (can verify against source)
- ✅ MCQ generation uses approved triplets

Phase 2 is complete when:
- ✅ Users can search PubMed by keywords
- ✅ PDF text extraction works
- ✅ Automatic extraction triggers after source ingestion

---

## Next Steps

1. Review this plan
2. Create feature branch (e.g., `feature/provenance-verification`)
3. Start with Phase 1, Task 1.1 (Database schema)
4. Proceed sequentially through tasks
5. Test after each task
6. Merge to main when stable
