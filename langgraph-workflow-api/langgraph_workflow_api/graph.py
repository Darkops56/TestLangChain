import os
from typing import TypedDict, Annotated
import operator
from google import genai
from langgraph.graph import StateGraph, END


DEFAULT_MODEL = "gemini-2.0-flash"

SYSTEM_PROMPT = (
    "You are a helpful AI assistant integrated into a LangGraph workflow. "
    "Respond to the user's input in a clear, concise, and helpful manner."
)


class AgentState(TypedDict):
    input: str
    response: str | None
    raw_response: str | None
    messages: Annotated[list[str], operator.add]


def ai_agent_node(state: AgentState, client: genai.Client) -> dict:
    if not state["input"]:
        return {
            "response": "No input provided.",
            "raw_response": None,
            "messages": ["AI Agent: Empty input received"],
        }

    model_name = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    response = client.models.generate_content(
        model=model_name,
        contents=state["input"],
        config={"system_instruction": SYSTEM_PROMPT},
    )
    content = response.text or ""

    return {
        "response": content,
        "raw_response": content,
        "messages": ["AI Agent: Response generated"],
    }


def build_graph(client: genai.Client) -> StateGraph:
    workflow = StateGraph(AgentState)

    workflow.add_node("ai_agent", lambda s: ai_agent_node(s, client))

    workflow.set_entry_point("ai_agent")
    workflow.add_edge("ai_agent", END)

    return workflow.compile()


def run_workflow(input_text: str, client: genai.Client) -> dict:
    initial_state: AgentState = {
        "input": input_text,
        "response": None,
        "raw_response": None,
        "messages": [],
    }
    graph = build_graph(client)
    result = graph.invoke(initial_state)
    return dict(result)
