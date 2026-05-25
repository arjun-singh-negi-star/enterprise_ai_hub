import os
import time
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_core.documents import Document

def run_ingestion():
    # Load architecture configurations
    load_dotenv()
    
    api_key = os.getenv("PINECONE_API_KEY")
    index_name = os.getenv("PINECONE_INDEX_NAME", "enterprise-knowledge-hub")
    google_key = os.getenv("GOOGLE_API_KEY")
    
    if not api_key or not google_key:
        print("[CRITICAL] Missing required keys in .env. Verify PINECONE_API_KEY and GOOGLE_API_KEY.")
        return

    print("--> [INGESTION] Verifying connection to Pinecone Vector Database...")
    pc = Pinecone(api_key=api_key)
    
    # Programmatic index tracking and provisioning
    existing_indexes = [idx["name"] for idx in pc.list_indexes()]
    
    if index_name not in existing_indexes:
        print(f"--> [INGESTION] Creating new index: '{index_name}'...")
        pc.create_index(
            name=index_name,
            dimension=768,  # Must stay 768 to align with preview output matching constraints
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )
        print("--> [INGESTION] Waiting for cloud resource index to fully resolve...")
        time.sleep(10)
    else:
        print(f"--> [INGESTION] Active cloud index '{index_name}' confirmed.")

    # Load corporate source files
    print("--> [INGESTION] Parsing documents from local storage layer...")
    raw_documents = []
    kb_dir = "knowledge_base"
    
    if not os.path.exists(kb_dir):
        print(f"[ERROR] Directory '{kb_dir}' not detected at project execution root.")
        return

    for filename in os.listdir(kb_dir):
        if filename.endswith(".txt"):
            file_path = os.path.join(kb_dir, filename)
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                raw_documents.append(Document(page_content=content, metadata={"source": filename}))

    if not raw_documents:
        print("[WARNING] Zero valid source documents identified. Place .txt reference documents in /knowledge_base.")
        return

    print("--> [INGESTION] Initializing Google gemini-embedding-2-preview vector model...")
    # FIX: Targets updated production-grade stable model identifier with forced 768 matrix compression
    embeddings = GoogleGenerativeAIEmbeddings(
        model="gemini-embedding-2-preview",
        output_dimensionality=768
    )

    # Sync and upsert content to Pinecone via LangChain bindings
    print(f"--> [INGESTION] Loading {len(raw_documents)} source contexts into Pinecone index vector space...")
    PineconeVectorStore.from_documents(
        documents=raw_documents,
        embedding=embeddings,
        index_name=index_name
    )
    
    print("🎯 [SUCCESS] Vector Space ingestion completed. Your live RAG Agent tool is fully optimized.")

if __name__ == "__main__":
    run_ingestion()