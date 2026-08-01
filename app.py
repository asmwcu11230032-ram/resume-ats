import streamlit as st
import pdfplumber
import sqlite3
import pandas as pd
import re
import plotly.express as px

import spacy

# Load Spacy Model
@st.cache_resource
def load_spacy():
    import en_core_web_sm
    return en_core_web_sm.load()

nlp = load_spacy()


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
def clean_and_tokenize(text):
    text = text.lower()

    # Split strictly by comma, dash, bullet, or newline
    raw_skills = re.split(r'[\n\r\t,;•\-]', text)

    keywords = set()
    for skill in raw_skills:
        # Clean special characters but preserve full skill phrases
        clean_skill = re.sub(r'[^a-z0-9\s]', ' ', skill)
        clean_skill = " ".join(clean_skill.split())

        # Keep phrases/words longer than 2 characters
        if len(clean_skill) > 2:
            keywords.add(clean_skill)

    return keywords
# Extract Name, Email, Phone from Resume Text
def extract_details(text):
    doc = nlp(text)
    
    # Extract Email
    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    email = email_match.group(0) if email_match else "N/A"
    
    # Extract Phone
    phone_match = re.search(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
    phone = phone_match.group(0) if phone_match else "N/A"
    
    # Extract Name using Spacy PERSON Entity
    name = "Candidate"
    for ent in doc.ents:
        if ent.label_ == "PERSON" and len(ent.text.split()) <= 3:
            name = ent.text.strip()
            break
            
    if name == "Candidate":
        first_line = text.strip().split('\n')[0]
        if len(first_line.split()) <= 4 and not any(char.isdigit() for char in first_line):
            name = first_line.strip()

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
    jd_keywords = clean_and_tokenize(jd_text)
    
    for file in uploaded_files:
        with pdfplumber.open(file) as pdf:
            resume_text = " ".join([page.extract_text() or "" for page in pdf.pages])
            
        resume_keywords = clean_and_tokenize(resume_text)
        name, email, phone = extract_details(resume_text)
        
        # Skill Matching Logic
        matched = jd_keywords.intersection(resume_keywords)
        missing = jd_keywords - resume_keywords

        # Match Score Calculation
        match_score = round((len(matched) / len(jd_keywords)) * 100, 2) if jd_keywords else 0.0

        # Save to Database
        c.execute('''
            INSERT INTO candidates (name, email, phone, match_score, matched_skills, missing_skills)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, email, phone, match_score, ", ".join(matched), ", ".join(missing)))
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
