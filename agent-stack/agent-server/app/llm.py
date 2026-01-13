import os
import json

BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
PLANNER_MODEL = os.getenv("PLANNER_MODEL", "llama3.2:latest")
CODER_MODEL = os.getenv("CODER_MODEL", "deepseek-coder:6.7b")
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() == "true"

client = None


def _get_client():
    global client
    if client is None:
        try:
            import ollama
            client = ollama.Client(host=BASE_URL)
            # Test connection
            client.list()
            print(f"Connected to Ollama at {BASE_URL}")
        except Exception as e:
            print(f"Ollama not available ({e}), using mock mode")
            return None
    return client


def chat(model: str, system: str, messages: list[dict], temperature: float = 0.2) -> str:
    c = _get_client()

    if c is None or MOCK_MODE:
        return _mock_chat(model, system, messages)

    try:
        resp = c.chat(
            model=model,
            messages=[{"role": "system", "content": system}, *messages],
            options={"temperature": temperature},
        )
        return resp["message"]["content"]
    except Exception as e:
        print(f"Ollama error: {e}, falling back to mock")
        return _mock_chat(model, system, messages)


def _mock_chat(model: str, system: str, messages: list[dict]) -> str:
    """Mock responses for testing without Ollama"""
    last_msg = messages[-1]["content"] if messages else ""

    # Detect if this is a planner or coder call based on system prompt
    if "planner" in system.lower():
        return """1. Analyze requirements
2. Create project structure
3. Write main code file
4. Add README documentation
5. Review and finalize"""

    elif "reviewer" in system.lower():
        # Check if files exist in the context
        if "README" in last_msg and ".py" in last_msg:
            return "DONE: Task completed successfully. Created Python package with CLI and documentation."
        return "NOT_DONE: Need to create remaining files."

    else:
        # Coder - emit tool calls
        if "Files: []" in last_msg or "Files: ['']" in last_msg:
            # No files yet, create main.py
            return json.dumps({
                "tool": "write_file",
                "path": "hello_cli.py",
                "content": '''#!/usr/bin/env python3
"""Hello CLI - A simple command line tool."""
import argparse

def main():
    parser = argparse.ArgumentParser(description="Say hello!")
    parser.add_argument("--name", default="World", help="Name to greet")
    args = parser.parse_args()
    print(f"Hello, {args.name}!")

if __name__ == "__main__":
    main()
'''
            })
        elif "hello_cli.py" in last_msg and "README" not in last_msg:
            # Create README
            return json.dumps({
                "tool": "write_file",
                "path": "README.md",
                "content": '''# Hello CLI

A simple Python CLI that prints hello.

## Installation

```bash
pip install -e .
```

## Usage

```bash
python hello_cli.py
python hello_cli.py --name Alice
```

## Output

```
Hello, World!
Hello, Alice!
```
'''
            })
        else:
            # All done
            return json.dumps({
                "tool": "finish",
                "answer": "Created hello_cli.py and README.md successfully."
            })


def planner(system: str, messages: list[dict]) -> str:
    return chat(PLANNER_MODEL, system, messages, temperature=0.2)


def coder(system: str, messages: list[dict]) -> str:
    return chat(CODER_MODEL, system, messages, temperature=0.2)
