# findtext.py (or app.py)

import os
import io
import tempfile
import time
from flask import Flask, request, render_template, redirect, url_for
# Firestore imports
from google.cloud import firestore
# Email imports
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# Your existing core logic imports
import fitz 
from docx import Document 
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import pandas as pd

app = Flask(__name__)

# --- CONFIGURATION ---
MAX_ATTEMPTS = 3
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'malazjanbeih@gmail.com') # Set this environment variable
SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY') # Set this environment variable
# Initialize Firestore Client
db = firestore.Client()
USERS_COLLECTION = 'user_usage'


# --- UTILITY FUNCTIONS ---

def send_permission_email(user_id):
    """Sends an email to the admin requesting permission."""
    if not SENDGRID_API_KEY:
        print("Warning: SENDGRID_API_KEY not set. Cannot send email.")
        return False
        
    subject = f"Permission Request for FindText App from User: {user_id}"
    content = f"User {user_id} has exceeded the {MAX_ATTEMPTS} usage limit and requires manual approval for further searches."
    
    message = Mail(
        from_email=ADMIN_EMAIL,
        to_emails=ADMIN_EMAIL,
        subject=subject,
        html_content=content
    )
    
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"Email sent. Status Code: {response.status_code}")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def check_and_update_usage(user_id):
    """Checks usage and updates the count. Returns True if allowed, False otherwise."""
    user_ref = db.collection(USERS_COLLECTION).document(user_id)
    
    try:
        # Transactionally read and update the usage to prevent race conditions
        @firestore.transactional
        def update_in_transaction(transaction):
            snapshot = user_ref.get(transaction=transaction)
            
            if snapshot.exists:
                data = snapshot.to_dict()
                attempts = data.get('attempts', 0)
            else:
                attempts = 0

            # If user is approved, allow unlimited access (or set a high limit)
            if data.get('approved', False):
                 return True, 0 # Allowed, no further limit check needed
            
            if attempts < MAX_ATTEMPTS:
                # Increment and allow
                new_attempts = attempts + 1
                transaction.set(user_ref, {'attempts': new_attempts, 'last_use': firestore.SERVER_TIMESTAMP}, merge=True)
                return True, new_attempts
            else:
                # Limit exceeded
                return False, attempts

        allowed, attempts = update_in_transaction(db.transaction())
        
        if not allowed and attempts == MAX_ATTEMPTS:
            # First time hitting the limit, send permission email
            send_permission_email(user_id)
            
        return allowed
        
    except Exception as e:
        print(f"Database error: {e}")
        # Fail safe: If database is down, deny access to prevent unlimited use
        return False


# --- EXISTING CORE LOGIC (Simplified for brevity, assume content from previous response) ---
# Paste your original text extraction and search functions here.
# For example: extract_text_from_doc(), run_semantic_search()
# Ensure they are defined BEFORE the Flask routes.

def extract_text_from_doc(file_stream, file_name):
    # ... (Your robust text extraction code using fitz and python-docx) ...
    # Placeholder:
    return "Extracted text placeholder" 
    
def run_semantic_search(text, search_text, similarity_threshold):
    # ... (Your TF-IDF and cosine similarity code) ...
    # Placeholder:
    return [{"text": "Sample result", "page": "N/A", "similarity": "0.99"}]
    
# --- FLASK WEB ROUTES ---

@app.route('/', methods=['GET'])
def index():
    """Renders the user identification form."""
    return render_template('id_form.html')

@app.route('/upload', methods=['POST'])
def handle_identification():
    """Validates user ID and redirects to the search form if allowed."""
    user_id = request.form.get('user_id', '').strip()
    
    if not user_id:
        return render_template('id_form.html', error="Please enter a valid email or mobile number.")
    
    if check_and_update_usage(user_id):
        # Store user ID temporarily in the session (requires Flask secret key)
        # For simplicity in this serverless example, we'll pass the ID via a cookie/query param 
        # or rely on the user re-entering it for now, but Session is the standard way.
        # Given Cloud Run, we use a simple temporary method.
        return redirect(url_for('search_page', user_id=user_id))
    else:
        # Limit exceeded
        return render_template('results.html', error=f"Usage limit ({MAX_ATTEMPTS} tries) exceeded. A request for extended permission has been sent to the administrator ({ADMIN_EMAIL}).")


@app.route('/search_page', methods=['GET'])
def search_page():
    """Renders the actual search form."""
    user_id = request.args.get('user_id')
    # Optional: Re-verify usage here if security is paramount
    
    return render_template('search_form.html', user_id=user_id)


@app.route('/process_search', methods=['POST'])
def process_search():
    """Handles the file upload and search request."""
    
    user_id = request.form.get('user_id') # Get user ID hidden field
    search_text = request.form.get('search_text', '').strip()
    threshold_input = request.form.get('similarity_threshold')
    
    # ... (Rest of your existing processing logic for threshold, file handling, 
    # and calling extract_text_from_doc and run_semantic_search) ...
    
    # --- PROCESSING STARTS HERE ---
    
    try:
        similarity_threshold = float(threshold_input) if threshold_input else 0.7
    except ValueError:
        similarity_threshold = 0.7

    if 'document' not in request.files or not search_text:
        return render_template('results.html', error="Please provide a file and search text."), 400

    uploaded_file = request.files['document']
    
    extracted_text = extract_text_from_doc(uploaded_file.stream, uploaded_file.filename)
    
    search_results = run_semantic_search(extracted_text, search_text, similarity_threshold)

    if search_results:
        df = pd.DataFrame(search_results)
        result_table = df[['text', 'page', 'similarity']].to_html(classes='table table-striped', index=False)
    else:
        result_table = "No matching text found above the similarity threshold."

    return render_template('results.html', 
                           search_text=search_text, 
                           threshold=similarity_threshold,
                           result_table=result_table)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
