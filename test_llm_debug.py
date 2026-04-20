import os
from dotenv import load_dotenv
from agents.llm_agent import LLMAgent
from core.state import initialize_conversation_state

load_dotenv()

def test_llm():
    print("Testing LLM Agent...")
    state = initialize_conversation_state()
    state["question"] = "What is a common symptom of the flu?"
    
    try:
        result = LLMAgent(state)
        print("Result:", result.get("generation"))
        print("Success:", result.get("llm_success"))
    except Exception as e:
        print("Error during LLMAgent execution:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_llm()
