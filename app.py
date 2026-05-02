from flask import Flask, render_template, request, redirect, session
import sqlite3

app = Flask(__name__)
app.secret_key = 'secret123'


# ---------------- DATABASE SETUP ----------------

def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Questions table
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

    # Users table
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

    cursor.execute("""
    INSERT INTO questions (exam_id, question, option1, option2, option3, option4, correct_option)
    VALUES (1, 'Java is?', 'Language', 'Car', 'Animal', 'Game', 'Language')
    """)

    conn.commit()
    conn.close()


def insert_user():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("DELETE FROM users")

    cursor.execute("""
    INSERT INTO users (roll_no, password)
    VALUES ('123', '123')
    """)

    conn.commit()
    conn.close()


# Initialize DB and insert data
init_db()
insert_sample_data()
insert_user()


# ---------------- ROUTES ----------------

# Login Page
@app.route('/')
def home():
    return render_template('login.html')


# Login Logic
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
    else:
        return "Invalid Login"


# Dashboard (Protected)
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/')
    return render_template('dashboard.html')


# Test Page (Protected + DB Questions)
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


# Submit (Dynamic Scoring)
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

    total_questions = len(correct_data)

    # 🔥 SAVE RESULT IN DATABASE
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
                           total=total_questions)

@app.route('/history')
def history():
    if 'user' not in session:
        return redirect('/')

    user = session['user']

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM results WHERE user_roll=?", (user,))
    data = cursor.fetchall()

    conn.close()

    return render_template('history.html', results=data)
# Logout
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')


# Run App
if __name__ == '__main__':
    app.run()