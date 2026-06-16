import os
import ssl
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
# 2. POSTGRESQL CONNECTION (pg8000 - Pure Python, No DLL)
# ==========================================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./enterprise_saas.db")

if "postgresql" in DATABASE_URL or "postgres" in DATABASE_URL:
    # ✅ pg8000 = Pure Python PostgreSQL driver
    # DLL nahi chahiye, Windows Application Control policy block nahi karegi
    
    # postgresql:// → postgresql+pg8000:// mein convert karo
    if "postgresql+pg8000" not in DATABASE_URL:
        PG8000_URL = DATABASE_URL.replace(
            "postgresql://", "postgresql+pg8000://"
        ).replace(
            "postgres://", "postgresql+pg8000://"
        )
    else:
        PG8000_URL = DATABASE_URL

    # SSL context banao Supabase ke liye
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE  # Development ke liye

    engine = create_engine(
        PG8000_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={
            "ssl_context": ssl_context
        }
    )
    print("✅ [DB] PostgreSQL engine initialized via pg8000 (Pure Python)")

else:
    # ✅ SQLite fallback for local development
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
    print("✅ [DB] SQLite engine initialized")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()