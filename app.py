import streamlit as st
import pandas as pd
import sqlite3
import re
import pdfplumber
import spacy
import plotly.express as px

# 1. Page Setup
st.set_page_config(
    page_title="AI Resume Screening System",
    page_icon="💼",
    layout="wide"
)

# Clean High-Contrast CSS for Tabs and Buttons
st.markdown("""
    <style>
    /* Tab Styling - Clear Text Visibility */
    .stTabs [data-baseweb="tab"] {
        font-size: 16px;
        font-weight: bold;
        color: #94a3b8 !important;
    }
    .stTabs [aria-selected="true"] {
        color: #38bdf8 !important;
        border-bottom-color: #38bdf8 !important;
    }
    
    /* Candidate Card Styling */
    .candidate-card {
        background-color: #1e293b;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 15px;
        border-left: 5px solid #38bdf8;
    }
    .candidate-card h3 {
        color: #ffffff !important;
        margin-top: 0;
    }
    .candidate-card p {
        color: #cbd5e1 !important;
        font-size: 15px;
        margin: 5px 0;
    }
    .match-tag {
        color: #4ade80 !important;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

# Load NLP Model
import os

@st.cache_resource
def load_nlp():
    try:
        return spacy.load("en_core_web_sm")
    except OSError:
        os.system("python -m spacy download en_core_web_sm")
        return spacy.load("en_core_web_sm")
nlp = load_nlp()

# 2. Database Functions
def init_db():
    conn = sqlite3.connect("candidate_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            phone TEXT,
            score REAL,
            matched_skills TEXT,
            missing_skills TEXT
        )
    """)
    conn.commit()
    conn.close()

def clear_db():
    conn = sqlite3.connect("candidate_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM candidates")
    conn.commit()
    conn.close()

init_db()

def save_to_db(name, email, phone, score, matched_skills, missing_skills):
    conn = sqlite3.connect("candidate_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO candidates (name, email, phone, score, matched_skills, missing_skills)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, email, phone, score, ", ".join(matched_skills), ", ".join(missing_skills)))
    conn.commit()
    conn.close()

# 3. Text & Skill Processing
def extract_text_from_pdf(file):
    text = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + " "
    return text

def extract_contact_info(text):
    email = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    phone = re.search(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
    return email.group(0) if email else "N/A", phone.group(0) if phone else "N/A"

def extract_name(text, filename):
    doc = nlp(text[:300])
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            return ent.text
    clean_name = filename.replace('.pdf', '').replace('_', ' ').replace('-', ' ')
    return clean_name.title()

def process_nlp_matching(resume_text, jd_text):
    jd_words = [w.strip().lower() for w in re.split(r'[,;\n\s]+', jd_text) if len(w.strip()) > 1]
    jd_keywords = set(jd_words)
    resume_lower = resume_text.lower()
    
    matched = [kw for kw in jd_keywords if kw in resume_lower]
    missing = [kw for kw in jd_keywords if kw not in resume_lower]

    score = round((len(matched) / len(jd_keywords) * 100), 2) if jd_keywords else 0
    return min(100, score), matched, missing

# 4. Streamlit App Body
st.title("🎯 AI Resume Screening & Ranking System")
st.caption("Powered by Natural Language Processing (NLP) & SQLite Database")
st.markdown("---")

with st.sidebar:
    st.header("⚙️ Control Panel")
    jd_input = st.text_area("Paste Job Description (JD):", height=150, placeholder="e.g. data entry, accountant, python")
    uploaded_files = st.file_uploader("Upload Resumes (PDF):", type=["pdf"], accept_multiple_files=True)
    
    col_btn1, col_btn2 = st.columns([2, 1])
    analyze_btn = col_btn1.button("🚀 Analyze & Save DB", type="primary", use_container_width=True)
    if col_btn2.button("🗑️ Reset DB"):
        clear_db()
        st.session_state.pop('df_results', None)
        st.success("Database Cleared!")

tab1, tab2, tab3 = st.tabs(["📊 Live Ranking Dashboard", "🗄️ SQL Database View", "📈 Analytics & Insights"])

if analyze_btn:
    if not jd_input or not uploaded_files:
        st.warning("Please upload resumes and paste a job description first!")
    else:
        results = []
        for file in uploaded_files:
            text = extract_text_from_pdf(file)
            email, phone = extract_contact_info(text)
            name = extract_name(text, file.name)
            score, matched, missing = process_nlp_matching(text, jd_input)
            
            save_to_db(name, email, phone, score, matched, missing)

            results.append({
                "Name": name,
                "Match Score": score,
                "Email": email,
                "Phone": phone,
                "Matched Skills": ", ".join(matched),
                "Skill Gap": ", ".join(missing)
            })

        df = pd.DataFrame(results).sort_values(by="Match Score", ascending=False)
        st.session_state['df_results'] = df
        st.success(f"Processed {len(uploaded_files)} resumes and saved to Database!")

# TAB 1: Ranking
with tab1:
    if 'df_results' in st.session_state:
        df = st.session_state['df_results']
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Candidates Processed", len(df))
        col2.metric("Highest Match Score", f"{df['Match Score'].max()}%")
        col3.metric("Average Match Score", f"{round(df['Match Score'].mean(), 1)}%")

        st.subheader("🏆 Ranked Candidate Profiles")
        for idx, row in df.iterrows():
            st.markdown(f"""
                <div class="candidate-card">
                    <h3>{row['Name']} — <span class="match-tag">{row['Match Score']}% Match</span></h3>
                    <p><b>📧 Email:</b> {row['Email']} | <b>📞 Phone:</b> {row['Phone']}</p>
                    <p><b>✅ Matched Skills:</b> {row['Matched Skills'] if row['Matched Skills'] else 'None'}</p>
                    <p><b>⚠️ Missing Skills (Gaps):</b> {row['Skill Gap'] if row['Skill Gap'] else 'None'}</p>
                </div>
            """, unsafe_allow_html=True)
    else:
        st.info("Upload resumes and click 'Analyze & Save DB' to view rankings.")

# TAB 2: SQL DB View
with tab2:
    st.subheader("🗄️ Candidate Records Stored in SQLite Database")
    conn = sqlite3.connect("candidate_database.db")
    db_df = pd.read_sql_query("SELECT * FROM candidates ORDER BY score DESC", conn)
    conn.close()

    if not db_df.empty:
        st.dataframe(db_df, use_container_width=True)
        st.download_button(
            label="📥 Export SQL Records as CSV",
            data=db_df.to_csv(index=False),
            file_name="candidate_records.csv",
            mime="text/csv",
            type="primary"
        )
    else:
        st.info("No records found in database. Analyze resumes or upload files to view records.")

# TAB 3: Analytics
with tab3:
    if 'df_results' in st.session_state:
        df = st.session_state['df_results']
        st.subheader("📈 Candidate Match Score Comparison")
        fig = px.bar(
            df, x="Name", y="Match Score", color="Match Score",
            title="Match Score Ranking Chart", color_continuous_scale="Viridis",
            template="plotly_dark"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Analytics chart will display after resume processing.")
