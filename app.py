# app.py
from flask import Flask, render_template, request, jsonify
import sqlite3
import datetime
import re
from google.generativeai.client import configure
from google.generativeai.generative_models import GenerativeModel

app = Flask(__name__)

configure(api_key='')
gemini_model = GenerativeModel('gemini-2.5-flash')

def init_db():
    conn = sqlite3.connect('healthcare.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            date_of_birth DATE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            glucose REAL NOT NULL,
            haemoglobin REAL NOT NULL,
            cholesterol REAL NOT NULL,
            remarks TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_dob(dob):
    try:
        birth_date = datetime.datetime.strptime(dob, '%Y-%m-%d').date()
        return birth_date <= datetime.date.today()
    except:
        return False

def predict_disease(name, dob, email, glucose, haemoglobin, cholesterol):
    prompt = f"""Patient: {name}, Glucose: {glucose} mg/dL, Haemoglobin: {haemoglobin} g/dL, Cholesterol: {cholesterol} mg/dL

Provide a brief health risk assessment in exactly this format:
🔍 Risk Assessment: [main risk in one line]
📊 Key Finding: [key finding based on abnormal values]
💡 Recommendation: [one line advice]
"""
    
    try:
        chat = gemini_model.start_chat(history=[])
        gemini_response = chat.send_message(prompt)
        response_text = gemini_response.text
        if len(response_text) > 350:
            response_text = response_text[:350] + "..."
        return response_text
    except:
        return "🔍 Risk Assessment: Unable to analyze\n📊 Key Finding: Please consult doctor\n💡 Recommendation: Schedule health checkup"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/patients', methods=['GET'])
def get_patients():
    conn = sqlite3.connect('healthcare.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, full_name, date_of_birth, email, glucose, haemoglobin, cholesterol, remarks FROM patients ORDER BY id DESC')
    patients = cursor.fetchall()
    conn.close()
    
    patients_list = []
    for patient in patients:
        patients_list.append({
            'id': patient[0],
            'full_name': patient[1],
            'date_of_birth': patient[2],
            'email': patient[3],
            'glucose': patient[4],
            'haemoglobin': patient[5],
            'cholesterol': patient[6],
            'remarks': patient[7]
        })
    return jsonify(patients_list)

@app.route('/api/patients', methods=['POST'])
def add_patient():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid JSON payload'}), 400
    
    if not data.get('full_name') or not data.get('date_of_birth') or not data.get('email'):
        return jsonify({'error': 'Missing required fields'}), 400
    
    if not validate_email(data['email']):
        return jsonify({'error': 'Invalid email format'}), 400
    
    if not validate_dob(data['date_of_birth']):
        return jsonify({'error': 'Date of birth cannot be in the future'}), 400
    
    try:
        glucose = float(data['glucose'])
        haemoglobin = float(data['haemoglobin'])
        cholesterol = float(data['cholesterol'])
    except:
        return jsonify({'error': 'Blood test values must be numeric'}), 400
    
    if glucose <= 0 or haemoglobin <= 0 or cholesterol <= 0:
        return jsonify({'error': 'Blood test values must be positive numbers'}), 400
    
    remark = predict_disease(
        data['full_name'], 
        data['date_of_birth'], 
        data['email'], 
        glucose, 
        haemoglobin, 
        cholesterol
    )
    
    conn = sqlite3.connect('healthcare.db')
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO patients (full_name, date_of_birth, email, glucose, haemoglobin, cholesterol, remarks)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (data['full_name'], data['date_of_birth'], data['email'], glucose, haemoglobin, cholesterol, remark))
        conn.commit()
        patient_id = cursor.lastrowid
        conn.close()
        
        return jsonify({
            'id': patient_id,
            'full_name': data['full_name'],
            'date_of_birth': data['date_of_birth'],
            'email': data['email'],
            'glucose': glucose,
            'haemoglobin': haemoglobin,
            'cholesterol': cholesterol,
            'remarks': remark
        }), 201
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Email already exists'}), 400

@app.route('/api/patients/<int:patient_id>', methods=['PUT'])
def update_patient(patient_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid JSON payload'}), 400
    
    if data.get('email') and not validate_email(data['email']):
        return jsonify({'error': 'Invalid email format'}), 400
    
    if data.get('date_of_birth') and not validate_dob(data['date_of_birth']):
        return jsonify({'error': 'Date of birth cannot be in the future'}), 400
    
    if data.get('glucose'):
        try:
            data['glucose'] = float(data['glucose'])
            if data['glucose'] <= 0:
                return jsonify({'error': 'Glucose must be positive'}), 400
        except:
            return jsonify({'error': 'Glucose must be numeric'}), 400
    
    if data.get('haemoglobin'):
        try:
            data['haemoglobin'] = float(data['haemoglobin'])
            if data['haemoglobin'] <= 0:
                return jsonify({'error': 'Haemoglobin must be positive'}), 400
        except:
            return jsonify({'error': 'Haemoglobin must be numeric'}), 400
    
    if data.get('cholesterol'):
        try:
            data['cholesterol'] = float(data['cholesterol'])
            if data['cholesterol'] <= 0:
                return jsonify({'error': 'Cholesterol must be positive'}), 400
        except:
            return jsonify({'error': 'Cholesterol must be numeric'}), 400
    
    conn = sqlite3.connect('healthcare.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT full_name, date_of_birth, glucose, haemoglobin, cholesterol, email FROM patients WHERE id = ?', (patient_id,))
    current = cursor.fetchone()
    if not current:
        conn.close()
        return jsonify({'error': 'Patient not found'}), 404
    
    full_name = data.get('full_name', current[0])
    dob = data.get('date_of_birth', current[1])
    glucose = data.get('glucose', current[2])
    haemoglobin = data.get('haemoglobin', current[3])
    cholesterol = data.get('cholesterol', current[4])
    email = data.get('email', current[5])
    
    if 'email' in data or 'glucose' in data or 'haemoglobin' in data or 'cholesterol' in data:
        remark = predict_disease(full_name, dob, email, glucose, haemoglobin, cholesterol)
    else:
        cursor.execute('SELECT remarks FROM patients WHERE id = ?', (patient_id,))
        remarks_row = cursor.fetchone()
        remark = remarks_row[0] if remarks_row and remarks_row[0] is not None else ''
    
    update_fields = []
    update_values = []
    
    if 'full_name' in data:
        update_fields.append('full_name = ?')
        update_values.append(data['full_name'])
    if 'date_of_birth' in data:
        update_fields.append('date_of_birth = ?')
        update_values.append(data['date_of_birth'])
    if 'email' in data:
        update_fields.append('email = ?')
        update_values.append(data['email'])
    if 'glucose' in data:
        update_fields.append('glucose = ?')
        update_values.append(data['glucose'])
    if 'haemoglobin' in data:
        update_fields.append('haemoglobin = ?')
        update_values.append(data['haemoglobin'])
    if 'cholesterol' in data:
        update_fields.append('cholesterol = ?')
        update_values.append(data['cholesterol'])
    
    update_fields.append('remarks = ?')
    update_values.append(remark)
    update_values.append(patient_id)
    
    query = f'UPDATE patients SET {", ".join(update_fields)} WHERE id = ?'
    cursor.execute(query, update_values)
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Patient updated successfully'}), 200

@app.route('/api/patients/<int:patient_id>', methods=['DELETE'])
def delete_patient(patient_id):
    conn = sqlite3.connect('healthcare.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM patients WHERE id = ?', (patient_id,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    
    if affected:
        return jsonify({'message': 'Patient deleted successfully'}), 200
    else:
        return jsonify({'error': 'Patient not found'}), 404

if __name__ == '__main__':
    app.run(debug=True)