from flask import Flask, render_template, request, redirect, session
import os
import psycopg2
from groq import Groq

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

# ---------------- GROQ ----------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


# ---------------- DATABASE ----------------

def get_db_connection():
    return psycopg2.connect(os.environ.get("DATABASE_URL"))


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        roll_no TEXT UNIQUE,
        password TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS questions (
        id SERIAL PRIMARY KEY,
        exam_id INTEGER,
        question TEXT,
        option1 TEXT,
        option2 TEXT,
        option3 TEXT,
        option4 TEXT,
        correct_option TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS results (
        id SERIAL PRIMARY KEY,
        user_roll TEXT,
        exam_id INTEGER,
        score INTEGER,
        correct INTEGER,
        wrong INTEGER,
        unanswered INTEGER
    );
    """)

    conn.commit()
    conn.close()


def insert_user_once():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]

    if count == 0:
        cursor.execute("INSERT INTO users (roll_no, password) VALUES (%s, %s)", ('123', '123'))
        cursor.execute("INSERT INTO users (roll_no, password) VALUES (%s, %s)", ('admin', 'admin'))
        conn.commit()

    conn.close()


# Initialize DB
init_db()
insert_user_once()


# ---------------- ROUTES ----------------

@app.route('/')
def home():
    return render_template('login.html')


@app.route('/login', methods=['POST'])
def login():
    roll = request.form['roll']
    password = request.form['password']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE roll_no=%s AND password=%s", (roll, password))
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

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM questions WHERE exam_id=%s", (exam_id,))
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

    conn = get_db_connection()
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
    VALUES (%s, %s, %s, %s, %s, %s)
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

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM results WHERE user_roll=%s", (session['user'],))
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

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM questions")
    questions = cursor.fetchall()

    conn.close()

    return render_template('admin.html', questions=questions)

@app.route('/delete_question', methods=['POST'])
def delete_question():
    if session.get('user') != 'admin':
        return "Access Denied"

    q_id = request.form['id']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM questions WHERE id=%s", (q_id,))

    conn.commit()
    conn.close()

    return redirect('/admin')
    
@app.route('/add_question', methods=['POST'])
def add_question():
    if session.get('user') != 'admin':
        return "Access Denied"

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO questions (exam_id, question, option1, option2, option3, option4, correct_option)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
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


# ---------------- AI ----------------

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

    content = request.form.get('content')

    if not content:
        return "❌ No content received"

    print("CONTENT RECEIVED:\n", content)

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        lines = content.split("\n")

        question = ""
        options = []
        answer = ""

        for line in lines:
            line = line.strip()

            if line.lower().startswith("question"):
                question = line.split(":", 1)[1].strip()
                options = []

            elif line.startswith(("A)", "B)", "C)", "D)")):
                options.append(line[2:].strip())

            elif line.lower().startswith("answer"):
                answer = line.split(":", 1)[1].strip()
                answer = answer.replace("A)", "").replace("B)", "").replace("C)", "").replace("D)", "").strip()

                if len(options) == 4:
                    cursor.execute("""
                        INSERT INTO questions
                        (exam_id, question, option1, option2, option3, option4, correct_option)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
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

        return "<h3>✅ Questions saved successfully!</h3><a href='/admin'>Back</a>"

    except Exception as e:
        conn.rollback()
        conn.close()
        print("ERROR:", e)
        return f"❌ Error occurred: {e}"


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


if __name__ == '__main__':
    app.run()
