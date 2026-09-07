import openai
from openai import OpenAI
from pydantic import BaseModel
from typing import Literal
import json

client = OpenAI(
    max_retries=3,
    timeout=30
)

class OpenAIServiceError(RuntimeError):
    pass

def get_customer_status(customer_id: str) -> dict[str, str]:
    customers = {
        "cust_123": {
            "plan": "Enterprise",
            "region": "ca-central",
            "status": "active",
            "open_incidents": 1
        },
        "cust_456": {
            "plan": "Pro",
            "region": "ca-east",
            "status": "active",
            "open_incidents": 0            
        },
        "cust_suspended": {
            "plan": "Enterprise",
            "region": "ca-west",
            "status": "suspended",
            "open_incidents": 0             
        }
    }

    try:
        return customers[customer_id]

    except KeyError as e:
        raise LookupError(f"Customer {customer_id} is not found")

def search_logs(customer_id, error_code) -> dict[str, str]:

    if customer_id == "cust_404":
        raise LookupError("Customer not found")

    if customer_id == "cust_timeout":
        raise TimeoutError("Logging service timed out")

    logs = {
        "401": "Invalid API key",
        "429": "Rate limit exceeded",
        "503": "Authentication service unavailable",
        "500": "Internal server error" 
    }

    return {
        "customer_id": customer_id,
        "error_code": logs[error_code]
    }

def get_active_incidents(service: str) -> dict[str, str|list[dict[str, str]]]:
    return {
        "service": service,
        "incidents": [
            {
                "id": "INC-4821",
                "status": "investigating",
                "title": "Elevated errors in authentication service"
            }
        ]
    }

def get_api_usage(customer_id: str) -> dict[str, int]:
    customers_to_usage = {
        "cust_123": {
            "requests_last_minute": 982,
            "rate_limit": 1000,
            "failed_requests": 80
        },
        "cust_456": {
            "requests_last_minute": 1,
            "rate_limit": 1000,
            "failed_requests": 0
        }
    }

    try:
        return customers_to_usage[customer_id]

    except KeyError as e:
        raise LookupError(f"Customer with {customer_id} is not found")

tools = [
    {
        "type": "function",
        "name": "get_customer_status",
        "description": "Get account and service status information for a specific customer.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"}
            },
            "required": ["customer_id"],
            "additionalProperties": False
        },
        "strict": True
    },

    {
        "type": "function",
        "name": "search_logs",
        "description": """
        Search application logs for a specific customer and HTTP error code.
Use this only when both customer_id and error_code are known.
Never infer or invent either value. If either is missing, ask the user.
""",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "error_code": {"type": "string"}
            },
            "required": ["customer_id", "error_code"],
            "additionalProperties": False
        },
        "strict": True
    },

    {
        "type": "function",
        "name": "get_active_incidents",
        "description": "Get currently active incidents for a service.",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {"type": "string"}
            },
            "required": ["service"],
            "additionalProperties": False
        },
        "strict": True
    },

    {
        "type": "function",
        "name": "get_api_usage",
        "description": "Get user's API usage and rate-limit information",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"}
            },
            "required": ["customer_id"],
            "additionalProperties": False
        },
        "strict": True
    }

]

instructions = """
You are a technical support assistant.

Use the available tools when needed to investigate customer issues.

Rules:
- Never invent customer data or tool results.
- Never guess required tool arguments.
- Tool arguments must come explicitly from the user, previous conversation or previous tool calls
- values like "unknown", "unspecified", "N/A" or made-up values are NOT valid tool arguments
- If any tool argument is not known DO NOT call the tool, instead return status="needs_information" and ask the user for more information instead.
- If enough information for performing investigation is present return status="analysis_complete"
- If a tool returns ok=false, treat that tool operation as failed.
- Do not claim that no data exists merely because a tool failed.

Output rules:
- If status="needs_information":
    - "question" must contain question for the user
    - "analysis" must be null
- If status = "analysis_complete":
    - "question" must be null
    - "analysis must contain completed support analysis"
- Do not return status = "analysis_complete" until the required investigation has been preformed
"""

class IncidentFacts(BaseModel):
    service: str | None
    error_code: int | None
    environment: Literal["production", "staging", "development"] | None

class Impact(BaseModel):
    affected_users: int | None
    affected_percentage: float | None
    locations: list[str]

class RecommendedAction(BaseModel):
    action: str
    priority: Literal["low", "medium", "high"]
    owner: Literal["support", "engineering", "customer"]

class SupportAnalysis(BaseModel):
    incident: IncidentFacts
    impact: Impact
    needs_escalation: bool
    summary: str
    recommended_actions: list[RecommendedAction]

class AgentResponse(BaseModel):
    status: Literal[
        "needs_information",
        "analysis_complete"
    ]
    question: str | None
    analysis: SupportAnalysis | None


def run_stream_structured(input_data:str, previous_response_id=None) -> tuple[str, list[str]|None, AgentResponse | None]:

    try:

        with client.responses.stream(
            model="gpt-5",
            instructions=instructions,
            input=input_data,
            previous_response_id=previous_response_id,
            # stream=True,
            tools=tools,
            text_format=AgentResponse
        ) as stream:

            for event in stream:
                if event.type == "response.output_text.delta":
                    print(event.delta, end="", flush=True)

            response = stream.get_final_response()

    except openai.APITimeoutError as e:
        raise OpenAIServiceError("The OpenAI API request timed out after retries")
    
    except openai.RateLimitError as e:
        raise OpenAIServiceError("The OpenAI API rate limit was exceeded after retries")

    except openai.APIConnectionError as e:
        raise OpenAIServiceError("Could not connect to OpenAI API after retries")

    except openai.InternalServerError as e:
        raise OpenAIServiceError("OpenAI API returned internal server error after retries")

    except openai.AuthenticationError as e:
        raise OpenAIServiceError("OpenAI API authetication failed. Check API key")

    except openai.BadRequestError as e:
        raise OpenAIServiceError(f"Bad request, error: {e}")

    except openai.APIError as e:
        raise OpenAIServiceError(f"Unexpected OpenAI API error: {e}")



    function_calls = [item for item in response.output if item.type == "function_call"]

    return response.id, function_calls, response.output_parsed

tool_functions = {
    "get_customer_status": get_customer_status,
    "search_logs": search_logs,
    "get_active_incidents": get_active_incidents,
    "get_api_usage": get_api_usage
}


def execute_tool(name, arguments):

    function = tool_functions.get(name)

    if function is None:
        raise ValueError(f"Unknown tool: {name}")

    try:
        result = function(**arguments)

        return {
            "ok": True,
            "data": result
        }

    except LookupError:
        return {
            "ok": False,
            "error": {
                "code": "not_found",
                "message": "The requested resource was not found.",
                "retryable": False
            }
        }

    except TimeoutError:
        return {
            "ok": False,
            "error": {
                "code": "timeout",
                "message": "The backend service timed out.",
                "retryable": True
            }
        }

    except Exception:
        return {
            "ok": False,
            "error": {
                "code": "internal_error",
                "message": "The tool encountered an unexpected error.",
                "retryable": False
            }
        }


def process_user_request(user_input,previous_response_id=None):
    response_id, function_calls, parsed = run_stream_structured(input_data=user_input, previous_response_id=previous_response_id)
    print(f"""\n*************FUNCTION CALLS**************\n
    {function_calls}
    \n*************END OF FUNCTION CALLS***************
    """)

    MAX_TOOL_ROUNDS = 5

    for _ in range(MAX_TOOL_ROUNDS):

        if not function_calls:
            # print("this is the place to call model outside tool loop for the final analisys")
            if parsed:                
                print("\n\nSTRUCTURED OUTPUT:\n")
                print(parsed.model_dump_json(indent=2))
            return response_id

        tool_outputs = []

        for call in function_calls:

            arguments = json.loads(call.arguments)

            print("\n*** Executing tool calls ***")

            print(f"\n[Calling function: '{call.name}' with arguments: {arguments}]")

            tool_output = execute_tool(call.name, arguments)

            print(f"[Tool result: {tool_output}\n")
            print("\n*** End of tool calls ***")

            tool_outputs.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": json.dumps(tool_output)
            })

        response_id, function_calls, parsed = run_stream_structured(input_data=tool_outputs, previous_response_id = response_id)

    raise RuntimeError("Maximum tall-call rounds exceeded")

previous_response_id = None

while True:

    user_input = input("\nYou: ")

    if user_input.lower() in ["quit", "exit", "stop", "bye"]:
        break

    if user_input.lower() == "new":
        previous_response_id = None
        print("Conversation reset")
        continue

    print("\nAssistant: ", end="", flush=True)

    try:

        previous_response_id = process_user_request(user_input, previous_response_id)

    except OpenAIServiceError as e:
        print(f"\n\n>>hey there, we experienced an error: [{e}]")