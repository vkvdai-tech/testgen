import streamlit as st
import time
import base64
from io import BytesIO
from google import genai
from google.genai import types  # <--- MAKE SURE THIS EXACT LINE IS ADDED!
from openai import OpenAI
from pypdf import PdfReader
from PIL import Image

# 1. Page Config & Basic Passcode Security
st.set_page_config(page_title="UPSC Question Factory", layout="wide")
st.title("🎯 UPSC GS Paper I Master MCQ Generator")

ACCESS_PASSWORD = "your_secret_password_here"  # Change this to your shared password!

with st.sidebar:
    st.header("🔐 Access & Provider Setup")
    user_pass = st.text_input("Enter App Access Password", type="password")
    
    # Provider Selection Toggle
    provider = st.selectbox("Select AI Provider", ["Gemini (Google)", "OpenAI (ChatGPT)"])
    
    user_api_key = ""
    if provider == "Gemini (Google)":
        user_api_key = st.text_input("Enter Gemini API Key", type="password")
    else:
        user_api_key = st.text_input("Enter OpenAI API Key (sk-...)", type="password")
    
if user_pass != ACCESS_PASSWORD:
    st.warning("Please enter the correct App Access Password in the sidebar to open the workspace.")
    st.stop()

if not user_api_key:
    st.info(f"Please enter your {provider} API Key in the sidebar to proceed.")
    st.stop()

# Hardcoded Master Prompt Verbatim
MASTER_PROMPT = """
🎯 UPSC CIVIL SERVICES PRELIMS — MASTER MCQ GENERATION PROMPT
Version 3.0 | Complete Question Format Edition | Updated Through UPSC Prelims 2026
🧠 ROLE & PERSONA
You are a Senior UPSC Civil Services Examination Paper Setter...
[PASTE YOUR ENTIRE PROMPT DOCUMENT CONTENT DIRECTLY HERE]
"""

# Helper function to extract text from a uploaded PDF file
def extract_pdf_text(uploaded_pdf):
    reader = PdfReader(uploaded_pdf)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

# Helper function to encode PIL images to base64 for OpenAI's vision processing
def encode_image_to_base64(pil_img):
    buffered = BytesIO()
    pil_img.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

# 2. Main Workspace Setup
file_type = st.radio("What are you uploading today?", ["Entire Textbook / Notes (PDF)", "Screenshots / Images"])

if file_type == "Entire Textbook / Notes (PDF)":
    uploaded_file = st.file_uploader("Upload PDF Notes", type=["pdf"])
    
    if uploaded_file and st.button("🚀 Process Book Topic-by-Topic"):
        st.info("Extracting document content...")
        full_text = extract_pdf_text(uploaded_file)
        
        # Slicing the book into tighter operational blocks (~15-20 pages per chunk)
        # This gives the model a laser focus on specific details for deeper extraction
        chunk_size = 40000 
        chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
        
        st.success(f"Successfully split material into {len(chunks)} precise reading segments.")
        
        final_output = ""
        output_area = st.empty() 
        
        for index, chunk in enumerate(chunks):
            st.write(f"📖 **Analyzing Segment {index+1} of {len(chunks)}...**")
            
            # Resetting execution state for the current sub-topic chunk
            continue_generation = True
            loop_counter = 1
            segment_history_prompt = f"SOURCE MATERIAL TO EXTRACT FROM:\n{chunk}\n\n"
            
            while continue_generation and loop_counter <= 4: # Allows up to 4 consecutive deep sweeps per segment
                st.write(f"✍️ Generating batch {loop_counter} for Segment {index+1}...")
                
                # Command execution payload
                if loop_counter == 1:
                    current_prompt = segment_history_prompt + "Activation Command: Concept map complete. Extract the maximum possible questions from this segment now."
                else:
                    current_prompt = "CRITICAL: The concept map for this segment is NOT yet fully exhausted. Continue generating the next batch of completely new, non-repetitive UPSC questions following the exact same formats and quality criteria. Do not repeat previous questions. If there are absolutely no more hidden nuances left to extract, reply with the exact text: 'SEGMENT_EXHAUSTED'."

                try:
                    if provider == "Gemini (Google)":
                        g_client = genai.Client(api_key=user_api_key)
                        # We cleanly isolate your Master Prompt rules into system_instruction config
                        response = g_client.models.generate_content(
                            model='gemini-2.5-pro',
                            contents=current_prompt,
                            config=types.GenerateContentConfig(
                                system_instruction=MASTER_PROMPT,
                                temperature=0.2 # Lower temperature forces higher legal & factual precision
                            )
                        )
                        raw_text = response.text
                    else:
                        o_client = OpenAI(api_key=user_api_key)
                        response = o_client.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {"role": "system", "content": MASTER_PROMPT},
                                {"role": "user", "content": current_prompt}
                            ],
                            temperature=0.2
                        )
                        raw_text = response.choices[0].message.content
                    
                    # Check if the model has naturally extracted everything out of this text block
                    if "SEGMENT_EXHAUSTED" in raw_text or len(raw_text.strip()) < 100:
                        st.write(f"✨ Segment {index+1} completely exhausted.")
                        continue_generation = False
                    else:
                        batch_header = f"\n\n### 📚 SEGMENT {index+1} | BATCH {loop_counter} ({provider}) ###\n\n"
                        final_output += batch_header + raw_text
                        output_area.markdown(final_output)
                        
                        loop_counter += 1
                        
                        # Brief safety delay between consecutive API calls
                        time.sleep(5)
                        
                except Exception as e:
                    st.error(f"Error on segment {index+1}, batch {loop_counter}: {e}")
                    time.sleep(10)
                    break
            
            # Rate limit guard for free tiers between major segment switches
            if index < len(chunks) - 1:
                st.write("⏳ Resting 25 seconds before moving to the next segment...")
                time.sleep(25)
        
        st.success("🎉 Comprehensive Extraction Complete!")
        st.download_button("📥 Download All Generated Questions (.txt)", final_output, file_name="UPSC_Max_Exhaustion_Pool.txt")
