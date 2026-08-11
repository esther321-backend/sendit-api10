import os
import time
import json
import psutil
import platform
import logging
from datetime import datetime
from typing import Optional, List
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status, Request, Form
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select, SQLModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import aiofiles

from database.session import get_session, engine
from models.user import User, UserCreate, UserResponse
from models.document import Document, DocumentCreate
from auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, get_current_admin, get_current_manager
)
from services.weather import get_weather

# 1. Initialize FastAPI App
app = FastAPI(title="SendIt API", version="1.0.0")

# Auto-create database tables on startup
@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)

# 2. Configuration & Rate Limiting
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_FILE_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 5 * 1024 * 1024))  # 5 MB
ALLOWED_EXTENSIONS = [".pdf", ".jpg", ".jpeg", ".png", ".docx"]

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 3. Logging & Middleware Setup
LOG_FILE = os.getenv("LOG_FILE", "app.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=10485760, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

start_time = time.time()

@app.middleware("http")
async def log_requests(request: Request, call_next):
    req_start = time.time()
    response = await call_next(request)
    process_time = time.time() - req_start
    logger.info(
        f"{request.method} {request.url.path} - Status: {response.status_code} - Time: {process_time:.3f}s"
    )
    return response

# 4. Monitoring Endpoints (Lab 10)
@app.get("/health", tags=["Monitoring"])
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "uptime": time.time() - start_time,
        "system": {
            "platform": platform.platform(),
            "python": platform.python_version()
        }
    }

@app.get("/metrics", tags=["Monitoring"])
def get_metrics(current_user: User = Depends(get_current_admin)):
    return {
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_usage": psutil.disk_usage('/').percent
    }

# 5. Authentication Endpoints (Lab 9)
@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED, tags=["Authentication"])
def register_user(user_in: UserCreate, session: Session = Depends(get_session)):
    existing_user = session.exec(select(User).where(User.username == user_in.username)).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Username already exists")
    
    existing_email = session.exec(select(User).where(User.email == user_in.email)).first()
    if existing_email:
        raise HTTPException(status_code=409, detail="Email already registered")

    db_user = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
        full_name=user_in.full_name,
        role=user_in.role
    )
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user

@app.post("/login", tags=["Authentication"])
def login(form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == form_data.username)).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

# 6. Document Endpoints (Lab 9)
@app.post("/documents/upload", tags=["Documents"])
@limiter.limit("10/hour")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    city: str = Form(...),
    description: Optional[str] = Form(None),
    country: str = Form("Kenya"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    file_extension = os.path.splitext(file.filename)[1].lower()
    if file_extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

    contents = await file.read()
    file_size = len(contents)
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(400, f"File too large. Max size: {MAX_FILE_SIZE // (1024*1024)} MB")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{current_user.id}_{file.filename.replace(' ', '_')}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)

    async with aiofiles.open(file_path, 'wb') as out_file:
        await out_file.write(contents)

    document = Document(
        filename=safe_filename,
        original_filename=file.filename,
        file_size=file_size,
        file_type=file.content_type or "application/octet-stream",
        city=city,
        country=country,
        description=description,
        uploader_id=current_user.id,
        file_path=file_path,
        status="processing"
    )
    session.add(document)
    session.commit()
    session.refresh(document)

    try:
        weather_data = await get_weather(city, country)
        if weather_data:
            document.weather_data = json.dumps(weather_data)
            document.weather_fetched_at = datetime.utcnow()
            document.status = "enriched"
            session.commit()
    except Exception as e:
        logger.error(f"Weather API error: {e}")
        document.status = "uploaded"
        session.commit()

    return {
        "message": "Document uploaded successfully",
        "document_id": document.id,
        "filename": document.original_filename,
        "status": document.status
    }

@app.get("/documents", tags=["Documents"])
@limiter.limit("30/minute")
def list_documents(
    request: Request,
    status: Optional[str] = None,
    city: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    query = select(Document)
    if current_user.role not in ["admin", "manager"]:
        query = query.where(Document.uploader_id == current_user.id)
    if status:
        query = query.where(Document.status == status)
    if city:
        query = query.where(Document.city == city)
    return session.exec(query).all()

@app.get("/documents/{document_id}", tags=["Documents"])
@limiter.limit("30/minute")
def get_document(
    request: Request,
    document_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    if current_user.role not in ["admin", "manager"] and document.uploader_id != current_user.id:
        raise HTTPException(403, "Access denied")
    return document

@app.delete("/documents/{document_id}", tags=["Documents"])
def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_manager),
    session: Session = Depends(get_session)
):
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    if os.path.exists(document.file_path):
        os.remove(document.file_path)
    session.delete(document)
    session.commit()
    return {"message": "Document deleted successfully"}

@app.post("/documents/{document_id}/enrich", tags=["Documents"])
@limiter.limit("5/minute")
async def enrich_document(
    request: Request,
    document_id: int,
    current_user: User = Depends(get_current_manager),
    session: Session = Depends(get_session)
):
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    
    if document.status == "enriched":
        return {"message": "Document already enriched"}

    weather_data = await get_weather(document.city, document.country)
    if weather_data:
        document.weather_data = json.dumps(weather_data)
        document.weather_fetched_at = datetime.utcnow()
        document.status = "enriched"
        session.commit()
        return {"message": "Document enriched successfully", "weather": weather_data}
    else:
        document.status = "failed"
        session.commit()
        raise HTTPException(500, "Failed to enrich document with weather data")

@app.get("/documents/{document_id}/weather", tags=["Documents"])
@limiter.limit("10/minute")
def get_document_weather(
    request: Request,
    document_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    if current_user.role not in ["admin", "manager"] and document.uploader_id != current_user.id:
        raise HTTPException(403, "Access denied")
    if not document.weather_data:
        raise HTTPException(404, "No weather data available for this document")
        
    return {
        "document_id": document.id,
        "city": document.city,
        "country": document.country,
        "weather": json.loads(document.weather_data)
    }
