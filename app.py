import streamlit as st
import time
import base64
from io import BytesIO
from google import genai
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
        
        # Slicing chunk sizes based on standard provider context balances
        # OpenAI has a smaller output window than Gemini, chunking securely helps prevent cut-offs
        chunk_size = 60000 if provider == "OpenAI (ChatGPT)" else 100000
        chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
        
        st.success(f"Successfully processed book into {len(chunks)} consecutive operational segments.")
        
        final_output = ""
        output_area = st.empty() 
        
        for index, chunk in enumerate(chunks):
            st.write(f"📖 Working on Segment {index+1} of {len(chunks)} using {provider}...")
            
            prompt_payload = (
                f"{MASTER_PROMPT}\n\n"
                f"SOURCE MATERIAL SEGMENT:\n{chunk}\n\n"
                f"Activation Command: Concept map complete. Segment {index+1} sub-topics identified. "
                f"Beginning UPSC MCQ generation across 12 question formats. Generating questions now..."
            )
            
            try:
                if provider == "Gemini (Google)":
                    g_client = genai.Client(api_key=user_api_key)
                    response = g_client.models.generate_content(
                        model='gemini-3.5-flash',
                        contents=prompt_payload,
                    )
                    raw_text = response.text
                else:
                    o_client = OpenAI(api_key=user_api_key)
                    # Using gpt-4o for complex matching logic/Tier 3 questions
                    response = o_client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": prompt_payload}]
                    )
                    raw_text = response.choices[0].message.content
                
                segment_questions = f"\n\n### 📚 QUESTIONS FROM SEGMENT {index+1} ({provider}) ###\n\n" + raw_text
                final_output += segment_questions
                output_area.markdown(final_output)
                
                # Moderate time delays to preserve account rate limit buckets safely
                if index < len(chunks) - 1:
                    delay = 5 if provider == "OpenAI (ChatGPT)" else 30
                    st.write(f"⏳ Rest interval: pausing {delay} seconds...")
                    time.sleep(delay)
                    
            except Exception as e:
                st.error(f"Error executing request on segment {index+1}: {e}")
                time.sleep(10)
                continue
        
        st.success("🎉 Processing Loop Complete!")
        st.download_button("📥 Download Generated Pool (.txt)", final_output, file_name="UPSC_Generated_Pool.txt")

else:
    uploaded_images = st.file_uploader("Upload screenshots", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    
    if uploaded_images and st.button("🚀 Generate Questions From Images"):
        final_img_output = ""
        output_img_area = st.empty()
        
        for idx, img_file in enumerate(uploaded_images):
            st.write(f"🖼️ Parsing Image {idx+1} using {provider}...")
            img = Image.open(img_file)
            
            try:
                if provider == "Gemini (Google)":
                    g_client = genai.Client(api_key=user_api_key)
                    contents_payload = [
                        f"{MASTER_PROMPT}\n\nExtract and map all conceptual points out of this image framework.",
                        img
                    ]
                    response = g_client.models.generate_content(
                        model='gemini-1.5-pro',
                        contents=contents_payload,
                    )
                    raw_text = response.text
                else:
                    o_client = OpenAI(api_key=user_api_key)
                    base64_image = encode_image_to_base64(img)
                    
                    response = o_client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": f"{MASTER_PROMPT}\n\nExtract and map all conceptual points out of this image framework."},
                                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                                ]
                            }
                        ]
                    )
                    raw_text = response.choices[0].message.content
                
                img_questions = f"\n\n### 🖼️ QUESTIONS FROM SCREENSHOT {idx+1} ###\n\n" + raw_text
                final_img_output += img_questions
                output_img_area.markdown(final_img_output)
                
                if idx < len(uploaded_images) - 1:
                    time.sleep(5)
                    
            except Exception as e:
                st.error(f"Error processing image {idx+1}: {e}")
                
        st.success("🎉 Image Queue Complete!")
        st.download_button("📥 Download Image Questions (.txt)", final_img_output, file_name="UPSC_Screenshot_Questions.txt")
