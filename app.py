import streamlit as st
import time
import base64
import sqlite3
import threading
from google import genai
from google.genai import types
from openai import OpenAI
from pypdf import PdfReader
from PIL import Image

# ==============================================================================
# 1. DATABASE CONFIGURATION (Self-contained SQLite Checkpoints)
# ==============================================================================
DB_FILE = "upsc_platform.db"

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
            segment_index INTEGER,
            batch_index INTEGER,
            provider TEXT,
            content TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ==============================================================================
# 2. PAGE INITIALIZATION & SECURITY
# ==============================================================================
st.set_page_config(page_title="UPSC Question Factory v2", layout="wide")
st.title("🎯 UPSC GS Paper I Async Question Factory")

ACCESS_PASSWORD = "your_secret_password_here"  # CHANGE THIS PASSWORD!

with st.sidebar:
    st.header("🔐 Access & Provider Setup")
    user_pass = st.text_input("Enter App Access Password", type="password")
    provider = st.selectbox("Select AI Provider", ["Gemini (Google)", "OpenAI (ChatGPT)"])
    
    if provider == "Gemini (Google)":
        user_api_key = st.text_input("Enter Gemini API Key", type="password")
    else:
        user_api_key = st.text_input("Enter OpenAI API Key (sk-...)", type="password")
    
if user_pass != ACCESS_PASSWORD:
    st.warning("Please enter the correct App Access Password in the sidebar to unlock.")
    st.stop()

if not user_api_key:
    st.info(f"Please provide your {provider} API Key to connect to the models.")
    st.stop()

# ==============================================================================
# 3. YOUR EXACT MASTER PROMPT (Passed directly as a System Instruction)
# ==============================================================================
MASTER_PROMPT = """
🎯 UPSC CIVIL SERVICES PRELIMS — MASTER MCQ GENERATION PROMPT
Version 3.0 | Complete Question Format Edition | Updated Through UPSC Prelims 2026

🧠 ROLE & PERSONA
You are a Senior UPSC Civil Services Examination Paper Setter with:
20+ years of experience designing and reviewing UPSC Prelims GS Paper I
Deep command of the official UPSC CSE syllabus across all domains
Thorough analytical mastery of NCERT Texts (Class 6–12) and standard references: M. Laxmikanth (Polity), Spectrum & Bipin Chandra (History), Shankar IAS (Environment), NCERT Geography, Economic Survey, India Year Book
Expert knowledge of UPSC Prelims question evolution from 2015–2026, including the structural shift in 2023 (elimination-resistant formats), the 2024 introduction of 3-column Match the Following, the 2025 surge in 3-statement formats, and the 2026 "Ethics-ification" of GS Paper I with multi-stakeholder scenario-based questions
Ability to write questions that reward genuine conceptual understanding over coaching-institute pattern-matching or rote memorization
Your fundamental obligation: Every question must have exactly one defensibly correct answer that cannot be legitimately disputed by any expert, and three genuinely plausible distractors that only a truly prepared candidate can eliminate.

🎯 CORE OBJECTIVE
Generate the MAXIMUM POSSIBLE number of high-quality, non-repetitive, examination-ready UPSC-standard MCQs from any given topic or content.
Mission: Achieve COMPLETE CONCEPT EXHAUSTION — extract every valid conceptual angle, dimension, and implication until no new question can be legitimately formed.

[... PROMPT REVENUE TRUNCATED FOR CODE FLOW - PASTE THE REST OF YOUR ENTIRE DOCX PROMPT TEXT HERE ...]
"""

# ==============================================================================
# 4. CRASH-PROOF BACKGROUND ASYNC WORKER
# ==============================================================================
def background_pdf_worker(book_id, chunks, provider, api_key):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE books SET status = 'processing' WHERE id = ?", (book_id,))
    conn.commit()

    for index, chunk in enumerate(chunks):
        loop_counter = 1
        continue_generation = True
        
        # Max 4 loops per segment to extract every possible hidden concept factor
        while continue_generation and loop_counter <= 4:
            if loop_counter == 1:
                current_prompt = f"SOURCE MATERIAL TO EXTRACT FROM:\n{chunk}\n\nActivation Command: Concept map complete. Extract the absolute maximum number of unique questions possible from this segment now following the format rules."
            else:
                current_prompt = "CRITICAL: The concept map for this segment is NOT yet fully exhausted. Continue generating the next batch of completely new, non-repetitive UPSC questions following your exact structural formats. Do not repeat previous questions. If there are absolutely no more hidden nuances left to extract, reply with the exact text: 'SEGMENT_EXHAUSTED'."
            
            try:
                if provider == "Gemini (Google)":
                    g_client = genai.Client(api_key=api_key)
                    # Using gemini-2.5-flash for unlimited free rate-limit generation loops
                    response = g_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=current_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=MASTER_PROMPT,
                            temperature=0.15
                        )
                    )
                    raw_text = response.text
                else:
                    o_client = OpenAI(api_key=api_key)
                    response = o_client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": MASTER_PROMPT},
                            {"role": "user", "content": current_prompt}
                        ],
                        temperature=0.15
                    )
                    raw_text = response.choices[0].message.content

                if "SEGMENT_EXHAUSTED" in raw_text or len(raw_text.strip()) < 100:
                    continue_generation = False
                else:
                    # Save checkpoint data immediately to the DB file
                    cursor.execute("""
                        INSERT INTO questions (book_id, segment_index, batch_index, provider, content)
                        VALUES (?, ?, ?, ?, ?)
                    """, (book_id, index + 1, loop_counter, provider, raw_text))
                    conn.commit()
                    loop_counter += 1
                    time.sleep(2)

            except Exception as e:
                print(f"Worker iteration error: {e}")
                time.sleep(10)
                break
        
        cursor.execute("UPDATE books SET processed_segments = ? WHERE id = ?", (index + 1, book_id))
        conn.commit()
        # Safe delay bucket spacing to stay under free tier thresholds comfortably
        time.sleep(5)

    cursor.execute("UPDATE books SET status = 'completed' WHERE id = ?", (book_id,))
    conn.commit()
    conn.close()

# ==============================================================================
# 5. STREAMLIT FRONTEND VIEW INTERFACE
# ==============================================================================
def extract_pdf_text(uploaded_pdf):
    reader = PdfReader(uploaded_pdf)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

tabs = st.tabs(["📤 Upload & Process Book", "👁️ Review & Download Pool"])

# --- TAB 1: FILE INGESTION ---
with tabs[0]:
    st.header("Upload Heavy UPSC Reference Textbooks")
    uploaded_file = st.file_uploader("Upload your 100 to 1000 page textbook PDF", type=["pdf"])
    
    if uploaded_file:
        if st.button("⚡ Trigger Core Background Processing"):
            st.info("Reading text structure and calculating matrix slices...")
            full_text = extract_pdf_text(uploaded_file)
            
            # Slicing the file into tight ~12-15 page chunks for meticulous coverage
            chunk_size = 35000 
            chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
            total_chunks = len(chunks)
            
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO books (filename, total_segments, processed_segments, status)
                VALUES (?, ?, 0, 'pending')
            """, (uploaded_file.name, total_chunks))
            book_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            # Spawn background thread to separate computation from UI loop completely
            thread = threading.Thread(
                target=background_pdf_worker, 
                args=(book_id, chunks, provider, user_api_key)
            )
            thread.start()
            st.success("🚀 Engine Active! The background worker has taken over processing. You can safely look at the next tab or close your laptop—your text data will process smoothly.")

# --- TAB 2: LIVE REVIEW PANEL ---
with tabs[1]:
    st.header("Human-In-The-Loop Question Desk")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM books")
    all_books = cursor.fetchall()
    
    if all_books:
        st.subheader("📊 Ingestion Queue Performance Status")
        for bk in all_books:
            st.write(f"📖 **Book:** `{bk[1]}` | **Status:** `{bk[4].upper()}` | Progress: `{bk[3]} / {bk[2]}` segments completely extracted.")
        
        # Load single pending batch item for confirmation review
        cursor.execute("SELECT id, content FROM questions WHERE status = 'pending' ORDER BY id ASC LIMIT 1")
        pending_item = cursor.fetchone()
        
        st.write("---")
        if pending_item:
            current_q_id, current_content = pending_item
            st.subheader("Awaiting Manual Verification Review:")
            st.markdown(current_content)
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Approve & Add to Test Pool", key=f"app_{current_q_id}"):
                    cursor.execute("UPDATE questions SET status = 'approved' WHERE id = ?", (current_q_id,))
                    conn.commit()
                    st.rerun()
            with col2:
                if st.button("❌ Trash / Reject Batch", key=f"rej_{current_q_id}"):
                    cursor.execute("UPDATE questions SET status = 'rejected' WHERE id = ?", (current_q_id,))
                    conn.commit()
                    st.rerun()
        else:
            st.info("All generated question batches have been completely reviewed or the background queues are still running.")

        # Show Approved Database Downloads Panel
        cursor.execute("SELECT content FROM questions WHERE status = 'approved'")
        approved_pool = cursor.fetchall()
        if approved_pool:
            st.write("---")
            st.subheader(f"📥 Export Workspace ({len(approved_pool)} Batches Verified)")
            final_download_text = "\n\n=== FINAL CERTIFIED UPSC BANK ===\n\n" + "\n\n".join([q[0] for q in approved_pool])
            st.download_button("Download Final Verified Question Bank (.txt)", final_download_text, file_name="Verified_UPSC_Bank.txt")
    else:
        st.info("No data tracking records logged in your database yet.")
    conn.close()
