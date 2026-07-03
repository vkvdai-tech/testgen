import streamlit as st
import time
import sqlite3
from google import genai
from google.genai import types
from openai import OpenAI
import pdfplumber  # Switched for superior hybrid image/text layout extraction

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
# 3. PURE 4-OPTION UPSC MASTER PROMPT (With 2026 Shift Alignment)
# ==============================================================================
MASTER_PROMPT = """
You are an expert UPSC Civil Services Examination Paper Setter updated through the latest 2026 trends. Extract the MAXIMUM possible number of unique, high-difficulty, conceptual multiple-choice questions from the provided text block.

CRITICAL CONSTRAINTS:
1. Grounding: Rely ONLY on facts explicitly mentioned in the source material text. Do not use external facts.
2. Structure: Every single question MUST be a strict 4-option multiple-choice question with options labeled exactly as (a), (b), (c), and (d). You are strictly FORBIDDEN from generating True/False structures or short-answer text elements.

Template Format:
Question: [Insert question statement here]
(a) [Option A]
(b) [Option B]
(c) [Option C]
(d) [Option D]
Answer: [Correct letter only, e.g., (c)]
Explanation: [Concise 3-4 sentence concept analysis explaining why the answer is factually correct based on the text]
Topic: [Specific syllabus micro-topic name]

Leave exactly one blank line between questions. If the text has no new concepts left, reply with exactly: 'SEGMENT_EXHAUSTED'.
"""

# ==============================================================================
# 4. EXPLICIT GENERATION PIPELINE 
# ==============================================================================
def process_book_synchronously(book_id, chunks, provider, api_key):
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
    
    for index, chunk in enumerate(chunks):
        loop_counter = 1
        segment_history = []
        
        st.write(f"📖 Processing Data Block {index+1} of {total_chunks}...")
        
        # Will dynamically evaluate up to 3 passes to gather all details
        while loop_counter <= 3:
            target_format = FORMAT_ROTATION.get(loop_counter, "Standard 4-option complex UPSC MCQ.")
            current_prompt = (
                f"SOURCE MATERIAL TEXT SECTOR:\n{chunk}\n\n"
                f"MANDATORY PATTERN RULE: Generate strict 4-option multiple choice questions using exclusively these target formats: {target_format}\n"
                f"Ensure absolute structural diversity. History to avoid duplication:\n" + "\n---\n".join(segment_history) + "\n\n"
                f"Extract now."
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
                        temperature=0.2
                    )
                    raw_text = response.choices[0].message.content
                else:
                    g_client = genai.Client(api_key=api_key)
                    response = g_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=current_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=MASTER_PROMPT,
                            temperature=0.2
                        )
                    )
                    raw_text = response.text

                if "SEGMENT_EXHAUSTED" in raw_text or len(raw_text.strip()) < 40:
                    break
                else:
                    segment_history.append(raw_text)
                    cursor.execute("INSERT INTO questions (book_id, content) VALUES (?, ?)", (book_id, raw_text))
                    conn.commit()
                    loop_counter += 1
                    time.sleep(1)

            except Exception as e:
                st.error(f"❌ API Processing Failure: {str(e)}")
                loop_counter = 99
                break
        
        cursor.execute("UPDATE books SET processed_segments = ? WHERE id = ?", (index + 1, book_id))
        conn.commit()
        progress_bar.progress((index + 1) / total_chunks)

    cursor.execute("UPDATE books SET status = 'completed' WHERE id = ?", (book_id,))
    conn.commit()
    conn.close()

# ==============================================================================
# 5. ADVANCED LAYOUT PARSING INTERFACE
# ==============================================================================
def extract_robust_pdf_text(uploaded_pdf):
    text = ""
    # Open using pdfplumber to bypass image overlay layout breaks
    with pdfplumber.open(uploaded_pdf) as pdf:
        for page in pdf.pages:
            # Tries layout extraction strategy first
            page_text = page.extract_text(layout=False)
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

    if not book_record:
        if st.button("🚀 Start Generating UPSC Questions"):
            with st.spinner("Extracting layered text zones from hybrid PDF layout..."):
                full_text = extract_robust_pdf_text(uploaded_file)
            
            if not full_text or len(full_text) < 15:
                st.error("❌ EXTRACTION EXHAUSTED: The parser could not find readable text structures inside this PDF format. If this file contains purely scanned bitmap photographs, please use an OCR-pre-processed document.")
                st.stop()
                
            st.info(f"Successfully processed text matrix. Captured {len(full_text)} characters. Running generation engine...")
            
            chunk_size = 35000
            chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
            
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO books (filename, total_segments, status) VALUES (?, ?, 'pending')", (uploaded_file.name, len(chunks)))
            book_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            process_book_synchronously(book_id, chunks, provider, user_api_key)
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
        
        st.write(f"📖 **Topic:** {uploaded_file.name} | Status: **{status.upper()}**")
        st.write(f"Total entries loaded in DB: **{len(raw_rows)}**")
        
        compiled_questions = "\n\n".join([row[0] for row in raw_rows]) if raw_rows else ""
        full_output_bank = f"=== UPSC EXAM POOL: {uploaded_file.name} ===\n\n{compiled_questions}"
        
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
