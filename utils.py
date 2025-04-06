from dataclasses import dataclass, field
from pydantic import BaseModel
from typing import Annotated, Union

@dataclass
class State:
    findings_notes: str = ""

@dataclass
class QueryInstruction(BaseModel):
    findings_notes: str = ''
    instruction: str = field(default="")

@dataclass
class QueryGenerateAgentDeps:
    db_manager: DatabaseManager

class Success(BaseModel):
    sql_query: Annotated[str, MinLen(1)]

class InvalidRequest(BaseModel):
    error_message: str

QueryGenerateAgentResponse: TypeAlias = Union[Success, InvalidRequest]

@dataclass
class QueryAgentResponse(BaseModel):
    queries_used: list[str] = field(default_factory=list)
    fetched_data: list = field(default_factory=list)

@dataclass
class AnalyzeDataResponse(BaseModel):
    new_findings: str
    updated_findings_notes: str
    is_culprit_found: bool = False
