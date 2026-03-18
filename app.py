import os
from flask import Flask, render_template, request, redirect
import psycopg2
from datetime import date, datetime
import schedule
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
        task TEXT,
        status TEXT DEFAULT 'pending',
        created_at DATE DEFAULT CURRENT_DATE,
        user_id INTEGER REFERENCES users(id)
    )
    """)

    # LEARNING
    c.execute("""
    CREATE TABLE IF NOT EXISTS learning (
        id SERIAL PRIMARY KEY,
        topic TEXT,
        hours REAL,
        platform TEXT,
        created_at DATE DEFAULT CURRENT_DATE,
        user_id INTEGER REFERENCES users(id)
    )
    """)

    # GOALS
    c.execute("""
    CREATE TABLE IF NOT EXISTS goals (
        id SERIAL PRIMARY KEY,
        start_date DATE,
        end_date DATE,
        user_id INTEGER REFERENCES users(id)
    )
    """)

    conn.commit()
    conn.close()
    
# ---------------- Home  ----------------
@app.route("/")
def home():
    if current_user.is_authenticated:
        return redirect("/index")  
       return render_template( "index.html", index)# logged in user
    return redirect("/login")           # not logged in

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
        return redirect("/login")

    return render_template("signup.html")

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

        if user and check_password_hash(user[3], password):
            login_user(User(user[0], user[1], user[2]))
            return redirect("/dashboard")

        return "Invalid credentials!"

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")

# ---------------- TASKS ----------------
@app.route("/tasks", methods=["GET", "POST"])
@login_required
def tasks():
    conn = connect_db()
    c = conn.cursor()

    if request.method == "POST":
        task = request.form["task"]
        c.execute(
            "INSERT INTO tasks (task, user_id) VALUES (%s, %s)",
            (task, current_user.id)
        )
        conn.commit()

    c.execute("SELECT * FROM tasks WHERE user_id=%s", (current_user.id,))
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

    return redirect("/tasks")

# ---------------- LEARNING ----------------
@app.route("/learning", methods=["GET", "POST"])
@login_required
def learning():
    conn = connect_db()
    c = conn.cursor()

    if request.method == "POST":
        c.execute(
            "INSERT INTO learning (topic, hours, platform, user_id) VALUES (%s,%s,%s,%s)",
            (
                request.form["topic"],
                float(request.form["hours"]),
                request.form["platform"],
                current_user.id
            )
        )
        conn.commit()

    c.execute("SELECT * FROM learning WHERE user_id=%s", (current_user.id,))
    data = c.fetchall()

    conn.close()
    return render_template("learning.html", data=data)

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
@login_required
def dashboard():
    conn = connect_db()
    c = conn.cursor()

    c.execute("SELECT * FROM tasks WHERE user_id=%s", (current_user.id,))
    tasks = c.fetchall()

    c.execute("SELECT * FROM learning WHERE user_id=%s", (current_user.id,))
    learning = c.fetchall()

    done_tasks = [t for t in tasks if t[2] == "Done"]
    completion = (len(done_tasks)/len(tasks)*100) if tasks else 0

    total_hours = sum([float(l[2]) for l in learning]) if learning else 0

    conn.close()

    xp = len(done_tasks)*10 + int(total_hours*5)

    return render_template(
        "dashboard.html",
        completion=round(completion,2),
        total_hours=total_hours,
        xp=xp,
        level=xp//100
    )

# ---------------- RUN ----------------
if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_scheduler, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
