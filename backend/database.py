import os
import ssl
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# ==========================================
# SUPABASE CLIENT
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    print("⚠️ Supabase keys missing!")
    supabase = None

# ==========================================
# DATABASE ENGINE
# ==========================================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./enterprise_saas.db")

if "postgresql" in DATABASE_URL or "postgres" in DATABASE_URL:
    # ✅ pg8000 URL format
    if "postgresql+pg8000" not in DATABASE_URL:
        PG8000_URL = DATABASE_URL.replace(
            "postgresql://", "postgresql+pg8000://"
        ).replace("postgres://", "postgresql+pg8000://")
    else:
        PG8000_URL = DATABASE_URL

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:
        engine = create_engine(
            PG8000_URL,
            pool_size=3,
            max_overflow=5,
            pool_pre_ping=True,
            pool_recycle=300,
            connect_args={"ssl_context": ssl_context}
        )
        # Test connection
        with engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("SELECT 1"))
        print("✅ [DB] PostgreSQL connected via pg8000")
    except Exception as e:
        print(f"⚠️ [DB] PostgreSQL failed: {e}")
        print("⚠️ [DB] Falling back to SQLite...")
        engine = create_engine(
            "sqlite:///./enterprise_saas.db",
            connect_args={"check_same_thread": False}
        )
else:
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