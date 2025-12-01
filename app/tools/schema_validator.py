"""Schema validation tool for triplets."""
from google.adk.tools import FunctionTool
from typing import Dict
import yaml
import os

# Load schema
SCHEMA_PATH = os.path.join(
    os.path.dirname(__file__), 
    "../schema/schema.yaml"
)

with open(SCHEMA_PATH, 'r') as f:
    SCHEMA = yaml.safe_load(f)


def validate_triplet_schema(subject: str, action: str, object: str, relation: str) -> Dict:
    """
    Validate triplet against medical schema.
    
    Args:
        subject: Triplet subject
        action: Triplet action
        object: Triplet object
        relation: Relation type (e.g., "TREATS", "CAUSES")
    
    Returns:
        Dict with 'valid' (bool) and 'errors' (list)
    """
    errors = []
    
    # Check if relation exists in schema
    valid_relations = [r["id"] for r in SCHEMA.get("relations", []) if r.get("enabled", True)]
    if relation not in valid_relations:
        errors.append(f"Relation '{relation}' not in schema or not enabled")
        return {
            "valid": False,
            "errors": errors
        }
    
    # Find relation definition
    relation_def = next(
        (r for r in SCHEMA.get("relations", []) if r["id"] == relation),
        None
    )
    
    if not relation_def:
        errors.append(f"Relation '{relation}' definition not found")
        return {
            "valid": False,
            "errors": errors
        }
    
    # Check domain/range constraints if schema defines entity types
    # Note: This is a simplified check - full validation would require entity type detection
    # For now, we validate that the relation is valid and enabled
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "relation": relation,
        "relation_enabled": relation_def.get("enabled", True)
    }


schema_validator_tool = FunctionTool(validate_triplet_schema)

