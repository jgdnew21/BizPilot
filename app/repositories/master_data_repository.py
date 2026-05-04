import json
from pathlib import Path


class MasterDataRepository:
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)

    def load_items(self) -> list[dict]:
        return json.loads((self.base_dir / "items.json").read_text(encoding="utf-8"))

    def load_suppliers(self) -> list[dict]:
        return json.loads((self.base_dir / "suppliers.json").read_text(encoding="utf-8"))

    def load_warehouses(self) -> list[dict]:
        return json.loads((self.base_dir / "warehouses.json").read_text(encoding="utf-8"))
