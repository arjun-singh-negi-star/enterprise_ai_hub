import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

# Example Postgres URL format: postgresql://user:password@localhost:5432/saas_db
# Agar abhi local DB nahi hai, toh development ke liye hum SQLite use kar sakte hain
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./enterprise_saas.db")

engine = create_engine(
    DATABASE_URL, 
    # check_same_thread=False is only needed for SQLite
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()