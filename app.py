from flask import Flask, render_template, request, redirect, session
import sqlite3
import os
from groq import Groq

app = Flask(__name__)
app.secret_key = 'secret123'

# 🔐 Groq API
client = Groq(api_key="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")

# ---------------- DATABASE ----------------

def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id INTEGER,
        question TEXT,
        option1 TEXT,
        option2 TEXT,
        option3 TEXT,
        option4 TEXT,
        correct_option TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        roll_no TEXT UNIQUE,
        password TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_roll TEXT,
        exam_id INTEGER,
        score INTEGER,
        correct INTEGER,
        wrong INTEGER,
        unanswered INTEGER
    )
    ''')

    conn.commit()
    conn.close()


def insert_sample_data():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("DELETE FROM questions")

    cursor.execute("""
    INSERT INTO questions (exam_id, question, option1, option2, option3, option4, correct_option)
    VALUES (1, '2 + 2 = ?', '3', '4', '5', '6', '4')
    """)

    conn.commit()
    conn.close()


def insert_user():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("DELETE FROM users")

    cursor.execute("INSERT INTO users (roll_no, password) VALUES ('123', '123')")
    cursor.execute("INSERT INTO users (roll_no, password) VALUES ('admin', 'admin')")

    conn.commit()
    conn.close()


# Initialize DB
init_db()
insert_sample_data()
insert_user()


# ---------------- ROUTES ----------------

@app.route('/')
def home():
    return render_template('login.html')


@app.route('/login', methods=['POST'])
def login():
    roll = request.form['roll']
    password = request.form['password']

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE roll_no=? AND password=?", (roll, password))
    user = cursor.fetchone()
    conn.close()

    if user:
        session['user'] = roll
        return redirect('/dashboard')
    return "Invalid Login"


@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/')
    return render_template('dashboard.html')


@app.route('/test/<int:exam_id>')
def test(exam_id):
    if 'user' not in session:
        return redirect('/')

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM questions WHERE exam_id=?", (exam_id,))
    data = cursor.fetchall()
    conn.close()

    questions = []
    for row in data:
        questions.append({
            "id": row[0],
            "question": row[2],
            "options": [row[3], row[4], row[5], row[6]]
        })

    return render_template('test.html', questions=questions)


@app.route('/submit', methods=['POST'])
def submit():
    if 'user' not in session:
        return redirect('/')

    user = session['user']

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT id, correct_option FROM questions")
    correct_data = cursor.fetchall()

    score = 0
    correct_count = 0
    wrong_count = 0
    unanswered = 0

    for q_id, correct in correct_data:
        user_answer = request.form.get(f"q{q_id}")

        if user_answer is None:
            unanswered += 1
        elif user_answer == correct:
            score += 4
            correct_count += 1
        else:
            score -= 1
            wrong_count += 1

    cursor.execute("""
    INSERT INTO results (user_roll, exam_id, score, correct, wrong, unanswered)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (user, 1, score, correct_count, wrong_count, unanswered))

    conn.commit()
    conn.close()

    return render_template('result.html',
                           score=score,
                           correct=correct_count,
                           wrong=wrong_count,
                           unanswered=unanswered,
                           total=len(correct_data))


@app.route('/history')
def history():
    if 'user' not in session:
        return redirect('/')

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM results WHERE user_roll=?", (session['user'],))
    data = cursor.fetchall()
    conn.close()

    return render_template('history.html', results=data)


# ---------------- ADMIN ----------------

@app.route('/admin')
def admin():
    if 'user' not in session:
        return redirect('/')

    if session['user'] != 'admin':
        return "Access Denied"

    return render_template('admin.html')


@app.route('/add_question', methods=['POST'])
def add_question():
    if session.get('user') != 'admin':
        return "Access Denied"

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO questions (exam_id, question, option1, option2, option3, option4, correct_option)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        request.form['exam_id'],
        request.form['question'],
        request.form['option1'],
        request.form['option2'],
        request.form['option3'],
        request.form['option4'],
        request.form['correct']
    ))

    conn.commit()
    conn.close()

    return redirect('/admin')


# ---------------- AI GENERATOR ----------------

@app.route('/generate', methods=['POST'])
def generate():
    if session.get('user') != 'admin':
        return "Access Denied"

    topic = request.form['topic']

    prompt = f"""
    Generate exactly 3 MCQ questions on {topic}.
    Strict format:

    Question: ...
    A) ...
    B) ...
    C) ...
    D) ...
    Answer: option text only
    """

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}]
        )

        content = response.choices[0].message.content

        return render_template('generated.html', content=content)

    except Exception as e:
        return f"Error: {e}"


@app.route('/save_ai', methods=['POST'])
def save_ai():
    if session.get('user') != 'admin':
        return "Access Denied"

    content = request.form['content']
    lines = content.split("\n")

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    question = ""
    options = []
    answer = ""

    for line in lines:
        line = line.strip()

        if line.startswith("Question"):
            question = line.split(":", 1)[1].strip()
            options = []

        elif line.startswith(("A)", "B)", "C)", "D)")):
            options.append(line[2:].strip())

        elif line.startswith("Answer"):
            answer = line.split(":", 1)[1].strip()
            answer = answer.replace("A)", "").replace("B)", "").replace("C)", "").replace("D)", "").strip()

            if len(options) == 4:
                cursor.execute("""
                INSERT INTO questions (exam_id, question, option1, option2, option3, option4, correct_option)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    1,
                    question,
                    options[0],
                    options[1],
                    options[2],
                    options[3],
                    answer
                ))

    conn.commit()
    conn.close()

    return "<h3>AI Questions Saved Successfully! ✅</h3><a href='/admin'>Back</a>"


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


if __name__ == '__main__':
    app.run(debug=True)
