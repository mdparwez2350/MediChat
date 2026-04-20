
import sys
import os

print(f"Python executable: {sys.executable}")
print(f"CWD: {os.getcwd()}")

try:
    import pydantic
    print(f"Pydantic version: {pydantic.VERSION}")
    print(f"Pydantic file: {pydantic.__file__}")
except Exception as e:
    print(f"Error importing pydantic: {e}")

try:
    import chromadb.config
    print(f"Chromadb config file: {chromadb.config.__file__}")
    
    # Check if Settings class has the field
    if hasattr(chromadb.config.Settings, 'chroma_server_nofile'):
        print("Settings class HAS chroma_server_nofile")
    else:
        print("Settings class does NOT have chroma_server_nofile")
        
    print("Content of config file around line 103:")
    with open(chromadb.config.__file__, 'r') as f:
        lines = f.readlines()
        for i in range(100, 120):
            if i < len(lines):
                print(f"{i+1}: {lines[i].rstrip()}")
except Exception as e:
    print(f"Error checking chromadb config: {e}")

print("-" * 20)
try:
    import chromadb
    print(f"ChromaDB version: {chromadb.__version__}")
    client = chromadb.PersistentClient(path="./test_db")
    print("PersistentClient created successfully")
except Exception as e:
    print(f"Error creating client: {e}")
