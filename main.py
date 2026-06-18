import sys
from client import OpenRouterClient, DEFAULT_MODEL

def main():
    print("==========================================================")
    print("   Hybrid Agent - Phase 1: OpenRouter SLM Client Setup   ")
    print("==========================================================")
    
    try:
        agent = OpenRouterClient()
        print(f"Connected to OpenRouter. Using Model: {DEFAULT_MODEL}")
        print("Type your message and press Enter. Type 'exit' or 'quit' to stop.\n")
    except ValueError as e:
        print(f"\nConfiguration Error: {e}")
        print("Please create a '.env' file in this folder and add your key:")
        print("OPENROUTER_API_KEY=your_actual_key_here\n")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error initializing agent: {e}")
        sys.exit(1)

    # Initialize chat history
    conversation_history = []

    while True:
        try:
            user_input = input("\nYou: ").strip()
            if not user_input:
                continue
            
            if user_input.lower() in ["exit", "quit"]:
                print("Goodbye!")
                break
            
            # Append user message
            conversation_history.append({"role": "user", "content": user_input})
            
            print("Agent: ", end="", flush=True)
            
            # Request streaming response from OpenRouter
            full_response = ""
            for chunk in agent.generate_chat_response_stream(conversation_history):
                print(chunk, end="", flush=True)
                full_response += chunk
            print() # Print new line at the end
            
            # Append agent response to history
            conversation_history.append({"role": "assistant", "content": full_response})

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"\nAn error occurred: {e}")

if __name__ == "__main__":
    main()
