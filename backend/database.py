import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# ==========================================
# 1. SUPABASE CLIENT (For Authentication & Storage)
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    print("⚠️ Supabase keys missing in .env file! Auth might fail.")
    supabase = None

# ==========================================
# 2. POSTGRESQL CONNECTION POOLING (SQLAlchemy)
# ==========================================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./enterprise_saas.db")

# Enterprise Connection Pooling settings for PostgreSQL (Supabase)
if "postgresql" in DATABASE_URL or "postgres" in DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,          # Keeps 10 connections open
        max_overflow=20,       # Can go up to 30 under heavy load
        pool_pre_ping=True     # Prevents connection drop errors
    )
else:
    # Fallback for local SQLite development
    engine = create_engine(
        DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()