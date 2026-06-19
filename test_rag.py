import json
from tools import execute_tool

def test_pydantic_validation():
    print("--- Testing Pydantic Validation ---")
    
    # Test valid input for write_file
    args = {"filename": "temp_test_val.txt", "content": "Hello Validation!"}
    res = execute_tool("write_file", args)
    print("Valid write_file call result:", res)
    assert "success" in res
    
    # Test invalid input for write_file (missing 'content')
    args_invalid = {"filename": "temp_test_val.txt"}
    res_invalid = execute_tool("write_file", args_invalid)
    print("Invalid write_file call result:", res_invalid)
    assert "validation_error" in res_invalid

    # Clean up
    import os
    if os.path.exists("temp_test_val.txt"):
        os.remove("temp_test_val.txt")
    print("Pydantic validation checks passed!\n")

def test_rag_capabilities():
    print("--- Testing RAG Capabilities ---")
    
    # Trigger indexing
    idx_res = json.loads(execute_tool("index_codebase", {}))
    print("Indexing result:", idx_res)
    assert idx_res["status"] == "success"
    
    # Perform search
    search_res = json.loads(execute_tool("search_codebase", {"query": "DEFAULT_MODEL"}))
    print("Search results:")
    for result in search_res["results"]:
        print(f"- Path: {result['metadata']['path']}, Score: {result['score']:.4f}")
        print(f"  Snippet: {result['content'][:100]}...")
    
    assert len(search_res["results"]) > 0
    print("RAG query checks passed!\n")

if __name__ == "__main__":
    test_pydantic_validation()
    test_rag_capabilities()
    print("All tests completed successfully!")
