import pytest
from pathlib import Path
from app.errors import DataError
from app.modules.handover.parser import parse_receipts, parse_evidence
from app.settings import KEY, UNIT


RECEIPTS_HEADER = f'领料回单,合单锯切计划,合单记录值({UNIT})'
EVIDENCE_HEADER = f'{KEY},补录记录值({UNIT})'


@pytest.fixture
def anchor(client):
    return client.post('/api/runs', json={}).json()['manifest']['run_id']


@pytest.fixture
def registered(client, anchor):
    response = client.post(f'/api/handover/{anchor}/receipts', json={})
    assert response.status_code == 200
    return response.json()


def by_id(judgements, receipt_id):
    return next(item for item in judgements if item['receipt_id'] == receipt_id)


def test_sample_receipts_split_total_levels(registered):
    r1 = by_id(registered['judgements'], 'LL-20261123-01')
    r2 = by_id(registered['judgements'], 'LL-20261123-02')
    assert r1['code'] == 'TOTAL_MATCH' and r1['delta'] == '0'
    assert r2['code'] == 'TOTAL_DELTA' and r2['delta'] == '1000'
    # 总额相符也不能替各单下结论：逐单全部停在待凭据。
    assert {row['code'] for row in r1['rows']} == {'PENDING_EVIDENCE'}
    assert r1['pending'] == ['00101', '00102'] and r1['evidence_sha256'] is None


def test_receipt_registration_is_idempotent(client, anchor, registered):
    again = client.post(f'/api/handover/{anchor}/receipts', json={}).json()
    assert again == registered
    timeline = client.get(f'/api/handover/{anchor}/receipts/LL-20261123-01/timeline').json()
    assert [item['seq'] for item in timeline['judgements']] == [1]


def test_same_receipt_with_other_content_rejected(client, anchor, registered):
    payload = f'{RECEIPTS_HEADER}\nLL-20261123-01,00101;00102,9999\n'
    response = client.post(f'/api/handover/{anchor}/receipts', json={'receipts': payload})
    assert (response.status_code, response.json()['code']) == (422, 'RECEIPT_CONFLICT')


def test_parser_rejects_bad_width_duplicate_and_header():
    with pytest.raises(DataError) as error:
        parse_receipts(f'{RECEIPTS_HEADER}\nLL-1,00101\n'.encode())
    assert error.value.code == 'WIDTH'
    payload = f'{RECEIPTS_HEADER}\nLL-1,00101;00101,100\n'.encode()
    with pytest.raises(DataError) as error:
        parse_receipts(payload)
    assert error.value.code == 'WIDTH'
    payload = f'{RECEIPTS_HEADER}\nLL-1,00101,100\nLL-1,00102,100\n'.encode()
    with pytest.raises(DataError) as error:
        parse_receipts(payload)
    assert error.value.code == 'RECEIPT_CONFLICT'
    with pytest.raises(DataError) as error:
        parse_receipts(f'{RECEIPTS_HEADER}\n\n'.encode())
    assert error.value.code == 'HEADER_ONLY'


def test_evidence_parser_rejects_duplicate_key():
    payload = f'{EVIDENCE_HEADER}\n00101,1\n00101,2\n'.encode()
    with pytest.raises(DataError) as error:
        parse_evidence(payload)
    assert error.value.code == 'EVIDENCE_CONFLICT'


def test_team_can_only_sign_evidenced_total_conclusion(client, anchor, registered):
    missing_note = client.post(f'/api/handover/{anchor}/receipts/LL-20261123-01/signoff',
                               json={'scope': 'TOTAL', 'decision': '确认', 'note': '  '})
    assert (missing_note.status_code, missing_note.json()['code']) == (422, 'REVIEW_NOTE')
    blocked = client.post(f'/api/handover/{anchor}/receipts/LL-20261123-03/signoff',
                          json={'scope': 'TOTAL', 'decision': '确认', 'note': '总额不符也要签'})
    assert (blocked.status_code, blocked.json()['code']) == (422, 'HANDOVER_BLOCKED')
    ok = client.post(f'/api/handover/{anchor}/receipts/LL-20261123-01/signoff',
                     json={'scope': 'TOTAL', 'decision': '确认', 'note': '总额相符，各单待补录'})
    assert ok.status_code == 200 and ok.json()['version'] == 1


def test_order_signoff_blocked_without_evidence(client, anchor, registered):
    response = client.post(f'/api/handover/{anchor}/receipts/LL-20261123-01/signoff',
                           json={'scope': 'ORDER', 'decision': '确认', 'note': '无凭据强签'})
    assert (response.status_code, response.json()['code']) == (422, 'HANDOVER_BLOCKED')


def test_evidence_rejudges_each_order_and_keeps_original_conclusion(client, anchor, registered):
    response = client.post(f'/api/handover/{anchor}/receipts/LL-20261123-01/evidence', json={})
    assert response.status_code == 200
    current = response.json()
    assert current['code'] == 'EVIDENCE_MATCH' and current['evidence_sha256']
    assert [(row['key'], row['code'], row['delta']) for row in current['rows']] == [
        ('00101', 'MATCH', '0'), ('00102', 'MATCH', '0')]
    timeline = client.get(f'/api/handover/{anchor}/receipts/LL-20261123-01/timeline').json()['judgements']
    assert [item['seq'] for item in timeline] == [2, 1]
    # 原交班结论仍可查：seq 1 停留在回单层级。
    assert timeline[-1]['code'] == 'TOTAL_MATCH' and timeline[-1]['evidence_sha256'] is None


def test_total_match_can_hide_one_over_one_under(client, anchor, registered):
    # 00103 实算 6000、00104 实算 12000，回单合计 17000；补录成一少一多、合计仍为 17000。
    payload = f'{EVIDENCE_HEADER}\n00103,7000\n00104,10000\n'
    response = client.post(f'/api/handover/{anchor}/receipts/LL-20261123-02/evidence',
                           json={'evidence': payload})
    current = response.json()
    assert current['code'] == 'EVIDENCE_DELTA' and current['delta'] == '1000'
    assert [(row['key'], row['code']) for row in current['rows']] == [
        ('00103', 'AMOUNT_DELTA'), ('00104', 'AMOUNT_DELTA')]
    blocked = client.post(f'/api/handover/{anchor}/receipts/LL-20261123-02/signoff',
                          json={'scope': 'ORDER', 'decision': '确认', 'note': '差异未平'})
    assert (blocked.status_code, blocked.json()['code']) == (422, 'HANDOVER_BLOCKED')


def test_evidence_must_match_receipt_scope_and_total(client, anchor, registered):
    missing = f'{EVIDENCE_HEADER}\n00101,0\n'
    response = client.post(f'/api/handover/{anchor}/receipts/LL-20261123-01/evidence',
                           json={'evidence': missing})
    assert (response.status_code, response.json()['code']) == (422, 'EVIDENCE_SCOPE')
    wrong_total = f'{EVIDENCE_HEADER}\n00101,1\n00102,11998\n'
    response = client.post(f'/api/handover/{anchor}/receipts/LL-20261123-01/evidence',
                           json={'evidence': wrong_total})
    assert (response.status_code, response.json()['code']) == (422, 'EVIDENCE_TOTAL')
    # 被拒补录不产生判定记录。
    timeline = client.get(f'/api/handover/{anchor}/receipts/LL-20261123-01/timeline').json()
    assert [item['seq'] for item in timeline['judgements']] == [1]


def test_retrying_same_evidence_adds_no_record(client, anchor, registered):
    first = client.post(f'/api/handover/{anchor}/receipts/LL-20261123-01/evidence', json={}).json()
    second = client.post(f'/api/handover/{anchor}/receipts/LL-20261123-01/evidence', json={}).json()
    assert first == second
    timeline = client.get(f'/api/handover/{anchor}/receipts/LL-20261123-01/timeline').json()
    assert [item['seq'] for item in timeline['judgements']] == [2, 1]


def test_distinct_valid_evidence_appends_judgement(client, anchor, registered):
    client.post(f'/api/handover/{anchor}/receipts/LL-20261123-01/evidence', json={})
    swapped = f'{EVIDENCE_HEADER}\n00101,100\n00102,11900\n'
    response = client.post(f'/api/handover/{anchor}/receipts/LL-20261123-01/evidence',
                           json={'evidence': swapped})
    assert response.json()['code'] == 'EVIDENCE_DELTA'
    timeline = client.get(f'/api/handover/{anchor}/receipts/LL-20261123-01/timeline').json()
    assert [item['seq'] for item in timeline['judgements']] == [3, 2, 1]


def test_order_signoff_after_evidence_resolves(client, anchor, registered):
    client.post(f'/api/handover/{anchor}/receipts/LL-20261123-01/evidence', json={})
    response = client.post(f'/api/handover/{anchor}/receipts/LL-20261123-01/signoff',
                           json={'scope': 'ORDER', 'decision': '确认', 'note': '逐单差异已平'})
    assert response.status_code == 200 and response.json()['version'] == 1
    history = client.get(f'/api/handover/{anchor}').json()['receipts']
    r1 = next(item for item in history if item['receipt_id'] == 'LL-20261123-01')
    assert r1['current']['code'] == 'EVIDENCE_MATCH'
    assert [sign['scope'] for sign in r1['signoffs']] == ['ORDER']


def test_unknown_run_and_receipt_are_404(client, anchor, registered):
    assert client.get('/api/handover/missing').status_code == 404
    assert client.get(f'/api/handover/{anchor}/receipts/missing/timeline').status_code == 404
    response = client.post(f'/api/handover/{anchor}/receipts/missing/evidence', json={})
    assert response.status_code == 404 and response.json()['code'] == 'RECEIPT_UNKNOWN'


def test_handover_requires_registered_run(client):
    response = client.post('/api/handover/unknown-run/receipts', json={})
    assert response.status_code == 404 and response.json()['code'] == 'RUN_UNKNOWN'


def test_total_delta_never_allows_confirm_even_after_evidence(client, anchor, registered):
    # R3 回单总额比实算多 1；即便补录凭据（与回单同合计），总额仍不平，只能退回。
    payload = f'{EVIDENCE_HEADER}\n00105,1\n00106,5000\n'
    response = client.post(f'/api/handover/{anchor}/receipts/LL-20261123-03/evidence',
                           json={'evidence': payload})
    assert response.json()['code'] == 'EVIDENCE_DELTA'
    blocked = client.post(f'/api/handover/{anchor}/receipts/LL-20261123-03/signoff',
                          json={'scope': 'TOTAL', 'decision': '确认', 'note': '强行确认'})
    assert (blocked.status_code, blocked.json()['code']) == (422, 'HANDOVER_BLOCKED')
    returned = client.post(f'/api/handover/{anchor}/receipts/LL-20261123-03/signoff',
                           json={'scope': 'TOTAL', 'decision': '退回', 'note': '总额不符，退回仓库'})
    assert returned.status_code == 200


def test_return_requires_note(client, anchor, registered):
    response = client.post(f'/api/handover/{anchor}/receipts/LL-20261123-01/signoff',
                           json={'scope': 'TOTAL', 'decision': '退回', 'note': ''})
    assert (response.status_code, response.json()['code']) == (422, 'REVIEW_NOTE')


def test_concurrent_evidence_retry_keeps_single_judgement(client, anchor, registered):
    from concurrent.futures import ThreadPoolExecutor
    from app.modules.handover.service import supplement
    payload = (Path(__file__).resolve().parents[1] / 'sample_data/evidence.csv').read_bytes()
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(
            lambda _: supplement(anchor, 'LL-20261123-01', payload), range(4)))
    assert all(item['code'] == outcomes[0]['code'] for item in outcomes)
    timeline = client.get(f'/api/handover/{anchor}/receipts/LL-20261123-01/timeline').json()
    assert [item['seq'] for item in timeline['judgements']] == [2, 1]
