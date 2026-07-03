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
# 2. CONFIGURATION & CORE ACCESS
# ==============================================================================
st.set_page_config(page_title="UPSC Elite MCQ Factory v4", layout="wide")
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
# 3. HIGH-DIFFICULTY BLUEPRINT (Bans Conversational Padding)
# ==============================================================================
MASTER_PROMPT = """
You are a Senior UPSC Civil Services Examination Paper Setter updated through the latest 2026 trends. Your absolute mandate is to construct an exhaustive test pool matching this exact mathematical difficulty distribution:
- 60% BRUTAL BOUNCERS (Very Hard): Multi-layer conceptual reasoning, obscure structural exceptions, or complex functional interactions.
- 30% MEDIUM: Tricky conceptual application questions with high-yield distractors.
- 10% EASY: Core standard factual baseline validations.

CRITICAL INSTRUCTIONS:
1. Every item must be a strict 4-option MCQ labeled (a), (b), (c), and (d). True/False formats are strictly FORBIDDEN.
2. Build distractors using convincing half-truths or misapplied timelines. Options must look exceptionally attractive but contain subtle, completely fatal logical flaws.

Template Output Structure:
Question: [Insert question text here]
(a) [Option A]
(b) [Option B]
(c) [Option C]
(d) [Option D]
Answer: [Correct letter only, e.g., (c)]
Explanation: [Concise 3-4 sentence breakdown explicitly highlighting the logical trap designed to break pattern-matching habits]
Topic: [Specific syllabus micro-topic tag]

Leave exactly one blank line between questions. Do not output any introductory or concluding conversational padding.
"""

# ==============================================================================
# 4. STRICT DYNAMIC MODEL ENFORCEMENT LOOP (Fixes Format Skippage)
# ==============================================================================
def process_book_synchronously(book_id, chunks, fallback_topic_name, provider, api_key):
    total_chunks = len(chunks)
    progress_bar = st.progress(0.0)
    
    # HARDCODED TEMPLATE ENFORCERS - Forces the AI to use different architectures per loop pass
    FORMAT_BLUEPRINTS = {
        1: (
            "CRITICAL FORMAT RULE: Every question in this batch MUST be an Assertion-Reason (Causal Logic) format.\n"
            "Structure structure exactly like this:\n"
            "Question: Statement I: [Assertion Text]. Statement II: [Reasoning Text]. Which one of the following is correct?\n"
            "(a) Both Statement I and Statement II are correct and Statement II is the correct explanation for Statement I\n"
            "(b) Both Statement I and Statement II are correct but Statement II is not the correct explanation for Statement I\n"
            "(c) Statement I is correct but Statement II is incorrect\n"
            "(d) Statement I is incorrect but Statement II is correct"
        ),
        2: (
            "CRITICAL FORMAT RULE: Every question in this batch MUST follow the 2024-2026 Three-Column Match Matrix layout.\n"
            "Structure exactly like this:\n"
            "Question: Consider the following columns:\n"
            "Column A (Term) | Column B (Provisions) | Column C (Constitutional Article/Year)\n"
            "1. [Item A] | [Provision A] | [Article A]\n"
            "2. [Item B] | [Provision B] | [Article B]\n"
            "3. [Item C] | [Provision C] | [Article C]\n"
            "How many of the pairs given above are correctly matched?\n"
            "(a) Only one pair\n"
            "(b) Only two pairs\n"
            "(c) All three pairs\n"
            "(d) None of the pairs"
        ),
        3: (
            "CRITICAL FORMAT RULE: Every question in this batch MUST follow the strict 2026 Administrative/Situational Scenario format.\n"
            "Structure exactly like this:\n"
            "Question: [Frame a complex situational scenario or governance deadlock testing the practical execution/tradeoffs of the legal principles discussed in the text]. In this context, which of the following actions is legally or constitutionally valid?\n"
            "(a) [Option A]\n"
            "(b) [Option B]\n"
            "(c) [Option C]\n"
            "(d) [Option D]"
        ),
        4: (
            "CRITICAL FORMAT RULE: Every question in this batch MUST follow the strict 2026 Evidence-Inference Matrix configuration.\n"
            "Structure exactly like this:\n"
            "Question: Consider the following claims based on the text:\n"
            "I. [Fact statement I]\n"
            "II. [Fact statement II]\n"
            "III. [Fact statement III]\n"
            "Based on the above, evaluate the validity of these logical inferences:\n"
            "1. [Inference 1]\n"
            "2. [Inference 2]\n"
            "Which of the inferences given above logically follow?\n"
            "(a) 1 only\n"
            "(b) 2 only\n"
            "(c) Both 1 and 2\n"
            "(d) Neither 1 nor 2"
        )
    }

    for index, chunk_text in enumerate(chunks):
        loop_counter = 1
        segment_history = []
        
        # Pull global history before processing chunks to lock out duplicates completely
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT content FROM questions WHERE book_id = ?", (book_id,))
        global_history = cursor.fetchall()
        conn.close()
        
        compiled_history_text = "\n---\n".join([row[0] for row in global_history]) if global_history else "None"

        if len(chunk_text.strip()) < 50:
            st.warning(f"⚠️ Low layout density. Injecting native knowledge backup layers for: '{fallback_topic_name}'")
            chunk_context = f"Exhaustively map the target civil services syllabus framework for topic: {fallback_topic_name}"
        else:
            st.write(f"📖 Processing Source Segment Block {index+1} of {total_chunks}...")
            chunk_context = f"SOURCE DOCUMENT MATERIAL SECTOR:\n{chunk_text}"

        while loop_counter <= 4:
            # Force structural lock
            isolated_format_rule = FORMAT_BLUEPRINTS.get(loop_counter)
            
            current_prompt = (
                f"{chunk_context}\n\n"
                f"{isolated_format_rule}\n\n"
                f"CRITICAL REPETITION CONSTRAINT: Do NOT focus on the same sub-themes or duplicate topics you already outputted.\n"
                f"Review this global log window and ensure your new questions target completely fresh conceptual dimensions:\n"
                f"=== ALREADY EXTRACTED QUESTIONS (AVOID THESE CONCEPTS) ===\n"
                f"{compiled_history_text[:14000]}\n"
                f"===========================================================\n\n"
                f"Generate the isolated configuration sequence now."
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
                        temperature=0.4
                    )
                    raw_text = response.choices[0].message.content
                else:
                    g_client = genai.Client(api_key=api_key)
                    response = g_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=current_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=MASTER_PROMPT,
                            temperature=0.4
                        )
                    )
                    raw_text = response.text

                if len(raw_text.strip()) < 50 or "SEGMENT_EXHAUSTED" in raw_text:
                    loop_counter += 1
                    continue
                else:
                    segment_history.append(raw_text)
                    
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO questions (book_id, content) VALUES (?, ?)", (book_id, raw_text))
                    conn.commit()
                    conn.close()
                    
                    loop_counter += 1
                    time.sleep(1)

            except Exception as e:
                st.error(f"❌ API Loop Failure: {str(e)}")
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
# 5. USER INTERFACE
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
            with st.spinner("Extracting layout text data..."):
                full_text = extract_robust_pdf_text(uploaded_file)
            
            if not full_text or len(full_text) < 10:
                chunks = ["OCR_FALLBACK_TRIGGER_EMPTY_TEXT_LAYER"]
            else:
                st.info(f"Parsed {len(full_text)} characters. Formatting isolated context blocks...")
                chunk_size = 35000
                chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
            
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO books (filename, total_segments, status) VALUES (?, ?, 'pending')", (uploaded_file.name, len(chunks)))
            book_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            with st.spinner("Generating ultra-hard isolated UPSC variations... Stay on this window."):
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
        full_output_bank = f"=== UPSC ELITE-TIER VARIATION POOL FOR TOPIC: {clean_topic_name} ===\n\n{compiled_questions}"
        
        st.download_button(
            label="📥 Download Clean UPSC Bank (.txt)",
            data=full_output_bank,
            file_name=f"UPSC_Isolated_Elite_{uploaded_file.name.replace('.pdf', '')}.txt",
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
