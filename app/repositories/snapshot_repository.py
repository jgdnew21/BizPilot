import json
from pathlib import Path

from app.domain.purchase.material_request import PurchaseSnapshot


class SnapshotRepository:
    def __init__(self, snapshot_dir: str):
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, snapshot_id: str) -> Path:
        return self.snapshot_dir / f"{snapshot_id}.json"

    def save(self, snapshot: PurchaseSnapshot) -> None:
        self._path(snapshot.snapshot_id).write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")

    def get(self, snapshot_id: str) -> PurchaseSnapshot | None:
        p = self._path(snapshot_id)
        if not p.exists():
            return None
        return PurchaseSnapshot.model_validate_json(p.read_text(encoding="utf-8"))

    def update(self, snapshot: PurchaseSnapshot) -> None:
        self.save(snapshot)

    def latest_by_session_and_status(
        self, session_id: str, status: str, doc_type: str | None = None
    ) -> PurchaseSnapshot | None:
        snapshots: list[PurchaseSnapshot] = []
        for path in self.snapshot_dir.glob("*.json"):
            snap = PurchaseSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
            if snap.session_id != session_id or snap.status != status:
                continue
            if doc_type and snap.doc_type != doc_type:
                continue
            snapshots.append(snap)
        if not snapshots:
            return None
        snapshots.sort(key=lambda s: s.created_at, reverse=True)
        return snapshots[0]
