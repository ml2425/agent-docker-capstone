"""SequentialAgent pipeline for MCQ generation."""
from google.adk.agents import Agent, SequentialAgent
from google.adk.models.google_llm import Gemini
from app.tools.pubmed_tools import pubmed_search_tool, pubmed_fetch_tool
from app.tools.schema_validator import schema_validator_tool
from app.tools.kb_tools import kb_query_tool
from app.tools.tavily_search import tavily_search_tool
from google.adk.tools import google_search


# Source Ingestion Agent
source_ingestion_agent = Agent(
    name="SourceIngestionAgent",
    model=Gemini(model="gemini-2.5-flash-lite"),
    instruction="""
    You are a source ingestion agent. Your task is to:
    1. If given PubMed keywords, search and return article metadata
    2. If given a PubMed ID, fetch the article details
    3. If given PDF content, extract and structure the text
    4. Return a source_payload JSON with:
       - source_id (PubMed ID like "PMID:12345678" or PDF filename hash)
       - source_type ("pubmed" or "pdf")
       - title, authors, year (if available)
       - content (abstract or PDF text)
    
    Always use the pubmed_search or pubmed_fetch tools when dealing with PubMed.
    """,
    tools=[pubmed_search_tool, pubmed_fetch_tool],
    output_key="source_payload"
)


# Fact Extraction Agent (CRITICAL - Context Sentences)
fact_extraction_agent = Agent(
    name="FactExtractionAgent",
    model=Gemini(model="gemini-2.5-flash-lite"),
    instruction="""
    You are a fact extraction agent. Extract Subject-Action-Object triplets from medical source text.
    
    CRITICAL REQUIREMENTS:
    1. For each triplet, extract 2-4 VERBATIM sentences from the source text that support the triplet
    2. These context sentences must appear in the original source text (copy them exactly, word-for-word)
    3. Return JSON array with fields:
       - subject (string)
       - action (string)
       - object (string)
       - relation (string, from medical schema: TREATS, CAUSES, PREDISPOSES, SUGGESTS, INDICATES, etc.)
       - context_sentences (array of 2-4 verbatim sentences from source)
       - source_id (from source_payload)
       - source_title (from source_payload)
    
    Use the schema_validator tool to validate relations against the medical schema.
    
    Example output:
    [
      {
        "subject": "Metformin",
        "action": "treats",
        "object": "Type 2 Diabetes",
        "relation": "TREATS",
        "context_sentences": [
          "Metformin is the first-line treatment for type 2 diabetes mellitus.",
          "It works by reducing hepatic glucose production and improving insulin sensitivity."
        ],
        "source_id": "PMID:12345678",
        "source_title": "Metformin in Type 2 Diabetes..."
      }
    ]
    """,
    tools=[schema_validator_tool],
    output_key="extracted_triplets"
)


# KB Management Agent
kb_management_agent = Agent(
    name="KBManagementAgent",
    model=Gemini(model="gemini-2.5-flash-lite"),
    instruction="""
    You are a KB management agent. Your task is to:
    1. Check extracted triplets for duplicates against existing KB using kb_query_tool
    2. Validate triplets against schema using schema_validator_tool
    3. Prepare triplets for human review (status: pending)
    4. Return list of triplets ready for review
    
    Note: Do NOT automatically store triplets. They must be reviewed by human first.
    Mark triplets as ready_for_review with validation status.
    """,
    tools=[kb_query_tool, schema_validator_tool],
    output_key="triplets_for_review"
)


# MCQ Generation Agent (with Google Search)
mcq_generation_agent = Agent(
    name="MCQGenerationAgent",
    model=Gemini(model="gemini-2.5-flash-lite"),
    instruction="""
    You are an MCQ generation agent. Generate clinical-style MCQs from approved triplets.
    
    Requirements:
    1. Use approved triplets and source text to create clinical stem (scenario)
    2. Generate one question
    3. Create 5 options: 1 correct (from triplet) + 4 distractors
    4. Distractors must be medically plausible and factually true in isolation but incorrect for this question
    5. First, query KB using kb_query_tool to find plausible swap triplets for distractors
    6. If KB doesn't have enough plausible swap triplets, use google_search to find medically plausible alternatives
    7. Generate Visual Kernel Draft (VKD) - simple descriptive prompt for image generation
    
    Return JSON:
    {
      "stem": "Clinical scenario text...",
      "question": "What is...?",
      "options": ["Option A", "Option B", "Option C", "Option D", "Option E"],
      "correct_option": 0,
      "visual_kernel_draft": "Simple description for image...",
      "triplet_id": 123,
      "source_id": 456
    }
    """,
    tools=[kb_query_tool, google_search],
    output_key="mcq_draft"
)


# Visual Refiner Agent
visual_refiner_agent = Agent(
    name="VisualRefinerAgent",
    model=Gemini(model="gemini-2.5-flash-lite"),
    instruction="""
    You are a visual refiner agent. Refine Visual Kernel Draft into Optimized Visual Prompt.
    
    Tasks:
    1. Refine VKD by adding specifics: "high-resolution", "axial CT slice", "medical textbook style"
    2. Generate Visual Triplet (Subject-Action-Object) corresponding to the visual concept
    3. Validate Visual Triplet against schema using schema_validator_tool
    
    Return JSON:
    {
      "optimized_visual_prompt": "High-resolution medical illustration...",
      "visual_triplet": "Metformin → demonstrates → Mechanism",
      "schema_valid": true
    }
    """,
    tools=[schema_validator_tool],
    output_key="visual_payload"
)


# Zero-Triplet Fallback Agent
zero_triplet_fallback_agent = Agent(
    name="ZeroTripletFallbackAgent",
    model=Gemini(model="gemini-2.5-flash-lite"),
    instruction="""
    You provide a safety net when FactExtractionAgent returns zero triplets.

    1. Inspect prior outputs:
       - If extracted_triplets contains one or more entries, respond with:
         {"fallback_payload": null}
       - Otherwise, continue.
    2. Using source_payload.content (or any provided source text), draft ONE clinically sound provenance triplet:
       {
         "subject": ...,
         "action": ...,
         "object": ...,
         "relation": <schema relation>,
         "context_sentences": ["verbatim sentence 1", "verbatim sentence 2"]
       }
    3. From that triplet, craft exactly one MCQ with 5 options (index correct_option).
    4. Include a lightweight provenance summary so a reviewer can verify the fallback.

    Return JSON shape:
    {
      "fallback_triplet": {...},
      "fallback_mcq": {
        "stem": "...",
        "question": "...",
        "options": [...five items...],
        "correct_option": 0,
        "visual_kernel_draft": "...optional..."
      },
      "notes": "brief rationale"
    }
    """,
    output_key="fallback_payload"
)


# SequentialAgent Pipeline
mcq_pipeline = SequentialAgent(
    name="MCQPipeline",
    sub_agents=[
        source_ingestion_agent,
        fact_extraction_agent,
        kb_management_agent,
        mcq_generation_agent,
        visual_refiner_agent,
        zero_triplet_fallback_agent,
    ]
)


def set_pipeline_model(model) -> None:
    """Apply the provided LLM model to every agent in the pipeline."""
    agents = [
        source_ingestion_agent,
        fact_extraction_agent,
        kb_management_agent,
        mcq_generation_agent,
        visual_refiner_agent,
        zero_triplet_fallback_agent,
    ]
    for agent in agents:
        agent.model = model


def set_distractor_tool(provider: str) -> None:
    """Configure distractor search tool based on provider."""
    tools = [kb_query_tool]
    if provider == "gemini":
        tools.append(google_search)
    elif provider == "openai":
        tools.append(tavily_search_tool)
    mcq_generation_agent.tools = tools



