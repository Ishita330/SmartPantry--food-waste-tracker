from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import sqlite3
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import os
import requests

app = Flask(__name__)

app.secret_key = os.getenv('SECRET_KEY', 'dev_key')
  # Replace with a secure random key

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # Redirect to login if unauthorized


class User(UserMixin):
    def __init__(self, id_, username, password_hash):
        self.id = id_
        self.username = username
        self.password_hash = password_hash

    @staticmethod
    def get(user_id):
        conn = sqlite3.connect('pantry.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return User(row[0], row[1], row[2])
        return None


# DB initialization
def init_db():
    conn = sqlite3.connect('pantry.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS pantry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            expiry_date TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('pantry.db')
    c = conn.cursor()
    c.execute("SELECT id, username, password FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        id_, username, password_hash = row
        return User(id_, username, password_hash)
    return None

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()

        if not username or not password:
            flash('Username and password are required.', 'error')
            return redirect('/register')

        # Hash the password
        hashed_password = generate_password_hash(password)

        # Save to DB
        conn = sqlite3.connect('pantry.db')
        c = conn.cursor()

        # Check if username exists
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        if c.fetchone():
            flash('Username already exists.', 'error')
            conn.close()
            return redirect('/register')

        # Insert user
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
        conn.commit()
        conn.close()
        flash('Registration successful! Please log in.', 'success')
        return redirect('/login')

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()

        conn = sqlite3.connect('pantry.db')
        c = conn.cursor()
        c.execute("SELECT id, username, password FROM users WHERE username = ?", (username,))
        row = c.fetchone()
        conn.close()

        if row and check_password_hash(row[2], password):
            user = User(row[0], row[1], row[2])
            login_user(user)
            flash('Logged in successfully!', 'success')
            return redirect('/inventory')
        else:
            flash('Invalid username or password', 'error')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect('/login')

#home 
@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        name = request.form['name']
        quantity = request.form['quantity']
        expiry_date = request.form['expiry_date']

        conn = sqlite3.connect('pantry.db')
        c = conn.cursor()
        c.execute('INSERT INTO pantry (name, quantity, expiry_date) VALUES (?, ?, ?)',
                  (name, quantity, expiry_date))
        conn.commit()
        conn.close()
        return redirect('/inventory')

    return render_template('index.html')

# View Pantry
@app.route('/inventory')
@login_required
def inventory():
    conn = sqlite3.connect('pantry.db')
    c = conn.cursor()
    c.execute('SELECT * FROM pantry')
    rows = c.fetchall()
    conn.close()

    items = []
    today = datetime.now().date()

    for row in rows:
        item_id, name, quantity, expiry_str = row
        try:
            expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        except ValueError:
            try:
                expiry_date = datetime.strptime(expiry_str, "%d-%m-%Y").date()
            except ValueError:
                expiry_date = None  # fallback if both formats fail
        if expiry_date is None:
            continue  # skip bad rows
        days_left = (expiry_date - today).days

        items.append({
            'id': item_id,
            'name': name,
            'quantity': quantity,
            'expiry_date': expiry_date.strftime("%Y-%m-%d"),
            'days_left': days_left
        })

    return render_template('inventory.html', items=items)

@app.route('/delete/<int:item_id>', methods=['POST'])
def delete_item(item_id):
    conn = sqlite3.connect('pantry.db')
    c = conn.cursor()
    c.execute('DELETE FROM pantry WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    return redirect('/inventory')

@app.route('/recommend')
@login_required
def recommend():
    import pandas as pd
    from datetime import datetime
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    # Carbon impact levels
    carbon_impact_map = {
    # Low impact 🌱
    'lentils': 'low', 'beans': 'low', 'peas': 'low', 'tofu': 'low', 'tempeh': 'low',
    'broccoli': 'low', 'spinach': 'low', 'lettuce': 'low', 'zucchini': 'low',
    'cucumber': 'low', 'tomato': 'low', 'carrot': 'low', 'cabbage': 'low',
    'cauliflower': 'low', 'brinjal': 'low', 'eggplant': 'low', 'chickpeas': 'low',
    'mushrooms': 'low', 'sweet potato': 'low', 'potato': 'low', 'onion': 'low',
    'garlic': 'low', 'ginger': 'low', 'millets': 'low', 'oats': 'low',
    'barley': 'low', 'quinoa': 'low', 'pumpkin': 'low',

    # Medium impact ⚠️
    'bread': 'medium', 'rice': 'medium', 'pasta': 'medium', 'cheese': 'medium',
    'milk': 'medium', 'yogurt': 'medium', 'butter': 'medium', 'paneer': 'medium',
    'egg': 'medium', 'wheat flour': 'medium', 'maida': 'medium', 'corn': 'medium',
    'sugar': 'medium', 'banana': 'medium', 'apple': 'medium', 'orange': 'medium',
    'grapes': 'medium', 'pear': 'medium', 'almonds': 'medium', 'cashews': 'medium',
    'raisins': 'medium', 'coconut': 'medium', 'coffee': 'medium', 'tea': 'medium',

    # High impact 🔥
    'beef': 'high', 'pork': 'high', 'lamb': 'high', 'mutton': 'high', 'chicken': 'high',
    'fish': 'high', 'prawns': 'high', 'salmon': 'high', 'tuna': 'high', 'crab': 'high',
    'duck': 'high', 'goat': 'high', 'turkey': 'high', 'processed meat': 'high',
    'ice cream': 'high', 'chocolate': 'high', 'ghee': 'high', 'mayonnaise': 'high',
    'pizza': 'high', 'burger': 'high', 'mayo': 'high'
}

    csv_url = 'https://drive.google.com/uc?export=download&id=1Ssh0OQX8JtiAmUKDtvUowzlb1Lr0ZGNG'
    csv_path = 'recipes_data.csv'

    # Download if file doesn't exist
    if not os.path.exists(csv_path):
        print("Downloading recipes_data.csv...")
        r = requests.get(csv_url)
        with open(csv_path, 'wb') as f:
            f.write(r.content)

    # Now load the CSV
    df = pd.read_csv(csv_path)

    df = df[['name', 'ingredients']]

    # Load pantry items from DB
    conn = sqlite3.connect('pantry.db')
    c = conn.cursor()
    c.execute('SELECT name, expiry_date FROM pantry')
    rows = c.fetchall()
    conn.close()

    today = datetime.now().date()
    pantry_items = []
    weights = {}

    for name, expiry_str in rows:
        try:
            expiry = datetime.strptime(expiry_str, "%Y-%m-%d").date()
            days_left = (expiry - today).days
            if days_left < 0:
                continue
            weight = max(0.1, 1 - (days_left / 10))  # Decay weight
            clean_name = name.strip().lower()
            pantry_items.append(clean_name)
            weights[clean_name] = weight
        except:
            continue

    if not pantry_items:
        return "No valid (non-expired) ingredients in your pantry to recommend recipes from."

    # TF-IDF similarity
    user_ingredients = ", ".join(pantry_items)
    recipe_ingredients = df['ingredients'].tolist()
    combined = recipe_ingredients + [user_ingredients]

    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(combined)
    cosine_sim = cosine_similarity(tfidf_matrix[-1], tfidf_matrix[:-1])
    similarity_scores = cosine_sim[0]

    top_indices = similarity_scores.argsort()[-10:][::-1]
    scored = []

    for idx in top_indices:
        row = df.iloc[idx]
        recipe_ings = [i.strip().lower() for i in row['ingredients'].split(',')]
        score = 0
        for ing in recipe_ings:
            for pantry_item in pantry_items:
                if pantry_item in ing:
                    score += weights.get(pantry_item, 0.1)
        scored.append((row['name'], recipe_ings, score))

    scored.sort(key=lambda x: x[2], reverse=True)

    # Prepare top 3 with pantry match and carbon footprint
    highlighted = []
    for name, ingredients_list, _ in scored[:3]:
        structured_ings = []
        impact_levels = {'low': 0, 'medium': 0, 'high': 0}

        for ing in ingredients_list:
            ing_clean = ing.strip().lower()
            is_available = any(p in ing_clean for p in pantry_items)
            impact = carbon_impact_map.get(ing_clean, 'unknown')
            if impact in impact_levels:
                impact_levels[impact] += 1

            structured_ings.append({
                'name': ing,
                'available': is_available  # ✅ or ❌ in template
            })

        # Determine majority carbon label
        if impact_levels['high'] > max(impact_levels['medium'], impact_levels['low']):
            label = "🔥 High Carbon Footprint"
            label_class = "high"
        elif impact_levels['medium'] > max(impact_levels['low'], impact_levels['high']):
            label = "⚠️ Medium Carbon Footprint"
            label_class = "medium"
        elif impact_levels['low'] > max(impact_levels['medium'], impact_levels['high']):
            label = "🌱 Low Carbon Footprint"
            label_class = "low"
        else:
            label = "❓ Unknown Footprint"
            label_class = "unknown"

        highlighted.append({
            'title': name,
            'ingredients': structured_ings,
            'carbon_label': label,
            'carbon_label_class': label_class
        })

    return render_template('recommend.html', recipes=highlighted)

@app.route('/export')
@login_required
def export_pantry():
    import csv
    from flask import Response

    conn = sqlite3.connect('pantry.db')
    c = conn.cursor()
    c.execute('SELECT name, quantity, expiry_date FROM pantry')
    rows = c.fetchall()
    conn.close()

    def generate():
        yield 'name,quantity,expiry_date\n'
        for row in rows:
            yield f'{row[0]},{row[1]},{row[2]}\n'

    return Response(generate(), mimetype='text/csv',
                    headers={"Content-Disposition": "attachment;filename=pantry_export.csv"})

@app.route('/import', methods=['GET', 'POST'])
@login_required
def import_pantry():
    import csv
    import io

    if request.method == 'POST':
        uploaded_file = request.files['file']
        if uploaded_file.filename.endswith('.csv'):
            data = uploaded_file.read().decode('utf-8')
            reader = csv.DictReader(io.StringIO(data))
            
            conn = sqlite3.connect('pantry.db')
            c = conn.cursor()
            for row in reader:
                try:
                    name = row['name'].strip()
                    quantity = int(row['quantity'])
                    expiry_date = row['expiry_date'].strip()
                    c.execute('INSERT INTO pantry (name, quantity, expiry_date) VALUES (?, ?, ?)',
                              (name, quantity, expiry_date))
                except:
                    continue  # skip bad rows
            conn.commit()
            conn.close()
            return redirect('/inventory')
        else:
            return "Please upload a valid .csv file"

    return render_template('import.html')

@app.route('/cleanup', methods=['POST'])
def cleanup():
    today = datetime.now().date()
    conn = sqlite3.connect('pantry.db')
    c = conn.cursor()
    c.execute("DELETE FROM pantry WHERE expiry_date < ?", (today.strftime("%Y-%m-%d"),))
    conn.commit()
    conn.close()
    return redirect('/inventory')

@app.route('/chart')
@login_required
def chart():
    conn = sqlite3.connect('pantry.db')
    c = conn.cursor()
    c.execute('SELECT expiry_date FROM pantry')
    raw_dates = c.fetchall()
    conn.close()

    today = datetime.now().date()
    buckets = {"Today": 0, "Next 3 Days": 0, "4–7 Days": 0, "8+ Days": 0}

    for (date_str,) in raw_dates:
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d").date()
            delta = (date - today).days
            if delta < 0:
                continue
            elif delta == 0:
                buckets["Today"] += 1
            elif delta <= 3:
                buckets["Next 3 Days"] += 1
            elif delta <= 7:
                buckets["4–7 Days"] += 1
            else:
                buckets["8+ Days"] += 1
        except ValueError:
            continue  # skip invalid date rows

    labels = list(buckets.keys())
    values = list(buckets.values())

    return render_template("chart.html", labels=labels, values=values)


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
