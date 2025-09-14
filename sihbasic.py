# student_risk_dashboard.py

import psycopg2
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# -----------------------------
# Database Connection Helper
# -----------------------------
DB_URL = "postgresql://postgres:Manitjain009.@db.ixhqsbvdalrefnotxmqi.supabase.co:5432/postgres"


def get_connection():
    return psycopg2.connect(DB_URL, sslmode="require")


def fetch_students():
    conn = get_connection()
    query = """
        SELECT s.id,
               s.name,
               s.email,
               s.contact_no,
               COALESCE(AVG(a.attendance), 0) AS attendance_percentage,
               COALESCE(AVG(m.maths), 0) AS maths,
               COALESCE(AVG(m.dsa), 0) AS dsa,
               COALESCE(AVG(m.oop), 0) AS oop,
               COALESCE(AVG(m.economics), 0) AS economics,
               COALESCE(SUM(f.amount), 0) AS fees_paid
        FROM student s
        LEFT JOIN attendance a ON s.id = a.student_id
        LEFT JOIN marks m ON s.id = m.student_id
        LEFT JOIN fees f ON s.id = f.student_id
        GROUP BY s.id, s.name, s.email, s.contact_no
        ORDER BY s.id;
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df


def log_login(username):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO mentor_logins (username, login_time) VALUES (%s, NOW())", (username,))
    conn.commit()
    conn.close()


# -----------------------------
# Add / Delete Student
# -----------------------------
def add_student(name, email, contact_no, attendance, maths, dsa, oop, economics, fees_paid):
    conn = get_connection()
    cur = conn.cursor()

    # Insert student
    cur.execute(
        "INSERT INTO student (name, email, contact_no) VALUES (%s, %s, %s) RETURNING id",
        (name, email, contact_no),
    )
    student_id = cur.fetchone()[0]

    # Insert attendance
    cur.execute(
        "INSERT INTO attendance (student_id, attendance) VALUES (%s, %s)",
        (student_id, attendance),
    )

    # Insert marks
    cur.execute(
        "INSERT INTO marks (student_id, maths, dsa, oop, economics) VALUES (%s, %s, %s, %s, %s)",
        (student_id, maths, dsa, oop, economics),
    )

    # Insert fees
    cur.execute(
        "INSERT INTO fees (student_id, amount) VALUES (%s, %s)",
        (student_id, fees_paid),
    )

    conn.commit()
    conn.close()


def delete_student(student_id):
    conn = get_connection()
    cur = conn.cursor()
    # Delete related records first (to avoid foreign key issues)
    cur.execute("DELETE FROM attendance WHERE student_id=%s", (student_id,))
    cur.execute("DELETE FROM marks WHERE student_id=%s", (student_id,))
    cur.execute("DELETE FROM fees WHERE student_id=%s", (student_id,))
    cur.execute("DELETE FROM student WHERE id=%s", (student_id,))
    conn.commit()
    conn.close()


# -----------------------------
# Risk Calculation
# -----------------------------
TOTAL_FEES = 30000


def calculate_risk(row):
    risk_flags = []
    if row['attendance_percentage'] < 75:
        risk_flags.append("Low Attendance")
    avg_score = (row['maths'] + row['dsa'] + row['oop'] + row['economics']) / 4
    if avg_score < 40:
        risk_flags.append("Low Marks")
    if row['fees_paid'] < 0.5 * TOTAL_FEES:
        risk_flags.append("Fee Pending")
    return ", ".join(risk_flags) if risk_flags else "OK"


def assign_risk_level(row):
    avg_score = (row['maths'] + row['dsa'] + row['oop'] + row['economics']) / 4
    if (row['attendance_percentage'] < 50 or avg_score < 30 or row['fees_paid'] < 0.25 * TOTAL_FEES):
        return "High"
    elif (50 <= row['attendance_percentage'] < 75 or 30 <= avg_score < 40 or
          0.25 * TOTAL_FEES <= row['fees_paid'] < 0.5 * TOTAL_FEES):
        return "Medium"
    elif (75 <= row['attendance_percentage'] < 80 or 40 <= avg_score < 50):
        return "Low"
    else:
        return "OK"


# -----------------------------
# Dynamic Mentor Assignment
# -----------------------------
MAX_STUDENTS_PER_MENTOR = 10


def assign_mentors(df):
    num_students = len(df)
    num_mentors = (num_students + MAX_STUDENTS_PER_MENTOR - 1) // MAX_STUDENTS_PER_MENTOR
    mentors = [f"Mentor {chr(65 + i)}" for i in range(num_mentors)]  # A, B, C ...

    mentor_list = []
    for i, _ in enumerate(df.itertuples()):
        mentor_index = i // MAX_STUDENTS_PER_MENTOR
        mentor_list.append(mentors[mentor_index])

    df['mentor'] = mentor_list
    return df


# -----------------------------
# Login System
# -----------------------------
USERS = {
    "Admin": "Supermentor@123",  # Super Mentor
    "Mentor A": "MentorA@123",
    "Mentor B": "MentorB@123",
    "Mentor C": "MentorC@123",
    "Mentor D": "MentorD@123",
    "Mentor E": "MentorE@123"
}

st.title("📊 Student Risk Dashboard")

# Session defaults
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "last_activity" not in st.session_state:
    st.session_state.last_activity = None
if "username" not in st.session_state:
    st.session_state.username = None


def logout():
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.last_activity = None
    st.warning("⏳ Session expired or logged out. Please log in again.")


# Auto logout after 5 minutes
if st.session_state.logged_in and st.session_state.last_activity:
    if datetime.now() - st.session_state.last_activity > timedelta(minutes=5):
        logout()

# -----------------------------
# LOGIN FORM
# -----------------------------
if not st.session_state.logged_in:
    username = st.text_input("👤 Username")
    password = st.text_input("🔑 Password", type="password")

    if st.button("Login"):
        if username in USERS and password == USERS[username]:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.last_activity = datetime.now()
            log_login(username)
            st.success(f"✅ Logged in as {username}")
            st.rerun()
        else:
            st.error("❌ Invalid credentials. Try again.")

# -----------------------------
# DASHBOARD (Only if logged in)
# -----------------------------
if st.session_state.logged_in:
    st.session_state.last_activity = datetime.now()

    df = fetch_students()
    df['risk_status'] = df.apply(calculate_risk, axis=1)
    df['dropout_label'] = df['risk_status'].apply(lambda x: 0 if x == "OK" else 1)
    df['risk_level'] = df.apply(assign_risk_level, axis=1)
    df = assign_mentors(df)

    username = st.session_state.username

    # -----------------------------
    # SUPER MENTOR VIEW
    # -----------------------------
    if username == "Admin":
        st.subheader("🛠 Super Mentor Controls")

        # Add student form
        with st.expander("➕ Add New Student"):
            new_name = st.text_input("Name")
            new_email = st.text_input("Email")
            new_contact = st.text_input("Contact No")
            new_attendance = st.number_input("Attendance %", min_value=0.0, max_value=100.0, value=75.0)
            new_maths = st.number_input("Maths Marks", min_value=0.0, max_value=100.0, value=50.0)
            new_dsa = st.number_input("DSA Marks", min_value=0.0, max_value=100.0, value=50.0)
            new_oop = st.number_input("OOP Marks", min_value=0.0, max_value=100.0, value=50.0)
            new_economics = st.number_input("Economics Marks", min_value=0.0, max_value=100.0, value=50.0)
            new_fees = st.number_input("Fees Paid", min_value=0.0, value=0.0)

            if st.button("Add Student"):
                if new_name and new_email and new_contact:
                    add_student(new_name, new_email, new_contact,
                                new_attendance, new_maths, new_dsa, new_oop, new_economics, new_fees)
                    st.success("✅ Student added successfully!")
                    st.rerun()
                else:
                    st.error("⚠️ Name, Email and Contact are required!")

        # Delete student form
        with st.expander("🗑 Delete Student"):
            student_to_delete = st.selectbox("Select Student to Delete", df['name'])
            student_id = df[df['name'] == student_to_delete]['id'].iloc[0]
            if st.button("Delete Student"):
                delete_student(student_id)
                st.warning(f"🚨 Student {student_to_delete} deleted!")
                st.rerun()

        # Probable Dropouts
        probable_dropouts = df[df['risk_level'].isin(["High", "Medium"])]
        st.subheader("⚠️ Probable Dropouts")
        st.dataframe(probable_dropouts[['id', 'name', 'attendance_percentage',
                                        'maths', 'dsa', 'oop', 'economics',
                                        'fees_paid', 'risk_level']])

        # Risk Distribution Pie Chart
        st.subheader("📊 Risk Distribution of All Students")
        risk_counts = df['risk_level'].value_counts()
        fig_pie, ax_pie = plt.subplots()
        ax_pie.pie(risk_counts, labels=risk_counts.index, autopct="%1.1f%%",
                   startangle=90, colors=["lightgreen", "yellow", "orange", "red"])
        ax_pie.axis("equal")
        st.pyplot(fig_pie)

    # -----------------------------
    # MENTOR VIEW
    # -----------------------------
    else:
        mentor_students = df[df['mentor'].str.strip().str.lower() == username.strip().lower()]

        st.subheader(f"👨‍🏫 Students Assigned to {username}")
        if mentor_students.empty:
            st.warning("⚠️ No students assigned to you yet.")
        else:
            st.dataframe(
                mentor_students[['id', 'name', 'attendance_percentage', 'fees_paid', 'risk_status', 'risk_level']])

            # Risk Distribution Pie Chart
            st.subheader("📊 Risk Distribution of Your Students")
            risk_counts = mentor_students['risk_level'].value_counts()
            fig_pie, ax_pie = plt.subplots()
            ax_pie.pie(risk_counts, labels=risk_counts.index, autopct="%1.1f%%",
                       startangle=90, colors=["lightgreen", "yellow", "orange", "red"])
            ax_pie.axis("equal")
            st.pyplot(fig_pie)

            # Select student
            student_choice = st.selectbox("Select a Student:", mentor_students['name'])
            student_data = mentor_students[mentor_students['name'] == student_choice].iloc[0]

            st.subheader(f"📌 Details for {student_choice}")
            st.write(student_data)

            # Student vs Class Average
            avg_scores = df[['maths', 'dsa', 'oop', 'economics']].mean()
            fig, ax = plt.subplots()
            student_scores = [student_data['maths'], student_data['dsa'], student_data['oop'],
                              student_data['economics']]
            subjects = ['Maths', 'DSA', 'OOP', 'Economics']

            x = range(len(subjects))
            ax.bar(x, student_scores, width=0.4, label=f"{student_choice}", align="center")
            ax.bar([i + 0.4 for i in x], avg_scores, width=0.4, label="Class Average", align="center")
            ax.set_xticks([i + 0.2 for i in x])
            ax.set_xticklabels(subjects)
            ax.set_ylabel("Scores")
            ax.set_title("Student vs Class Average")
            ax.legend()
            st.pyplot(fig)

            # Attendance comparison
            fig2, ax2 = plt.subplots()
            ax2.bar(["Student", "Class Avg"],
                    [student_data['attendance_percentage'], df['attendance_percentage'].mean()],
                    color=["blue", "green"])
            ax2.set_ylabel("Attendance %")
            st.pyplot(fig2)

            # Fees comparison
            fig3, ax3 = plt.subplots()
            ax3.bar(["Student", "Class Avg"],
                    [student_data['fees_paid'], df['fees_paid'].mean()],
                    color=["purple", "orange"])
            ax3.set_ylabel("Fees Paid")
            st.pyplot(fig3)

    if st.button("🚪 Logout"):
        logout()
        st.rerun()
