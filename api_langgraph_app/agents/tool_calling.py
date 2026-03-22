import json
from typing import Any, Dict, List, Type

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel


def _structured_to_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    if hasattr(value, 'model_dump'):
        return value.model_dump()
    return {}


def _content_to_payload(content: Any) -> Any:
    if isinstance(content, str):
        text = content.strip()
        if not text:
            return ''
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return content


def _append_tool_result(tool_results: Dict[str, Any], tool_name: str, payload: Any) -> None:
    existing = tool_results.get(tool_name)
    if existing is None:
        tool_results[tool_name] = payload
        return
    if isinstance(existing, list):
        existing.append(payload)
        return
    tool_results[tool_name] = [existing, payload]


def _build_tool_graph(llm_with_tools, tool_node: ToolNode):
    def agent_node(state: MessagesState):
        return {'messages': [llm_with_tools.invoke(state['messages'])]}

    def should_continue(state: MessagesState):
        last_msg = state['messages'][-1]
        if getattr(last_msg, 'tool_calls', None):
            return 'tools'
        return END

    workflow = StateGraph(MessagesState)
    workflow.add_node('agent', agent_node)
    workflow.add_node('tools', tool_node)
    workflow.set_entry_point('agent')
    workflow.add_conditional_edges(
        'agent',
        should_continue,
        {
            'tools': 'tools',
            END: END,
        },
    )
    workflow.add_edge('tools', 'agent')
    return workflow.compile()


def run_langgraph_tool_agent(
    llm: ChatOpenAI,
    system_prompt: str,
    user_prompt: str,
    tools: List[BaseTool],
    response_schema: Type[BaseModel],
    agent_name: str | None = None,
) -> Dict[str, Any]:
    llm_with_tools = llm.bind_tools(tools)
    tool_node = ToolNode(tools)
    app = _build_tool_graph(llm_with_tools, tool_node)
    result = app.invoke(
        {
            'messages': [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
        }
    )

    messages = result.get('messages', [])
    used_tools: List[str] = []
    tool_results: Dict[str, Any] = {}
    response_text = ''

    for message in messages:
        if isinstance(message, AIMessage):
            content = getattr(message, 'content', '')
            if isinstance(content, str) and content.strip():
                response_text = content
            for tool_call in getattr(message, 'tool_calls', None) or []:
                tool_name = tool_call.get('name')
                if tool_name and tool_name not in used_tools:
                    used_tools.append(tool_name)
        elif isinstance(message, ToolMessage):
            tool_name = getattr(message, 'name', None)
            if tool_name:
                _append_tool_result(tool_results, tool_name, _content_to_payload(message.content))

    structured_llm = llm.with_structured_output(response_schema, method='function_calling')
    structured_prompt = HumanMessage(
        content='Based on the full conversation and tool results above, return the final answer in the required schema.'
    )
    structured_response = structured_llm.invoke(messages + [structured_prompt])
    structured_dict = _structured_to_dict(structured_response)

    if not response_text and structured_dict:
        response_text = json.dumps(structured_dict, default=str)

    return {
        'response_text': response_text,
        'structured_response': structured_dict,
        'tool_results': tool_results,
        'used_tools': used_tools,
        'messages': messages,
    }


def run_prebuilt_tool_agent(*args, **kwargs):
    return run_langgraph_tool_agent(*args, **kwargs)


def run_tool_calling_agent(*args, **kwargs):
    return run_langgraph_tool_agent(*args, **kwargs)
