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
# 1. CACHE LAYER ARCHITECTURE
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
# 2. APPLICATION WORKSPACE CONFIGURATION
# ==============================================================================
st.set_page_config(page_title="UPSC Master Engine", layout="wide")
st.title("🎯 UPSC GS Paper I Pure MCQ Generator")

ACCESS_PASSWORD = "Arjun_vasu"  # CHANGE TO YOUR TARGET KEY

with st.sidebar:
    st.header("🔐 Access Setup")
    user_pass = st.text_input("Enter App Access Password", type="password")
    provider = st.selectbox("Select AI Provider", ["OpenAI (ChatGPT)", "Gemini (Google)", "Anthropic (Claude)"])
    
    anthropic_model = None
    if provider == "Anthropic (Claude)":
        anthropic_model = st.selectbox("Select Claude Architecture", ["claude-fable-5", "claude-opus-4-8"])
        
    user_api_key = st.text_input(f"Enter {provider} API Key", type="password")
    
if user_pass != ACCESS_PASSWORD:
    st.warning("Please provide valid access credentials to continue.")
    st.stop()

if not user_api_key:
    st.info(f"Please provide your {provider} API key to start the run.")
    st.stop()

# ==============================================================================
# 3. HIGH-DIFFICULTY BLUEPRINT SPECIFICATION
# ==============================================================================
MASTER_PROMPT = """
You are a Senior UPSC CSE Paper Setter. Your absolute mandate is to construct an exhaustive test pool matching this difficulty distribution:
- 60% BRUTAL BOUNCERS (Very Hard): 3rd-order conceptual reasoning or obscure structural exceptions.
- 30% MEDIUM: Conceptual application questions with high-yield distractors.
- 10% EASY: Core standard baseline validations.

CRITICAL INSTRUCTIONS:
1. Output strict 4-option MCQs labeled (a), (b), (c), and (d). True/False formats are strictly FORBIDDEN.
2. Build distractors using half-truths or context swaps that contain subtle, completely fatal logical flaws.

Template Output Structure:
Question: [Insert question statement here]
(a) [Option A]
(b) [Option B]
(c) [Option C]
(d) [Option D]
Answer: [Correct letter only, e.g., (b)]
Explanation: [Concise 3-4 sentence analytical breakdown explaining option validity and logical trap mechanics]
Topic: [Syllabus micro-topic tag]

Leave exactly one blank line between questions. No conversational padding or intro notes allowed.
"""

# ==============================================================================
# 4. TOKEN-OPTIMIZED GENERATION ENGINE
# ==============================================================================
def process_book_synchronously(book_id, chunks, fallback_topic_name, provider, api_key, anthropic_model_choice=None):
    total_chunks = len(chunks)
    progress_bar = st.progress(0.0)
    
    BASE_SYSTEM = "Senior UPSC CSE Paper Setter Mode. Output only clean plain-text questions according to the requested format instruction."

    # Compressed index dictionary to minimize input token processing limits
    FORMAT_RULES = {
        1: "Format: ASSERTION-REASON causal logic. Structure: 'Statement-I: [Fact] Statement-II: [Explanation] Both true and II correct explanation (a), both true but II not correct explanation (b), I true II false (c), I false II true (d)'. No 'since' or 'because' in statements.",
        2: "Format: MULTI-STATEMENT COUNTABLE. Structure: 'Consider statements: 1... 2... 3... How many statements are correct? (a) Only one (b) Only two (c) All three (d) None'. Avoid 'All three' as correct answer.",
        3: "Format: THREE-COLUMN MATCH MATRIX. Structure: 'Match Columns: Column A | Column B | Column C. How many pairs are correctly matched? (a) Only one pair (b) Only two pairs (c) All three pairs (d) None of the pairs'.",
        4: "Format: ADMINISTRATIVE SCENARIO / SITUATIONAL JUDGMENT. Structure: Describe an intricate governance deadlock testing functional exceptions or legal boundary execution. Question: 'In this context, which action is constitutionally valid?'",
        5: "Format: 2026 EVIDENCE-INFERENCE MATRIX. Structure: Present 3 facts (I, II, III) and 2 logical inferences (1, 2). Question: 'Which inferences logically follow? (a) 1 only (b) 2 only (c) Both 1 and 2 (d) Neither 1 nor 2'.",
        6: "Format: CHRONOLOGICAL SEQUENCE. Structure: Present 4 events/acts/procedural steps. Question: 'What is the correct chronological sequence? (a) 1->2->3->4...'.",
        7: "Format: APPLIED CURRENT AFFAIRS. Structure: Anchor stem in named policy/judgment. Test static underlying concept mechanics. No vague 'recently in news' lines.",
        8: "Format: TWO-COLUMN MATCH CLASSIC. Structure: Match List-I with List-II. 4 items per list. Use option grid combinations. 1 item must be the distinguishing factor.",
        9: "Format: PURE CONCEPTUAL ISOLATION. Structure: Question: 'Which statement best captures the exact operational legal boundary of [Concept Name]?'",
        10: "Format: NEGATIVE MARKING TRAP. Structure: (a) Correct concept/context, (b) Correct concept/wrong context, (c) Related concept, (d) Partially correct but wrong in this specific case.",
        11: "Format: PASSAGE-BASED COMPREHENSION. Structure: Provide real 3-8 line dense textual excerpt. Ask which inferences (1, 2, 3) follow using standard combinatorial choice patterns.",
        12: "Format: ANALYTICAL PROBABILITY. Structure: Question stem must evaluate relative weight or impact using 'MOST LIKELY consequence', 'LEAST LIKELY reason', or 'GREATEST IMPACT'."
    }

    for index, chunk_text in enumerate(chunks):
        chunk_context = f"THEME: {fallback_topic_name}" if len(chunk_text.strip()) < 50 else f"SOURCE CONTENT:\n{chunk_text}"
        st.write(f"📖 Processing Context Block {index+1} of {total_chunks}...")

        for format_id in range(1, 13):
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT content FROM questions WHERE book_id = ?", (book_id,))
            global_history = cursor.fetchall()
            conn.close()
            compiled_history = "\n---\n".join([row[0] for row in global_history]) if global_history else "None"

            target_rule = FORMAT_RULES.get(format_id)
            
            current_prompt = (
                f"{MASTER_PROMPT}\n\n"
                f"{chunk_context}\n\n"
                f"TASK MAPPING REQUIREMENT:\n{target_rule}\n\n"
                f"ANTI-REPETITION LOG (AVOID THESE CONCEPTS):\n{compiled_history[:10000]}\n\n"
                f"Output your questions directly now."
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
                        system=BASE_SYSTEM,
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
                st.error(f"❌ Execution failure at layout structure iteration {format_id}: {str(e)}")
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
# 5. WORKSPACE FRAMEWORK
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
            with st.spinner("Parsing layout structure..."):
                full_text = extract_robust_pdf_text(uploaded_file)
            
            if not full_text or len(full_text) < 10:
                chunks = ["OCR_FALLBACK_TRIGGER_EMPTY_TEXT_LAYER"]
            else:
                st.info(f"Parsed {len(full_text)} context characters. Setting memory channels...")
                chunk_size = 35000
                chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
            
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO books (filename, total_segments, status) VALUES (?, ?, 'pending')", (uploaded_file.name, len(chunks)))
            book_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            with st.spinner("Compiling structural variations... Please maintain active browser focus."):
                chosen_claude = anthropic_model if provider == "Anthropic (Claude)" else None
                process_book_synchronously(book_id, chunks, clean_topic_name, provider, user_api_key, chosen_claude)
            st.success("Compilation loops finished successfully!")
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
            st.success("App cache cleared successfully.")
            st.rerun()
