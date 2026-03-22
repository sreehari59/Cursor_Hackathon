import json
import os
from typing import Dict, List, Optional


class InventoryManager:
    """Manages inventory and material availability."""

    def __init__(self, inventory_file: str, materials_file: str):
        self.inventory = self._load_json(inventory_file)
        self.materials = self._load_json(materials_file)
        data_dir = os.path.dirname(inventory_file) or 'data'

        self.procurement_policy = self._load_optional_json(
            os.path.join(data_dir, 'procurement.json'),
            {
                'primary_supplier': 'ChemCorp Asia',
                'primary_lead_time_days': 10,
                'alternate_supplier': 'EuroChem GmbH',
                'alternate_lead_time_days': 14,
            },
        )
        self.production_policy = self._load_optional_json(
            os.path.join(data_dir, 'production.json'),
            {
                'weekly_capacity': 4000,
                'standard_lead_time_days': 22,
                'max_overtime_hours_per_day': 4,
                'working_days_per_week': 5,
                'max_planning_weeks': 4,
            },
        )
        self.logistics_policy = self._load_optional_json(
            os.path.join(data_dir, 'logistics.json'),
            {
                'location_profiles': {
                    'local city': {'type': 'local', 'distance_km': 50},
                    'regional state': {'type': 'regional', 'distance_km': 300},
                    'national': {'type': 'national', 'distance_km': 1000},
                },
                'shipping_modes': {
                    'ground': {'cost_per_unit': 0.30, 'transit_days': 5},
                    'express': {'cost_per_unit': 0.85, 'transit_days': 3},
                    'air': {'cost_per_unit': 2.10, 'transit_days': 1},
                },
                'default_mode': 'ground',
            },
        )
        self.finance_policy = self._load_optional_json(
            os.path.join(data_dir, 'finance.json'),
            {
                'margin_floor': 0.15,
                'target_margin': 0.22,
                'rush_surcharge_rate': 0.12,
                'base_cost_per_unit': 8.5,
                'volume_discounts': [
                    {'min_qty': 0, 'max_qty': 99, 'rate': 0.0},
                    {'min_qty': 100, 'max_qty': 999, 'rate': 0.01},
                    {'min_qty': 1000, 'max_qty': 4999, 'rate': 0.02},
                    {'min_qty': 5000, 'max_qty': 99999999, 'rate': 0.03},
                ],
            },
        )
        self.supplier_catalog = self._load_optional_json(
            os.path.join(data_dir, 'suppliers.json'),
            {'suppliers': {}},
        )
        self.factory_schedule = self._load_optional_json(
            os.path.join(data_dir, 'factory.json'),
            {'lines': [], 'strategy_profiles': {}},
        )
        self.carrier_network = self._load_optional_json(
            os.path.join(data_dir, 'carriers.json'),
            {'origin': 'Plant-01', 'carrier_networks': {}},
        )
        self.sales_policy = self._load_optional_json(
            os.path.join(data_dir, 'sales.json'),
            {
                'default_customer': {
                    'tier': 'standard',
                    'max_price_uplift': 0.20,
                    'acceptable_delivery_buffer_days': 2,
                    'annual_volume': 25000,
                    'relationship_years': 1,
                },
                'customers': {
                    'acme corp': {
                        'tier': 'strategic',
                        'max_price_uplift': 0.25,
                        'acceptable_delivery_buffer_days': 3,
                        'annual_volume': 120000,
                        'relationship_years': 5,
                    }
                },
            },
        )

    def _load_json(self, filepath: str) -> List:
        with open(filepath, 'r', encoding='utf-8') as handle:
            return json.load(handle)

    def _load_optional_json(self, filepath: str, default: Dict) -> Dict:
        if not os.path.exists(filepath):
            return dict(default)
        with open(filepath, 'r', encoding='utf-8') as handle:
            return json.load(handle)

    def get_inventory_dict(self) -> Dict:
        return {item['material_id']: item for item in self.inventory}

    def get_materials_dict(self) -> Dict:
        return {item['sku']: item for item in self.materials}

    def get_product_bom(self, sku: str) -> Optional[Dict]:
        for material in self.materials:
            if material['sku'] == sku:
                return material
        return None

    def get_material_price(self, material_id: str) -> Optional[float]:
        for item in self.inventory:
            if item['material_id'] == material_id:
                return item['unit_cost']
        return None

    def get_material_stock(self, material_id: str) -> Optional[int]:
        for item in self.inventory:
            if item['material_id'] == material_id:
                return item['stock']
        return None

    def get_volume_discount_rate(self, quantity: int) -> float:
        for tier in self.finance_policy.get('volume_discounts', []):
            if quantity >= int(tier.get('min_qty', 0)) and quantity <= int(tier.get('max_qty', 0)):
                return float(tier.get('rate', 0.0))
        return 0.0

    def get_customer_profile(self, customer: str) -> Dict:
        customer_key = str(customer or '').strip().lower()
        customers = self.sales_policy.get('customers', {})
        profile = customers.get(customer_key)
        if profile:
            return profile
        return self.sales_policy.get('default_customer', {})

    def get_location_profile(self, location: str) -> Dict:
        location_key = str(location or '').strip().lower()
        profiles = self.logistics_policy.get('location_profiles', {})
        return profiles.get(location_key, {'type': 'national', 'distance_km': 1000})
