"""PDF section detection and chunking for medical papers.
Section configuration is easily modifiable for future changes."""
import re
from typing import List, Dict, Tuple
from pypdf import PdfReader
from io import BytesIO


# ============================================================================
# SECTION CONFIGURATION - Easy to modify for future changes
# ============================================================================

# Sections to KEEP (used for MCQ generation)
# Add or remove sections here as needed
KEEP_SECTIONS = [
    "Abstract",
    "Methods",
    "Results",
    "Discussion",
    "Conclusion"
]

# Sections to FILTER OUT (not used for MCQ generation)
# References is excluded as it only contains citations to other papers
FILTER_SECTIONS = [
    "Introduction",  # Usually background, not core findings
    "References",    # Only citations, no MCQ value
]

# Section detection patterns
# Format: (regex_pattern, canonical_section_name)
# Add new patterns here to detect additional sections
SECTION_PATTERNS: List[Tuple[str, str]] = [
    (r'^\s*(ABSTRACT|Summary)\s*$', "Abstract"),
    (r'^\s*(INTRODUCTION|Background)\s*$', "Introduction"),
    (r'^\s*(METHODS?|Methodology|Materials and Methods)\s*$', "Methods"),
    (r'^\s*(RESULTS?|Findings)\s*$', "Results"),
    (r'^\s*(DISCUSSION)\s*$', "Discussion"),
    (r'^\s*(CONCLUSION|Conclusions)\s*$', "Conclusion"),
    (r'^\s*(REFERENCES?|Bibliography)\s*$', "References"),
    # Add more patterns here as needed:
    # (r'^\s*(ACKNOWLEDGMENTS?)\s*$', "Acknowledgments"),
    # (r'^\s*(APPENDIX)\s*$', "Appendix"),
]

# Paragraph grouping for unknown sections
# Number of paragraphs to group together (like PubMed abstract length)
PARAGRAPHS_PER_CHUNK = 2


# ============================================================================
# PDF TEXT EXTRACTION
# ============================================================================

def extract_pdf_text(pdf_bytes: bytes) -> str:
    """
    Extract text from PDF bytes.
    
    Args:
        pdf_bytes: PDF file content as bytes
    
    Returns:
        Extracted text string
    """
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        raise ValueError(f"Failed to extract PDF text: {e}")


# ============================================================================
# SECTION PARSING FUNCTIONS
# ============================================================================

def detect_section_header(line: str) -> tuple[bool, str | None]:
    """
    Detect if a line is a section header.
    
    Args:
        line: Text line to check
        
    Returns:
        (is_header, section_name) tuple
    """
    for pattern, section_name in SECTION_PATTERNS:
        if re.match(pattern, line, re.IGNORECASE):
            return True, section_name
    return False, None


def chunk_pdf_by_sections(pdf_bytes: bytes, pdf_filename: str) -> List[Dict[str, any]]:
    """
    Split PDF into sections, filter out unwanted sections.
    For unknown sections, split by paragraphs (2 paragraphs = 1 chunk).
    
    Args:
        pdf_bytes: PDF file content as bytes
        pdf_filename: Original PDF filename (for logging)
        
    Returns:
        List of chunks ready to be stored as Source records.
        Each chunk has: section_title, content, order, is_known_section
    """
    # Extract text from PDF
    full_text = extract_pdf_text(pdf_bytes)
    lines = full_text.split('\n')
    
    chunks = []
    current_section = None
    current_content = []
    section_order = 0
    unknown_content = []  # Text before first section or between unknown sections
    
    for line in lines:
        is_header, detected_section = detect_section_header(line)
        
        if is_header:
            # Save previous section if it should be kept
            if current_section and current_section in KEEP_SECTIONS and current_content:
                section_text = '\n'.join(current_content).strip()
                if section_text:
                    chunks.append({
                        "section_title": current_section,
                        "content": section_text,
                        "order": section_order,
                        "is_known_section": True
                    })
                    section_order += 1
            
            # If previous section was filtered, discard its content
            if current_section and current_section in FILTER_SECTIONS:
                # Discard content (Introduction, References, etc.)
                pass
            
            # Start new section
            current_section = detected_section
            current_content = []
        else:
            if current_section:
                # Add to current section
                current_content.append(line)
            else:
                # Text before any section header detected - treat as unknown
                unknown_content.append(line)
    
    # Save final section if it should be kept
    if current_section and current_section in KEEP_SECTIONS and current_content:
        section_text = '\n'.join(current_content).strip()
        if section_text:
            chunks.append({
                "section_title": current_section,
                "content": section_text,
                "order": section_order,
                "is_known_section": True
            })
            section_order += 1
    
    # Handle unknown sections (text before first header or between unknown sections)
    # Split by paragraphs, group N paragraphs per chunk
    if unknown_content:
        unknown_text = '\n'.join(unknown_content).strip()
        if unknown_text:
            # Split by paragraphs (double newline)
            paragraphs = [p.strip() for p in unknown_text.split('\n\n') if p.strip()]
            
            # Group paragraphs per chunk
            for i in range(0, len(paragraphs), PARAGRAPHS_PER_CHUNK):
                chunk_paragraphs = paragraphs[i:i+PARAGRAPHS_PER_CHUNK]
                chunk_content = '\n\n'.join(chunk_paragraphs)
                
                if chunk_content.strip():
                    chunks.append({
                        "section_title": "Unknown Section",
                        "content": chunk_content,
                        "order": section_order,
                        "is_known_section": False
                    })
                    section_order += 1
    
    # If no chunks found at all, treat entire document as one chunk
    if not chunks:
        chunks.append({
            "section_title": "Full Document",
            "content": full_text.strip(),
            "order": 0,
            "is_known_section": False
        })
    
    return chunks

