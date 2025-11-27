"""LoopAgent for MCQ refinement."""
from google.adk.agents import Agent, LoopAgent
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini
from typing import Dict


def exit_loop() -> Dict:
    """Exit loop when MCQ is approved"""
    return {"status": "approved"}


# MCQ Writer Agent
mcq_writer = Agent(
    name="MCQWriter",
    model=Gemini(model="gemini-2.5-flash-lite"),
    instruction="""
    Generate MCQ from approved triplets and source text.
    Output the MCQ in JSON format with stem, question, options, and correct_option.
    Output key: current_mcqs
    """,
    output_key="current_mcqs"
)


# MCQ Critic Agent
mcq_critic = Agent(
    name="MCQCritic",
    model=Gemini(model="gemini-2.5-flash-lite"),
    instruction="""
    Review the MCQ for quality, provenance, and clinical accuracy.
    
    Check:
    1. Clinical stem is realistic and appropriate
    2. Question is clear and unambiguous
    3. Correct answer is verifiable from the source triplet
    4. Distractors are medically plausible
    5. Options are balanced in length and complexity
    
    If the MCQ is good, return exactly 'APPROVED'.
    Otherwise, suggest specific fixes and improvements.
    Output key: critique
    """,
    output_key="critique"
)


# MCQ Refiner Agent
mcq_refiner = Agent(
    name="MCQRefiner",
    model=Gemini(model="gemini-2.5-flash-lite"),
    instruction="""
    Review the critique.
    
    If critique contains 'APPROVED', call exit_loop to stop refinement.
    Otherwise, improve current_mcqs based on the critique suggestions.
    Output the improved MCQ in the same JSON format.
    Output key: current_mcqs
    """,
    tools=[FunctionTool(exit_loop)],
    output_key="current_mcqs"
)


# LoopAgent for MCQ Refinement
mcq_refinement_loop = LoopAgent(
    name="MCQRefinementLoop",
    sub_agents=[mcq_critic, mcq_refiner],
    max_iterations=3
)


def set_refinement_model(model) -> None:
    """Apply the provided LLM model to refinement agents."""
    agents = [mcq_writer, mcq_critic, mcq_refiner, mcq_refinement_loop]
    for agent in agents:
        agent.model = model

