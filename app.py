import streamlit as st
import time
import sqlite3
import re
from google import genai
from google.genai import types
from openai import OpenAI
import anthropic  
import pdfplumber

# ==============================================================================
# 1. DATABASE LAYER (Self-Healing Sequential Operational Cache)
# ==============================================================================
DB_FILE = "upsc_platform_simple.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE,
            total_segments INTEGER,
            processed_segments INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER,
            content TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ==============================================================================
# 2. CONFIGURATION & CORE SETUP
# ==============================================================================
st.set_page_config(page_title="UPSC 12-Format Master Factory", layout="wide")
st.title("🎯 UPSC GS Paper I Pure MCQ Generator")

ACCESS_PASSWORD = "Arjun_vasu"  # CHANGE THIS PASSWORD FOR YOUR APPLICATION

with st.sidebar:
    st.header("🔐 Access Setup")
    user_pass = st.text_input("Enter App Access Password", type="password")
    
    provider = st.selectbox(
        "Select AI Provider", 
        ["OpenAI (ChatGPT)", "Gemini (Google)", "Anthropic (Claude)"]
    )
    
    anthropic_model = None
    if provider == "Anthropic (Claude)":
        anthropic_model = st.selectbox("Select Claude Architecture", ["claude-fable-5", "claude-opus-4-8"])
        
    user_api_key = st.text_input(f"Enter {provider} API Key", type="password")
    
if user_pass != ACCESS_PASSWORD:
    st.warning("Please enter the correct App Access Password in the sidebar to unlock.")
    st.stop()

if not user_api_key:
    st.info(f"Please provide your {provider} API Key to continue.")
    st.stop()

# ==============================================================================
# 3. HIGH-DIFFICULTY GLOBAL PAPER-SETTING FRAMEWORK
# ==============================================================================
MASTER_PROMPT = """
You are a Senior UPSC Civil Services Examination Paper Setter updated through the latest 2026 analytical trends. Your absolute mandate is to construct an exhaustive test pool matching this exact mathematical difficulty distribution:
- 60% BRUTAL BOUNCERS (Very Hard): Requires 3rd-order logical deductions, resolving functional friction between different provisions/acts, or analyzing obscure structural exceptions.
- 30% MEDIUM: Tricky conceptual application questions with high-yield distractors.
- 10% EASY: Core standard factual baseline validations.

CRITICAL QUALITY ASSURANCE RULES:
1. Every item must be a strict 4-option MCQ labeled (a), (b), (c), and (d). True/False structures or bare statement listings are strictly FORBIDDEN.
2. Build distractors using convincing half-truths, close-synonym traps, context swaps, or misapplied timelines. Options must look exceptionally attractive but contain subtle, completely fatal logical flaws.
3. Grounding: Rely ONLY on facts explicitly mentioned in the source material text or core syllabus theme. Do not use external data filler or invent non-existent quotes.

Template Output Structure:
Question: [Insert question text here]
(a) [Option A]
(b) [Option B]
(c) [Option C]
(d) [Option D]
Answer: [Correct letter only, e.g., (b)]
Explanation: [Concise 3-4 sentence breakdown explicitly highlighting the logical trap designed to break pattern-matching habits and explain option validity]
Topic: [Specific syllabus micro-topic tag]

Leave exactly one blank line between questions. Do not output any introductory or concluding conversational padding or notes.
"""

# ==============================================================================
# 4. EXPLICIT 12-FORMAT GENERATION PIPELINE ENGINE (Total Isolated Frameworks)
# ==============================================================================
def process_book_synchronously(book_id, chunks, fallback_topic_name, provider, api_key, anthropic_model_choice=None):
    total_chunks = len(chunks)
    progress_bar = st.progress(0.0)
    
    BASE_SYSTEM = (
        "You are a Senior UPSC CSE Paper Setter. Generate ultra-hard conceptual questions based "
        "STRICTLY on the text block or topic provided. Deliver only clean, plain text blocks using the explicit structure assigned."
    )

    # Dictionary containing all 12 distinct civil services question variations from your precise structural checklist
    FORMAT_BLUEPRINTS = {
        1: (
            "CRITICAL FORMAT RULE: You must generate a FORMAT 1: DIRECT / STANDALONE question.\n"
            "Ensure distractors are specifically wrong in a testable way, containing recognizable concepts that an unprepared aspirant would consider plausible.\n"
            "You can choose variant 1A (Positive Direct), 1B (Negative Direct using NOT/EXCEPT), 1C (Definitional), or 1D (Correct Set/Pair Pairings).\n"
            "Follow the standard template format structure exactly."
        ),
        2: (
            "CRITICAL FORMAT RULE: You must generate a FORMAT 2A/2B/2C: MULTI-STATEMENT question.\n"
            "Structure exactly like this:\n"
            "Question: Consider the following statements:\n1. [Statement 1 - Near truth trap, plausible on the surface but wrong in one key detail]\n2. [Statement 2]\n3. [Statement 3]\n"
            "Choose a variant sub-style: 'Which of the statements given above is/are correct?', 'Which of the statements given above is/are INCORRECT?', or 'How many of the statements given above are correct?'.\n"
            "Constraint: Never make all statements correct or all incorrect. For 'how many correct', avoid 'All three' as the correct answer option choice."
        ),
        3: (
            "CRITICAL FORMAT RULE: You must generate a FORMAT 3: ASSERTION-REASON causal logic question.\n"
            "You must evaluate the causal relationship between two statements without using 'since' or 'because' within the statement text. Follow this options grid structure EXACTLY:\n\n"
            "Question: Statement-I: [Factual/empirical or constitutional claim about a phenomenon]\n"
            "Statement-II: [Causal/explanatory claim about why Statement-I is true]\n"
            "Which one of the following is correct in respect of the above statements?\n"
            "(a) Both Statement-I and Statement-II are correct and Statement-II is the correct explanation of Statement-I\n"
            "(b) Both Statement-I and Statement-II are correct but Statement-II is NOT the correct explanation of Statement-I\n"
            "(c) Statement-I is correct but Statement-II is incorrect\n"
            "(d) Statement-I is incorrect but Statement-II is correct"
        ),
        4: (
            "CRITICAL FORMAT RULE: You must generate a FORMAT 4: MATCH THE FOLLOWING (Two-Column) question.\n"
            "Structure exactly like this:\n"
            "Question: Match List-I with List-II:\n"
            "List-I | List-II\n"
            "A. [Term/Event 1] | 1. [Description 1]\n"
            "B. [Term/Event 2] | 2. [Description 2]\n"
            "C. [Term/Event 3] | 3. [Description 3]\n"
            "D. [Term/Event 4] | 4. [Description 4]\n"
            "Choose the correct answer from the options given below:\n"
            "    A  B  C  D\n"
            "(a) 1  2  3  4\n"
            "(b) 2  3  4  1\n"
            "(c) 3  4  1  2\n"
            "(d) 4  1  2  3\n"
            "Constraint: Design options so that 2-3 matches are likely known, and 1 is the distinguishing factor requiring concept reasoning."
        ),
        5: (
            "CRITICAL FORMAT RULE: You must generate a FORMAT 5: THREE-COLUMN MATCH THE FOLLOWING question.\n"
            "Structure exactly like this:\n"
            "Question: Match List-I, List-II, and List-III:\n"
            "List-I | List-II | List-III\n"
            "A. [Item A1] | 1. [Item B1] | I. [Item C1]\n"
            "B. [Item A2] | 2. [Item B2] | II. [Item C2]\n"
            "C. [Item A3] | 3. [Item B3] | III. [Item C3]\n"
            "D. [Item A4] | 4. [Item B4] | IV. [Item C4]\n"
            "Which of the following combinations is correct?\n"
            "(a) A-1-I, B-2-II, C-3-III, D-4-IV\n"
            "(b) A-2-III, B-1-IV, C-4-I, D-3-II\n"
            "(c) A-3-II, B-4-I, C-1-IV, D-2-III\n"
            "(d) A-4-IV, B-3-III, C-2-II, D-1-I"
        ),
        6: (
            "CRITICAL FORMAT RULE: You must generate a FORMAT 6: CHRONOLOGICAL / SEQUENCE QUESTION.\n"
            "Choose either Format A (Pure Chronology of acts/developments) or Format B (Procedural sequence steps). Follow this configuration schema layout:\n"
            "Question: Consider the following developments:\n1. [Item 1]\n2. [Item 2]\n3. [Item 3]\n4. [Item 4]\n"
            "What is the correct chronological order or representation sequence of the above?\n"
            "(a) 1 -> 2 -> 3 -> 4\n(b) 3 -> 1 -> 4 -> 2\n(c) 2 -> 4 -> 1 -> 3\n(d) 1 -> 3 -> 2 -> 4"
        ),
        7: (
            "CRITICAL FORMAT RULE: You must generate a FORMAT 7: APPLIED / CURRENT AFFAIRS LINKED QUESTION.\n"
            "Anchor the stem in a real policy development, Supreme Court judgment, international treaty, or named legislative event from the text material.\n"
            "Structure using sub-variants 7A (News Anchor + Static Concept), 7B (Concept Application to Real Scenario), or 7C ('Which provision/act governs this situation').\n"
            "Constraint: Always use real, explicit event names - no vague 'recently in news' text lines."
        ),
        8: (
            "CRITICAL FORMAT RULE: You must generate a FORMAT 8: SCENARIO-BASED / SITUATIONAL JUDGMENT (2026 trend).\n"
            "Place a real-world governance dilemma, administrative conflict, or legal paradox in the stem. Do NOT ask it as an ethical choice; root it entirely in legal/constitutional correctness.\n"
            "Structure exactly like this:\n"
            "Question: [Elaborate a contextual scenario tracking executive powers or fundamental rights friction]. In the above context, which of the following actions/conclusions is the most constitutionally/legally appropriate?\n"
            "(a) [Legally correct but contextually nuanced option]\n"
            "(b) [Plausible but constitutionally overreaching option]\n"
            "(c) [Procedurally reasonable but legally incorrect option]\n"
            "(d) [Common-sense answer that misapplies the legal framework]"
        ),
        9: (
            "CRITICAL FORMAT RULE: You must generate a FORMAT 9: MAP-BASED / SPATIAL CONCEPTUAL QUESTION.\n"
            "Test spatial awareness, borders, environmental features, National Parks, or regional treaty zones through text-based multi-statement descriptions.\n"
            "Structure using either sub-style variants 9A (Location Identification), 9B (Spatial Relationship matrices), or 9C (Current Geography Linkages)."
        ),
        10: (
            "CRITICAL FORMAT RULE: You must generate a FORMAT 10: NEGATIVE MARKING TRAP question.\n"
            "This question must be explicitly engineered to punish over-confident guessing via context loops. Follow this design logic layout:\n"
            "Question: Which one of the following statements about [Target Concept] is correct?\n"
            "(a) [Correct concept applied to correct context]\n"
            "(b) [Correct concept applied to wrong context - primary distractor]\n"
            "(c) [Related but different concept, described accurately - secondary distractor]\n"
            "(d) [Partially correct - true in general, wrong in this specific case - tertiary distractor]"
        ),
        11: (
            "CRITICAL FORMAT RULE: You must generate a FORMAT 11: PASSAGE-BASED QUESTION.\n"
            "Extract or compile a strict 3-8 line dense textual excerpt from a legal provision, act, or historic declaration. Follow this layout design exactly:\n"
            "Question: Read the following passage:\n'[Insert 3-8 line analytical passage text excerpt]'\nWith reference to the above passage, which of the following inferences is/are correct?\n"
            "1. [Inference A - directly verifiable from text]\n2. [Inference B - requires reading between lines logical deduction]\n3. [Inference C - plausible but unsupported trap going beyond text]\n"
            "Options choices:\n(a) 1 only\n(b) 2 only\n(c) 1 and 2 only\n(d) 1, 2 and 3"
        ),
        12: (
            "CRITICAL FORMAT RULE: You must generate a FORMAT 12: 'WHICH IS LEAST/MOST LIKELY' ANALYTICAL question.\n"
            "Test relative conceptual impact significance or macroeconomic/political probabilities rather than static factual recall.\n"
            "Structure the question stem explicitly using parameters like: 'With reference to [X], which of the following is the MOST LIKELY consequence of [Y]?', 'Which of the following is the LEAST LIKELY reason for [Z]?', or 'Which one of the following would have the GREATEST IMPACT on [outcome]?'"
        )
    }

    # Iterate through chunks dynamically
    for index, chunk_text in enumerate(chunks):
        if len(chunk_text.strip()) < 50:
            chunk_context = f"CORE SYLLABUS DOMAIN THEME: {fallback_topic_name}"
        else:
            st.write(f"📖 Processing Source Segment Block {index+1} of {total_chunks}...")
            chunk_context = f"SOURCE MATERIAL CONTENT ZONE:\n{chunk_text}"

        # Sequentially map all 12 distinct format identifiers
        for format_id in range(1, 13):
            
            # Fetch ongoing global history directly to lock down duplicates
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT content FROM questions WHERE book_id = ?", (book_id,))
            global_history = cursor.fetchall()
            conn.close()
            compiled_history = "\n---\n".join([row[0] for row in global_history]) if global_history else "None"

            isolated_format_rule = FORMAT_BLUEPRINTS.get(format_id)
            
            current_prompt = (
                f"{chunk_context}\n\n"
                f"{isolated_format_rule}\n\n"
                f"ANTI-REPETITION CONSTRAINT MANDATE:\n"
                f"You are forbidden from generating questions targeting the same items, clauses, or core phrases as previous outputs.\n"
                f"Review your historical logging windows and ensure your output focuses on alternative sub-topics or unique conceptual angles:\n"
                f"=== LOG OF PAST EXTRACTED QUESTIONS (AVOID) ===\n"
                f"{compiled_history[:16000]}\n"
                f"================================================\n\n"
                f"Generate your isolated clean question structure payload block now."
            )
            
            try:
                if provider == "OpenAI (ChatGPT)":
                    o_client = OpenAI(api_key=api_key)
                    response = o_client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": BASE_SYSTEM}, {"role": "user", "content": current_prompt}],
                        temperature=0.3
                    )
                    raw_text = response.choices[0].message.content
                elif provider == "Gemini (Google)":
                    g_client = genai.Client(api_key=api_key)
                    response = g_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=current_prompt,
                        config=types.GenerateContentConfig(system_instruction=BASE_SYSTEM, temperature=0.3)
                    )
                    raw_text = response.text
                elif provider == "Anthropic (Claude)":
                    a_client = anthropic.Anthropic(api_key=api_key)
                    response = a_client.messages.create(
                        model=anthropic_model_choice,
                        max_tokens=4000,
                        system=BASE_SYSTEM + "\n\n" + MASTER_PROMPT,
                        messages=[{"role": "user", "content": current_prompt}],
                        temperature=0.3
                    )
                    raw_text = response.content[0].text

                if len(raw_text.strip()) > 50 and "SEGMENT_EXHAUSTED" not in raw_text:
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO questions (book_id, content) VALUES (?, ?)", (book_id, raw_text))
                    conn.commit()
                    conn.close()
                    time.sleep(1)

            except Exception as e:
                st.error(f"❌ Structural Execution Exception at Format {format_id}: {str(e)}")
                break
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE books SET processed_segments = ? WHERE id = ?", (index + 1, book_id))
        conn.commit()
        conn.close()
        progress_bar.progress((index + 1) / total_chunks)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE books SET status = 'completed' WHERE id = ?", (book_id,))
    conn.commit()
    conn.close()

# ==============================================================================
# 5. USER INTERFACE VIEW
# ==============================================================================
def extract_robust_pdf_text(uploaded_pdf):
    text = ""
    with pdfplumber.open(uploaded_pdf) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text(layout=True)
            if page_text:
                text += page_text + "\n"
    return text.strip()

uploaded_file = st.file_uploader("Upload Topic / Chapter PDF", type=["pdf"])

if uploaded_file:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, processed_segments, total_segments, status FROM books WHERE filename = ?", (uploaded_file.name,))
    book_record = cursor.fetchone()
    conn.close()

    clean_topic_name = re.sub(r'[-_]', ' ', uploaded_file.name.replace('.pdf', '')).title()

    if not book_record:
        if st.button("🚀 Start Generating UPSC Questions"):
            with st.spinner("Extracting multi-column text vectors..."):
                full_text = extract_robust_pdf_text(uploaded_file)
            
            if not full_text or len(full_text) < 10:
                chunks = ["OCR_FALLBACK_TRIGGER_EMPTY_TEXT_LAYER"]
            else:
                st.info(f"Parsed {len(full_text)} characters. Initializing structural layout passes...")
                chunk_size = 35000
                chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
            
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO books (filename, total_segments, status) VALUES (?, ?, 'pending')", (uploaded_file.name, len(chunks)))
            book_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            with st.spinner("Executing full 12-Format sequential processing loop... This will build all variants."):
                chosen_claude = anthropic_model if provider == "Anthropic (Claude)" else None
                process_book_synchronously(book_id, chunks, clean_topic_name, provider, user_api_key, chosen_claude)
            st.success("12-Format compilation loop completed successfully!")
            st.rerun()
    else:
        book_id, processed, total, status = book_record
        st.write("---")
        
        conn_live = sqlite3.connect(DB_FILE)
        cur_live = conn_live.cursor()
        cur_live.execute("SELECT content FROM questions WHERE book_id = ? ORDER BY id ASC", (book_id,))
        raw_rows = cur_live.fetchall()
        conn_live.close()
        
        st.write(f"📖 **Topic Baseline:** {clean_topic_name} | Status: **{status.upper()}**")
        st.write(f"Total entries loaded in DB: **{len(raw_rows)}** items across 12 explicit layouts.")
        
        compiled_questions = "\n\n".join([row[0] for row in raw_rows]) if raw_rows else ""
        full_output_bank = f"=== UPSC 12-FORMAT EXHAUSTIVE POOL FOR TOPIC: {clean_topic_name} ===\n\n{compiled_questions}"
        
        st.download_button(
            label="📥 Download Clean UPSC Bank (.txt)",
            data=full_output_bank,
            file_name=f"UPSC_12Format_Elite_{uploaded_file.name.replace('.pdf', '')}.txt",
            mime="text/plain",
            disabled=(len(raw_rows) == 0)
        )
            
        st.write("---")
        if st.button("🔄 Reset Engine for New Topic"):
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM books")
            cursor.execute("DELETE FROM questions")
            conn.commit()
            conn.close()
            st.success("Engine successfully cleared and reset.")
            st.rerun()
