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
You are an expert UPSC Civil Services Examination Paper Setter updated through the May 2026 Prelims trends. Your task is to extract the MAXIMUM possible number of unique, high-difficulty, conceptual multiple-choice questions from the provided text block.

You must strictly generate questions spanning these specific formats:
1. Assertion-Reason (Causal Logic): Statement I followed by Statement II, evaluating if Statement II is the correct explanation of Statement I.
2. Scenario-Based Situational Case Studies: Evaluating real-world governance, administrative logjams, or policy paradoxes based on the text principles.
3. 2026 Evidence-Inference Matrix: Providing 3 contextual facts (Roman numerals I, II, III), followed by 2 analytical inferences, forcing the user to evaluate which inferences are logically valid.
4. Countable Multi-Statement Classic: "How many of the statements given above are correct? (a) Only one (b) Only two (c) All three (d) None".

CRITICAL RULES:
1. Grounding: Rely ONLY on facts explicitly mentioned in the source material text. Do not look outside the text block.
2. Formatting: Output the questions cleanly following the exact plain-text schema below. Do not output introduction words, emojis, markdown line dividers, or extra labels.

Template:
Question: [Insert question statement here]
(a) [Option A]
(b) [Option B]
(c) [Option C]
(d) [Option D]
Answer: [Correct option letter only, e.g., (c)]
Explanation: [Concise 3-4 sentence concept analysis explaining why the answer is factually correct based on the text]
Topic: [Specific syllabus micro-topic name]

Leave exactly one blank line between questions. If the text block has been completely exhausted of new concepts, reply with exactly: 'SEGMENT_EXHAUSTED'.
"""

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
        
        # UI Auto-refresh loop block (Refreshes metrics and downloads panel automatically every 6 seconds)
        @st.fragment(run_every=6)
        def show_live_status(b_id, tot, f_name):
            conn_live = sqlite3.connect(DB_FILE)
            cur_live = conn_live.cursor()
            
            cur_live.execute("SELECT processed_segments, status FROM books WHERE id = ?", (b_id,))
            proc, stat = cur_live.fetchone()
            
            cur_live.execute("SELECT content FROM questions WHERE book_id = ? ORDER BY id ASC", (b_id,))
            raw_rows = cur_live.fetchall()
            conn_live.close()
            
            # Displays moving metrics live
            st.metric(
                label=f"📖 Active Target: {f_name}", 
                value=f"Status: {stat.upper()}", 
                delta=f"{proc} / {tot} Chunks Done"
            )
            
            if raw_rows:
                st.success(f"✨ Compiled {len(raw_rows)} distinct raw question blocks inside storage.")
                full_output_bank = f"=== MASTER QUESTION POOL FOR: {f_name} ===\n\n" + "\n\n".join([row[0] for row in raw_rows])
                
                st.download_button(
                    label="📥 Download Compiled Question Document (.txt)",
                    data=full_output_bank,
                    file_name=f"UPSC_Bank_{f_name.replace('.pdf', '')}.txt",
                    mime="text/plain"
                )
            else:
                st.info("Connecting token channels... The status delta above will automatically increment as blocks complete.")
        
        show_live_status(book_id, total, uploaded_file.name)
            
        if st.button("🗑️ Reset Engine & Clear Book Record"):
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM books WHERE id = ?", (book_id,))
            cursor.execute("DELETE FROM questions WHERE book_id = ?", (book_id,))
            conn.commit()
            conn.close()
            st.success("App storage cleared successfully.")
            st.rerun()
            
