import asyncio
import logging
import os
import uuid
from dotenv import load_dotenv
from google import genai
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.models import WorkflowRequest, WorkflowResponse, WorkflowResult
from langgraph_workflow_api.graph import run_workflow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError(
        "GEMINI_API_KEY not found. "
        "Copy .env.example to .env and set your Gemini API key."
    )

gemini_client = genai.Client(api_key=api_key)

app = FastAPI(title="LangGraph Workflow API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

results: dict[str, dict] = {}
lock = asyncio.Lock()


@app.post("/workflow/run", status_code=202)
async def start_workflow(body: WorkflowRequest) -> WorkflowResponse:
    run_id = str(uuid.uuid4())

    async def execute():
        try:
            loop = asyncio.get_event_loop()
            state = await loop.run_in_executor(None, run_workflow, body.input, gemini_client)
        except Exception as e:
            logger.error("Workflow %s failed: %s", run_id, e)
            state = {
                "input": body.input,
                "response": None,
                "raw_response": None,
                "messages": [f"Workflow execution failed: {e}"],
            }
        async with lock:
            results[run_id] = state

    asyncio.ensure_future(execute())

    return WorkflowResponse(run_id=run_id)


@app.get("/workflow/result/{run_id}")
async def get_result(run_id: str) -> WorkflowResult:
    async with lock:
        state = results.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return WorkflowResult(**state)
