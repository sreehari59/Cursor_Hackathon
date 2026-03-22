from datetime import datetime, timedelta

from .models import OrderRequest


def build_mock_process_order_response(request: OrderRequest) -> dict:
    """Return a deterministic mock response while LangGraph execution is disabled."""

    unit_price = 10.8 if request.priority == 'expedited' else 10.4
    quantity = max(1, int(request.quantity))
    total_deal_value = round(unit_price * quantity, 2)

    lead_time_days = 14 if request.priority == 'expedited' else 21
    delivery_date = (datetime.utcnow().date() + timedelta(days=lead_time_days)).strftime('%Y-%m-%d')

    return {
        'status': 'SUCCESS',
        'order_id': request.order_id,
        'product_sku': request.product_sku,
        'quantity': quantity,
        'customer_location': request.customer_location,
        'final_price': unit_price,
        'total_deal_value': total_deal_value,
        'delivery_date': delivery_date,
        'cost_breakdown': {
            'discount_rate': 0.02 if quantity >= 1000 else 0.0,
            'profit_margin': 0.25,
        },
        'consensus_reached': True,
        'agent_responses': {
            'procurement': {
                'agent': 'Procurement Agent',
                'can_proceed': True,
                'reasoning': 'Mock: primary supplier confirms material reservation.',
                'confidence': 0.9,
            },
            'production': {
                'agent': 'Production Agent',
                'can_proceed': True,
                'reasoning': 'Mock: production line can absorb rush order with limited overtime.',
                'confidence': 0.88,
                'production_days': lead_time_days - 3,
                'overtime_hours': 4,
            },
            'logistics': {
                'agent': 'Logistics Agent',
                'can_proceed': True,
                'reasoning': 'Mock: routing supports requested volume.',
                'confidence': 0.87,
                'delivery_date': delivery_date,
                'shipping_cost': round(total_deal_value * 0.03, 2),
            },
            'finance': {
                'agent': 'Finance Agent',
                'can_proceed': True,
                'reasoning': 'Mock: commercial constraints satisfied.',
                'confidence': 0.89,
                'discount_rate': 0.02 if quantity >= 1000 else 0.0,
                'margin': 0.25,
                'final_price': unit_price,
                'total_deal_value': total_deal_value,
            },
            'sales': {
                'agent': 'Sales Agent',
                'can_proceed': True,
                'reasoning': 'Mock: customer relationship supports proposed terms.',
                'confidence': 0.86,
                'agreed_price': unit_price,
            },
        },
        'mock_mode': True,
        'timestamp': datetime.utcnow().isoformat(),
    }
