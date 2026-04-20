import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
import os

MODEL_PATH = r"./biogpt-merged/"

if not os.path.exists(MODEL_PATH):
    raise ValueError(f"Model folder not found: {MODEL_PATH}")

print("Loading Medical AI...")

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    torch_dtype=torch.float32,
    low_cpu_mem_usage=True,
)
model.eval()

print("Ready!\n")

# Generate Answer
def get_answer(question):
    """Get answer for a question"""
    inputs = tokenizer(question, return_tensors="pt", truncation=True, max_length=512)
    
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=200,
            temperature=0.7,
            top_p=0.9,
            do_sample=True,
            repetition_penalty=1.2,
            pad_token_id=tokenizer.pad_token_id,
        )
    
    answer = tokenizer.decode(outputs[0], skip_special_tokens=True)
    
    # Remove question from answer
    if answer.startswith(question):
        answer = answer[len(question):].strip()
    
    return answer

# Main Loop
print("Ask any medical question!")
print("Type 'exit' to quit")
print()

while True:
    # Get question
    question = input("Your Question: ").strip()
    
    # Check exit
    if question.lower() in ['exit', 'quit', 'q']:
        print("\nGoodbye!")
        break
    
    # Skip empty
    if not question:
        continue
    
    # Get answer
    print("\nThinking...\n")
    answer = get_answer(question)
    
    # Show answer
    print("Answer:")
    print("-" * 60)
    print(answer)
    print("-" * 60)
    print()