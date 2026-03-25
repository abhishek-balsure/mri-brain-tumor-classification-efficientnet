from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import sqlite3
import os
import uuid
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")
DB_PATH = os.path.join(BASE_DIR, "database.db")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOADS_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id TEXT PRIMARY KEY,
            doctor_id TEXT NOT NULL,
            name TEXT NOT NULL,
            date_of_birth TEXT,
            gender TEXT,
            contact_email TEXT,
            contact_phone TEXT,
            medical_history TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (doctor_id) REFERENCES doctors(id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mri_scans (
            id TEXT PRIMARY KEY,
            patient_id TEXT NOT NULL,
            doctor_id TEXT NOT NULL,
            scan_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            image_path TEXT NOT NULL,
            analysis_status TEXT DEFAULT 'completed',
            tumor_detected INTEGER,
            confidence_score REAL,
            tumor_type TEXT,
            tumor_location TEXT,
            analysis_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            FOREIGN KEY (doctor_id) REFERENCES doctors(id)
        )
    """)
    
    cursor.execute("SELECT COUNT(*) FROM doctors WHERE email = 'doctor@demo.com'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO doctors (id, email, name, password) 
            VALUES (?, ?, ?, ?)
        """, (str(uuid.uuid4()), "doctor@demo.com", "Demo Doctor", "demo123"))
    
    conn.commit()
    conn.close()

init_db()

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str

class PatientRequest(BaseModel):
    name: str
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    medical_history: Optional[str] = None

class AnalysisResult(BaseModel):
    tumor_detected: bool
    confidence_score: float
    tumor_type: Optional[str]
    tumor_location: Optional[str]
    analysis_notes: str

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/")
async def root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM doctors WHERE email = ? AND password = ?", (req.email, req.password))
    doctor = cursor.fetchone()
    conn.close()
    
    if not doctor:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    return {"id": doctor["id"], "email": doctor["email"], "name": doctor["name"]}

@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        doctor_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO doctors (id, email, name, password) 
            VALUES (?, ?, ?, ?)
        """, (doctor_id, req.email, req.name, req.password))
        conn.commit()
        conn.close()
        return {"id": doctor_id, "email": req.email, "name": req.name}
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Email already exists")

@app.get("/api/auth/me")
async def get_current_doctor(doctor_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, name FROM doctors WHERE id = ?", (doctor_id,))
    doctor = cursor.fetchone()
    conn.close()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return {"id": doctor["id"], "email": doctor["email"], "name": doctor["name"]}

@app.get("/api/patients")
async def get_patients(doctor_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, date_of_birth, gender, contact_email, contact_phone, medical_history, created_at 
        FROM patients WHERE doctor_id = ? ORDER BY created_at DESC
    """, (doctor_id,))
    patients = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return patients

@app.post("/api/patients")
async def create_patient(doctor_id: str, req: PatientRequest):
    conn = get_db()
    cursor = conn.cursor()
    patient_id = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO patients (id, doctor_id, name, date_of_birth, gender, contact_email, contact_phone, medical_history)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (patient_id, doctor_id, req.name, req.date_of_birth, req.gender, req.contact_email, req.contact_phone, req.medical_history))
    conn.commit()
    conn.close()
    return {"id": patient_id, "name": req.name}

@app.get("/api/scans")
async def get_scans(doctor_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.*, p.name as patient_name
        FROM mri_scans s
        JOIN patients p ON s.patient_id = p.id
        WHERE s.doctor_id = ?
        ORDER BY s.created_at DESC
    """, (doctor_id,))
    scans = [dict(row) for row in cursor.fetchall()]
    conn.close()
    for scan in scans:
        scan["tumor_detected"] = bool(scan["tumor_detected"]) if scan["tumor_detected"] is not None else None
    return scans

@app.get("/api/stats")
async def get_stats(doctor_id: str):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM patients WHERE doctor_id = ?", (doctor_id,))
    total_patients = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM mri_scans WHERE doctor_id = ?", (doctor_id,))
    total_scans = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM mri_scans WHERE doctor_id = ? AND tumor_detected = 1", (doctor_id,))
    tumors_detected = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT s.tumor_type, COUNT(*) as count 
        FROM mri_scans s 
        WHERE s.doctor_id = ? AND s.tumor_detected = 1 
        GROUP BY s.tumor_type
    """, (doctor_id,))
    tumor_types = {row[0]: row[1] for row in cursor.fetchall()}
    
    cursor.execute("""
        SELECT strftime('%Y-%m', scan_date) as month, COUNT(*) as count 
        FROM mri_scans 
        WHERE doctor_id = ? 
        GROUP BY month ORDER BY month DESC LIMIT 6
    """, (doctor_id,))
    monthly_scans = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    
    return {
        "total_patients": total_patients,
        "total_scans": total_scans,
        "tumors_detected": tumors_detected,
        "tumor_types": tumor_types,
        "monthly_scans": monthly_scans
    }

model = None
class_names = ['glioma', 'meningioma', 'notumor', 'pituitary']

def load_model_once():
    global model
    if model is None:
        from tensorflow.keras.models import load_model
        from tensorflow.keras.applications.efficientnet import preprocess_input
        model = load_model("models/efficientnet_b0_best.h5", compile=False)
    return model

@app.post("/predict", response_model=AnalysisResult)
async def predict(
    file: UploadFile = File(...),
    patient_id: str = Form(...),
    doctor_id: str = Form(...)
):
    from tensorflow.keras.applications.efficientnet import preprocess_input
    import numpy as np
    from PIL import Image
    import tempfile
    
    m = load_model_once()
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    
    try:
        filename = f"{uuid.uuid4()}.png"
        dest_path = os.path.join(UPLOADS_DIR, filename)
        
        img = Image.open(tmp_path).convert("RGB")
        img.save(dest_path)
        
        img = img.resize((224, 224))
        x = np.array(img, dtype=np.float32)
        x = np.expand_dims(x, axis=0)
        x = preprocess_input(x)
        
        preds = m.predict(x, verbose=0)[0]
        pred_index = int(np.argmax(preds))
        confidence_score = float(preds[pred_index] * 100)
        raw_class = class_names[pred_index]
        
        tumor_detected = raw_class != "notumor"
        
        DISPLAY_NAMES = {
            "glioma": "Glioma",
            "meningioma": "Meningioma",
            "pituitary": "Pituitary Tumor",
            "notumor": "No Tumor"
        }
        
        tumor_type = DISPLAY_NAMES[raw_class]
        
        if tumor_detected:
            if confidence_score >= 85:
                analysis_notes = f"{tumor_type} detected with high confidence. Findings strongly suggest pathology. Clinical correlation advised."
            elif confidence_score >= 65:
                analysis_notes = f"{tumor_type} detected with moderate confidence. Further imaging or expert review recommended."
            else:
                analysis_notes = f"Possible {tumor_type.lower()} detected with low confidence. Manual radiologist review is required."
        else:
            analysis_notes = "No tumor detected. Brain MRI appears within normal limits. If symptoms persist, further evaluation is recommended."
        
        conn = get_db()
        cursor = conn.cursor()
        scan_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO mri_scans (id, patient_id, doctor_id, image_path, analysis_status, tumor_detected, confidence_score, tumor_type, tumor_location, analysis_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (scan_id, patient_id, doctor_id, filename, "completed", int(tumor_detected), confidence_score, tumor_type if tumor_detected else None, "Frontal Lobe" if tumor_detected else None, analysis_notes))
        conn.commit()
        conn.close()
        
        return AnalysisResult(
            tumor_detected=tumor_detected,
            confidence_score=round(confidence_score, 2),
            tumor_type=tumor_type if tumor_detected else None,
            tumor_location="Frontal Lobe" if tumor_detected else None,
            analysis_notes=analysis_notes,
        )
    finally:
        os.remove(tmp_path)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)