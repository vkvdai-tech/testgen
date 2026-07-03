import streamlit as st
import time
import sqlite3
import re
from google import genai
from google.genai import types
from openai import OpenAI
import pdfplumber

# ==============================================================================
# 1. DATABASE LAYER (Self-Healing Cache Schema)
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
# 2. CONFIGURATION & CORE ACCESS
# ==============================================================================
st.set_page_config(page_title="UPSC Elite MCQ Factory", layout="wide")
st.title("🎯 UPSC GS Paper I Pure MCQ Generator")

ACCESS_PASSWORD = "Arjun_vasu"  # CHANGE THIS PASSWORD FOR SECURITY!

with st.sidebar:
    st.header("🔐 Access Setup")
    user_pass = st.text_input("Enter App Access Password", type="password")
    provider = st.selectbox("Select AI Provider", ["OpenAI (ChatGPT)", "Gemini (Google)"])
    user_api_key = st.text_input(f"Enter {provider} API Key", type="password")
    
if user_pass != ACCESS_PASSWORD:
    st.warning("Please enter the correct App Access Password in the sidebar to unlock.")
    st.stop()

if not user_api_key:
    st.info(f"Please provide your {provider} API Key to continue.")
    st.stop()

# ==============================================================================
# 3. HIGH-DIFFICULTY DISTRIBUTION MASTER PROMPT (60% Very Hard Mandate)
# ==============================================================================
MASTER_PROMPT = """
You are a Senior UPSC Civil Services Examination Paper Setter updated through the latest 2026 analytical trends. Your absolute mandate is to construct an exhaustive test pool matching this exact mathematical difficulty distribution:
- 60% VERY HARD / BRUTAL BOUNCERS: Questions requiring 3rd-order logical deductions, resolving functional conflicts between different provisions/acts, or analyzing obscure exceptions.
- 30% MEDIUM: Conceptual application questions with deceptive traps.
- 10% EASY: Core standard factual baseline questions.

CRITICAL STRUCTURAL RULES:
1. Anti-Coaching Trap Mechanics: Build distractors using convincing half-truths, misapplied timelines, or inverted operational conditions. Options must look exceptionally attractive but contain subtle, completely fatal logical flaws.
2. Structure: Every item must be a strict 4-option MCQ labeled (a), (b), (c), and (d). True/False structures are strictly FORBIDDEN.

Template Format:
Question: [Insert question statement here]
(a) [Option A]
(b) [Option B]
(c) [Option C]
(d) [Option D]
Answer: [Correct letter only, e.g., (b)]
Explanation: [Concise 3-4 sentence breakdown explicitly highlighting the logical trap designed to break pattern-matching habits]
Topic: [Specific syllabus micro-topic tag]

Leave exactly one blank line between questions. Do not output any introductory or concluding conversational padding.
"""

# ==============================================================================
# 4. ROBUST INLINE PROCESSING PIPELINE WITH DEDUPLICATION WINDOW
# ==============================================================================
def process_book_synchronously(book_id, chunks, fallback_topic_name, provider, api_key):
    total_chunks = len(chunks)
    progress_bar = st.progress(0.0)
    
    FORMAT_ROTATION = {
        1: "Strict Advanced Countable Formats ('How many statements are correct? Only one, Only two, All three, None'). (Target: VERY HARD)",
        2: "Strict Assertion-Reason Causal Logic Formats (Statement I and Statement II evaluation). (Target: VERY HARD)",
        3: "Strict 2026 Evidence-Inference Matrix Formats (Roman numeral configurations paired with numbered claims). (Target: VERY HARD / MEDIUM)",
        4: "Strict 4-option multi-statement combination pairs or complex standard matching configurations. (Target: MEDIUM / EASY)"
    }

    for index, chunk_text in enumerate(chunks):
        loop_counter = 1
        segment_history = []
        
        # Pull live global history directly from the DB at the start of each segment to kill duplicates completely
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT content FROM questions WHERE book_id = ?", (book_id,))
        global_history = cursor.fetchall()
        conn.close()
        
        compiled_history_text = "\n---\n".join([row[0] for row in global_history]) if global_history else "None"

        if len(chunk_text.strip()) < 50:
            st.warning(f"⚠️ Activating native core context fallback layer for topic: '{fallback_topic_name}'")
            chunk_context = f"Exhaustively map and generate questions targeting the elite-tier syllabus dimensions of: {fallback_topic_name}"
        else:
            st.write(f"📖 Processing Text Block {index+1} of {total_chunks}...")
            chunk_context = f"SOURCE MATERIAL SOURCE CONTEXT:\n{chunk_text}"

        while loop_counter <= 4:
            target_format = FORMAT_ROTATION.get(loop_counter, "Complex 4-option analytical UPSC MCQ.")
            
            current_prompt = (
                f"{chunk_context}\n\n"
                f"MANDATORY STYLE CONSTRAINT: Generate questions using exclusively this target structure: {target_format}\n"
                f"CRITICAL REPETITION BARRIER: Do NOT reuse the same historical provisions, legal articles, cases, or phrasing options from previous passes.\n"
                f"Review this global question log to avoid overlap and target completely different conceptual facets:\n"
                f"=== ALREADY GENERATED QUESTION BANK LOG ===\n"
                f"{compiled_history_text[:12000]}\n"
                f"===========================================\n\n"
                f"Generate the next elite question sequence now."
            )
            
            try:
                if provider == "OpenAI (ChatGPT)":
                    o_client = OpenAI(api_key=api_key)
                    response = o_client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": MASTER_PROMPT},
                            {"role": "user", "content": current_prompt}
                        ],
                        temperature=0.35  # Perfectly balanced to encourage brutal traps without prompt derailment
                    )
                    raw_text = response.choices[0].message.content
                else:
                    g_client = genai.Client(api_key=api_key)
                    response = g_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=current_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=MASTER_PROMPT,
                            temperature=0.35
                        )
                    )
                    raw_text = response.text

                if "SEGMENT_EXHAUSTED" in raw_text and loop_counter > 1:
                    break
                elif len(raw_text.strip()) < 50:
                    loop_counter += 1
                    continue
                else:
                    segment_history.append(raw_text)
                    
                    # Open separate localized file locks safely for transactions
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO questions (book_id, content) VALUES (?, ?)", (book_id, raw_text))
                    conn.commit()
                    conn.close()
                    
                    loop_counter += 1
                    time.sleep(1)

            except Exception as e:
                st.error(f"❌ Core API Process Exception: {str(e)}")
                loop_counter = 99
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
# 5. USER FLOW INTERFACE
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
            with st.spinner("Extracting layered text layout data..."):
                full_text = extract_robust_pdf_text(uploaded_file)
            
            if not full_text or len(full_text) < 10:
                chunks = ["OCR_FALLBACK_TRIGGER_EMPTY_TEXT_LAYER"]
            else:
                st.info(f"Parsed {len(full_text)} context characters. Splitting text channels...")
                chunk_size = 35000
                chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
            
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO books (filename, total_segments, status) VALUES (?, ?, 'pending')", (uploaded_file.name, len(chunks)))
            book_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            with st.spinner("Compiling ultra-hard UPSC questions... Please stay on this window."):
                process_book_synchronously(book_id, chunks, clean_topic_name, provider, user_api_key)
            st.success("Generation completed successfully!")
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
        st.write(f"Total entries loaded in DB: **{len(raw_rows)}**")
        
        compiled_questions = "\n\n".join([row[0] for row in raw_rows]) if raw_rows else ""
        full_output_bank = f"=== UPSC ELITE-TIER POOL FOR TOPIC: {clean_topic_name} ===\n\n{compiled_questions}"
        
        st.download_button(
            label="📥 Download Clean UPSC Bank (.txt)",
            data=full_output_bank,
            file_name=f"UPSC_Elite_{uploaded_file.name.replace('.pdf', '')}.txt",
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
