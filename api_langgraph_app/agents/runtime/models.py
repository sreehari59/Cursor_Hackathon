import operator
from dataclasses import dataclass
from typing import Annotated, List, Optional, TypedDict

from langchain_core.messages import BaseMessage


@dataclass
class OrderRequest:
    """Represents an incoming order request."""

    order_id: str
    product_sku: str
    quantity: int
    customer_location: str
    priority: str = 'normal'
    customer: str = 'Acme Corp'
    requested_price: float = 10.0
    requested_delivery_days: int = 18
    negotiation_context: Optional[dict] = None


class LLMAgentState(TypedDict):
    """State carried through the LangGraph workflow."""

    order: dict
    inventory: list
    materials: list
    procurement_analysis: Optional[str]
    production_analysis: Optional[str]
    logistics_analysis: Optional[str]
    finance_analysis: Optional[str]
    sales_analysis: Optional[str]
    messages: Annotated[List[BaseMessage], operator.add]
    all_can_proceed: bool
    final_decision: Optional[str]
