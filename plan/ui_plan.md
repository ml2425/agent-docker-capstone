# UI Implementation Plan: Verifiable Medical MCQ Generator

## Overview
This document outlines the complete UI structure for the Chainlit-based interface. The UI will be built using Chainlit 2.9.2 API, with a focus on skeleton/placeholder implementation first, followed by full functionality.

**Key Requirements:**
- Default LLM: ChatGPT 4o
- Optional LLM: Gemini 2.5 (user-switchable)
- Two main pages: Source Search/Upload & MCQ Review
- PubMed keyword search (not just ID input)
- PDF upload functionality
- Triplet review UI
- MCQ review with provenance display

---

## UI Architecture

### Navigation Structure
```
┌─────────────────────────────────────────┐
│  Header: LLM Selector | Settings Icon   │
├─────────────────────────────────────────┤
│  Navigation Tabs:                       │
│  [Source Search/Upload] [MCQ Review]    │
│  [Triplet Review] [Knowledge Base]      │
├─────────────────────────────────────────┤
│  Chat Display Area (Main Content)        │
│  - Messages, Articles, MCQs displayed    │
│  - Scrollable chat history               │
├─────────────────────────────────────────┤
│  Chat Input (Bottom)                     │
│  [Text input field] [Send Button]        │
└─────────────────────────────────────────┘
```

### Page Structure

#### **Page 1: Source Search/Upload** (Primary Entry Point)
- **Purpose:** Ingest medical sources (PubMed articles or PDFs)
- **Components:**
  1. LLM Model Selector (Header)
  2. Chat Display Area (shows search results, articles)
  3. Chat Input (for entering search queries, commands)
  4. PubMed Keyword Search Section (can be via chat or dedicated UI)
  5. PDF Upload Section
  6. Ingested Sources List
  7. Status/Progress Indicators

#### **Page 2: Triplet Review** (New - Critical Gap)
- **Purpose:** Human review of extracted triplets before KB storage
- **Components:**
  1. Triplet Cards with Context Sentences
  2. Accept/Reject Actions
  3. Schema Validation Status
  4. Source Provenance Display

#### **Page 3: MCQ Review** (HITL Gate)
- **Purpose:** Review, edit, approve generated MCQs
- **Components:**
  1. Chat Display Area (shows generated MCQs in chat format)
  2. Chat Input (for commands like "generate MCQ", "regenerate", etc.)
  3. MCQ Display (Stem, Options, Correct Answer)
  4. Provenance Tag
  5. Visual Prompt Section
  6. Edit/Regenerate/Approve/Reject Actions
  7. Image Generation Button

#### **Page 4: Knowledge Base** (Optional - Future)
- **Purpose:** Browse approved triplets and MCQs
- **Components:**
  1. Search/Filter Interface
  2. Triplet List View
  3. MCQ List View

---

## Detailed Component Specifications

### 1. Header Component (Global)

**Location:** Top of every page

**Elements:**
```
┌─────────────────────────────────────────────────────┐
│  🏥 Medical MCQ Generator    [ChatGPT 4o ▼]  ⚙️    │
└─────────────────────────────────────────────────────┘
```

**Functionality:**
- **LLM Selector Dropdown:**
  - Default: "ChatGPT 4o"
  - Option: "Gemini 2.5"
  - Updates session state when changed
  - Shows current selection with icon
- **Settings Icon (⚙️):**
  - Placeholder for future settings
  - Can show API key status, theme toggle, etc.

**Chainlit Implementation:**
- Use `cl.Sidebar` for persistent header
- Use `cl.select` or custom HTML for LLM selector
- Store selection in session state: `cl.user_session.set("llm_model", "chatgpt-4o")`

---

### 0. Chat Interface (Global - Core Chainlit Feature)

**Location:** Main content area (always visible)

**Layout:**
```
┌─────────────────────────────────────────────────────┐
│  Chat Display Area (Scrollable)                     │
│  ┌─────────────────────────────────────────────┐   │
│  │ User: "Search PubMed for diabetes treatment"│   │
│  └─────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────┐   │
│  │ Assistant: [Article cards displayed here]   │   │
│  │ 📄 Article 1: Metformin in Type 2...        │   │
│  │ 📄 Article 2: Diabetes Management...        │   │
│  └─────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────┐   │
│  │ User: "Generate MCQ from article 1"         │   │
│  └─────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────┐   │
│  │ Assistant: [MCQ displayed here]              │   │
│  │ Clinical Stem: "A 45-year-old..."          │   │
│  │ Question: "What is the first-line..."       │   │
│  └─────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────┤
│  Chat Input:                                         │
│  [Type your message or command...] [Send] [📎]     │
└─────────────────────────────────────────────────────┘
```

**Components:**
- **Chat Display Area:**
  - Scrollable message history
  - User messages (right-aligned or distinct style)
  - Assistant messages (left-aligned or distinct style)
  - **Article Display:** When PubMed search returns results, display as cards/messages in chat
  - **MCQ Display:** When MCQ is generated, display as formatted message in chat
  - **Triplet Display:** When triplets are extracted, display as formatted messages
- **Chat Input:**
  - Text input field at bottom
  - Send button
  - File attachment button (for PDF upload)
  - Supports natural language commands:
    - "Search PubMed for [keywords]"
    - "Upload PDF"
    - "Generate MCQ from [source]"
    - "Show triplets"
    - "Regenerate MCQ"

**Functionality:**
- **Natural Language Interface:**
  - Users can type commands in natural language
  - System interprets and executes actions
  - Results displayed in chat format
- **Message Types:**
  - **Text Messages:** User queries, system responses
  - **Article Cards:** PubMed search results displayed as rich cards
  - **MCQ Cards:** Generated MCQs displayed as formatted cards
  - **Triplet Cards:** Extracted triplets displayed as cards
  - **Action Buttons:** Inline buttons for Accept/Reject/Edit within chat messages
- **Chat History:**
  - Maintains conversation history
  - Scrollable to view past interactions
  - Can reference previous messages

**Placeholder Implementation:**
- Chat input field visible and functional
- Mock messages displayed (user query + assistant response)
- Mock article cards in chat display
- Mock MCQ cards in chat display
- Send button shows placeholder message

**Chainlit API Usage:**
```python
# Chat input handler
@cl.on_message
async def on_message(message: cl.Message):
    # Process user message
    user_input = message.content
    
    # Display user message
    await cl.Message(content=user_input, author="User").send()
    
    # Process command and generate response
    if "search" in user_input.lower():
        # Display articles in chat
        articles = search_pubmed(keywords)
        for article in articles:
            with cl.card():
                cl.text(f"**{article.title}**")
                cl.text(f"{article.authors} | {article.year}")
                cl.button("Select", action="select_article", value=article.id)
    
    elif "generate mcq" in user_input.lower():
        # Display MCQ in chat
        mcq = generate_mcq()
        with cl.card():
            cl.text("**Clinical Stem:**")
            cl.text(mcq.stem)
            cl.text("**Question:**")
            cl.text(mcq.question)
            # ... display options, provenance, etc.
            cl.button("Approve", action="approve_mcq", value=mcq.id)
```

---

### 2. Source Search/Upload Page

#### 2.1 PubMed Keyword Search Section

**Option A: Via Chat Input (Primary Method)**
- User types in chat: "Search PubMed for diabetes treatment"
- Results displayed as article cards in chat display area

**Option B: Dedicated Search UI (Alternative)**
- Traditional search box + button
- Results can also appear in chat or dedicated section

**Layout (Chat-based):**
```
┌─────────────────────────────────────────────────────┐
│  Chat Display Area:                                 │
│  ┌─────────────────────────────────────────────┐   │
│  │ User: "Search PubMed for diabetes treatment" │   │
│  └─────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────┐   │
│  │ Assistant: Found 5 articles:                 │   │
│  │ ┌───────────────────────────────────────┐   │   │
│  │ │ 📄 Metformin in Type 2 Diabetes...    │   │   │
│  │ │    Smith J, et al. | 2023             │   │   │
│  │ │    Abstract preview...                 │   │   │
│  │ │    [Select Article]                   │   │   │
│  │ └───────────────────────────────────────┘   │   │
│  │ ┌───────────────────────────────────────┐   │   │
│  │ │ 📄 [Next article card...]             │   │   │
│  │ └───────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────┘   │
│  [Chat input: "Type your message..."] [Send]        │
└─────────────────────────────────────────────────────┘
```

**Layout (Dedicated UI - Alternative):**
```
┌─────────────────────────────────────────────────────┐
│  📚 Search PubMed Articles                          │
├─────────────────────────────────────────────────────┤
│  [Search input: "diabetes treatment"]               │
│  [🔍 Search]                                        │
├─────────────────────────────────────────────────────┤
│  Results (5 articles):                              │
│  ┌─────────────────────────────────────────────┐   │
│  │ 📄 Metformin in Type 2 Diabetes...          │   │
│  │    Smith J, et al. | 2023                   │   │
│  │    Abstract preview...                      │   │
│  │    [Select Article]                         │   │
│  └─────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────┐   │
│  │ 📄 [Next article card...]                    │   │
│  └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

**Components:**
- **Chat Input (Primary):** User types search query in chat input field
- **Dedicated Search (Alternative):** `cl.text_input()` for keyword entry + `cl.button()` to trigger
- **Results Display in Chat:** 
  - Articles displayed as `cl.card()` or `cl.element()` within chat messages
  - Show: Title, Authors, Year, Abstract preview (truncated)
  - **DO NOT show PubMed ID** (internal only)
  - Each card has "Select Article" button
  - Cards appear as assistant messages in chat history
- **Loading State:** Show spinner/placeholder message in chat while searching
- **Error Handling:** Display error message in chat if search fails

**Placeholder Implementation:**
- Mock search results (3-5 hardcoded articles)
- Placeholder icons (📄, 🔍)
- "Search" button triggers mock results
- "Select Article" button shows success message

**Chainlit API Usage:**
```python
# Search input
search_query = await cl.AskUserMessage(
    content="Enter PubMed search keywords:",
    timeout=300
).send()

# Results display
for article in search_results:
    with cl.card():
        cl.text(f"**{article.title}**")
        cl.text(f"{article.authors} | {article.year}")
        cl.text(article.abstract_preview)
        cl.button("Select Article", action="select_article", value=article.id)
```

---

#### 2.2 PDF Upload Section

**Layout:**
```
┌─────────────────────────────────────────────────────┐
│  📁 Upload PDF Document                             │
├─────────────────────────────────────────────────────┤
│  [Drag & Drop Area or File Picker]                  │
│  Supported: PDF files only                          │
│  [Upload]                                           │
├─────────────────────────────────────────────────────┤
│  Uploaded Files:                                    │
│  • diabetes_guidelines_2023.pdf [Extract] [Remove] │
└─────────────────────────────────────────────────────┘
```

**Components:**
- **File Upload:** `cl.file_upload()` for PDF selection
- **Upload Button:** Trigger extraction
- **Uploaded Files List:** Show filename, status, actions
- **Progress Indicator:** Show extraction progress

**Placeholder Implementation:**
- File upload widget (may show "Not implemented" message)
- Mock uploaded file list
- "Extract" button shows placeholder message

**Chainlit API Usage:**
```python
# File upload
files = await cl.AskFileMessage(
    content="Upload a PDF document:",
    accept=["application/pdf"],
    max_files=1,
    timeout=300
).send()

# Display uploaded files
for file in uploaded_files:
    cl.text(f"📄 {file.name}")
    cl.button("Extract", action="extract_pdf", value=file.id)
```

---

#### 2.3 Ingested Sources List

**Layout:**
```
┌─────────────────────────────────────────────────────┐
│  📋 Ingested Sources (Last 5)                      │
├─────────────────────────────────────────────────────┤
│  1. Metformin in Type 2 Diabetes... (PubMed)       │
│     [View] [Extract Triplets]                      │
│  2. diabetes_guidelines_2023.pdf (PDF)              │
│     [View] [Extract Triplets]                      │
└─────────────────────────────────────────────────────┘
```

**Components:**
- List of recently ingested sources (max 5)
- Show source type (PubMed/PDF), title/filename
- Actions: View details, Extract triplets
- Link to triplet review after extraction

**Placeholder Implementation:**
- Hardcoded list of 2-3 mock sources
- Buttons show placeholder messages

---

### 3. Triplet Review Page (NEW - Critical)

**Layout:**
```
┌─────────────────────────────────────────────────────┐
│  🔍 Review Extracted Triplets                       │
│  Source: Metformin in Type 2 Diabetes...            │
├─────────────────────────────────────────────────────┤
│  Triplet 1 of 5                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │ Subject: Metformin                          │   │
│  │ Action: treats                              │   │
│  │ Object: Type 2 Diabetes                    │   │
│  │ Relation: TREATS                            │   │
│  │ ✅ Schema Valid                             │   │
│  ├─────────────────────────────────────────────┤   │
│  │ Provenance Evidence:                        │   │
│  │ "Metformin is the first-line treatment..."  │   │
│  │ "It works by reducing hepatic glucose..."   │   │
│  │ "Clinical trials have shown..."            │   │
│  ├─────────────────────────────────────────────┤   │
│  │ 📌 Provenance:                              │   │
│  │ Title: Metformin in Type 2 Diabetes...     │   │
│  │ Authors: Smith J, et al.                    │   │
│  │ PubMed ID: 12345678                          │   │
│  │ (OR if PDF: Filename: diabetes_guide.pdf)   │   │
│  ├─────────────────────────────────────────────┤   │
│  │ [✅ Accept] [❌ Reject] [✏️ Edit]           │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  [◀ Previous] [Next ▶]  [Accept All] [Reject All]   │
└─────────────────────────────────────────────────────┘
```

**Components:**
- **Triplet Card:**
  - Subject, Action, Object, Relation display
  - Schema validation badge (✅ Valid / ⚠️ Needs Review)
  - Context sentences in quote block (2-4 sentences)
  - Source metadata (ID, title, authors, year)
- **Actions per Triplet:**
  - **Accept:** Store in KB
  - **Reject:** Discard triplet
  - **Edit:** Open inline editor to modify subject/action/object before accepting
- **Navigation:**
  - Previous/Next buttons
  - Accept All / Reject All (bulk actions)
- **Progress Indicator:**
  - "Triplet X of Y"
  - Show count of accepted/rejected

**Placeholder Implementation:**
- Display 3-5 mock triplets with placeholder data
- Accept/Reject buttons show success messages
- No actual KB storage (placeholder)

**Chainlit API Usage:**
```python
# Triplet card
with cl.card():
    cl.text(f"**Subject:** {triplet.subject}")
    cl.text(f"**Action:** {triplet.action}")
    cl.text(f"**Object:** {triplet.object}")
    cl.text(f"**Relation:** {triplet.relation}")
    
    # Schema validation
    if triplet.schema_valid:
        cl.text("✅ Schema Valid")
    else:
        cl.text("⚠️ Needs Review")
    
    # Context sentences
    cl.text("**Provenance Evidence:**")
    for sentence in triplet.context_sentences:
        cl.text(f"> {sentence}")
    
    # Provenance Display
    cl.text("**📌 Provenance:**")
    cl.text(f"**Title:** {triplet.source_title}")
    cl.text(f"**Authors:** {triplet.source_authors}")
    if triplet.source_id.startswith("PMID"):
        cl.text(f"**PubMed ID:** {triplet.source_id.replace('PMID:', '')}")
    else:
        cl.text(f"**Filename:** {triplet.source_id}")
    
    # Actions
    cl.button("✅ Accept", action="accept_triplet", value=triplet.id)
    cl.button("❌ Reject", action="reject_triplet", value=triplet.id)
    cl.button("✏️ Edit", action="edit_triplet", value=triplet.id)
```

---

### 4. MCQ Review Page

**Layout (Chat-based Display with Dual MCQ Display):**
```
┌─────────────────────────────────────────────────────┐
│  Chat Display Area:                                 │
│  ┌─────────────────────────────────────────────┐   │
│  │ User: "Generate MCQ from article 1"        │   │
│  └─────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────┐   │
│  │ Assistant: Generated MCQ:                   │   │
│  │ ┌───────────────────────────────────────┐   │   │
│  │ │ 📝 Original MCQ                       │   │   │
│  │ │ Status: Pending                       │   │   │
│  │ │                                       │   │   │
│  │ │ Clinical Stem:                        │   │   │
│  │ │ "A 45-year-old patient with Type 2..."│   │   │
│  │ │                                       │   │   │
│  │ │ Question:                              │   │   │
│  │ │ "What is the first-line treatment?"   │   │   │
│  │ │                                       │   │   │
│  │ │ Options:                               │   │   │
│  │ │ A) Metformin                          │   │   │
│  │ │ B) Insulin                            │   │   │
│  │ │ C) Sulfonylurea                       │   │   │
│  │ │ D) GLP-1 Agonist                      │   │   │
│  │ │ E) DPP-4 Inhibitor                    │   │   │
│  │ │                                       │   │   │
│  │ │ ✅ Correct Answer: A) Metformin      │   │   │
│  │ │                                       │   │   │
│  │ │ 📌 Provenance:                        │   │   │
│  │ │ Title: Metformin in Type 2 Diabetes...│   │   │
│  │ │ Authors: Smith J, et al.              │   │   │
│  │ │ PubMed ID: 12345678                  │   │   │
│  │ │ Triplet: Metformin → treats → Type 2...│   │   │
│  │ │                                       │   │   │
│  │ │ 🎨 Optimized Visual Prompt:           │   │   │
│  │ │ [Display box with prompt text]        │   │   │
│  │ │ [Generate Image]                     │   │   │
│  │ │                                       │   │   │
│  │ │ 🖼️ Generated Image:                   │   │   │
│  │ │ [Image display box]                   │   │   │
│  │ │ Generate with: ○ ChatGPT 4o ● Gemini │   │   │
│  │ │ [Use This Image] [Regenerate] [Remove]│   │   │
│  │ └───────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────┐   │
│  │ User: "Add more clinical context to stem"   │   │
│  └─────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────┐   │
│  │ Assistant: Updated MCQ (LLM Generated):      │   │
│  │ ┌───────────────────────────────────────┐   │   │
│  │ │ 📝 Updated MCQ (LLM Generated)        │   │   │
│  │ │ Status: Pending Review               │   │   │
│  │ │                                       │   │   │
│  │ │ Clinical Stem:                        │   │   │
│  │ │ "A 45-year-old obese patient with     │   │   │
│  │ │  Type 2 Diabetes, HbA1c 8.5%,        │   │   │
│  │ │  presents with elevated glucose..."   │   │   │
│  │ │                                       │   │   │
│  │ │ Question:                              │   │   │
│  │ │ "What is the first-line treatment?"   │   │   │
│  │ │                                       │   │   │
│  │ │ Options:                               │   │   │
│  │ │ A) Metformin                          │   │   │
│  │ │ B) Insulin                            │   │   │
│  │ │ C) Sulfonylurea                       │   │   │
│  │ │ D) GLP-1 Agonist                      │   │   │
│  │ │ E) DPP-4 Inhibitor                    │   │   │
│  │ │                                       │   │   │
│  │ │ ✅ Correct Answer: A) Metformin      │   │   │
│  │ │                                       │   │   │
│  │ │ 📌 Provenance:                        │   │   │
│  │ │ Title: Metformin in Type 2 Diabetes...│   │   │
│  │ │ Authors: Smith J, et al.              │   │   │
│  │ │ PubMed ID: 12345678                  │   │   │
│  │ │ Triplet: Metformin → treats → Type 2...│   │   │
│  │ │                                       │   │   │
│  │ │ 🎨 Optimized Visual Prompt:           │   │   │
│  │ │ [Updated display box with prompt]    │   │   │
│  │ │ [Generate Image]                     │   │   │
│  │ │                                       │   │   │
│  │ │ 🖼️ Generated Image:                   │   │   │
│  │ │ [Image display box]                   │   │   │
│  │ │ Generate with: ○ ChatGPT 4o ● Gemini │   │   │
│  │ │ [Use This Image] [Regenerate] [Remove]│   │   │
│  │ │                                       │   │   │
│  │ │ Actions:                               │   │   │
│  │ │ [✅ Accept Update] [❌ Reject Update] │   │   │
│  │ │ [🔄 Request Another Update]            │   │   │
│  │ │ [↩️ Revert to Original]                │   │   │
│  │ └───────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────┘   │
│  [Chat input: "Type your message..."] [Send]        │
└─────────────────────────────────────────────────────┘
```

**Components:**
- **Original MCQ Display (First Display):**
  - Shows the initially generated MCQ
  - Clinical stem/vignette
  - Question text
  - 5 options (A-E)
  - Correct answer highlighted
  - All provenance, visual prompt, image sections
  - Actions: Edit MCQ, Regenerate MCQ, Approve, Reject
- **Updated MCQ Display (Second Display - When LLM Updates Requested):**
  - Appears when user requests additions/updates via chat
  - Shows LLM-generated updated version
  - Side-by-side or sequential comparison with original
  - Same structure as original (stem, question, options, provenance, etc.)
  - Actions: Accept Update, Reject Update, Request Another Update, Revert to Original
  - Visual indicator showing this is an "updated" version
- **Provenance Section (Display Box):**
  - **Title:** Literature/article title
  - **Authors:** Author names (e.g., "Smith J, et al.")
  - **Source ID:** PubMed ID (e.g., "12345678") OR Filename (e.g., "diabetes_guide.pdf") if uploaded
  - **Associated Triplet:** Subject → Action → Object
  - **Highlighted** to emphasize anti-hallucination
- **Optimized Visual Prompt Section (Display Box):**
  - **Display Box:** Shows the optimized visual prompt text (read-only or editable)
  - **Visual Triplet:** Subject-Action-Object for the visual concept
  - **Generate Image Button:** Explicit action to trigger image generation
- **Generated Image Section (Display Box):**
  - **Image Display Box:** Shows generated image when available
  - **LLM Selector for Image Generation:**
    - Radio buttons or toggle: "ChatGPT 4o" or "Gemini 2.5"
    - User selects which LLM to use for image generation
  - **Actions:**
    - "Use This Image" - Accept and store image with MCQ
    - "Regenerate" - Generate new image with selected LLM
    - "Remove" - Remove image from MCQ
- **Actions (Original MCQ):**
  - **Edit MCQ:** Open inline editor to modify stem, question, options
  - **Regenerate MCQ:** Trigger LLM to generate completely new MCQ (uses current LLM selection from header)
  - **Request Update/Addition:** User types in chat (e.g., "Add more clinical context", "Make question more specific") - triggers second display
  - **Approve:** Store MCQ in repository
  - **Reject:** Discard MCQ
- **Actions (Updated MCQ - Second Display):**
  - **Accept Update:** Replace original MCQ with updated version
  - **Reject Update:** Discard updated version, keep original
  - **Request Another Update:** Ask LLM to try different update/addition
  - **Revert to Original:** Go back to original MCQ, discard update

**Placeholder Implementation:**
- Display mock MCQ with placeholder data
- All buttons show placeholder messages
- No actual generation/storage

**Chainlit API Usage:**
```python
# Chat message handler - MCQ displayed in chat
@cl.on_message
async def on_message(message: cl.Message):
    if "generate mcq" in message.content.lower():
        # Display Original MCQ as assistant message in chat
        with cl.Message(content="Generated MCQ:", author="Assistant"):
            with cl.card():
                cl.text("**📝 Original MCQ**")
                cl.text("**Status:** Pending")
                
                cl.text("**Clinical Stem:**")
                cl.text(mcq.stem)
                
                cl.text("**Question:**")
                cl.text(mcq.question)
                
                cl.text("**Options:**")
                for i, option in enumerate(mcq.options, start=1):
                    marker = "✅" if i == mcq.correct_option else "  "
                    cl.text(f"{marker} {chr(64+i)}) {option}")
                
                # Provenance Display Box
                with cl.card():
                    cl.text("**📌 Provenance:**")
                    cl.text(f"**Title:** {mcq.source_title}")
                    cl.text(f"**Authors:** {mcq.source_authors}")
                    if mcq.source_id.startswith("PMID"):
                        cl.text(f"**PubMed ID:** {mcq.source_id.replace('PMID:', '')}")
                    else:
                        cl.text(f"**Filename:** {mcq.source_id}")
                    cl.text(f"**Triplet:** {mcq.triplet}")
                
                # Optimized Visual Prompt Display Box
                with cl.card():
                    cl.text("**🎨 Optimized Visual Prompt:**")
                    cl.text(mcq.visual_prompt)
                    cl.text(f"**Visual Triplet:** {mcq.visual_triplet}")
                    cl.button("Generate Image", action="generate_image", value=mcq.id)
                
                # Generated Image Display Box
                if mcq.generated_image_url:
                    with cl.card():
                        cl.text("**🖼️ Generated Image:**")
                        cl.image(mcq.generated_image_url)
                        
                        # LLM Selector for Image Generation
                        image_llm = cl.select(
                            "Generate with:",
                            options=["ChatGPT 4o", "Gemini 2.5"],
                            value=mcq.image_generation_llm or "ChatGPT 4o"
                        )
                        
                        cl.button("Use This Image", action="use_image", value=mcq.id)
                        cl.button("Regenerate", action="regenerate_image", value=mcq.id)
                        cl.button("Remove", action="remove_image", value=mcq.id)
                
                # Actions for Original MCQ
                cl.button("✏️ Edit MCQ", action="edit_mcq", value=mcq.id)
                cl.button("🔄 Regenerate MCQ", action="regenerate_mcq", value=mcq.id)
                cl.button("✅ Approve", action="approve_mcq", value=mcq.id)
                cl.button("❌ Reject", action="reject_mcq", value=mcq.id)
    
    elif any(keyword in message.content.lower() for keyword in ["update", "add", "modify", "change", "improve"]):
        # User requested update/addition - show second display
        updated_mcq = await request_llm_update(original_mcq, message.content)
        
        with cl.Message(content="Updated MCQ (LLM Generated):", author="Assistant"):
            with cl.card():
                cl.text("**📝 Updated MCQ (LLM Generated)**")
                cl.text("**Status:** Pending Review")
                
                cl.text("**Clinical Stem:**")
                cl.text(updated_mcq.stem)
                
                cl.text("**Question:**")
                cl.text(updated_mcq.question)
                
                cl.text("**Options:**")
                for i, option in enumerate(updated_mcq.options, start=1):
                    marker = "✅" if i == updated_mcq.correct_option else "  "
                    cl.text(f"{marker} {chr(64+i)}) {option}")
                
                # Provenance Display Box (same as original)
                with cl.card():
                    cl.text("**📌 Provenance:**")
                    cl.text(f"**Title:** {updated_mcq.source_title}")
                    cl.text(f"**Authors:** {updated_mcq.source_authors}")
                    if updated_mcq.source_id.startswith("PMID"):
                        cl.text(f"**PubMed ID:** {updated_mcq.source_id.replace('PMID:', '')}")
                    else:
                        cl.text(f"**Filename:** {updated_mcq.source_id}")
                    cl.text(f"**Triplet:** {updated_mcq.triplet}")
                
                # Optimized Visual Prompt Display Box
                with cl.card():
                    cl.text("**🎨 Optimized Visual Prompt:**")
                    cl.text(updated_mcq.visual_prompt)
                    cl.text(f"**Visual Triplet:** {updated_mcq.visual_triplet}")
                    cl.button("Generate Image", action="generate_image", value=updated_mcq.id)
                
                # Generated Image Display Box
                if updated_mcq.generated_image_url:
                    with cl.card():
                        cl.text("**🖼️ Generated Image:**")
                        cl.image(updated_mcq.generated_image_url)
                        
                        image_llm = cl.select(
                            "Generate with:",
                            options=["ChatGPT 4o", "Gemini 2.5"],
                            value=updated_mcq.image_generation_llm or "ChatGPT 4o"
                        )
                        
                        cl.button("Use This Image", action="use_image", value=updated_mcq.id)
                        cl.button("Regenerate", action="regenerate_image", value=updated_mcq.id)
                        cl.button("Remove", action="remove_image", value=updated_mcq.id)
                
                # Actions for Updated MCQ
                cl.button("✅ Accept Update", action="accept_update", value=updated_mcq.id)
                cl.button("❌ Reject Update", action="reject_update", value=updated_mcq.id)
                cl.button("🔄 Request Another Update", action="request_another_update", value=updated_mcq.id)
                cl.button("↩️ Revert to Original", action="revert_to_original", value=updated_mcq.id)
```

---

## Session State Management

**Key State Variables:**
```python
cl.user_session.set("llm_model", "chatgpt-4o")  # or "gemini-2.5"
cl.user_session.set("ingested_sources", [])      # List of source IDs
cl.user_session.set("pending_triplets", [])     # Triplets awaiting review
cl.user_session.set("current_mcq", None)        # Current MCQ being reviewed
cl.user_session.set("session_id", "session_123") # For agent pipeline
```

---

## User Flows

### Flow 1: PubMed Article → Triplet Extraction → Review → MCQ Generation

1. User on **Source Search/Upload** page
2. Enters keywords → Searches PubMed
3. Selects article → Triggers automatic extraction
4. **Triplet Review** page appears with extracted triplets
5. User reviews/accepts triplets
6. Navigates to **MCQ Review** page
7. Generates MCQ from approved triplets
8. Reviews MCQ → Approves/Rejects

### Flow 2: PDF Upload → Extraction → Review

1. User uploads PDF
2. PDF text extracted automatically
3. Triplets extracted
4. **Triplet Review** page appears
5. User accepts/rejects triplets
6. Proceeds to MCQ generation

### Flow 3: LLM Switching

1. User clicks LLM selector in header
2. Selects "Gemini 2.5" (or switches back to ChatGPT 4o)
3. Selection stored in session state
4. All subsequent agent calls use selected LLM
5. UI shows current selection

---

## Placeholder Implementation Strategy

### Phase 1: Skeleton UI (Current Focus)

**Goal:** Get all UI components visible with placeholder data and icons

**Tasks:**
1. Create main Chainlit app file: `chainlit_entry.py`
2. Set up page navigation (tabs or sidebar)
3. Implement header with LLM selector (placeholder)
4. Build Source Search/Upload page skeleton:
   - Search input + button (mock results)
   - PDF upload widget (mock upload)
   - Ingested sources list (hardcoded)
5. Build Triplet Review page skeleton:
   - Display 3-5 mock triplets
   - Provenance display box (Title, Authors, PubMed ID or Filename)
   - Accept/Reject/Edit buttons (show messages only)
6. Build MCQ Review page skeleton:
   - Display mock Original MCQ in chat
   - Display mock Updated MCQ (second display) when user requests update
   - Provenance display box (Title, Authors, PubMed ID or Filename)
   - Optimized Visual Prompt display box
   - Generated Image display box with LLM selector (ChatGPT 4o / Gemini 2.5)
   - Original MCQ actions: Edit MCQ, Regenerate MCQ, Approve, Reject (show messages only)
   - Updated MCQ actions: Accept Update, Reject Update, Request Another Update, Revert to Original (show messages only)
7. Add placeholder icons (📚, 📁, 🔍, ✅, ❌, etc.)

**No Backend Integration Yet:**
- No actual PubMed API calls
- No PDF extraction
- No agent pipeline calls
- No database operations
- All buttons show "Feature coming soon" or similar messages

---

## Chainlit 2.9.2 API Considerations

**Key Components to Use:**
- `cl.Message()` - For displaying content in chat
- `cl.card()` - For card layouts (articles, MCQs, triplets)
- `cl.button()` / `cl.action()` - For interactive buttons
- `cl.text_input()` - For text inputs (alternative to chat)
- `cl.file_upload()` - For file uploads (can be via chat or dedicated UI)
- `cl.select()` - For dropdowns (LLM selector)
- `cl.Sidebar()` - For navigation/settings
- `cl.user_session` - For state management
- `@cl.on_message` - **CRITICAL:** For handling chat input messages
- `@cl.action_callback` - For button callbacks
- **Chat Input:** Built-in Chainlit chat input at bottom (always available)
- **Chat Display:** Built-in Chainlit message display area (scrollable)

**Avoid Deprecated APIs:**
- Check Chainlit 2.9.2 documentation for current patterns
- Use async/await patterns
- Use `cl.AskUserMessage` for user input (if needed)

---

## File Structure

```
app/
  ui/
    chainlit_app.py          # Main Chainlit app
    components/
      header.py              # Header with LLM selector
      source_search.py       # PubMed search component
      pdf_upload.py          # PDF upload component
      triplet_review.py      # Triplet review component
      mcq_review.py          # MCQ review component
    utils/
      session_manager.py     # Session state helpers
chainlit_entry.py            # Entry point (runs chainlit)
```

---

## Next Steps After Skeleton UI

1. **Integrate PubMed API** - Replace mock search with real biopython calls
2. **Integrate PDF Extraction** - Add pypdf for text extraction
3. **Connect Agent Pipeline** - Wire up Google ADK agents
4. **Add Database Operations** - Store triplets and MCQs
5. **Implement Real Actions** - Make buttons functional

---

## Success Criteria for Skeleton UI

✅ Chat interface functional (input + display area)
✅ Chat message handler implemented (`@cl.on_message`)
✅ Articles displayed in chat format when searched
✅ Original MCQ displayed in chat format when generated
✅ Updated MCQ (second display) shown when user requests LLM updates/additions
✅ Both MCQ displays visible side-by-side or sequentially for comparison
✅ All 4 pages visible and navigable
✅ LLM selector in header (functional switching)
✅ Placeholder icons and mock data displayed
✅ All buttons present (Edit, Accept, Reject, Regenerate - show messages, no backend)
✅ Provenance display boxes show: Title, Authors, PubMed ID OR Filename
✅ Optimized Visual Prompt display box visible
✅ Generated Image display box with LLM selector (ChatGPT 4o / Gemini 2.5) visible
✅ Navigation between pages works
✅ Chat history scrollable and maintained
✅ UI is visually organized and clear
✅ Ready for backend integration

---

## Notes

- **Chainlit API Changes:** Previous implementation had issues with API changes. Use Chainlit 2.9.2 documentation as reference.
- **LLM Switching:** Must persist across page navigation (use session state).
- **Provenance Emphasis:** Always highlight provenance information to reinforce anti-hallucination goals.
- **Dark Mode:** Prefer dark mode if Chainlit supports it (check theme settings).

