import streamlit as st
import time
import sqlite3
import threading
from google import genai
from google.genai import types
from openai import OpenAI
from pypdf import PdfReader

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
            segment_index INTEGER,
            batch_index INTEGER,
            content TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ==============================================================================
# 2. CONFIGURATION & CORE ACCESS
# ==============================================================================
st.set_page_config(page_title="UPSC Fast Generator", layout="wide")
st.title("🎯 UPSC GS Paper I Bulk Question Generator")

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
# 3. COMPACT & EFFECTIVE MASTER SYSTEM PROMPT (2026 Pattern Aligned)
# ==============================================================================
MASTER_PROMPT = """
You are a Senior UPSC CSE Paper Setter. Extract the MAXIMUM possible number of unique, high-difficulty MCQs from the provided text.

CRITICAL RULES:
1. Grounding: Rely ONLY on facts explicitly stated in the source text. Do not invent external scenarios or concepts.
2. Formatting: Output the questions cleanly following the plain-text schema below. Do not output intro words, markdown lines, or emojis.

Template:
Question: [Insert question statement here]
(a) [Option A]
(b) [Option B]
(c) [Option C]
(d) [Option D]
Answer: [Correct letter only, e.g., (b)]
Explanation: [Concise 3-4 sentence factual analysis based strictly on the text]
Topic: [Syllabus topic name]

Leave exactly one blank line between questions. If the text has no new concepts left, reply ONLY with: 'SEGMENT_EXHAUSTED'.
"""
FORMAT_ROTATION = {
        1: (
            "1. Multi-Statement Classic (Evaluate statements I, II, III -> Choose: 1 and 2 only, etc.) "
            "2. Countable Multi-Statement (2023-2026 Trend: 'How many statements are correct? Only one, Only two, All three, None') "
            "3. Assertion-Reason (Statement I & Statement II causal logic evaluation)."
        ),
        2: (
            "4. Match the Following 2-Column Classic "
            "5. Match the Following 3-Column Matrix (2024-2026 Trend: Column A [Term], Column B [Provision], Column C [Article/Year]) "
            "6. Chronological Ordering (Arrange historical events, acts, or committee formations in sequence)."
        ),
        3: (
            "7. Scenario-Based / Situational Case Study (2026 Trend: Practical administrative tradeoffs or ethical choices based on the text principles) "
            "8. Definitional / Pure Conceptual Isolation (Testing the exact operational boundary of a term) "
            "9. Geographical / Map-Linked Context (If locations, rivers, boundaries, or national parks are mentioned)."
        ),
        4: (
            "10. 2026 Evidence-Inference Matrix (3 structural facts given as Roman numerals, 2 logical deductions given as numbers; evaluate validity) "
            "11. Passage-Based Comprehension MCQ (Read a micro-extract from the text and find the core implication) "
            "12. Direct Fact Elimination / 'Which of the following is NOT correct' format."
        )
    }

# ==============================================================================
# 4. BACKGROUND PROCESSING PIPELINE
# ==============================================================================
def bulk_generation_worker(book_id, chunks, provider, api_key):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE books SET status = 'processing' WHERE id = ?", (book_id,))
    conn.commit()

    FORMAT_ROTATION = {
        1: "Multi-Statement True/False Evaluation Questions.",
        2: "Advanced 'How many statements are correct' (Countable format) Questions.",
        3: "Assertion-Reason causal logic questions.",
        4: "Direct concept matching and standalone analytical questions."
    }

    for index, chunk in enumerate(chunks):
        loop_counter = 1
        continue_generation = True
        segment_history = []
        
        while continue_generation and loop_counter <= 4:
            target_formats = FORMAT_ROTATION.get(loop_counter, "Any standard remaining UPSC format.")
            
            base_instruction = (
                f"SOURCE MATERIAL TEXT SECTOR:\n{chunk}\n\n"
                f"TARGET TEMPLATE PATTERN: Focus on generating: {target_formats}\n"
            )

            if loop_counter == 1:
                current_prompt = base_instruction + "\nCommand: Extract the absolute maximum number of unique questions possible from this text segment now."
            else:
                history_text = "\n---\n".join(segment_history)
                current_prompt = (
                    f"{base_instruction}\n"
                    f"CRITICAL CONSTRAINT:\n"
                    f"Do NOT repeat the questions, option variations, or exact phrases you already outputted in earlier loops. Review your batch history to avoid duplication:\n{history_text}\n"
                    f"Generate a new batch of completely unique questions now. If exhausted, reply with exactly: 'SEGMENT_EXHAUSTED'."
                )
            
            try:
                if provider == "Gemini (Google)":
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
                else:
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

                if "SEGMENT_EXHAUSTED" in raw_text or len(raw_text.strip()) < 100:
                    continue_generation = False
                else:
                    segment_history.append(raw_text)
                    cursor.execute("""
                        INSERT INTO questions (book_id, segment_index, batch_index, content)
                        VALUES (?, ?, ?, ?)
                    """, (book_id, index + 1, loop_counter, raw_text))
                    conn.commit()
                    loop_counter += 1
                    time.sleep(1)

            except Exception as e:
                error_log = f"\n⚠️ [SYSTEM ERROR SEGMENT {index+1} BATCH {loop_counter}]: {str(e)}\n"
                cursor.execute("INSERT INTO questions (book_id, segment_index, batch_index, content) VALUES (?, ?, ?, ?)", 
                               (book_id, index + 1, loop_counter, error_log))
                conn.commit()
                break
        
        cursor.execute("UPDATE books SET processed_segments = ? WHERE id = ?", (index + 1, book_id))
        conn.commit()
        time.sleep(2)

    cursor.execute("UPDATE books SET status = 'completed' WHERE id = ?", (book_id,))
    conn.commit()
    conn.close()

# ==============================================================================
# 5. MAIN WORKSPACE VIEW WITH AUTO-REFRESH FRAGMENT
# ==============================================================================
# ==============================================================================
# 5. MAIN WORKSPACE VIEW WITH AUTO-REFRESH FRAGMENT (Download Option Always Open)
# ==============================================================================
def extract_pdf_text(uploaded_pdf):
    reader = PdfReader(uploaded_pdf)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

st.subheader("🤖 Bulk Extraction Engine")
uploaded_file = st.file_uploader("Upload Textbook / Notes PDF", type=["pdf"])

if uploaded_file:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, processed_segments, total_segments, status FROM books WHERE filename = ?", (uploaded_file.name,))
    book_record = cursor.fetchone()
    conn.close()

    if not book_record:
        if st.button("🚀 Trigger Full Automated Extraction Loop"):
            st.info("Reading complete book text structure...")
            full_text = extract_pdf_text(uploaded_file)
            
            chunk_size = 35000
            chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
            total_chunks = len(chunks)
            
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO books (filename, total_segments, status) VALUES (?, ?, 'pending')", (uploaded_file.name, total_chunks))
            book_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            thread = threading.Thread(target=bulk_generation_worker, args=(book_id, chunks, provider, user_api_key))
            thread.start()
            st.success("⚡ Processing Loop activated successfully!")
            st.rerun()
    else:
        book_id, processed, total, status = book_record
        st.write("---")
        
        # UI Auto-refresh loop block (Refreshes metrics and downloads panel automatically every 5 seconds)
        @st.fragment(run_every=5)
        def show_live_status(b_id, tot, f_name, current_status):
            conn_live = sqlite3.connect(DB_FILE)
            cur_live = conn_live.cursor()
            
            cur_live.execute("SELECT processed_segments, status FROM books WHERE id = ?", (b_id,))
            db_metrics = cur_live.fetchone()
            proc = db_metrics[0] if db_metrics else processed
            stat = db_metrics[1] if db_metrics else current_status
            
            cur_live.execute("SELECT content FROM questions WHERE book_id = ? ORDER BY id ASC", (b_id,))
            raw_rows = cur_live.fetchall()
            conn_live.close()
            
            # Displays moving metrics live
            st.metric(
                label=f"📖 Active Target: {f_name}", 
                value=f"Status: {stat.upper()}", 
                delta=f"{proc} / {tot} Chunks Extracted"
            )
            
            # Build text payload dynamically even if it's currently running empty
            compiled_questions = "\n\n".join([row[0] for row in raw_rows]) if raw_rows else ""
            full_output_bank = f"=== MASTER QUESTION POOL FOR: {f_name} ===\n\n{compiled_questions}"
            
            st.write("---")
            st.subheader("📥 Export Management Panel")
            st.info(f"✨ Total generated items caught in database: {len(raw_rows)} batches.")
            
            # The download button is now completely unlinked from the IF condition so it never goes missing
            st.download_button(
                label="📥 Download Compiled Question Document (.txt)",
                data=full_output_bank,
                file_name=f"UPSC_Bank_{f_name.replace('.pdf', '')}.txt",
                mime="text/plain",
                disabled=(len(raw_rows) == 0) # Button turns clickable the exact second the first question drops!
            )
        
        show_live_status(book_id, total, uploaded_file.name, status)
            
        st.write("---")
        if st.button("🗑️ Reset Engine & Clear Book Record"):
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM books WHERE id = ?", (book_id,))
            cursor.execute("DELETE FROM questions WHERE book_id = ?", (book_id,))
            conn.commit()
            conn.close()
            st.success("App storage cleared successfully.")
            st.rerun()
            
