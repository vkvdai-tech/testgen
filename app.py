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
st.set_page_config(page_title="UPSC Elite MCQ Factory v5", layout="wide")
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
# 4. EXPLICIT FORMAT-FORCING LOOP PIPELINE
# ==============================================================================
def process_book_synchronously(book_id, chunks, fallback_topic_name, provider, api_key):
    total_chunks = len(chunks)
    progress_bar = st.progress(0.0)
    
    # SYSTEM BASE SETTING
    BASE_SYSTEM = (
        "You are a Senior UPSC Civil Services Examination Paper Setter updated through the 2026 patterns. "
        "Your task is to generate ultra-hard, conceptual questions based STRICTLY on the text provided. "
        "Do not use external data or padding. Deliver only clean, plain text blocks using the template rule assigned."
    )

    for index, chunk_text in enumerate(chunks):
        # Establish structural context buckets
        if len(chunk_text.strip()) < 50:
            chunk_context = f"CORE UPSC SYLLABUS THEME: {fallback_topic_name}"
        else:
            st.write(f"📖 Crunching Document Segment Block {index+1} of {total_chunks}...")
            chunk_context = f"SOURCE DOCUMENT MATERIAL:\n{chunk_text}"

        # Loop 1 to 4 now represents an un-passable, isolated format assignment
        for format_id in range(1, 5):
            
            # Fetch ongoing live database log to avoid repeating core concepts
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT content FROM questions WHERE book_id = ?", (book_id,))
            global_history = cursor.fetchall()
            conn.close()
            compiled_history = "\n---\n".join([row[0] for row in global_history]) if global_history else "None"

            # Dynamic prompt injection targeting specific conceptual architectures
            if format_id == 1:
                prompt_instruction = (
                    "CRITICAL ASSIGNMENT: You must generate 2-3 elite-difficulty ASSERTION-REASON questions from the text.\n"
                    "You must evaluate the causal relationship between two statements. Follow this template EXACTLY:\n\n"
                    "Question: Statement I: [Insert core conceptual claim/fact from the text]\n"
                    "Statement II: [Insert a statement explaining the cause, reason, or exception behind Statement I]\n"
                    "Which one of the following is correct in respect of the above statements?\n"
                    "(a) Both Statement I and Statement II are correct and Statement II is the correct explanation for Statement I\n"
                    "(b) Both Statement I and Statement II are correct but Statement II is not the correct explanation for Statement I\n"
                    "(c) Statement I is correct but Statement II is incorrect\n"
                    "(d) Statement I is incorrect but Statement II is correct\n"
                    "Answer: [Letter only]\n"
                    "Explanation: [Provide a 3-4 sentence logical analysis breaking down why Statement II does or does not structurally explain Statement I based on the text]\n"
                    "Topic: [Syllabus tag]"
                )
            elif format_id == 2:
                prompt_instruction = (
                    "CRITICAL ASSIGNMENT: You must generate 1-2 complex 2024-2026 style THREE-COLUMN MATCH MATRIX questions.\n"
                    "Follow this template layout EXACTLY:\n\n"
                    "Question: Consider the following columns based on the text:\n"
                    "Column A (Concept/Term) | Column B (Provisions/Details) | Column C (Constitutional Article/Year/Context)\n"
                    "1. [Term 1] | [Provisions 1] | [Context 1]\n"
                    "2. [Term 2] | [Provisions 2] | [Context 2]\n"
                    "3. [Term 3] | [Provisions 3] | [Context 3]\n"
                    "How many of the pairs given above are correctly matched?\n"
                    "(a) Only one pair\n"
                    "(b) Only two pairs\n"
                    "(c) All three pairs\n"
                    "(d) None of the pairs\n"
                    "Answer: [Letter only]\n"
                    "Explanation: [Break down exactly which lines/pairs are correct or incorrect based strictly on the text]\n"
                    "Topic: [Syllabus tag]"
                )
            elif format_id == 3:
                prompt_instruction = (
                    "CRITICAL ASSIGNMENT: You must generate 2 brutal, multi-statement COUNTABLE questions (2025-2026 trend).\n"
                    "Follow this template layout EXACTLY:\n\n"
                    "Question: Consider the following statements regarding the provided text:\n"
                    "1. [Insert highly complex, half-truth statement testing a minor exception]\n"
                    "2. [Insert an inverted analytical fact statements]\n"
                    "3. [Insert another conceptual statement]\n"
                    "How many of the statements given above are correct?\n"
                    "(a) Only one\n"
                    "(b) Only two\n"
                    "(c) All three\n"
                    "(d) None\n"
                    "Answer: [Letter only]\n"
                    "Explanation: [Concise 3-4 sentence breakdown showing exactly why each statement stands or falls]\n"
                    "Topic: [Syllabus tag]"
                )
            else:
                prompt_instruction = (
                    "CRITICAL ASSIGNMENT: You must generate 1-2 high-difficulty ADMINISTRATIVE SCENARIO / SITUATIONAL CASE STUDY questions.\n"
                    "Set up a practical legal gridlock or functional paradox based on the text laws, and test structural judgment. Follow this template EXACTLY:\n\n"
                    "Question: [Frame an elaborate situational scenario or deadlock testing the execution boundaries of the principles mentioned in the text]. In this context, which of the following outcomes is legally or constitutionally valid?\n"
                    "(a) [Option A]\n"
                    "(b) [Option B]\n"
                    "(c) [Option C]\n"
                    "(d) [Option D]\n"
                    "Answer: [Letter only]\n"
                    "Explanation: [Provide a 3-4 sentence functional explanation breaking down the legal boundaries of the scenario trap based on the text]\n"
                    "Topic: [Syllabus tag]"
                )

            # Assemble clean isolated prompt instructions
            current_prompt = (
                f"{chunk_context}\n\n"
                f"{prompt_instruction}\n\n"
                f"ANTI-REPETITION MANDATE: Do NOT reuse concepts, articles, or clauses found in this log:\n"
                f"=== LOG OF PAST QUESTIONS TO AVOID ===\n"
                f"{compiled_history[:12000]}\n"
                f"======================================\n"
                f"Generate your clean output text now without any conversational chatter or notes."
            )
            
            try:
                if provider == "OpenAI (ChatGPT)":
                    o_client = OpenAI(api_key=api_key)
                    response = o_client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": BASE_SYSTEM},
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
                            system_instruction=BASE_SYSTEM,
                            temperature=0.3
                        )
                    )
                    raw_text = response.text

                if len(raw_text.strip()) > 50 and "SEGMENT_EXHAUSTED" not in raw_text:
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO questions (book_id, content) VALUES (?, ?)", (book_id, raw_text))
                    conn.commit()
                    conn.close()
                    time.sleep(1)

            except Exception as e:
                st.error(f"❌ Processing Execution Drop: {str(e)}")
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
            
            with st.spinner("Generating structured variations sequentially..."):
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
