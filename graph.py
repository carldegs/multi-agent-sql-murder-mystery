from __future__ import annotations as _annotations

import asyncio
from dataclasses import dataclass, field
from typing import Annotated, TypeAlias, Union

import sqlite3
from annotated_types import MinLen
from dotenv import load_dotenv
import logfire
from pydantic import BaseModel
from typing_extensions import TypeAlias

from db_manager import DatabaseManager
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.format_as_xml import format_as_xml
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

logfire.configure(
    scrubbing=False
)

# Load environment variables
load_dotenv()

# Load the content of db_schema.txt into db_schema
with open("db_schema.txt", "r") as file:
    db_schema = file.read()


@dataclass
class State:
    findings_notes: str = ""


decider_agent = Agent(
    'openai:gpt-4o',
    result_type=str,
    instrument=True,
    system_prompt=f"""
You are an agent solving crimes by piecing together clues from a database. You generate clear, focused instructions for another agent to execute, which will help uncover the next critical piece of evidence.

You will be provided:
	•	findings_notes: A detailed markdown log of everything discovered so far across multiple turns.
	•	A db_schema: Describing the structure of the database you can query.

⸻

Your objective:
	•	Analyze the findings_notes to determine the next most valuable clue to extract from the database.
	•	Generate a single instruction string describing what needs to be retrieved and why it is important to the investigation.
	•	The instruction can describe a complex operation, as long as it can be performed using a single (even multi-joined, nested, or aggregated) SQL query.

⸻

Important behavior:
	1.	Avoid redundant leads. If a suspect has confessed or has been cleared with strong evidence, do not re-investigate them.
	2.	Backtrack when necessary. If the investigation hits a dead-end or a false lead:
	•	Reanalyze previous turns for missed clues or weak assumptions.
	•	Revisit and validate earlier testimonies, relationships, timelines, or digital traces.
	•	Investigate inconsistencies or unresolved gaps in the narrative.
	3.	Support complex, multi-layered instructions as long as they are logically cohesive and can be expressed as a single SQL query.
(e.g., “Find all people who accessed the building between 9–11 PM but have no recorded alibi, and cross-check if any of them have previously been reported for theft.”)
	4.	Act like a detective.
	•	Interview or verify alibis.
	•	Analyze digital or physical traces.
	•	Identify patterns or correlations.
	•	Choose the next action that moves the case forward efficiently.

DB Schema:
{db_schema}
"""
)


@dataclass
class QueryInstruction(BaseModel):
    findings_notes: str = ''
    instruction: str = field(default="")


@dataclass
class DecideNextStep(BaseNode[State]):
    async def run(self, ctx: GraphRunContext[State]) -> QueryDatabase:
        # Call the decider agent with the findings
        result = await decider_agent.run(ctx.state.findings_notes)
        return QueryDatabase(instruction=result.data)


class Success(BaseModel):
    """Response when SQL could be successfully generated."""

    sql_query: Annotated[str, MinLen(1)]


class InvalidRequest(BaseModel):
    """Response the user input didn't include enough information to generate SQL."""

    error_message: str


QueryGenerateAgentResponse: TypeAlias = Union[Success, InvalidRequest]

query_generate_agent = Agent(
    'openai:gpt-4o',
    result_type=QueryGenerateAgentResponse,
    instrument=True,
    system_prompt=f"""You are an agent that generates a single optimized SQL query given a database schema and instructions on what to query.
The database follows the 'YYYYMMDD' date format. The name field might contain both the first and second name of the person. Combine all conditions into one query using JOIN, AND, OR, UNION, or subqueries as necessary. Do not generate multiple separate queries.

Rules:
	•	Always return only one SQL query that retrieves all the required data.
	•	Use SELECT * to retrieve all fields when querying.
	•	Optimize query performance by using JOIN instead of multiple queries.
	•	If filtering conditions are provided, include them in the WHERE clause efficiently.
	•	Use UNION only when necessary to combine results from different tables that are not directly joinable.
	•	The database schema is as follows: {db_schema}
""",
)


@dataclass
class QueryGenerateAgentDeps:
    db_manager: DatabaseManager


@query_generate_agent.result_validator
async def validate_result(ctx: RunContext[QueryGenerateAgentDeps], result: QueryGenerateAgentResponse) -> QueryGenerateAgentResponse:
    if isinstance(result, InvalidRequest):
        return result

    # Remove the startswith logic to allow flexibility in query structure
    try:
        db_manager = DatabaseManager("sql-murder-mystery.db")
        db_manager.connect()

        # Validate the SQL query using EXPLAIN
        db_manager.execute_query(f'EXPLAIN {result.sql_query}')
    except sqlite3.OperationalError as e:
        raise ModelRetry(f'Operational error in query: {e}') from e
    except sqlite3.Error as e:
        raise ModelRetry(f'Invalid query: {e}') from e
    finally:
        db_manager.close()

    return result


@dataclass
class QueryAgentResponse(BaseModel):
    queries_used: list[str] = field(default_factory=list)
    fetched_data: list = field(default_factory=list)


query_agent = Agent(
    'openai:gpt-4o',
    result_type=QueryAgentResponse,
    instrument=True,
    system_prompt=f"""
You are a highly capable data agent tasked with generating and executing complex and optimized SQL queries based on user instructions and the database schema provided.

Your responsibilities include:
	1.	Analyzing the instruction to determine the most effective way to retrieve the requested data.
	2.	Generating advanced SQL queries that may involve:
        • Multiple table joins
        • Filtering conditions
        • Aggregations (e.g., SUM, AVG, COUNT)
        • Window functions
        • Subqueries or Common Table Expressions (CTEs)
        • Sorting and pagination
	3.	Using generate_sql_query to generate the SQL query.
	4.	Using execute_sql_query to run the query.
	5.	Returning the results in the format of a JSON object, where each key corresponds to a column name and each value corresponds to the result for that column.

Always prioritize correctness, efficiency, and readability. Include aliases, properly format the SQL, and ensure the query reflects the intent of the instruction with precision.

Database schema:
{db_schema}
""",
)


@query_agent.tool
async def generate_sql_query(ctx, instructions: str) -> str:
    r = await query_generate_agent.run(
        format_as_xml({
            "instructions": instructions
        }),
    )
    return r.data


@query_agent.tool
async def execute_sql_query(ctx, sql_query: str) -> list:
    db_manager = DatabaseManager("sql-murder-mystery.db")
    db_manager.connect()
    result = db_manager.execute_query(sql_query)
    db_manager.close()
    return result


@dataclass
class QueryDatabase(BaseNode[State]):
    instruction: str = ""

    async def run(self, ctx: GraphRunContext[State]) -> AnalyzeData:
        # Call the query agent with the instruction
        result = await query_agent.run(
            self.instruction
        )

        return AnalyzeData(
            queries_used=result.data.queries_used,
            results=result.data.fetched_data,
        )


@dataclass
class AnalyzeDataResponse(BaseModel):
    turn_notes: str
    is_culprit_found: bool = False


analyzer_agent = Agent(
    'openai:gpt-4o',
    result_type=AnalyzeDataResponse,
    instrument=True,
    system_prompt=f"""
You are an agent that tries to solve crimes. You will be provided with:
	•	findings_notes: a markdown document containing all findings from previous turns.
	•	queries_used: the set of SQL queries that were executed this turn.
    •	results: the results of the SQL queries.


Response Format:
	•	turn_notes: Return a markdown document that summarizes the findings from this turn based on the queries_used and its results.
	•	is_culprit_found: Return True only if a suspect has been clearly identified and their testimony has been included in this or a previous turn. Otherwise, return False.

```markdown
## Turn [[turn_number]]
### Actions done
- Describe what the agent investigated this turn (e.g., “Checked recent travel logs for all persons of interest”)

### Findings
- Summarize what was learned from the SQL results. List down any new information, clues, or evidence discovered.
- Mention individuals with their name and ID when first introduced.
- If a suspect is identified but not yet interviewed, include a clear note: "**[Name] (ID) has not yet been interviewed.**"
```

Important Rules:
	1.	Never overwrite or remove previous findings. Always append the new turn to the end of findings_notes.
	2.	Set is_culprit_found = True only when:
	•	A specific individual is identified as the likely culprit.
	•	Their interview or testimony is present in the findings (current or previous turns) unless the query returned no results.
	3.	Use clear, concise markdown.
	4.	Ensure continuity in the narrative. Later turns may refer back to earlier ones for context.
"""
)


@dataclass
class AnalyzeData(BaseNode[State]):
    queries_used: list[str] = field(default_factory=list)
    results: list = field(default_factory=list)

    async def run(self, ctx: GraphRunContext[State]) -> GenerateDetectiveStory | DecideNextStep:
        # Call the analyzer agent with the results
        try:
            result = await analyzer_agent.run(
                format_as_xml({
                    "queries_used": self.queries_used,
                    "results": self.results,
                    "findings_notes": ctx.state.findings_notes,
                }),
            )
        except Exception as e:
            raise RuntimeError(f"Error analyzing data: {e}")

        ctx.state.findings_notes += "\n\n"
        ctx.state.findings_notes += result.data.turn_notes

        if result.data.is_culprit_found:
            return GenerateDetectiveStory()
        else:
            return DecideNextStep()


detective_agent = Agent(
    'openai:gpt-4o',
    result_type=str,
    instrument=True,
    system_prompt=f"You are Joins McQuery, a detective that talks like a noir investigator in the 1920s. You have just successfully solved a case and is now trying to write a story about the crime and the investigation. You will be provided a findings_notes, a long text containing all information gathered from all queries. Your goal is to write a story about the crime and the investigation. Ths story should be engaging, interesting and sounds like a true crime/noir novel from the 1920s."
)


@dataclass
class GenerateDetectiveStory(BaseNode[State, None, str]):
    async def run(self, ctx: GraphRunContext[State]) -> End:
        # Call the detective agent with the findings
        result = await detective_agent.run(
            f"Here are the notes containing the findings: {ctx.state.findings_notes}. Write a story about the crime and the investigation.",
        )
        print(result.data)
        return End(result.data)


async def main():
    state = State(
        findings_notes="The crime was a ​murder​ that occurred sometime on ​Jan.15, 2018​ and that it took place in ​SQL City​.")

    graph = Graph(nodes=(DecideNextStep, QueryDatabase,
                  AnalyzeData, GenerateDetectiveStory))
    result = await graph.run(DecideNextStep(), state=state)

    print(result.output)


if __name__ == "__main__":
    asyncio.run(main())
