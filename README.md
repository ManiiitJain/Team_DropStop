🎓 Academic Mentorship & Student Monitoring System

This is a Streamlit-based web application that integrates with PostgreSQL and Google Gemini AI to manage students, mentors, and academic risks.
It provides dashboards for Admins, Mentors, and Students with features like CSV uploads, AI chatbot support, performance analysis, and email notifications.

🚀 Features
🔑 Login Portal

Admin Login → Upload CSVs, manage records, view risk analysis, send emails to all parents.

Mentor Login → View assigned students, track performance, analyze risk distribution, and email parents.

Student Login → Access personal records and interact with an AI-powered chatbot mentor.

📊 Admin Dashboard

Upload Student, Attendance, Fees, and Marks CSV files.

Risk analysis based on attendance, marks, and fee payment status.

Risk visualization with pie charts.

Bulk email to parents with performance reports.

👨‍🏫 Mentor Dashboard

View only assigned students.

Risk analysis and visualization.

Send performance emails to parents.

Search for students by ID or Name.

Compare student attendance with class averages.

👩‍🎓 Student Dashboard

View personal performance, attendance, and risk status.

Chat with an AI-powered mentor (Gemini AI) for academic guidance.

🧠 Risk Assessment

High Risk → Attendance < 50% OR Avg score < 30 OR Fees unpaid.

Medium Risk → Attendance 50–74% OR Avg score 30–39.

Low Risk → Attendance 75–79% OR Avg score 40–49.

OK → Attendance ≥ 80% AND Avg score ≥ 50 AND Fees paid.

✉️ Email Alerts

Sends personalized performance reports to parents via Gmail SMTP.

Uses App Passwords for secure login.

🛠️ Tech Stack

Frontend → Streamlit

Backend/Database → PostgreSQL (via psycopg2)

AI Chatbot → Google Gemini
 (google-generativeai)
 

📂 Project Structure
project/
│── app.py                # Main Streamlit app (the code you provided)
│── requirements.txt       # Python dependencies
│── README.md              # Documentation
└── data/                  # (Optional) Sample CSV files


Visualization → Matplotlib

Emailing → Python smtplib + email.message
