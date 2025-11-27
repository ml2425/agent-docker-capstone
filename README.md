# Verifiable Medical MCQ Generator

A production-ready system for generating high-quality, verifiable medical multiple-choice questions (MCQs) using Google Agent Development Kit (ADK) with human-in-the-loop validation.

## Problem

Medical training programs need **small, trusted sets of multiple-choice questions** where every correct answer links back to a **verifiable source**. However:

- **Manual authoring is slow** and doesn't scale
- **LLMs without guardrails hallucinate** facts and create unverifiable content
- **Provenance tracking is missing** - you can't verify where answers came from
- **Quality control is manual** and time-consuming

This creates a critical gap: How do you generate medical MCQs at scale while ensuring **100% verifiable provenance**?

## Solution

This application solves the problem through a **multi-agent pipeline** powered by **Google ADK** that:

1. **Ingests sources** (PubMed articles or PDFs) with full provenance tracking
2. **Extracts facts** as schema-constrained triplets with **verbatim context sentences** (2-4 sentences proving provenance)
3. **Validates against medical ontology** before human review
4. **Generates MCQs** from approved facts with automatic distractor generation
5. **Refines quality** through iterative agent loops before human review
6. **Enables human-in-the-loop** approval at every critical stage
7. **Tracks everything** - every MCQ links back to source, triplet, and context sentences

**Key Innovation:** Context sentences (verbatim quotes from source) prove triplets came from source material, not LLM imagination.

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
- **ChatGPT 4o mini** (default) – OpenAI GPT-4o mini via custom OpenAI LLM wrapper
- **Gemini 2.5 Flash Lite** (optional) – Google Gemini 2.5 Flash Lite selectable from the UI

### Database
- **SQLite** - Persistent storage for sources, triplets, MCQs, and sessions

## Google ADK Features Used

This project implements **5 Google ADK features** (exceeding the 4+ requirement):

### 1. SequentialAgent Orchestration ⭐ **CORE**
**Location:** `app/agents/pipeline.py`

Deterministic pipeline ensuring provenance and triplet IDs survive every hop:
```
SourceIngestionAgent → FactExtractionAgent → KBManagementAgent → 
MCQGenerationAgent → VisualRefinerAgent
```

**Implementation:** Each agent passes structured data via `output_key`, ensuring predictable data handoff and auditable provenance.

### 2. LoopAgent QA Wrapper ⭐ **CORE**
**Location:** `app/agents/mcq_refinement.py`

Iterative MCQ refinement before human review:
- **MCQWriter** generates initial MCQ
- **MCQCritic** reviews quality, provenance, clinical accuracy
- **MCQRefiner** improves based on critique
- **Max 3 iterations** or exits when critic returns "APPROVED"

**Impact:** Reduces human review load by pre-filtering low-quality MCQs.

### 3. DatabaseSessionService (Persistent Sessions) ⭐ **CORE**
**Location:** `app/core/session.py`

Persistent session management across app restarts:
- Stores: selected LLM model, ingested sources, pending triplets, MCQs in review
- **Auto-restores last session** on app restart
- Maintains state across UI interactions

**Impact:** Users can resume work without re-uploading sources or losing context.

### 4. Context Compaction ⭐ **EFFICIENCY**
**Location:** `app/core/app.py`

Manages token usage in long sessions:
- Compacts every **5 turns**
- Keeps **2 previous turns** overlap
- Prevents context bloat while preserving recent context

**Impact:** Enables long sessions with multiple sources/MCQs without token limit issues.

### 5. Built-in Tools (Google Search) ⭐ **ENHANCEMENT**
**Location:** `app/agents/pipeline.py` (MCQGenerationAgent)

Fallback for distractor generation:
- When KB doesn't return enough plausible swap triplets
- Uses `google_search` tool to find medically plausible alternatives
- Ensures distractors remain factually true in isolation but incorrect for specific question

**Impact:** Maintains high-quality distractors even when knowledge base coverage is thin.

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
   - Select article to ingest
   - System automatically extracts triplets

2. **Triplet Review**
   - Review extracted triplets with context sentences
   - Verify provenance evidence
   - Accept/Reject triplets (only accepted stored in KB)

3. **MCQ Generation**
   - Select approved triplet
   - Generate MCQ (triggers agent pipeline)
   - Review generated MCQ with provenance

4. **MCQ Refinement**
   - Request updates from LLM
   - Approve/Reject final MCQ
   - Optional: Generate image from visual prompt

## Project Structure

```
agent-capstone/
├── app/
│   ├── agents/              # Google ADK agents
│   │   ├── pipeline.py      # SequentialAgent pipeline
│   │   └── mcq_refinement.py # LoopAgent for refinement
│   ├── core/                # Core configuration
│   │   ├── app.py          # App with context compaction
│   │   ├── session.py      # DatabaseSessionService
│   │   ├── runner.py       # Runner with session restore & model routing
│   │   ├── llm_manager.py  # Dataclass-driven LLM registry + fallback
│   │   └── openai_llm.py   # Custom BaseLlm wrapper for ChatGPT 4o mini
│   ├── db/                  # Database layer
│   │   ├── models.py        # SQLAlchemy models
│   │   └── database.py      # Database setup
│   ├── services/            # Business logic
│   │   ├── pubmed_service.py
│   │   ├── ingestion_service.py
│   │   └── kb_service.py
│   ├── tools/               # Custom tools for agents
│   │   ├── schema_validator.py
│   │   ├── kb_tools.py
│   │   ├── provenance_tools.py
│   │   └── pubmed_tools.py
│   └── ui/                  # Gradio UI
│       └── gradio_app.py
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

