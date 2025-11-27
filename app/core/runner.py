"""Runner with session restore functionality."""
from google.adk.runners import Runner
from google.genai import types
from app.core.app import app
from app.core.session import session_service
from typing import Optional, Any
import time

from app.core.llm_manager import llm_manager
from app.agents.pipeline import set_pipeline_model
from app.agents.mcq_refinement import set_refinement_model


runner = Runner(app=app, session_service=session_service)


async def run_agent(
    new_message: str,
    user_id: str = "default",
    session_id: Optional[str] = None,
    model_id: Optional[str] = None,
) -> Any:
    """
    Helper function to run agent and collect final result from async generator.
    
    Args:
        new_message: Message text to send to agent
        user_id: User identifier
        session_id: Session ID (if None, will create new session)
        model_id: Optional LLM identifier
    
    Returns:
        Final result from agent pipeline
    """
    if session_id is None:
        session_id = await create_new_session(user_id)
    
    # Apply the selected model across the pipeline and refinement loop.
    model = llm_manager.get_model(model_id)
    set_pipeline_model(model)
    set_refinement_model(model)
    
    query_content = types.Content(
        role="user",
        parts=[types.Part.from_text(text=new_message)],
    )
    
    result = None
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=query_content
    ):
        result = event
    
    return result


async def get_last_session(user_id: str = "default") -> Optional[str]:
    """
    Get last session ID for user.
    
    Args:
        user_id: User identifier
    
    Returns:
        Session ID or None if no previous session
    """
    try:
        # Query session service for most recent session
        # Note: DatabaseSessionService may need custom query method
        # For now, we'll create a new session if none exists
        # In production, implement proper session retrieval
        return None  # Placeholder - implement based on DatabaseSessionService API
    except Exception:
        return None


async def create_new_session(user_id: str = "default") -> str:
    """
    Create a new session.
    
    Args:
        user_id: User identifier
    
    Returns:
        New session ID
    """
    session_id = f"session_{int(time.time())}"
    try:
        await session_service.create_session(
            app_name="MedicalMCQGenerator",
            user_id=user_id,
            session_id=session_id
        )
        return session_id
    except Exception as e:
        # If session creation fails, return ID anyway
        # Session will be created on first use
        return session_id


async def restore_session(user_id: str, session_id: str):
    """
    Restore session state.
    
    Args:
        user_id: User identifier
        session_id: Session ID to restore
    
    Returns:
        Session object or None
    """
    try:
        session = await session_service.get_session(
            app_name="MedicalMCQGenerator",
            user_id=user_id,
            session_id=session_id
        )
        return session
    except Exception:
        return None

