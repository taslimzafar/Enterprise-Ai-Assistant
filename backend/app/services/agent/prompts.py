import json
from typing import Any


INTENT_CLASSIFIER_SYSTEM = """You are an intent classification system for an Enterprise AI Assistant.
Analyze the user's message and determine the correct intent category.

INTENT CATEGORIES:
1. "knowledge_question": The user is asking about company policies, documentation, benefits, leave, processes, guidelines, technical documents, organizational information, or any fact-based inquiry that requires consulting the enterprise knowledge base.
2. "conversational": The user is greeting, thanking, asking about the assistant's persona, or engaging in polite chitchat (e.g., "Hello", "Hi there", "Thank you", "Who are you?", "Good morning").
3. "unsupported": The user is asking to execute harmful actions, system exploits, or tasks completely outside an enterprise knowledge assistant's scope.

OUTPUT FORMAT:
Respond ONLY with a valid JSON object:
{
  "intent": "knowledge_question" | "conversational" | "unsupported"
}

RULE: If there is any doubt or if the message could refer to workplace matters, choose "knowledge_question".
"""

CONVERSATIONAL_SYSTEM_INSTRUCTION = """You are an Enterprise AI Assistant.
Respond warmly, politely, and concisely to conversational remarks, greetings, or questions about your role.
Remind the employee that you are ready to answer questions grounded in the organization's verified documents, policies, and knowledge base.
Do NOT invent or claim knowledge of specific organizational policies without consulting documents.
"""

UNSUPPORTED_SYSTEM_INSTRUCTION = """You are an Enterprise AI Assistant.
The user has requested an action or topic outside the scope of an enterprise knowledge assistant.
Politely explain that you are designed to assist with organization knowledge, documentation, policies, and workplace inquiries.
"""

TOOL_DECISION_SYSTEM = """You are the tool decision reasoning engine for an Enterprise AI Assistant.
Analyze the user request and available tools, and decide whether a tool call is necessary.

RULES:
1. Only select from the AVAILABLE TOOLS provided.
2. If the user asks a calculation or math question, call "calculator".
3. If the user asks about document statistics, total conversations, or organization counts, call "organization_stats" (or "database_query").
4. If the user asks a workplace knowledge question, call "knowledge_search".
5. If no tool is needed or information is already sufficient, choose "direct_answer".
6. Never make up arguments. Follow the parameters schema exactly.

OUTPUT FORMAT:
Respond ONLY with valid JSON:
{
  "action": "call_tool" | "direct_answer",
  "tool": "<tool_name>",
  "arguments": { <args> }
}
"""

TOOL_ANSWER_SYSTEM_INSTRUCTION = """You are an Enterprise AI Assistant.
You have executed a verified enterprise tool to fulfill the user's request.
Present the result clearly, concisely, and professionally to the user.
If a tool returned an error, explain the issue politely without leaking stack traces or internal systems.
If citing documents from knowledge_search, ensure citations ([Doc X]) are maintained.
"""


def format_classifier_prompt(question: str, history: list[dict[str, str]] | None = None) -> str:
    """Format prompt for the intent classifier."""
    hist_text = ""
    if history:
        items = [f"{m.get('role', 'user')}: {m.get('content', '')}" for m in history[-3:]]
        hist_text = "Recent context:\n" + "\n".join(items) + "\n\n"

    return f"""{hist_text}User Message:
{question}

Provide your classification JSON:"""


def format_tool_decision_prompt(
    question: str,
    available_tools: list[dict[str, Any]],
    history: list[dict[str, str]] | None = None,
) -> str:
    """Format prompt for the tool decision node."""
    tools_desc = json.dumps(available_tools, indent=2)
    hist_text = ""
    if history:
        items = [f"{m.get('role', 'user')}: {m.get('content', '')}" for m in history[-3:]]
        hist_text = "Recent context:\n" + "\n".join(items) + "\n\n"

    return f"""{hist_text}AVAILABLE TOOLS:
{tools_desc}

User Message:
{question}

Decide action (JSON):"""


def format_tool_answer_prompt(
    question: str,
    tool_name: str,
    tool_arguments: dict[str, Any] | None,
    tool_result: Any,
    tool_error: str | None = None,
) -> str:
    """Format prompt for synthesizing final response from tool execution outcome."""
    if tool_error:
        return f"""User Request:
{question}

Tool Executed: {tool_name}
Outcome: Error
Error Details: {tool_error}

Please provide a helpful, polite explanation to the user regarding this error."""

    return f"""User Request:
{question}

Tool Executed: {tool_name}
Tool Arguments: {json.dumps(tool_arguments or {})}
Tool Output Result:
{json.dumps(tool_result, indent=2) if isinstance(tool_result, (dict, list)) else str(tool_result)}

Provide a clear, accurate, and professional response summarizing or answering the user's request based on this verified data."""
