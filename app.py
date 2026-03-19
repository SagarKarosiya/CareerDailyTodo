import os
from flask import Flask,flash, render_template, request, redirect, url_for
import psycopg2
from datetime import date
import schedule
import sqlite3 
import time
import threading
from dotenv import load_dotenv

from flask_login import (
    LoginManager, UserMixin, login_user,
    login_required, logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------- INIT ----------------
load_dotenv()
app = Flask(__name__)
app.secret_key = "supersecretkey"

DATABASE_URL = os.getenv("DATABASE_URL")
# If you didn't change anything during installation, 
# the default user is usually 'postgres'
#DATABASE_URL = "postgresql://postgres:704948@localhost:5432/postgres"


# ---------------- LOGIN SETUP ----------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ---------------- USER CLASS ----------------
class User(UserMixin):
    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email

# ---------------- DATABASE ----------------
def connect_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = connect_db()
    c = conn.cursor()
    
    # ADD THIS LINE TO RESET THE LEARNING TABLE
    c.execute("DROP TABLE IF EXISTS learning CASCADE;")
    c.execute("DROP TABLE IF EXISTS tasks CASCADE;")
    c.execute("DROP TABLE IF EXISTS goals CASCADE;")
    
    
    # USERS
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )
    """)

    # TASKS
    c.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    task TEXT NOT NULL,
    description TEXT,
    category TEXT,
    frequency TEXT,
    status TEXT DEFAULT 'pending',
    created_at DATE DEFAULT CURRENT_DATE,
    user_id INTEGER REFERENCES users(id)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS learning (
    id SERIAL PRIMARY KEY,
    topic TEXT,
    hours REAL,
    platform TEXT,
    status TEXT DEFAULT 'Pending', -- <--- ADD THIS LINE
    created_at DATE DEFAULT CURRENT_DATE,
    user_id INTEGER REFERENCES users(id)
    )
    """)

    # GOALS
    # GOALS Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS goals (
        id SERIAL PRIMARY KEY,
        start_date DATE NOT NULL,
        end_date DATE NOT NULL,
        user_id INTEGER REFERENCES users(id)
    )
    """)

    conn.commit()
    conn.close()

# ---------------- LOAD USER ----------------
@login_manager.user_loader
def load_user(user_id):
    conn = connect_db()
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = c.fetchone()
    conn.close()

    if user:
        return User(user[0], user[1], user[2])
    return None

# ---------------- REMINDER ----------------
def send_reminder():
    conn = connect_db()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'")
    pending = c.fetchone()[0]

    if pending > 0:
        print(f"⚠️ Reminder: {pending} pending tasks!")

    conn.close()

schedule.every().day.at("20:00").do(send_reminder)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

# ---------------- ROUTES ----------------


# 🏠 HOME (Landing Page)
@app.route("/")
def home():
    if not current_user.is_authenticated:
        return render_template(
            "welcome2.html", 
            progress=0, streak=0, xp=0, level=0, xp_progress=0,
            days_left=90, data30=[0], data60=[0], data90=[0],
            total_tasks=0, completed_tasks=0, total_learning=0, completed_learning=0
        )

    conn = connect_db()
    c = conn.cursor()

    # 1. Fetch Task Counts
    c.execute("SELECT COUNT(*) FROM tasks WHERE user_id=%s", (current_user.id,))
    t_total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM tasks WHERE user_id=%s AND status='Done'", (current_user.id,))
    t_completed = c.fetchone()[0]

    # 2. Fetch Learning Counts (Assuming topics are individual items)
    c.execute("SELECT COUNT(*) FROM learning WHERE user_id=%s", (current_user.id,))
    l_total = c.fetchone()[0]
    # For now, let's assume all logged learning is 'completed' or adjust logic if you have a status column
    l_completed = l_total 

    # Calculations for Progress Bar
    progress = (t_completed / t_total * 100) if t_total > 0 else 0
    xp = t_completed * 10
    level = xp // 100
    
    # Days Left Logic (from your goals table)
    c.execute("SELECT end_date FROM goals WHERE user_id=%s", (current_user.id,))
    goal = c.fetchone()
    days_left = (goal[0] - date.today()).days if goal else 90

    conn.close()

    return render_template(
        "welcome2.html",
        total_tasks=t_total,
        completed_tasks=t_completed,
        total_learning=l_total,
        completed_learning=l_completed,
        progress=round(progress, 2),
        streak=5, # Placeholder
        xp=xp,
        level=level,
        xp_progress=xp % 100,
        days_left=max(0, days_left),
        data30=[10, 20, 30, 40, 50], # Placeholder
        data90=[30, 60, 90, 100]      # Placeholder
    ) 
# ---------------- AUTH ----------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        conn = connect_db()
        c = conn.cursor()

        try:
            c.execute(
                "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                (username, email, password)
            )
            conn.commit()
        except:
            conn.close()
            return "User already exists!"

        conn.close()
        return redirect(url_for("login"))

    return render_template("signup.html")


# ----------------Login--------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = connect_db()
        c = conn.cursor()

        c.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = c.fetchone()
        conn.close()

        if not user:
            flash("User not found! Please check your email or sign up.", "error")
            return redirect(url_for("login"))

        if not check_password_hash(user[3], password):
            flash("Incorrect password! Please try again.", "error")
            return redirect(url_for("login"))

        # If both are correct:
        login_user(User(user[0], user[1], user[2]))
        return redirect(url_for("home"))

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))

# ---------------- TASKS ----------------
@app.route("/tasks", methods=["GET", "POST"])
@login_required
def tasks():
    conn = connect_db()
    c = conn.cursor()

    if request.method == "POST":
        task_name = request.form["task"]
        description = request.form["description"]
        category = request.form["category"]
        frequency = request.form["frequency"]
        
        c.execute(
            "INSERT INTO tasks (task, description, category, frequency, user_id) VALUES (%s, %s, %s, %s, %s)",
            (task_name, description, category, frequency, current_user.id)
        )
        conn.commit()

    # Make sure to fetch all columns so the index numbers in HTML work
    c.execute("SELECT id, task, status, description, category, frequency FROM tasks WHERE user_id=%s ORDER BY id DESC", (current_user.id,))
    tasks = c.fetchall()

    conn.close()
    return render_template("tasks.html", tasks=tasks)

@app.route("/done/<int:id>")
@login_required
def done(id):
    conn = connect_db()
    c = conn.cursor()

    c.execute(
        "UPDATE tasks SET status='Done' WHERE id=%s AND user_id=%s",
        (id, current_user.id)
    )
    conn.commit()
    conn.close()

    return redirect(url_for("tasks"))

     # Delete Task Button
@app.route("/delete/<int:id>")
@login_required
def delete_task(id):
    conn = connect_db()
    c = conn.cursor()
    c.execute("DELETE FROM tasks WHERE id=%s AND user_id=%s", (id, current_user.id))
    conn.commit()
    conn.close()
    return redirect(url_for("tasks"))

# ---------------- LEARNING ----------------
@app.route("/learning", methods=["GET", "POST"])
@login_required
def learning():
    conn = connect_db()
    c = conn.cursor()

    if request.method == "POST":
        try:
            c.execute(
                "INSERT INTO learning (topic, hours, platform, user_id) VALUES (%s, %s, %s, %s)",
                (
                    request.form["topic"],
                    float(request.form["hours"]),
                    request.form["platform"],
                    current_user.id
                )
            )
            conn.commit()
        except Exception as e:
            print(f"Error inserting learning data: {e}")

    # Fetch data specifically in the order: topic, hours, platform
    c.execute("SELECT topic, hours, platform FROM learning WHERE user_id=%s", (current_user.id,))
    data = c.fetchall()

    # --- PREPARE DATA FOR CHART.JS ---
    # labels = List of topics (['Python', 'React', ...])
    # values = List of hours ([5.5, 10.0, ...])
    labels = [row[0] for row in data]
    values = [row[1] for row in data]

    c.close()
    conn.close()

    return render_template(
        "learning.html", 
        data=data, 
        labels=labels, 
        values=values
    )
 # Delete button
@app.route("/delete_learning/<topic>")
@login_required
def delete_learning(topic):
    conn = connect_db()
    c = conn.cursor()
    
    # We delete by topic name and user_id for security
    c.execute("DELETE FROM learning WHERE topic=%s AND user_id=%s", (topic, current_user.id))
    
    conn.commit()
    c.close()
    conn.close()
    return redirect(url_for("learning"))


# --------------Index --------------------
    # This is the actual Dashboard page
@app.route("/index")
@login_required
def index():
    conn = connect_db()
    c = conn.cursor()

    # --- TASK DATA ---
    c.execute("SELECT COUNT(*) FROM tasks WHERE user_id=%s", (current_user.id,))
    t_total = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM tasks WHERE user_id=%s AND status='Done'", (current_user.id,))
    t_completed = c.fetchone()[0] or 0

    # --- LEARNING DATA ---
    # --- LEARNING DATA ---
# Total topics the user has ever logged
    c.execute("SELECT COUNT(*) FROM learning WHERE user_id=%s", (current_user.id,))
    l_total = c.fetchone()[0] or 0

# Topics the user has finished (This now works because the column exists!)
    c.execute("SELECT COUNT(*) FROM learning WHERE user_id=%s AND status='Completed'", (current_user.id,))
    l_completed = c.fetchone()[0] or 0

# Calculate "Left to Complete"
    l_left = l_total - l_completed

    conn.close()

    # --- MATH FOR OVERALL PROGRESS ---
    # Combine Tasks + Learning for a "Master" progress bar
    total_items = t_total + l_total
    total_done = t_completed + l_completed
    overall_perc = round((total_done / total_items * 100), 1) if total_items > 0 else 0

    return render_template(
        "index.html",
        total_tasks=t_total,
        completed_tasks=t_completed,
        total_learning=l_total,
        completed_learning=l_completed,
        progress=overall_perc,
        days_left=90,
        data30=[10, 20, 30, 40, 50], # These should ideally come from DB too
        data90=[30, 60, 90, 100]
    )
# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
@login_required
def dashboard():
    conn = connect_db()
    c = conn.cursor()

    # Get Tasks Counts
    c.execute("SELECT COUNT(*) FROM tasks WHERE user_id=%s", (current_user.id,))
    total_tasks = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM tasks WHERE user_id=%s AND status='Done'", (current_user.id,))
    completed_tasks = c.fetchone()[0]

    # Get Learning Counts
    c.execute("SELECT COUNT(*) FROM learning WHERE user_id=%s", (current_user.id,))
    total_learning = c.fetchone()[0]
    completed_learning = total_learning 

    # Calculate Stats
    completion = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
    
    c.execute("SELECT SUM(hours) FROM learning WHERE user_id=%s", (current_user.id,))
    total_hours = c.fetchone()[0] or 0

    # Days Left
    c.execute("SELECT end_date FROM goals WHERE user_id=%s", (current_user.id,))
    goal = c.fetchone()
    days_left = (goal[0] - date.today()).days if goal else 90

    conn.close()

    return render_template(
        "dashboard.html",
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        total_learning=total_learning,
        completed_learning=completed_learning,
        completion=round(completion, 2),
        total_hours=total_hours,
        progress=round(completion, 2),
        xp=completed_tasks * 10,
        level=(completed_tasks * 10) // 100,
        streak=5,
        days_left=max(0, days_left),
        incomplete_tasks=total_tasks - completed_tasks
    )

# --------------- Set Goal ----------------

from datetime import datetime

@app.route("/set_goal", methods=["POST"])
@login_required
def set_goal():
    start_date = request.form.get("start")
    end_date = request.form.get("end")

    if start_date and end_date:
        conn = connect_db()
        c = conn.cursor()

        # Delete any old goals for this user first
        c.execute("DELETE FROM goals WHERE user_id=%s", (current_user.id,))
        
        # Insert the new goal
        c.execute(
            "INSERT INTO goals (start_date, end_date, user_id) VALUES (%s, %s, %s)",
            (start_date, end_date, current_user.id)
        )
        
        conn.commit()
        conn.close()
        flash("Goal period updated successfully!", "success")
    
    return redirect(url_for("dashboard"))

# -----------------Credit -------------
@app.route("/credits")
def credits():
    return render_template("credits.html")

# ---------------- RUN ----------------
if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_scheduler, daemon=True).start()
    app.run(host="0.0.0.0", port=1000 ,debug=True)
#    app.run(debug=True)
