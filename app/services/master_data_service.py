from app.domain.purchase.material_request import MatchedItem, MatchedSupplier, MatchedWarehouse
from app.repositories.master_data_repository import MasterDataRepository


class MasterDataService:
    def __init__(self, repository: MasterDataRepository):
        self.repository = repository

    def match_item(self, input_name: str) -> MatchedItem:
        for row in self.repository.load_items():
            if input_name in row.get("aliases", []):
                return MatchedItem(
                    item_input_name=input_name,
                    item_code=row["item_code"],
                    item_name=row["item_name"],
                    item_name_snapshot=row["item_name"],
                    purchase_uom=row["purchase_uom"],
                    status="matched",
                )
        return MatchedItem(item_input_name=input_name, status="unmatched")

    def match_supplier(self, input_name: str | None) -> MatchedSupplier:
        if not input_name:
            return MatchedSupplier(supplier_input=None, status="unmatched")
        for row in self.repository.load_suppliers():
            if input_name in row.get("aliases", []):
                return MatchedSupplier(
                    supplier_input=input_name,
                    supplier_standard_name=row["supplier_name"],
                    status="matched",
                )
        return MatchedSupplier(supplier_input=input_name, status="unmatched")

    def match_warehouse(self, input_name: str | None) -> MatchedWarehouse:
        if not input_name:
            return MatchedWarehouse(warehouse_input=None, status="unmatched")
        for row in self.repository.load_warehouses():
            if input_name in row.get("aliases", []):
                return MatchedWarehouse(
                    warehouse_input=input_name,
                    warehouse_standard_name=row["warehouse_name"],
                    status="matched",
                )
        return MatchedWarehouse(warehouse_input=input_name, status="unmatched")
