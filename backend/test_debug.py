# test_debug.py
from backend.graph import build_graph

print("--- Testing Graph Initialization ---")
try:
    graph = build_graph()
    if graph:
        print("✅ SUCCESS: Graph initialized successfully!")
    else:
        print("❌ FAILED: build_graph() returned None.")
except Exception as e:
    print(f"❌ CRITICAL ERROR: {str(e)}")
    