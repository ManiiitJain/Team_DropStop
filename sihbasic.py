import streamlit as st
import psycopg2
import pandas as pd
import string
import matplotlib.pyplot as plt
from psycopg2.extras import execute_values
from psycopg2 import sql
from datetime import datetime
import smtplib
from email.message import EmailMessage
import google.generativeai as genai  

# -----------------------------
# CONFIGURATION
# -----------------------------
genai.configure(api_key="YOUR_GEMINI_API_KEY")  
DB_URL = "postgresql://postgres.ixhqsbvdalrefnotxmqi:wwcbN4nmUC1YLW9C@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres"
STUDENTS_PER_MENTOR = 50

# -----------------------------
# SESSION STATE INITIALIZATION
# -----------------------------
def init_session_state():
    defaults = {
        "role": None,
        "mentor_id": None,
        "student_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# -----------------------------
# DATABASE CONNECTION
# -----------------------------
def get_connection():
    return psycopg2.connect(DB_URL, sslmode="require")

# -----------------------------
# LOG USER LOGIN
# -----------------------------
def log_user_login(username):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO logins (username, login_time) VALUES (%s, %s)",
            (username, datetime.now())
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        st.error(f"❌ Failed to log login: {e}")
    finally:
        cur.close()
        conn.close()

# -----------------------------
# CSV UPLOAD FUNCTION
# -----------------------------
def insert_csv_to_table(csv_file, table_name, conn):
    df = pd.read_csv(csv_file)
    if df.empty:
        st.warning(f"{table_name} CSV is empty, skipping...")
        return

    if table_name == "student":
        if "student_email" in df.columns:
            df.rename(columns={"student_email": "email"}, inplace=True)
        if "dob" in df.columns:
            df.drop(columns=["dob"], inplace=True)

    cursor = conn.cursor()
    cols = list(df.columns)

    values = [
        tuple(
            None if pd.isna(x) else
            int(x) if isinstance(x, (int, float)) and float(x).is_integer() else
            float(x) if isinstance(x, (int, float)) else
            str(x)
            for x in row
        )
        for row in df.to_numpy()
    ]

    insert_stmt = sql.SQL("INSERT INTO {table} ({fields}) VALUES %s").format(
        table=sql.Identifier(table_name),
        fields=sql.SQL(',').join(map(sql.Identifier, cols))
    )
    try:
        execute_values(cursor, insert_stmt, values)
        conn.commit()
        st.success(f"✅ Uploaded {len(df)} rows into {table_name}")
    except Exception as e:
        conn.rollback()
        st.error(f"❌ Error inserting into {table_name}: {e}")
    finally:
        cursor.close()

# -----------------------------
# FETCH STUDENTS
# -----------------------------
def fetch_students():
    conn = get_connection()
    query = """
        SELECT s.id, s.name, s.email, s.parent_email, s.contact_no,
               COALESCE(a.total_attendance,0) AS total_attendance,
               COALESCE(m.maths,0) AS maths,
               COALESCE(m.dsa,0) AS dsa,
               COALESCE(m.oop,0) AS oop,
               COALESCE(m.economics,0) AS economics,
               COALESCE(f.fee_status,'pending') AS fee_status
        FROM student s
        LEFT JOIN attendance a ON s.id = a.student_id
        LEFT JOIN marks m ON s.id = m.student_id
        LEFT JOIN fees f ON s.id = f.student_id
        ORDER BY s.id;
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df

# -----------------------------
# MENTOR ALLOCATION
# -----------------------------
def generate_mentor_ids(num_students, students_per_mentor=STUDENTS_PER_MENTOR):
    alphabet = list(string.ascii_uppercase)
    mentor_ids = []
    count, i = 0, 0
    while count < num_students:
        if i < 26:
            mentor_ids.append(f"Mentor {alphabet[i]}")
        else:
            prefix = (i // 26) - 1
            suffix = i % 26
            mentor_ids.append(f"Mentor {alphabet[prefix]}{alphabet[suffix]}")
        count += students_per_mentor
        i += 1
    return mentor_ids

def assign_students_to_mentors(student_df):
    num_students = len(student_df)
    mentor_ids = generate_mentor_ids(num_students)
    allocation = {}
    idx = 0
    for mentor in mentor_ids:
        allocation[mentor] = student_df.iloc[idx: idx + STUDENTS_PER_MENTOR]
        idx += STUDENTS_PER_MENTOR
    return allocation

# -----------------------------
# RISK CALCULATION
# -----------------------------
def calculate_risk(row):
    flags = []
    if row['total_attendance'] < 75:
        flags.append("Low Attendance")
    avg_score = (row['maths'] + row['dsa'] + row['oop'] + row['economics']) / 4
    if avg_score < 40:
        flags.append("Low Marks")
    if str(row['fee_status']).lower() != "paid":
        flags.append("Fee Pending")
    return ", ".join(flags) if flags else "OK"

def assign_risk_level(row):
    avg_score = (row['maths'] + row['dsa'] + row['oop'] + row['economics']) / 4
    if row['total_attendance'] < 50 or avg_score < 30 or str(row['fee_status']).lower() != "paid":
        return "High"
    elif 50 <= row['total_attendance'] < 75 or 30 <= avg_score < 40:
        return "Medium"
    elif 75 <= row['total_attendance'] < 80 or 40 <= avg_score < 50:
        return "Low"
    else:
        return "OK"

def highlight_risk(row):
    colors = {"OK": "lightgreen", "Low": "yellow", "Medium": "orange", "High": "red"}
    return ["background-color: %s" % colors.get(row.get("risk_level", ""), "")] * len(row)

# -----------------------------
# AI CHATBOT (Gemini)
# -----------------------------
def chat_with_ai(user_message):
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")  # ✅ using Gemini
        response = model.generate_content(user_message)
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"

# -----------------------------
# EMAIL FUNCTION
# -----------------------------
def send_email_to_parent(student, sender_email, app_password):
    parent_email = student.get('parent_email', None)
    if not parent_email:
        return

    subject = f"Performance Report: {student['name']}"
    body = f"""
Hello Parent,

Here is the performance summary for your child, {student['name']}:

Attendance: {student['total_attendance']}%
Maths: {student['maths']}
DSA: {student['dsa']}
OOP: {student['oop']}
Economics: {student['economics']}
Fee Status: {student['fee_status']}
Risk Level: {student['risk_level']}

Regards,
Academic Team
"""

    try:
        msg = EmailMessage()
        msg['From'] = sender_email
        msg['To'] = parent_email
        msg['Subject'] = subject
        msg.set_content(body)

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(sender_email, app_password)
            smtp.send_message(msg)

        st.success(f"✅ Email sent to {parent_email}")
    except Exception as e:
        st.error(f"❌ Failed to send email to {parent_email}: {e}")

# -----------------------------
# LOGOUT
# -----------------------------
def logout_button():
    if st.sidebar.button("🚪 Logout"):
        st.session_state.clear()
        st.success("You have been logged out")
        st.stop()

# -----------------------------
# LOGIN PAGE
# -----------------------------
def login_page():
    st.title("Login Portal")
    user_id = st.text_input("User ID")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if user_id == "Admin" and password == "Admin@123":
            st.session_state["role"] = "admin"
            st.success("Logged in as Admin")
            log_user_login(user_id)
            st.stop()
        elif user_id.startswith("Mentor"):
            mentor_name = user_id.split(" ")[1] if len(user_id.split(" ")) > 1 else ""
            if password == f"Mentor{mentor_name}@123":
                st.session_state["role"] = "mentor"
                st.session_state["mentor_id"] = user_id
                st.success(f"Logged in as {user_id}")
                log_user_login(user_id)
                st.stop()
            else:
                st.error("Invalid Mentor credentials")
        elif user_id.lower().startswith("student_"):
            try:
                sid = int(user_id.split("_")[1])
                if password == f"student_{sid}@123":
                    st.session_state["role"] = "student"
                    st.session_state["student_id"] = sid
                    st.success(f"Logged in as Student {sid}")
                    log_user_login(user_id)
                    st.stop()
                else:
                    st.error("Invalid Student credentials")
            except:
                st.error("Invalid Student ID format")
        else:
            st.error("Invalid credentials")

# -----------------------------
# ADMIN PAGE
# -----------------------------
def admin_page():
    logout_button()
    st.header("🛠 Admin Dashboard")

    # Email config only for Admin
    st.sidebar.title("📧 Email Config")
    sender_email = st.sidebar.text_input("Sender Gmail")
    app_password = st.sidebar.text_input("App Password", type="password")

    conn = get_connection()
    student_file = st.file_uploader("Upload Student CSV", type=["csv"], key="stu")
    attendance_file = st.file_uploader("Upload Attendance CSV", type=["csv"], key="att")
    fees_file = st.file_uploader("Upload Fees CSV", type=["csv"], key="fee")
    marks_file = st.file_uploader("Upload Marks CSV", type=["csv"], key="mar")

    if st.button("Upload All CSVs"):
        if student_file and attendance_file and fees_file and marks_file:
            insert_csv_to_table(student_file, "student", conn)
            insert_csv_to_table(attendance_file, "attendance", conn)
            insert_csv_to_table(fees_file, "fees", conn)
            insert_csv_to_table(marks_file, "marks", conn)
        else:
            st.error("Upload all 4 CSVs")
    conn.close()

    df = fetch_students()
    df['risk_status'] = df.apply(calculate_risk, axis=1).astype(str)
    df['risk_level'] = df.apply(assign_risk_level, axis=1).astype(str)

    st.subheader("📋 All Students")
    st.dataframe(df.style.apply(highlight_risk, axis=1))

    st.subheader("📊 Risk Distribution")
    counts = df['risk_level'].value_counts()
    color_map = {"OK": "lightgreen", "Low": "yellow", "Medium": "orange", "High": "red"}
    fig, ax = plt.subplots()
    ax.pie(
        [counts.get(l, 0) for l in ["OK", "Low", "Medium", "High"]],
        labels=["OK", "Low", "Medium", "High"],
        autopct="%1.1f%%",
        startangle=90,
        colors=[color_map["OK"], color_map["Low"], color_map["Medium"], color_map["High"]],
    )
    ax.axis("equal")
    st.pyplot(fig)

    # Send real emails (only if config filled)
    if sender_email and app_password:
        st.subheader("📨 Send Performance Emails to Parents")
        if st.button("Send Emails to All Students"):
            for _, student in df.iterrows():
                send_email_to_parent(student, sender_email, app_password)
    else:
        st.info("Enter Gmail + App Password in sidebar to enable email sending.")

# -----------------------------
# MENTOR PAGE
# -----------------------------
def mentor_page():
    mentor_id = st.session_state.get("mentor_id")
    if not mentor_id:
        st.warning("Mentor not logged in. Please login first.")
        login_page()
        return

    logout_button()
    st.header(f"👨‍🏫 Mentor Dashboard - {mentor_id}")

    # Email config only for Mentor
    st.sidebar.title("📧 Email Config")
    sender_email = st.sidebar.text_input("Sender Gmail")
    app_password = st.sidebar.text_input("App Password", type="password")

    df = fetch_students()
    df['risk_status'] = df.apply(calculate_risk, axis=1)
    df['risk_level'] = df.apply(assign_risk_level, axis=1)
    allocation = assign_students_to_mentors(df)
    mentor_students = allocation.get(mentor_id, pd.DataFrame())

    if mentor_students.empty:
        st.warning("No students assigned")
    else:
        st.dataframe(mentor_students.style.apply(highlight_risk, axis=1))
        counts = mentor_students['risk_level'].value_counts()
        color_map = {"OK": "lightgreen", "Low": "yellow", "Medium": "orange", "High": "red"}
        fig, ax = plt.subplots()
        ax.pie(
            [counts.get(l, 0) for l in ["OK", "Low", "Medium", "High"]],
            labels=["OK", "Low", "Medium", "High"],
            autopct="%1.1f%%",
            startangle=90,
            colors=[color_map["OK"], color_map["Low"], color_map["Medium"], color_map["High"]],
        )
        ax.axis("equal")
        st.pyplot(fig)

        # Send emails (only if config filled)
        if sender_email and app_password:
            st.subheader("📨 Send Emails to Your Students' Parents")
            if st.button("Send Emails to My Students"):
                for _, student in mentor_students.iterrows():
                    send_email_to_parent(student, sender_email, app_password)
        else:
            st.info("Enter Gmail + App Password in sidebar to enable email sending.")

        # Student search
        student_search = st.text_input("Search Student by ID or Name")
        if student_search:
            filtered = mentor_students[
                (mentor_students['id'].astype(str) == student_search) |
                (mentor_students['name'].str.contains(student_search, case=False))
            ]
            if not filtered.empty:
                st.dataframe(filtered.style.apply(highlight_risk, axis=1))
                avg_attendance = mentor_students['total_attendance'].mean()
                st.write(f"Class average attendance: {avg_attendance:.2f}%")
                for _, row in filtered.iterrows():
                    st.write(f"{row['name']}'s attendance vs class: {row['total_attendance']}% vs {avg_attendance:.2f}%")
            else:
                st.warning("Student not found")

# -----------------------------
# STUDENT PAGE
# -----------------------------
def student_page():
    student_id = st.session_state.get("student_id")
    role = st.session_state.get("role")
    if role != "student" or not student_id:
        st.warning("Student not logged in. Please login first.")
        login_page()
        return

    logout_button()
    st.header(f"👩‍🎓 Student Dashboard - ID {student_id}")

    df = fetch_students()
    df['risk_status'] = df.apply(calculate_risk, axis=1)
    df['risk_level'] = df.apply(assign_risk_level, axis=1)

    student_df = df[df['id'] == student_id]
    if student_df.empty:
        st.error("⚠️ No student record found. Please contact admin.")
        return

    student = student_df.iloc[0]
    st.write(student[['name', 'total_attendance', 'maths', 'dsa', 'oop', 'economics', 'risk_level']])

    # AI Chatbot
    user_message = st.text_input("Ask your AI mentor for help:")
    if user_message:
        response = chat_with_ai(user_message)
        st.write(response)

# -----------------------------
# MAIN
# -----------------------------
def main():
    role = st.session_state.get("role")
    if not role:
        login_page()
    else:
        if role == "admin":
            admin_page()
        elif role == "mentor":
            mentor_page()
        elif role == "student":
            student_page()

if __name__ == "__main__":
    main()
