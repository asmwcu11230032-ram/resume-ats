import streamlit as st
import pdfplumber
import sqlite3
import pandas as pd
import re
import plotly.express as px
import spacy

import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

# Download required NLTK datasets for NLP
nltk.download('punkt')
nltk.download('stopwords')

# NLP Function to process text
def process_text_nlp(text):
    tokens = word_tokenize(text.lower())
    stop_words = set(stopwords.words('english'))
    filtered_words = [word for word in tokens if word.isalnum() and word not in stop_words]
    return filtered_words

# Function to calculate similarity score
def calculate_score(resume_text, job_desc):
    resume_tokens = set(process_text_nlp(resume_text))
    job_tokens = set(process_text_nlp(job_desc))
    
    if not job_tokens:
        return 0.0
        
    common_words = resume_tokens.intersection(job_tokens)
    score = (len(common_words) / len(job_tokens)) * 100
    return round(score, 2)
# Database Setup
conn = sqlite3.connect('candidate_database.db', check_same_thread=False)
c = conn.cursor()

# Automatic fix for schema mismatch: drops old broken table
c.execute('DROP TABLE IF EXISTS candidates')

c.execute('''
CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT,
    phone TEXT,
    match_score REAL,
    matched_skills TEXT,
    missing_skills TEXT
)
''')
conn.commit()

# Fixed Phrase Splitter (Only splits on separators, never cuts inside words)
def calculate_matches(resume_text, jd_text):
    raw_skills = re.split(r'[,;\n]', jd_text)
    jd_skills = [skill.strip().lower() for skill in raw_skills if skill.strip()]
    
    resume_text_clean = resume_text.lower()
    matched_skills = []
    missing_skills = []
    
    for skill in jd_skills:
        pattern = r'\b' + re.escape(skill) + r'\b'
        if re.search(pattern, resume_text_clean):
            matched_skills.append(skill)
        else:
            missing_skills.append(skill)
            
    total_skills = len(jd_skills)
    score = (len(matched_skills) / total_skills * 100) if total_skills > 0 else 0.0
    
    return round(score, 2), matched_skills, missing_skills
# Extract Name, Email, Phone from Resume Text
def extract_details(text):
    # Extract Email
    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    email = email_match.group(0) if email_match else "N/A"

    # Extract Phone
    phone_match = re.search(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{4}', text)
    phone = phone_match.group(0) if phone_match else "N/A"

    # Extract Name (First line logic without Spacy)
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    name = "Candidate"
    if lines:
        first_line = lines[0]
        if len(first_line.split()) <= 4 and not any(char.isdigit() for char in first_line):
            name = first_line

    return name, email, phone

# Page UI Config
st.title("📄 Resume ATS & Candidate Matcher")

# Sidebar
st.sidebar.header("⚙️ Control Panel")
jd_text = st.sidebar.text_area("Paste Job Description (JD):", height=150)
uploaded_files = st.sidebar.file_uploader("Upload Resumes (PDF):", type=["pdf"], accept_multiple_files=True)

col_btn1, col_btn2 = st.sidebar.columns(2)
analyze_btn = col_btn1.button("🚀 Analyze & Save DB", type="primary")
reset_btn = col_btn2.button("🗑️ Reset DB")

if reset_btn:
    c.execute("DELETE FROM candidates")
    conn.commit()
    st.session_state.pop('df_results', None)
    st.sidebar.success("Database Reset Done!")

if analyze_btn and jd_text and uploaded_files:
    for file in uploaded_files:
        with pdfplumber.open(file) as pdf:
            resume_text = " ".join([page.extract_text() or "" for page in pdf.pages])

        # New Skill Matching and Score Calculation
        match_score, matched, missing = calculate_matches(resume_text, jd_text)
        name, email, phone = extract_details(resume_text)

        # Convert matched/missing lists to string
        matched_str = ", ".join(matched) if matched else "None"
        missing_str = ", ".join(missing) if missing else "None"

        # Save to Database
        c.execute('''
            INSERT INTO candidates (name, email, phone, match_score, matched_skills, missing_skills)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, email, phone, match_score, matched_str, missing_str))
        conn.commit()
    st.success(f"Processed {len(uploaded_files)} resumes and saved to Database!")

# Main Dashboard View
tab1, tab2, tab3 = st.tabs(["🏆 Live Ranking Dashboard", "📊 SQL Database View", "📈 Analytics & Insights"])

# Fetch Data from DB
df = pd.read_sql_query("SELECT * FROM candidates ORDER BY match_score DESC", conn)

with tab1:
    if not df.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Candidates Processed", len(df))
        col2.metric("Highest Match Score", f"{df['match_score'].max()}%")
        col3.metric("Average Match Score", f"{round(df['match_score'].mean(), 1)}%")
        
        st.subheader("🏆 Ranked Candidate Profiles")
        for idx, row in df.iterrows():
            with st.container():
                st.markdown(f"### {row['name']} — **{row['match_score']}% Match**")
                st.caption(f"📧 Email: {row['email']} | 📞 Phone: {row['phone']}")
                st.write(f"🟩 **Matched Skills:** {row['matched_skills'] if row['matched_skills'] else 'None'}")
                st.write(f"⚠️ **Missing Skills (Gaps):** {row['missing_skills'] if row['missing_skills'] else 'None'}")
                st.divider()
    else:
        st.info("No candidates analyzed yet. Upload resumes on the sidebar to view rankings.")

with tab2:
    if not df.empty:
        st.dataframe(df, use_container_width=True)
        st.download_button(
            label="📥 Export SQL Records as CSV",
            data=df.to_csv(index=False),
            file_name="candidate_records.csv",
            mime="text/csv",
            type="primary"
        )
    else:
        st.info("No records found in database.")

with tab3:
    if not df.empty:
        st.subheader("📊 Candidate Match Score Comparison")
        fig = px.bar(
            df, x="name", y="match_score", color="match_score",
            title="Match Score Ranking Chart", color_continuous_scale="Viridis",
            template="plotly_dark"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Analytics chart will display after resume processing.")
