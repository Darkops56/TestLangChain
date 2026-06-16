from pydantic import BaseModel


class WorkflowRequest(BaseModel):
    input: str


class WorkflowResponse(BaseModel):
    run_id: str


class WorkflowResult(BaseModel):
    input: str
    response: str | None = None
    raw_response: str | None = None
    messages: list[str] = []
