from fastapi.testclient import TestClient

from app.config import settings
from app.integrations.erpnext_client import ErpnextClient
from app.main import app


client = TestClient(app)


def test_health_ok():
    res = client.get('/health')
    assert res.status_code == 200
    assert res.json()['status'] == 'ok'


def test_ready_ok(tmp_path):
    snapshots = tmp_path / 'snapshots'
    master = tmp_path / 'master_data'
    master.mkdir(parents=True)
    (master / 'items.json').write_text('[]')
    (master / 'suppliers.json').write_text('[]')
    (master / 'warehouses.json').write_text('[]')

    old_snapshot, old_master = settings.snapshot_dir, settings.master_data_dir
    settings.snapshot_dir, settings.master_data_dir = str(snapshots), str(master)
    try:
        res = client.get('/health/ready')
    finally:
        settings.snapshot_dir, settings.master_data_dir = old_snapshot, old_master

    assert res.status_code == 200
    assert res.json()['status'] == 'ready'


def test_ready_missing_master_data_returns_503(tmp_path):
    snapshots = tmp_path / 'snapshots'
    master = tmp_path / 'master_data'
    master.mkdir(parents=True)

    old_snapshot, old_master = settings.snapshot_dir, settings.master_data_dir
    settings.snapshot_dir, settings.master_data_dir = str(snapshots), str(master)
    try:
        res = client.get('/health/ready')
    finally:
        settings.snapshot_dir, settings.master_data_dir = old_snapshot, old_master

    assert res.status_code == 503


def test_erpnext_health_uses_client_ping(monkeypatch):
    monkeypatch.setattr(ErpnextClient, 'ping', lambda self: (True, {'user': 'test@example.com'}))
    ok_res = client.get('/health/erpnext')
    assert ok_res.status_code == 200
    assert ok_res.json()['erpnext'] == 'reachable'

    monkeypatch.setattr(ErpnextClient, 'ping', lambda self: (False, {'message': 'connection failed'}))
    bad_res = client.get('/health/erpnext')
    assert bad_res.status_code == 503
    assert bad_res.json()['detail']['erpnext'] == 'unreachable'
