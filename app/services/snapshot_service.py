from datetime import datetime
from uuid import uuid4

from app.config import settings
from app.domain.purchase.material_request import PurchaseSnapshot
from app.repositories.snapshot_repository import SnapshotRepository


class SnapshotService:
    def __init__(self, repository: SnapshotRepository):
        self.repository = repository

    @classmethod
    def from_settings(cls) -> "SnapshotService":
        return cls(SnapshotRepository(settings.snapshot_dir))

    def generate_snapshot_id(self) -> str:
        return f"snap_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"

    def save(self, snapshot: PurchaseSnapshot) -> None:
        self.repository.save(snapshot)

    def get(self, snapshot_id: str) -> PurchaseSnapshot | None:
        return self.repository.get(snapshot_id)

    def update(self, snapshot: PurchaseSnapshot) -> None:
        self.repository.update(snapshot)

    def latest_by_session_and_status(
        self, session_id: str, status: str, doc_type: str | None = None
    ) -> PurchaseSnapshot | None:
        return self.repository.latest_by_session_and_status(session_id, status, doc_type)
