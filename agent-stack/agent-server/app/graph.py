import os
import uuid
from pathlib import Path
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

from .llm import planner, coder
from .tools import extract_tool_call, write_file_safe, read_file_safe, list_files

# Use local data dir if /data doesn't exist (non-Docker mode)
DATA_DIR = os.getenv("DATA_DIR", "/data")
if not Path(DATA_DIR).exists():
    DATA_DIR = str(Path(__file__).parent.parent.parent / "data")
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

MAX_STEPS = int(os.getenv("MAX_STEPS", "12"))


class State(TypedDict, total=False):
    run_id: str
    task: str
    plan: list[str]
    messages: list[dict]  # {role, content}
    workspace: str
    steps: int
    done: bool
    final: str
    error: str


PLANNER_SYS = """You are a senior planner agent.
Return a concise numbered plan (3-8 steps) for completing the user's task.
No extra commentary.
"""

CODER_SYS = """You are an execution agent. You can ONLY do work by emitting a single JSON tool call.

Allowed tools:
- {"tool":"write_file","path":"relative/path","content":"..."}
- {"tool":"read_file","path":"relative/path"}
- {"tool":"list_files"}
- {"tool":"finish","answer":"..."}  (use when done)

Rules:
- Keep edits minimal.
- If you need to see current code, call read_file or list_files first.
- Never output anything except ONE JSON object.
"""

REVIEW_SYS = """You are a strict reviewer.
Given the task, plan, and current workspace file list, decide if the task is done.

If done, answer: DONE: <one paragraph summary>
If not, answer: NOT_DONE: <one sentence what remains>
"""


def node_plan(state: State) -> State:
    task = state["task"]
    out = planner(PLANNER_SYS, [{"role": "user", "content": task}])
    # naive parse: split lines
    plan = [ln.strip(" -\t") for ln in out.splitlines() if ln.strip()]
    return {"plan": plan, "messages": [{"role": "assistant", "content": f"PLAN:\n{out}"}]}


def node_execute(state: State) -> State:
    ws = state["workspace"]
    msgs = state.get("messages", []).copy()
    steps = state.get("steps", 0)

    # Provide context: task + plan + file list
    files = list_files(ws)
    context = f"Task: {state['task']}\nPlan: {state.get('plan', [])}\nFiles: {files}\n"
    msgs.append({"role": "user", "content": context})

    # One tool call per graph step; the graph can cycle
    model_out = coder(CODER_SYS, msgs)
    tool = extract_tool_call(model_out)

    if not tool:
        return {"error": f"Model did not emit valid tool JSON. Output: {model_out}", "done": True}

    t = tool["tool"]
    if t == "list_files":
        files = list_files(ws)
        msgs.append({"role": "tool", "content": f"FILES:\n{files}"})
    elif t == "read_file":
        content = read_file_safe(ws, tool["path"])
        msgs.append({"role": "tool", "content": f"READ {tool['path']}:\n{content[:8000]}"})
    elif t == "write_file":
        write_file_safe(ws, tool["path"], tool["content"])
        msgs.append({"role": "tool", "content": f"WROTE {tool['path']} ({len(tool['content'])} chars)"})
    elif t == "finish":
        return {"final": tool.get("answer", ""), "done": True, "steps": steps + 1, "messages": msgs}
    else:
        return {"error": f"Unknown tool: {t}", "done": True}

    return {"messages": msgs, "steps": steps + 1}


def node_review(state: State) -> State:
    ws = state["workspace"]
    files = list_files(ws)
    review_in = f"Task: {state['task']}\nPlan: {state.get('plan', [])}\nFiles: {files}\n"
    out = planner(REVIEW_SYS, [{"role": "user", "content": review_in}])
    if out.startswith("DONE:"):
        return {"final": out[len("DONE:"):].strip(), "done": True}
    return {"done": False}


def route_after_execute(state: State) -> str:
    if state.get("done"):
        return END
    if state.get("steps", 0) >= MAX_STEPS:
        return END
    return "review"


def route_after_review(state: State) -> str:
    if state.get("done"):
        return END
    return "execute"


def build_graph():
    g = StateGraph(State)
    g.add_node("plan", node_plan)
    g.add_node("execute", node_execute)
    g.add_node("review", node_review)

    g.add_edge(START, "plan")
    g.add_edge("plan", "execute")
    g.add_conditional_edges("execute", route_after_execute, {"review": "review", END: END})
    g.add_conditional_edges("review", route_after_review, {"execute": "execute", END: END})

    return g.compile()
