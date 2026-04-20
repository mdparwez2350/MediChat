import os
from dotenv import load_dotenv
from core.langgraph_workflow import create_workflow
from core.state import initialize_conversation_state, reset_query_state
from tools.pdf_loader import process_documents
from tools.vector_store import get_or_create_vectorstore

load_dotenv()

def initialize_system():
    """Initialize the system and create vector database if needed"""
    data_dir = './data'
    persist_dir = './medical_db/'
    
    print("\n" + "="*60)
    print("Initializing Medical AI System...")
    print("="*60)
    
    # Try to load existing database first
    existing_db = get_or_create_vectorstore(persist_dir=persist_dir)
    
    if not existing_db:
        # Check if directory exists to create new database
        if os.path.exists(data_dir):
            print("Processing documents and creating vector database...")
            doc_splits = process_documents(data_dir)
            vectorstore = get_or_create_vectorstore(documents=doc_splits, persist_dir=persist_dir)
            if vectorstore:
                print("Vector database created successfully!")
            else:
                print("Failed to create vector database")
        else:
            print(f"Data directory not found at {data_dir}")
            print("System will work with limited functionality (no RAG)")

def main():
    # Initialize system
    initialize_system()
    
    # Create workflow
    print("\nCreating workflow...")
    app = create_workflow()
    
    # Initialize conversation state
    conversation_state = initialize_conversation_state()
    
    print("\n" + "="*60)
    print("Medical AI Assistant Ready!")
    print("="*60)
    print("Commands: 'exit' to quit, 'clear' to reset conversation")
    print("Ask any medical question for professional guidance!\n")

    while True:
        query = input("Your question: ").strip()

        if query.lower() == "exit":
            print("\nThank you for using Medical AI Assistant. Stay healthy!")
            break
        
        if query.lower() == "clear":
            conversation_state = initialize_conversation_state()
            print("\nConversation cleared. Starting fresh!\n")
            continue
        
        if not query:
            print("Please enter a question.\n")
            continue

        # Reset state for new query but keep conversation history
        conversation_state = reset_query_state(conversation_state)
        conversation_state["question"] = query
        
        print("\nProcessing your question...")
        
        # Process the query
        result = app.invoke(conversation_state)
        conversation_state.update(result)

        # Display the response with source
        if result.get("generation"):
            print(f"\nResponse: {result['generation']}")
            print(f"Source: {result.get('source', 'Unknown')}")
        else:
            print("\nUnable to generate response. Please try rephrasing.")

        print("\n" + "-" * 60 + "\n")

if __name__ == "__main__":
    main()
