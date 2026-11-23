from app.settings import TITLE


def test_page_and_stages(client):
    page = client.get('/')
    assert page.status_code == 200 and TITLE in page.text
    for route,field in [('intake','encoding'),('contract','accepted'),('quality','ready'),('domain','accepted'),('reconcile','balanced')]:
        response = client.post(f'/api/{route}',json={})
        assert response.status_code == 200 and field in response.json()


def test_malformed_sample_can_retry(client):
    invalid = client.post('/api/runs',json={'data':'"ab'})
    assert invalid.json()['code']=='CSV'
    assert client.post('/api/runs',json={}).json()['counts']['accepted']==26


def test_accepted_single_source_has_external_diff(client):
    report = client.post('/api/reconcile',json={}).json()
    assert report['balanced'] and report['book']['mismatched']==3


def test_handover_tab_and_routes_served(client):
    page = client.get('/')
    assert page.status_code == 200 and '合单交班' in page.text
    run_id = client.post('/api/runs', json={}).json()['manifest']['run_id']
    report = client.post(f'/api/handover/{run_id}/receipts', json={})
    assert report.status_code == 200 and len(report.json()['judgements']) == 3
    assert client.get(f'/api/handover/{run_id}').status_code == 200


def test_export_carries_handover_evidence(client):
    run_id = client.post('/api/runs', json={}).json()['manifest']['run_id']
    client.post(f'/api/handover/{run_id}/receipts', json={})
    client.post(f'/api/handover/{run_id}/receipts/LL-20261123-01/evidence', json={})
    bundle = client.get(f'/api/export/{run_id}').json()
    receipt = next(item for item in bundle['handover'] if item['receipt_id'] == 'LL-20261123-01')
    assert receipt['current']['code'] == 'EVIDENCE_MATCH'
    assert [judge['code'] for judge in reversed(
        client.get(f'/api/handover/{run_id}/receipts/LL-20261123-01/timeline').json()['judgements'])] == [
        'TOTAL_MATCH', 'EVIDENCE_MATCH']
