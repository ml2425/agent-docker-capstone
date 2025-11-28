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

## What’s Implemented Right Now

- **Tab 1 – Source Intake**
  - Search PubMed (top articles displayed with title + year) or upload a PDF.
  - Selecting entries simply adds them to the pending queue; no LLM call happens yet.
  - Queue supports pagination (6 per page) and bulk clear for quick clean-up.

- **Tab 2 – MCQ Builder**
  - Dropdown lists every pending article (title + year + PMID/file ID).
  - "Generate MCQ Draft (takes a few seconds)" calls Gemini API directly to return:
    - MCQ (stem/question/5 options/correct index)
    - Optimized visual prompt
    - Supporting SNOMED-style triplets (subject-action-object-relation)
  - Button labels include timing expectations to manage user experience.
  - Reviewer feedback input allows regeneration with context.
  - "Accept MCQ" persists MCQ + triplets to database (removes article from pending queue).
  - Visual prompt can be edited before acceptance.
  - "Show Image" button: On-demand image generation (first click generates, second click loads, third click displays - Gradio quirk).
  - Images are generated from visual prompts with configurable size (default aspect ratio, with local resizing if needed).
  - Images saved to `media/` folder with paths stored in database.
  - "Delete Image" button to remove images from storage.

- **Tab 3 – Knowledge Base**
  - Default view shows 6 MCQs per page with pagination (Prev/Next).
  - Search by PMID, title, authors, year, filename, or question text.
  - Enter MCQ ID and click "View Details" to see:
    - Complete MCQ with options and correct answer
    - Source information (title, authors, year, PMID)
    - Associated SNOMED-style triplet with context sentences
    - Visual prompt
    - Image display (if available)
  - Export All: Single button that downloads a comprehensive .txt file containing MCQ content, visual prompt, and image information (click twice to download - Gradio quirk).
  - "Open in Builder" adds source back to pending queue for editing.

## What’s Next

- Progress streaming during long LLM calls so users see when a draft is in flight.
- More granular provenance display (context sentences) inside the builder tab.
- Ability to re-open stored MCQs for edits (currently read-only).
- Optional image generation once prompts are accepted.

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

## FAQ

**Why no auto-triplet extraction anymore?**  
Speed + control. Reviewers wanted to pick one article, generate one MCQ, and iterate without waiting for the entire search result to finish. The pending queue gives instant feedback and defers heavy LLM calls to the builder tab.

**Where do the triplets show up?**  
Right now they’re displayed as markdown next to the MCQ draft (and stored automatically when you accept). Future work will add a richer transparency view.

**What if I want the old auto-mode back?**  
The legacy ADK flow is still documented in `plan/docs/implementation_plan.md`. We can re-enable it later, but the current prototype focuses on predictability and reviewer-driven actions.

---

Questions or ideas? Drop them in the issue tracker and reference the relevant tab/flow so we can keep iterating quickly. 👍

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
- **Gemini 2.5 Flash Lite** (default) – Direct API calls via `google.genai` for MCQ generation and image prompts. Used for core MCQ workflow.
- **ChatGPT 4o mini** (optional) – OpenAI GPT-4o mini via custom OpenAI LLM wrapper. Available for future ADK-based workflows.

### Database
- **SQLite** - Persistent storage for sources, triplets, MCQs, and sessions

## Implementation Approach

### Current Architecture: Hybrid ADK + Direct API

The application uses a **hybrid approach** combining Google ADK for orchestration capabilities with direct API calls for core MCQ generation:

1. **Direct Gemini API** (`app/services/gemini_mcq_service.py`)
   - Bypasses ADK runner for MCQ generation workflow
   - Direct calls to `google.genai.Client` for faster, more reliable responses
   - Returns structured JSON with MCQ, triplets, and visual prompts
   - Uses Pydantic-style JSON schema enforcement in prompts

2. **Gemini Imagen API** (`app/services/gemini_image_service.py`)
   - Direct image generation via `imagen-3.0-generate` model
   - Configurable image sizes (default 300x300)
   - Returns base64-encoded image bytes

3. **Google ADK** (Available but not primary for MCQ generation)
   - `app/agents/pipeline.py` contains SequentialAgent definitions
   - `app/core/runner.py` provides ADK runner integration
   - Used for future extensibility and complex orchestration needs

### Why Direct API?

- **Reliability**: Gemini 2.5 Flash Lite has tool-calling limitations with ADK's function calling style
- **Speed**: Direct API calls are faster for simple request-response patterns
- **Control**: Full control over prompt structure and JSON schema enforcement
- **Simplicity**: Avoids async generator/coroutine complexity in Gradio event handlers

See `plan/docs/tips.md` for detailed technical decisions and lessons learned.

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
   - Select any pending article from the dropdown to request an MCQ on demand
   - The builder prompts the LLM to return a 5-option MCQ plus supporting SNOMED-CT style triplets
   - Provide natural-language feedback to regenerate, then accept to persist the MCQ (and triplets) into SQLite
   - Edit or regenerate the visual prompt before accepting it into the database

3. **Knowledge Base (Tab 3)**
   - Browse 10 most recent MCQs with pagination
   - Search by PMID, title, authors, year, filename, or question text
   - View detailed MCQ information including triplets and images
   - Export MCQs as JSON or text
   - Re-open MCQs in Builder for editing

4. **Image Generation**
   - Generate images from visual prompts (default 300x300)
   - Preview before accepting
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
│   │   ├── ingestion_service.py  # Source registration (PubMed/PDF)
│   │   ├── kb_service.py          # Knowledge base operations
│   │   ├── gemini_mcq_service.py  # Direct Gemini API for MCQ generation
│   │   ├── gemini_image_service.py # Direct Gemini Imagen API
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
- **ChatGPT 4o mini default**: Custom `OpenAILlm` wrapper makes OpenAI the primary model
- **Gemini opt-in**: UI dropdown and session state let reviewers switch to Gemini 2.5 Flash Lite
- **Centralized control**: `LLMManager` enforces graceful fallbacks and shared configuration

## Testing

### Backend Testing (Without UI)

Run automated tests:
```bash
python test_backend.py
```

Interactive CLI for testing agents:
```bash
python test_agents_cli.py
```

**Note:** Test files are excluded from git (see `.gitignore`).

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

