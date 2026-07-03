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

ACCESS_PASSWORD = "Arjun_vasu"  # CHANGE THIS PASSWORD FOR YOUR SECURITY!

with st.sidebar:
    st.header("🔐 Access Setup")
    user_pass = st.text_input("Enter App Access Password", type="password")
    provider = st.selectbox("Select AI Provider", ["OpenAI (ChatGPT)", "Gemini (Google)", "Anthropic (Claude)"])
    
    anthropic_model_choice = None
    if provider == "Anthropic (Claude)":
        anthropic_model_choice = st.selectbox("Select Claude Architecture", ["claude-fable-5", "claude-opus-4-8"])
        
    user_api_key = st.text_input(f"Enter {provider} API Key", type="password")
    
if user_pass != ACCESS_PASSWORD:
    st.warning("Please provide valid access credentials to continue.")
    st.stop()

if not user_api_key:
    st.info(f"Please provide your {provider} API key to start the run.")
    st.stop()

# ==============================================================================
# 3. HIGH-DIFFICULTY GLOBAL PAPER-SETTING FRAMEWORK
# ==============================================================================
MASTER_PROMPT = """
You are a Senior UPSC Civil Services Examination Paper Setter updated through the latest 2026 analytical trends. 
Your absolute mandate is to construct an exhaustive test pool from the provided text matching this exact difficulty distribution:
- 60% BRUTAL BOUNCERS (Very Hard): Requires 3rd-order logical deductions, complex exceptions, or practical functional deadlocks.
- 30% MEDIUM: Tricky conceptual application questions with high-yield distractors.
- 10% EASY: Core standard factual baseline validations.

CRITICAL FORMAT-MIXING DIRECTIONS:
You must review the source text and generate questions using a diverse mix of the following 12 core formats:
- FORMAT 1 (Direct/Standalone): One stem; one clear correct answer. (Includes 1A Positive, 1B Negative NOT/EXCEPT, 1C Definitional, 1D Category Sets).
- FORMAT 2 (Multi-Statement): 'Consider the following statements: 1... 2... 3...'. Sub-variants: 2A (Which is correct combo options), 2B (Which is incorrect), 2C (How many statements are correct - prefer 'Only one' or 'Only two' as answers). 
- FORMAT 3 (Assertion-Reason): 'Statement-I: [Factual claim]. Statement-II: [Causal explanation why I is true]'. Options: (a) Both correct and II is correct explanation, (b) Both correct but II is NOT correct explanation, (c) I correct II incorrect, (d) I incorrect II correct. No 'since' or 'because' within statements.
- FORMAT 4 (Two-Column Match): Match List-I with List-II using standard option combinations.
- FORMAT 5 (Three-Column Match Matrix): Match List-I, List-II, and List-III using a combination grid option (e.g., A-1-I, B-2-II...). High Priority.
- FORMAT 6 (Chronological Order): Sequence 4 historical events, acts, or procedural legislative steps.
- FORMAT 7 (Applied / Current Affairs): Anchor stem in named policy/judgment/scheme context. Test the static underlying concept mechanics.
- FORMAT 8 (Scenario-Based Situational Judgment): Place an elaborate legal dilemma or constitutional friction in the stem. Ask which outcome/action is legally valid. Root in legal correctness, not general ethics.
- FORMAT 9 (Spatial/Map Awareness): Text-based tracking of geographical boundaries, locations, regional river paths, or territorial jurisdictions.
- FORMAT 10 (Negative Marking Trap Logic): Intentionally design option (b) as a correct concept applied to the wrong context, and option (d) as true in general but wrong in this specific case.
- FORMAT 11 (Passage-Based Inference): Provide a real 3-8 line textual document excerpt. Ask which inferences (1, 2, 3) follow using standard choice combinations.
- FORMAT 12 (Analytical Probability): Evaluate significance or likelihood using 'MOST LIKELY consequence', 'LEAST LIKELY reason', or 'GREATEST IMPACT'.

OUTPUT TEMPLATE (Repeat for each question generated):
Question: [Insert question statement here]
(a) [Option A]
(b) [Option B]
(c) [Option C]
(d) [Option D]
Answer: [Correct letter only, e.g., (c)]
Explanation: [Concise 3-4 sentence analytical breakdown explicitly highlighting the logical trap designed to break pattern-matching habits]
Topic: [Specific syllabus micro-topic tag]

Leave exactly one blank line between questions. No conversational chatter or intro notes allowed.
"""

# ==============================================================================
# 4. EXPLICIT 12-FORMAT GENERATION ENGINE (Robust Timeout Fix Configuration)
# ==============================================================================
def process_book_synchronously(book_id, chunks, fallback_topic_name, provider, api_key, anthropic_model_string=None):
    total_chunks = len(chunks)
    progress_bar = st.progress(0.0)
    
    BASE_SYSTEM = "Senior UPSC CSE Paper Setter Mode. Output only clean plain-text questions according to the requested format instruction."

    BATCHED_FORMATS = {
        1: "Task: Generate 3 unique questions mixing FORMAT 1, FORMAT 2, and FORMAT 3. Ensure 60% are Very Hard bouncers.",
        2: "Task: Generate 3 unique questions mixing FORMAT 4, FORMAT 5, and FORMAT 6.",
        3: "Task: Generate 3 unique questions mixing FORMAT 7, FORMAT 8, and FORMAT 9.",
        4: "Task: Generate 3 unique questions mixing FORMAT 10, FORMAT 11, and FORMAT 12."
    }

    for index, chunk_text in enumerate(chunks):
        chunk_context = f"THEME: {fallback_topic_name}" if len(chunk_text.strip()) < 50 else f"SOURCE CONTENT:\n{chunk_text}"
        st.write(f"📖 Processing Context Block {index+1} of {total_chunks}...")

        for batch_id in range(1, 5):
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT content FROM questions WHERE book_id = ? ORDER BY id DESC LIMIT 3", (book_id,))
            recent_rows = cursor.fetchall()
            conn.close()
            
            history_hints = []
            for row in recent_rows:
                found_topics = re.findall(r"Topic:\s*(.*)", row[0])
                if found_topics:
                    history_hints.append(found_topics[-1])
            compiled_hints = ", ".join(set(history_hints)) if history_hints else "None"

            target_batch_rule = BATCHED_FORMATS.get(batch_id)
            
            current_prompt = (
                f"{MASTER_PROMPT}\n\n"
                f"{chunk_context}\n\n"
                f"CURRENT EXECUTION REQUIREMENT FOR THIS BATCH:\n{target_batch_rule}\n\n"
                f"ANTI-REPETITION CONSTRAINT MANDATE:\nDo NOT target or reuse these sub-topics/concepts: [{compiled_hints}]\n\n"
                f"Output your questions directly now."
            )
            
            raw_text = ""
            for retry_attempt in range(1, 4):
                try:
                    if provider == "OpenAI (ChatGPT)":
                        o_client = OpenAI(api_key=api_key)
                        response = o_client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[{"role": "system", "content": BASE_SYSTEM}, {"role": "user", "content": current_prompt}],
                            temperature=0.35
                        )
                        raw_text = response.choices[0].message.content
                    elif provider == "Gemini (Google)":
                        g_client = genai.Client(api_key=api_key)
                        response = g_client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=current_prompt,
                            config=types.GenerateContentConfig(system_instruction=BASE_SYSTEM, temperature=0.35)
                        )
                        raw_text = response.text
                    elif provider == "Anthropic (Claude)":
                        # FIXED: Injected an explicit 120-second timeout limit to hold socket state open safely
                        a_client = anthropic.Anthropic(api_key=api_key, timeout=120.0)
                        response = a_client.messages.create(
                            model=anthropic_model_string,
                            max_tokens=4000,
                            system=BASE_SYSTEM,
                            messages=[{"role": "user", "content": current_prompt}],
                            temperature=0.35
                        )
                        raw_text = response.content[0].text
                    
                    if len(raw_text.strip()) > 50:
                        break  
                        
                except Exception as api_err:
                    if retry_attempt == 3:
                        st.error(f"❌ Connection Dropped Permanently at Batch {batch_id}: {str(api_err)}")
                    else:
                        time.sleep(3)  # Adaptive delay backup frame

            if len(raw_text.strip()) > 50 and "SEGMENT_EXHAUSTED" not in raw_text:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO questions (book_id, content) VALUES (?, ?)", (book_id, raw_text))
                conn.commit()
                conn.close()
                time.sleep(1)
        
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
# 5. USER INTERFACE LAYER
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
    clean_topic_name = re.sub(r'[-_]', ' ', uploaded_file.name.replace('.pdf', '')).title()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, processed_segments, total_segments, status FROM books WHERE filename = ?", (uploaded_file.name,))
    book_record = cursor.fetchone()
    conn.close()

    if not book_record:
        if st.button("🚀 Start Generating UPSC Questions"):
            # Auto-Rectifier: Clears stale database blocks to prevent early locks
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM books")
            cursor.execute("DELETE FROM questions")
            conn.commit()
            conn.close()
            
            with st.spinner("Extracting text matrix layers..."):
                full_text = extract_robust_pdf_text(uploaded_file)
            
            if not full_text or len(full_text) < 10:
                chunks = ["OCR_FALLBACK_TRIGGER_EMPTY_TEXT_LAYER"]
            else:
                # FIXED: Lowered data chunk boundaries down to 8,000 to keep prompt loads optimized for Claude
                chunk_size = 8000
                chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
                st.info(f"Parsed {len(full_text)} characters into {len(chunks)} optimized chunks. Initializing processing...")
            
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO books (filename, total_segments, status) VALUES (?, ?, 'pending')", (uploaded_file.name, len(chunks)))
            book_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            with st.spinner("Compiling structural variations... Please keep this window open."):
                process_book_synchronously(book_id, chunks, clean_topic_name, provider, user_api_key, anthropic_model_choice)
            st.success("Compilation loop complete!")
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
        st.write(f"Total entries loaded in DB: **{len(raw_rows)}** item batches across all 12 explicit layouts.")
        
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
