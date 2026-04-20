from flask import Flask
from flask import render_template
from flask import request
from flask import jsonify
from flask import session, redirect, url_for, flash
import os
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import secrets
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

from core.langgraph_workflow import create_workflow
from core.state import initialize_conversation_state
from core.state import reset_query_state
from tools.pdf_loader import process_documents
from tools.vector_store import get_or_create_vectorstore

load_dotenv()

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# Global workflow and conversation states
workflow_app = None
conversation_states = {}

# SQLite Database Setup
DB_PATH = './chat_db/MedChatbot_chats.db'

def init_db():
    """Initialize SQLite database with required tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create sessions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            source TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions (session_id)
        )
    ''')
    
    conn.commit()
    conn.close()

def save_message(session_id, role, content, source=None):
    """Save a message to the database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Ensure session exists
    cursor.execute('''
        INSERT OR IGNORE INTO sessions (session_id) VALUES (?)
    ''', (session_id,))
    
    # Update last active time
    cursor.execute('''
        UPDATE sessions SET last_active = CURRENT_TIMESTAMP WHERE session_id = ?
    ''', (session_id,))
    
    # Insert message
    cursor.execute('''
        INSERT INTO messages (session_id, role, content, source)
        VALUES (?, ?, ?, ?)
    ''', (session_id, role, content, source))
    
    conn.commit()
    conn.close()

def get_chat_history(session_id):
    """Retrieve chat history for a session"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT role, content, source, timestamp
        FROM messages
        WHERE session_id = ?
        ORDER BY timestamp ASC
    ''', (session_id,))
    
    messages = []
    for row in cursor.fetchall():
        messages.append({
            'role': row[0],
            'content': row[1],
            'source': row[2],
            'timestamp': row[3]
        })
    
    conn.close()
    return messages

def get_all_sessions():
    """Get all chat sessions"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT s.session_id, s.created_at, s.last_active, 
               (SELECT content FROM messages WHERE session_id = s.session_id 
                AND role = 'user' ORDER BY timestamp ASC LIMIT 1) as first_message
        FROM sessions s
        ORDER BY s.last_active DESC
    ''')
    
    sessions = []
    for row in cursor.fetchall():
        sessions.append({
            'session_id': row[0],
            'created_at': row[1],
            'last_active': row[2],
            'preview': row[3][:50] + '...' if row[3] and len(row[3]) > 50 else row[3]
        })
    
    conn.close()
    return sessions

def delete_session(session_id):
    """Delete a chat session and its messages"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
    cursor.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
    
    conn.commit()
    conn.close()

def initialize_system():
    global workflow_app
    
    data_dir = './data'
    persist_dir = './medical_db/'
    
    print("Initializing MedChatbot System...")
    
    # Initialize database
    init_db()
    print("Database initialized...")
    
    # Try to load existing database
    existing_db = get_or_create_vectorstore(persist_dir=persist_dir)
    
    if not existing_db and os.path.exists(data_dir):
        print("Creating vector database from documents directory...")
        doc_splits = process_documents(data_dir)
        get_or_create_vectorstore(documents=doc_splits, persist_dir=persist_dir)
    elif not existing_db:
        print("No vector database and no documents found - RAG features will be limited")
    
    workflow_app = create_workflow()
    print("MedChatbot Web Interface Ready!")

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        action = request.form.get('action')
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if action == 'signup':
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            if cursor.fetchone():
                flash('Username already exists. Please try logging in or use another username.', 'error')
            else:
                password_hash = generate_password_hash(password)
                cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
                conn.commit()
                flash('Account created successfully! Please log in.', 'success')
        elif action == 'login':
            cursor.execute("SELECT id, username, password_hash FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            if user and check_password_hash(user[2], password):
                session['user_id'] = user[0]
                session['username'] = user[1]
                conn.close()
                return redirect(url_for('index'))
            else:
                flash('Invalid username or password.', 'error')
                
        conn.close()
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('session_id', None)
    return redirect(url_for('login'))

@app.route('/api/chat', methods=['POST'])
def chat():
    global workflow_app, conversation_states
    
    data = request.json
    message = data.get('message', '')
    session_id = session.get('session_id')
    
    if not message:
        return jsonify({'error': 'No message provided'}), 400
    
    if not workflow_app:
        return jsonify({'error': 'System not initialized'}), 500
    
    # Save user message to database
    save_message(session_id, 'user', message)
    
    # Initialize or get conversation state
    if session_id not in conversation_states:
        conversation_states[session_id] = initialize_conversation_state()
    
    conversation_state = conversation_states[session_id]
    conversation_state = reset_query_state(conversation_state)
    conversation_state["question"] = message
    
    try:
        # Process query through workflow
        result = workflow_app.invoke(conversation_state)
        conversation_states[session_id].update(result)
        
        # Get current timestamp
        timestamp = datetime.now().strftime("%I:%M %p")
        
        # Extract response and source
        response = result.get('generation', 'Unable to generate response.')
        source = result.get('source', 'Unknown')
        
        # Save assistant response to database
        save_message(session_id, 'assistant', response, source)
        
        return jsonify({
            'response': response,
            'source': source,
            'timestamp': timestamp,
            'success': bool(result.get('generation'))
        })
    except Exception as e:
        print(f"Error processing chat: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'response': f"I encountered an error while processing your request: {str(e)}. Please ensure your API keys (especially GROQ_API_KEY) are configured correctly in the .env file.",
            'source': 'System Error',
            'timestamp': datetime.now().strftime("%I:%M %p"),
            'success': False
        }), 200 # Return 200 so the frontend can display the message instead of a connection error

@app.route('/api/predict_disease', methods=['POST'])
def predict_disease():
    data = request.json
    symptoms = data.get('symptoms', '')
    
    if not symptoms:
        return jsonify({'error': 'No symptoms provided'}), 400
        
    try:
        from tools.llm_client import get_llm
        llm = get_llm()
        if not llm:
            return jsonify({'error': 'LLM is not configured'}), 500
            
        prompt = f"""You are an advanced medical diagnostic and treatment AI system.
A patient has reported the following symptoms:
{symptoms}

Please analyze these symptoms and provide a comprehensive structured medical report.
Your report MUST include the following sections exactly:

### 1. Primary AI Diagnosis
List the top 3 most likely medical conditions. For each, provide a brief explanation and a confidence level (High/Medium/Low).

### 2. Recommended Treatment Plan
Provide detailed treatment advice for the given conditions, including:
- **Allopathic Prescription**: Recommended over-the-counter (OTC) medications or standard clinical treatments.
- **Ayurvedic Prescription**: Highly effective traditional Ayurvedic remedies, herbs, or formulations specifically best suited for these symptoms.
- **Home Remedies & Lifestyle**: Immediate lifestyle changes or home care.

### 3. Suggested Clinical Tests
List specific lab tests or clinical examinations the patient should undergo to confirm the diagnosis.

### 4. Immediate Action / Next Steps
Clear instructions on what the patient should do next.

### 5. Critical Medical Disclaimer
End with a strong, prominent disclaimer stating that you are an AI, this information is for educational purposes only, and they strictly must consult a healthcare professional before taking any medications or herbal supplements.

Format your output cleanly in markdown."""

        response = llm.invoke(prompt)
        prediction_text = response.content.strip() if hasattr(response, 'content') else str(response).strip()
        
        return jsonify({
            'success': True,
            'prediction': prediction_text
        })
    except Exception as e:
        print(f"Error predicting disease: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get chat history for current session"""
    session_id = session.get('session_id')
    if not session_id:
        return jsonify({'messages': []})
    
    messages = get_chat_history(session_id)
    return jsonify({'messages': messages, 'success': True})

@app.route('/api/sessions', methods=['GET'])
def get_sessions():
    """Get all chat sessions"""
    sessions = get_all_sessions()
    return jsonify({'sessions': sessions, 'success': True})

@app.route('/api/session/<session_id>', methods=['GET'])
def load_session(session_id):
    """Load a specific chat session"""
    session['session_id'] = session_id
    messages = get_chat_history(session_id)
    return jsonify({
        'messages': messages,
        'session_id': session_id,
        'success': True
    })

@app.route('/api/session/<session_id>', methods=['DELETE'])
def delete_chat_session(session_id):
    """Delete a chat session"""
    delete_session(session_id)
    
    # If current session was deleted, create new one
    if session.get('session_id') == session_id:
        session['session_id'] = str(uuid.uuid4())
    
    return jsonify({'message': 'Session deleted', 'success': True})

@app.route('/api/clear', methods=['POST'])
def clear():
    """Clear current conversation (in memory only, doesn't delete from DB)"""
    session_id = session.get('session_id')
    if session_id in conversation_states:
        conversation_states[session_id] = initialize_conversation_state()
    return jsonify({'message': 'Conversation cleared', 'success': True})

@app.route('/api/new-chat', methods=['POST'])
def new_chat():
    """Create a new chat session"""
    new_session_id = str(uuid.uuid4())
    session['session_id'] = new_session_id
    return jsonify({
        'message': 'New chat created',
        'session_id': new_session_id,
        'success': True
    })

@app.route('/api/health')
def health():
    return jsonify({'status': 'healthy', 'service': 'MedChatbot'})

if __name__ == '__main__':
    initialize_system()
    app.run(debug=True, port=5000)
