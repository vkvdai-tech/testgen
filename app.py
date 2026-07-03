import streamlit as st
import time
import sqlite3
import re
from google import genai
from google.genai import types
from openai import OpenAI
import pdfplumber

# ==============================================================================
# 1. DATABASE LAYER 
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
# 2. SETUP & KEYS
# ==============================================================================
st.set_page_config(page_title="UPSC MCQ Factory", layout="wide")
st.title("🎯 UPSC GS Paper I Pure MCQ Generator")

ACCESS_PASSWORD = "Arjun_vasu"  # CHANGE THIS PASSWORD!

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
# 3. HIGH-DIFFICULTY UPSC EXTRACTION MASTER PROMPT (Brutal Standard Edition)
# ==============================================================================
MASTER_PROMPT = """
You are a Senior UPSC Civil Services Examination Paper Setter. Your absolute mandate is to design brutal, highly analytical, elite-tier MCQs that reward deep structural reasoning over memorization. 

CRITICAL EXAM CONSTRAINTS:
1. Maximum Analytical Depth: Frame questions that test the functional friction between concepts, hidden constitutional nuances, exceptions to standard rules, and complex multi-layered historical sequences.
2. Anti-Coaching Trap Mechanics: Avoid basic, surface-level factual recall. Craft distracting options (a, b, c, d) that use half-truths, misapplied constitutional articles, or inverted logic. One or two options must look incredibly attractive but contain subtle fatal flaws.
3. Strict Grounding: Every question must be defensibly derived from the provided context or core syllabus.

You must output strict 4-option multiple-choice questions labeled as (a), (b), (c), and (d). Do NOT generate True/False questions.

Template Format:
Question: [Insert question statement here]
(a) [Option A]
(b) [Option B]
(c) [Option C]
(d) [Option D]
Answer: [Correct letter only, e.g., (b)]
Explanation: [Concise 3-4 sentence analytical breakdown explaining the subtle logical trap and why the option is defensibly correct]
Topic: [Specific micro-topic syllabus tag]

Leave exactly one blank line between questions. Do not include introductory conversational text.
"""

# ==============================================================================
# 4. ROBUST INLINE PROCESSING PIPELINE
# ==============================================================================
def process_book_synchronously(book_id, chunks, fallback_topic_name, provider, api_key):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    FORMAT_ROTATION = {
        1: "1. Multi-Statement Classic AND 2. Countable Multi-Statement AND 3. Assertion-Reason.",
        2: "4. Match the Following 2-Column AND 5. Match the Following 3-Column Matrix.",
        3: "7. Scenario-Based / Situational Case Study AND 8. Definitional / Pure Conceptual Isolation.",
        4: "10. 2026 Evidence-Inference Matrix AND 12. Direct Fact Elimination."
    }

    total_chunks = len(chunks)
    progress_bar = st.progress(0.0)
    
    for index, chunk_text in enumerate(chunks):
        loop_counter = 1
        segment_history = []
        
        # If the layout extraction failed, switch to native model context engine instantly
        if len(chunk_text.strip()) < 50:
            st.warning(f"⚠️ Low character density detected. Using deep model training layers for topic: '{fallback_topic_name}'")
            chunk_context = f"Analyze and generate questions exhaustively mapping the entire standard core syllabus topic: {fallback_topic_name}"
        else:
            st.write(f"📖 Crunching Context Block {index+1} ({len(chunk_text)} characters loaded)...")
            chunk_context = f"SOURCE MATERIAL TEXT SECTOR:\n{chunk_text}"

        while loop_counter <= 4:
            target_format = FORMAT_ROTATION.get(loop_counter, "Standard 4-option complex UPSC MCQ.")
            current_prompt = (
            cursor.execute("SELECT content FROM questions WHERE book_id = ?", (book_id,))
        global_history = cursor.fetchall()
        compiled_history_text = "\n---\n".join([row[0] for row in global_history]) if global_history else "None"

        while loop_counter <= 4:
            target_format = FORMAT_ROTATION.get(loop_counter, "Standard 4-option complex UPSC MCQ.")
            
            current_prompt = (
                f"{chunk_context}\n\n"
                f"MANDATORY PATTERN RULE: Generate questions using exclusively this target format: {target_format}\n"
                f"CRITICAL ANTI-REPETITION CONSTRAINT:\n"
                f"You are STRICTLY FORBIDDEN from repeating any historical themes, constitutional articles, core concepts, or option phrasing from previous loops.\n"
                f"Review this list of questions already generated for this run and ensure your new questions target completely different sub-topics and different logical angles:\n"
                f"=== ALREADY GENERATED QUESTIONS TO AVOID ===\n"
                f"{compiled_history_text[:12000]}\n"  # Feeds a safe memory slice of history back to block loops
                f"============================================\n\n"
                f"Execute elite question generation now."
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
                        temperature=0.3
                    )
                    raw_text = response.choices[0].message.content
                else:
                    g_client = genai.Client(api_key=api_key)
                    response = g_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=current_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=MASTER_PROMPT,
                            temperature=0.3
                        )
                    )
                    raw_text = response.text

                # Clean up empty responses or breaks
                if "SEGMENT_EXHAUSTED" in raw_text and loop_counter > 1:
                    break
                elif len(raw_text.strip()) < 50:
                    # Retry one variance loop layer instead of exiting empty
                    loop_counter += 1
                    continue
                else:
                    segment_history.append(raw_text)
                    cursor.execute("INSERT INTO questions (book_id, content) VALUES (?, ?)", (book_id, raw_text))
                    conn.commit()
                    loop_counter += 1
                    time.sleep(1)

            except Exception as e:
                st.error(f"❌ API Connection Drop: {str(e)}")
                loop_counter = 99
                break
        
        progress_bar.progress((index + 1) / total_chunks)

    cursor.execute("UPDATE books SET processed_segments = ?, status = 'completed' WHERE id = ?", (total_chunks, book_id))
    conn.commit()
    conn.close()

# ==============================================================================
# 5. USER FLOW INTERFACE
# ==============================================================================
def extract_robust_pdf_text(uploaded_pdf):
    text = ""
    with pdfplumber.open(uploaded_pdf) as pdf:
        for page in pdf.pages:
            # layout=True keeps columns aligned perfectly
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

    # Derived topic baseline fallback name from the file name string directly
    clean_topic_name = re.sub(r'[-_]', ' ', uploaded_file.name.replace('.pdf', '')).title()

    if not book_record:
        if st.button("🚀 Start Generating UPSC Questions"):
            with st.spinner("Extracting layout text matrix..."):
                full_text = extract_robust_pdf_text(uploaded_file)
            
            # Setup container fallback chunk array if parser returns completely blank characters
            if not full_text or len(full_text) < 10:
                chunks = ["OCR_FALLBACK_TRIGGER_EMPTY_TEXT_LAYER"]
            else:
                st.info(f"Extracted {len(full_text)} characters. Formatting context buckets...")
                chunk_size = 35000
                chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
            
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO books (filename, total_segments, status) VALUES (?, ?, 'pending')", (uploaded_file.name, len(chunks)))
            book_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            with st.spinner("Processing questions sequentially through OpenAI systems..."):
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
        full_output_bank = f"=== UPSC EXAM POOL FOR TOPIC: {clean_topic_name} ===\n\n{compiled_questions}"
        
        st.download_button(
            label="📥 Download Clean UPSC Bank (.txt)",
            data=full_output_bank,
            file_name=f"UPSC_{uploaded_file.name.replace('.pdf', '')}.txt",
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
            st.success("Engine reset ready.")
            st.rerun()
