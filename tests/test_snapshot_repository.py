from app.domain.purchase.material_request import PurchaseSnapshot
from app.repositories.snapshot_repository import SnapshotRepository


def test_snapshot_repository_save_and_get(tmp_path):
    repo = SnapshotRepository(str(tmp_path))
    snap = PurchaseSnapshot(
        snapshot_id='snap_x', doc_type='material_request', session_id='s', user_id='u', status='pending_confirmation',
        raw_text='x', markdown_text='m', structured_payload={'a': 1}
    )
    repo.save(snap)
    got = repo.get('snap_x')
    assert got is not None
    assert got.snapshot_id == 'snap_x'
