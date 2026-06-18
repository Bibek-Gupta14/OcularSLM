import sys
import json
from client import OpenRouterClient, DEFAULT_MODEL
from tools import TOOL_SCHEMAS, execute_tool

def main():
    print("==========================================================")
    print("       Hybrid Agent - Phase 3: Local Tool Executor        ")
    print("==========================================================")
    print("Available Tools: [write_file], [read_file], [take_screenshot]")
    print(f"Using Model: {DEFAULT_MODEL}")
    
    try:
        agent = OpenRouterClient()
        print("Connected to OpenRouter. Type your request.\n")
    except ValueError as e:
        print(f"\nConfiguration Error: {e}")
        sys.exit(1)

    # Initialize empty chat history (no system prompts for high compatibility)
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
            
            # Run the agent execution loop (it may invoke multiple tools in series)
            processing = True
            while processing:
                print("Thinking...", end="\r", flush=True)
                
                # Send the conversation history and the tools schemas to OpenRouter
                response_message = agent.generate_agent_response(
                    messages=conversation_history,
                    tools=TOOL_SCHEMAS,
                    model=DEFAULT_MODEL
                )
                
                # Check if the model decided to call any tools
                if hasattr(response_message, "tool_calls") and response_message.tool_calls:
                    print("Agent: [Requesting Tool Execution]")
                    
                    # Convert response_message to dictionary to save in history
                    # Some libraries don't allow saving raw response objects directly in history easily,
                    # so we format it matching the OpenAI structure.
                    assistant_msg = {
                        "role": "assistant",
                        "content": response_message.content or "",
                        "tool_calls": []
                    }
                    
                    for tool_call in response_message.tool_calls:
                        assistant_msg["tool_calls"].append({
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments
                            }
                        })
                    
                    conversation_history.append(assistant_msg)
                    
                    # Execute each requested tool
                    for tool_call in response_message.tool_calls:
                        tool_name = tool_call.function.name
                        tool_args = tool_call.function.arguments
                        tool_id = tool_call.id
                        
                        print(f" -> Calling Tool: [{tool_name}] with args: {tool_args}")
                        
                        # Execute the tool locally
                        result = execute_tool(tool_name, tool_args)
                        print(f" -> Result: {result}")
                        
                        # Append tool response message to history
                        conversation_history.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "name": tool_name,
                            "content": result
                        })
                    
                    # Loop back to let the model process the tool results and decide next steps
                    continue
                
                else:
                    # No more tool calls. Print the final answer.
                    print("Agent: ", end="", flush=True)
                    if response_message.content:
                        print(response_message.content)
                        conversation_history.append({"role": "assistant", "content": response_message.content})
                    else:
                        print("[No text returned by the model]")
                    
                    processing = False # Done with this user turn

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"\nAn error occurred in agent loop: {e}")

if __name__ == "__main__":
    main()
