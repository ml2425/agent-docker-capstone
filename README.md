# Verifiable Medical MCQ Generator

A production-ready system for generating high-quality, verifiable medical multiple-choice questions (MCQs) using Google Agent Development Kit (ADK) with human-in-the-loop validation.

## Why This Project Exists

Clinical educators need reliable MCQs tied to real literature. Traditional workflows either take too long (manual writing) or produce hallucinated content (uncurated LLMs). The goal here is to keep humans in control while the agentic stack does the heavy lifting:

- Every article (PubMed or PDF) is registered with provenance metadata.
- MCQs are only produced when the reviewer explicitly requests them (no hidden processing).
- Each draft carries at least one SNOMED-style triplet plus a full provenance trail.
- Nothing is saved to the knowledge base until a human accepts both the MCQ and its visual prompt.

## Current Architecture (High-Level)

```
Tab 1 (Source Intake)  -> Pending queue (SQLite)
Tab 2 (MCQ Builder)    -> Direct Gemini API calls (bypasses ADK for MCQ generation)
Tab 3 (Knowledge Base) -> Read-only search with pagination, export, and image display
```

Behind the scenes:

1. **LLM Manager** manages provider configurations (Gemini 2.5 Flash Lite default, ChatGPT 4o mini optional).
2. **Direct Gemini API** (`gemini_mcq_service.py`) generates MCQs with triplets and visual prompts (bypasses ADK runner for this workflow).
3. **Gemini Imagen API** (`gemini_image_service.py`) generates images from visual prompts.
4. **Media Service** stores images in `media/` folder with paths in database.
5. **SQLite** stores sources, pending queue, triplets, MCQs, visual prompts, and image paths.
6. **Gradio UI** orchestrates HITL review with in-memory caching for MCQ drafts before persistence.

## What's Implemented Right Now

- **Tab 1 – Source Intake**
  - Search PubMed (top articles displayed with title + year) or upload a PDF.
  - PDF uploads are automatically chunked by section (Abstract, Methods, Results, Discussion, Conclusion). Introduction and References sections are filtered out. Unknown sections are split into paragraph-based chunks (2 paragraphs per chunk).
  - Each PDF chunk is treated as a separate source, similar to PubMed abstracts, enabling focused MCQ generation from specific sections.
  - Selecting entries adds them to the pending queue; no LLM call happens yet.
  - Queue supports pagination (6 per page) and bulk clear for quick clean-up.

- **Tab 2 – MCQ Builder**
  - Dropdown lists every pending article or PDF chunk (title + year + PMID/file ID + section name for PDF chunks).
  - LLM model selector supports both Gemini 2.5 Flash Lite and ChatGPT 4o mini for MCQ generation.
  - "Generate MCQ Draft (takes a few seconds)" calls selected LLM API to return:
    - MCQ (stem/question/5 options/correct index)
    - Optimized visual prompt
    - Supporting SNOMED-style triplets (subject-action-object-relation)
  - Button labels include timing expectations to manage user experience.
  - Reviewer feedback input allows regeneration with context.
  - "Accept MCQ" persists MCQ + triplets to database (removes article from pending queue).
  - Visual prompt can be edited before acceptance.
  - "Show Image" button: On-demand image generation using selected LLM's image API (Gemini Imagen or OpenAI DALL-E). First click generates, second click loads, third click displays (Gradio rendering quirk).
  - Images are generated from visual prompts with configurable size (default 300x300, with local resizing to match requested dimensions).
  - Images saved to `media/` folder with paths stored in database.
  - "Delete Image" button to remove images from storage.

- **Tab 3 – Knowledge Base**
  - Default view shows 6 MCQs per page with pagination (Prev/Next).
  - Search by PMID, title, authors, year, filename, or question text.
  - Enter MCQ ID and click "View Details" to see:
    - Complete MCQ with options and correct answer
    - Source information (title, authors, year, PMID, or PDF filename with section for chunks)
    - Associated SNOMED-style triplet with context sentences
    - Visual prompt
    - Image display (if available)
  - Export All: Single button that downloads a comprehensive .txt file containing MCQ content, visual prompt, and image information (click twice to download - Gradio quirk).
  - "Open in Builder" adds source back to pending queue for editing.

## Google ADK Framework Features

This project implements 5+ features from the Google Agent Development Kit framework:

1. **SequentialAgent Orchestration** - Pipeline of agents (SourceIngestionAgent → FactExtractionAgent → KBManagementAgent → MCQGenerationAgent → VisualRefinerAgent) defined in `app/agents/pipeline.py`. Each agent passes structured data via `output_key` for deterministic data handoff.

2. **LoopAgent for MCQ Refinement** - Iterative refinement loop (Writer + Critic) defined in `app/agents/mcq_refinement.py`. Critic reviews MCQ quality, Refiner improves based on critique, exits when approved or max 3 iterations reached.

3. **DatabaseSessionService** - Persistent session management using `DatabaseSessionService` with SQLite. Sessions persist across app restarts with automatic restoration. Implemented in `app/core/session.py`.

4. **Context Compaction** - EventsCompactionConfig configured in `app/core/app.py` to manage token usage in long sessions. Compacts every 5 turns while keeping 2 previous turns overlap.

5. **Custom Tools** - Multiple custom tools implemented:
   - `schema_validator.py` - Validates triplets against medical ontology schema
   - `kb_tools.py` - Knowledge base query and storage operations
   - `provenance_tools.py` - Provenance verification and context sentence extraction
   - `pubmed_tools.py` - PubMed search and article fetching
   - `tavily_search.py` - Tavily search integration for distractor generation

6. **Built-in Tools** - Google Search tool from ADK used in MCQ generation agent for finding medically plausible distractors when KB coverage is insufficient.

These agents and tools are available in the codebase and can be integrated into workflows via the ADK runner. The current UI uses direct API calls for MCQ generation, but the agent infrastructure is in place for future extensibility.

## Running the App

```bash
uv venv && uv pip install -r requirements.txt
cp .env.example .env  # fill in OPENAI_API_KEY / GOOGLE_API_KEY / TAVILY_API_KEY
python app.py
```

The Gradio UI loads at `http://localhost:7860`.

## Key Files

- `app/ui/gradio_app.py` – All Gradio blocks + session glue.
- `app/agents/pipeline.py` – Sequential agent definitions (ingest → MCQ → visual).
- `app/core/llm_manager.py` – Provider registry + fallback logic.
- `app/db/models.py` – Source, triplet, pending queue, MCQ schema.
- `plan/docs/implementation_plan.md` – Technical roadmap (kept in sync).

## Tech Stack

### Core Framework
- **[Google Agent Development Kit (ADK)](https://github.com/google/agentic-development-kit)** - Agent orchestration and LLM integration
- **[Gradio](https://gradio.app/)** - Interactive web UI for human-in-the-loop workflows
- **[SQLAlchemy](https://www.sqlalchemy.org/)** - Database ORM for persistent storage

### Data & Services
- **[BioPython](https://biopython.org/)** - PubMed API integration
- **[PyPDF](https://pypdf.readthedocs.io/)** - PDF text extraction
- **[Pydantic](https://docs.pydantic.dev/)** - Data validation and settings management

### LLM Providers
- **Gemini 2.5 Flash Lite** (default) – Direct API calls via `google.genai` for MCQ generation. Gemini Imagen API (`gemini-2.5-flash-image`) for image generation.
- **ChatGPT 4o mini** (optional) – OpenAI GPT-4o mini via OpenAI API for MCQ generation. OpenAI DALL-E (`gpt-image-1`) for image generation. Both MCQ and image generation fully supported through UI model selector.

### Database
- **SQLite** - Persistent storage for sources, triplets, MCQs, and sessions

## Implementation Approach

### Current Architecture: Hybrid ADK + Direct API

The application uses a **hybrid approach** combining Google ADK for orchestration capabilities with direct API calls for core MCQ and image generation:

1. **Direct LLM API Calls** (`app/services/gemini_mcq_service.py`, `app/services/gemini_image_service.py`)
   - Supports both Gemini and OpenAI (ChatGPT) APIs
   - Direct calls to `google.genai.Client` or `openai.Client` based on user selection
   - Returns structured JSON with MCQ, triplets, and visual prompts
   - Universal JSON extractor handles both API response formats
   - Image generation routes to Gemini Imagen or OpenAI DALL-E based on model selection

2. **PDF Section Chunking** (`app/services/pdf_section_parser.py`)
   - Section-aware PDF processing for medical papers
   - Filters out Introduction and References sections
   - Chunks known sections (Abstract, Methods, Results, Discussion, Conclusion) as separate sources
   - Unknown sections split into paragraph-based chunks (2 paragraphs per chunk)
   - Each chunk becomes a separate Source record, enabling focused MCQ generation

3. **Google ADK** (Available for future workflows)
   - `app/agents/pipeline.py` contains SequentialAgent definitions
   - `app/agents/mcq_refinement.py` contains LoopAgent for iterative refinement
   - `app/core/runner.py` provides ADK runner integration
   - `app/core/app.py` configures context compaction
   - Used for future extensibility and complex orchestration needs

### Why Direct API?

- **Reliability**: Direct API calls provide consistent JSON responses from both Gemini and OpenAI
- **Speed**: Faster for simple request-response patterns without async generator overhead
- **Control**: Full control over prompt structure and JSON schema enforcement
- **Simplicity**: Avoids async generator/coroutine complexity in Gradio event handlers
- **Flexibility**: Easy to switch between LLM providers via model_id parameter

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Gradio UI Layer                       │
│  (Source Search/Upload, Triplet Review, MCQ Review)      │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│              Agent Pipeline Layer                        │
│  SequentialAgent: Source → Extract → KB → MCQ → Visual  │
│  LoopAgent: MCQ Refinement (Writer + Critic)           │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                  Tools Layer                             │
│  Custom Tools: Schema Validator, KB Writer, etc.        │
│  Built-in Tools: Google Search                          │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                Services Layer                            │
│  PubMed Service, Ingestion Service, KB Service          │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│              Database Layer (SQLite)                     │
│  Sessions DB, Triplets DB, MCQs DB, Sources DB         │
└─────────────────────────────────────────────────────────┘
```

## Installation

### Prerequisites
- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd agent-capstone
   ```

2. **Create virtual environment**
   ```bash
   uv venv
   # Or: python -m venv .venv
   ```

3. **Activate virtual environment**
   ```bash
   # Windows (PowerShell)
   .venv\Scripts\Activate.ps1
   
   # Linux/Mac
   source .venv/bin/activate
   ```

4. **Install dependencies**
   ```bash
   uv pip install -r requirements.txt
   # Or: pip install -r requirements.txt
   ```

5. **Configure environment variables**
   
   Create a `.env` file in the root directory:
   ```env
   # Required: ChatGPT 4o mini (default LLM)
   OPENAI_API_KEY=your_openai_api_key_here
   
   # Optional: Enable Gemini fallback / Google Search tools
   GOOGLE_API_KEY=your_google_api_key_here
   
   # Optional: Tavily search (used automatically when ChatGPT is active)
   TAVILY_API_KEY=your_tavily_api_key_here
   
   # Optional: For PubMed API (set your email)
   NCBI_EMAIL=your_email@example.com
   ```

6. **Initialize database**
   
   The database will be created automatically on first run. To initialize manually:
   ```python
   from app.db.database import init_db
   init_db()
   ```

## Usage

### Launch the Application

```bash
python app.py
```

The Gradio UI will be available at `http://localhost:7860`

### Workflow

1. **Source Ingestion**
   - Search PubMed by keywords or upload PDF
   - Select article(s) to add them to the Pending Review queue (no LLM calls yet)

2. **MCQ Builder (Tab 2)**
   - Select any pending article or PDF chunk from the dropdown to request an MCQ on demand
   - Choose LLM model (Gemini 2.5 Flash Lite or ChatGPT 4o mini) from dropdown
   - The builder prompts the selected LLM to return a 5-option MCQ plus supporting SNOMED-CT style triplets
   - Provide natural-language feedback to regenerate, then accept to persist the MCQ (and triplets) into SQLite
   - Edit or regenerate the visual prompt before accepting it into the database

3. **Knowledge Base (Tab 3)**
   - Browse 6 most recent MCQs per page with pagination
   - Search by PMID, title, authors, year, filename, or question text
   - View detailed MCQ information including triplets and images
   - Export all MCQ data as text file
   - Re-open MCQs in Builder for editing

4. **Image Generation**
   - Generate images from visual prompts using selected LLM's image API (Gemini Imagen or OpenAI DALL-E)
   - Default size 300x300, with automatic resizing to match requested dimensions
   - On-demand generation: click "Show Image" to generate and display
   - Images saved to `media/` folder with paths in database

## Project Structure

```
agent-capstone/
├── app/
│   ├── agents/              # Google ADK agents (available for future use)
│   │   ├── pipeline.py      # SequentialAgent pipeline definitions
│   │   └── mcq_refinement.py # LoopAgent for refinement
│   ├── core/                # Core configuration
│   │   ├── app.py          # App with context compaction
│   │   ├── session.py      # DatabaseSessionService
│   │   ├── runner.py       # Runner with session restore & model routing
│   │   ├── llm_manager.py  # Dataclass-driven LLM registry + fallback
│   │   └── openai_llm.py   # Custom BaseLlm wrapper for ChatGPT 4o mini
│   ├── db/                  # Database layer
│   │   ├── models.py        # SQLAlchemy models (Source, Triplet, MCQRecord, PendingSource)
│   │   └── database.py      # Database setup
   │   ├── services/            # Business logic
   │   │   ├── pubmed_service.py      # PubMed search via BioPython
   │   │   ├── ingestion_service.py  # Source registration (PubMed/PDF with chunking)
   │   │   ├── pdf_section_parser.py  # PDF section detection and chunking
   │   │   ├── kb_service.py          # Knowledge base operations
   │   │   ├── gemini_mcq_service.py  # Direct Gemini/OpenAI API for MCQ generation
   │   │   ├── gemini_image_service.py # Direct Gemini Imagen/OpenAI DALL-E API
   │   │   └── media_service.py       # Image storage in media/ folder
│   ├── tools/               # Custom tools for agents
│   │   ├── schema_validator.py
│   │   ├── kb_tools.py
│   │   ├── provenance_tools.py
│   │   ├── pubmed_tools.py
│   │   └── tavily_search.py
│   └── ui/                  # Gradio UI
│       └── gradio_app.py    # Main UI with Tab 1 (Intake), Tab 2 (Builder), Tab 3 (KB)
├── plan/                    # Planning documents (not tracked)
├── app.py                   # Main entry point
├── requirements.txt         # Python dependencies
└── .env                     # Environment variables (not tracked)
```

## Key Features

### Provenance Verification
- **Context Sentences**: Every triplet includes 2-4 verbatim sentences from source
- **Source Tracking**: Every MCQ links to PubMed ID or PDF filename
- **Audit Trail**: Complete history of extraction → review → approval

### Human-in-the-Loop
- **Triplet Review**: Accept/Reject/Edit before storage
- **MCQ Review**: Approve/Reject/Request Updates
- **Visual Prompt Editing**: Edit optimized visual prompts before image generation
- **Fallback Approvals**: Zero-triplet proposals stay queued in the UI until explicitly approved

### On-Demand Generation
- **No auto-processing**: Articles are queued without LLM calls until user explicitly requests MCQ generation
- **In-memory caching**: MCQ drafts stored in `pending_mcq_cache` until accepted
- **Session-persistent**: Pending articles persist in database across app restarts
- **Iterative refinement**: Reviewer feedback regenerates MCQ with context preservation

### Quality Assurance
- **Schema Validation**: Triplets validated against medical ontology
- **Automatic Refinement**: LoopAgent improves MCQs before human review
- **Distractor Quality**: KB + Google Search ensures plausible distractors

### Session Management
- **Persistent Sessions**: Work persists across app restarts
- **Context Compaction**: Efficient token usage in long sessions
- **State Restoration**: Auto-restore last session on startup

### LLM Flexibility
- **Dual Provider Support**: Both Gemini 2.5 Flash Lite and ChatGPT 4o mini fully supported
- **Unified Interface**: Single UI dropdown for model selection, works for both MCQ and image generation
- **Provider-Agnostic Services**: MCQ and image services route to appropriate API based on model_id
- **Centralized control**: `LLMManager` manages model configurations and fallbacks



## Development

### Adding New Agents

Follow Google ADK patterns from `plan/framework/agent_examples.txt`:

```python
from google.adk import Agent
from google.adk.models import Gemini

my_agent = Agent(
    name="MyAgent",
    model=Gemini(model="gemini-2.5-flash-lite"),
    instruction="Your agent instructions",
    tools=[my_tool],
    output_key="my_output"
)
```

### Adding Custom Tools

```python
from google.adk.tools import FunctionTool

def my_tool(param: str) -> dict:
    """Tool description"""
    return {"result": "value"}

my_tool_instance = FunctionTool(my_tool)
```

## Contributing

1. Create a feature branch from `development`
2. Make your changes
3. Test thoroughly
4. Submit a pull request

## License

MIT LICENSE

## Acknowledgments

- **Google Agent Development Kit** for agent orchestration framework
- **Gradio** for the excellent UI framework
- **BioPython** for PubMed integration
- Medical ontology schema based on standard medical knowledge representation

## References

- [Google ADK Documentation](https://github.com/google/agentic-development-kit)
- [Gradio Documentation](https://gradio.app/docs/)
- [PubMed API](https://www.ncbi.nlm.nih.gov/books/NBK25497/)

---

