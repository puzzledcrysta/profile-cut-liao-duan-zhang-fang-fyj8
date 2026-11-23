import json
from datetime import datetime, timezone
from app.errors import DataError
from app.store import connection
from app.modules.runs.repository import lookup
from .parser import parse_receipts, parse_evidence
from .adjudication import receipt_judgement, evidence_judgement, fingerprint


def _now():
    return datetime.now(timezone.utc).isoformat()


def _receipt_row(db, run_id, receipt_id):
    row = db.execute('SELECT * FROM handover_receipts WHERE run_id=? AND receipt_id=?',
                     (run_id, receipt_id)).fetchone()
    if row is None:
        raise DataError('RECEIPT_UNKNOWN', '没有此领料回单', 404)
    return row


def _store_judgement(db, run_id, receipt_id, result, evidence_sha256):
    seq = db.execute('SELECT COALESCE(MAX(seq),0) FROM handover_judgements WHERE run_id=? AND receipt_id=?',
                     (run_id, receipt_id)).fetchone()[0] + 1
    changed = _now()
    db.execute('INSERT INTO handover_judgements VALUES (?,?,?,?,?,?)',
               (run_id, receipt_id, seq, evidence_sha256,
                json.dumps(result, ensure_ascii=False), changed))
    return {'seq': seq, 'evidence_sha256': evidence_sha256, 'changed': changed, **result}


def _current_judgement(db, run_id, receipt_id):
    row = db.execute('SELECT result, evidence_sha256, changed, seq FROM handover_judgements '
                     'WHERE run_id=? AND receipt_id=? ORDER BY seq DESC LIMIT 1',
                     (run_id, receipt_id)).fetchone()
    return dict(row) if row else None


def register(run_id, payload):
    """登记合单回单并给出回单层级判定；同一回单同内容重试不新增任何记录。"""
    receipts = parse_receipts(payload)
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        run = lookup(db, run_id)
        accepted = json.loads(run['result'])['accepted']
        created = _now()
        judgements = []
        for receipt in receipts:
            existing = db.execute('SELECT canonical FROM handover_receipts WHERE run_id=? AND receipt_id=?',
                                  (run_id, receipt['receipt_id'])).fetchone()
            if existing is not None:
                if existing['canonical'] != receipt['canonical']:
                    raise DataError('RECEIPT_CONFLICT',
                                    f'领料回单 {receipt["receipt_id"]} 已按不同内容登记')
                current = _current_judgement(db, run_id, receipt['receipt_id'])
                judgements.append({**json.loads(current['result']), 'seq': current['seq'],
                                   'evidence_sha256': current['evidence_sha256'],
                                   'changed': current['changed']})
                continue
            result = receipt_judgement(receipt, accepted)
            db.execute('INSERT INTO handover_receipts VALUES (?,?,?,?,?,?,?)',
                       (run_id, receipt['receipt_id'], payload, receipt['canonical'],
                        json.dumps(receipt['keys'], ensure_ascii=False),
                        str(receipt['amount']), created))
            judgements.append(_store_judgement(db, run_id, receipt['receipt_id'], result, None))
        return {'run_id': run_id, 'registered': len(receipts), 'judgements': judgements}


def supplement(run_id, receipt_id, payload):
    """补齐与原回单相符的逐单凭据后重判各单差异；同一份补录重试不新增确认记录。"""
    entries = parse_evidence(payload)
    digest = fingerprint(receipt_id, payload)
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        run = lookup(db, run_id)
        receipt_row = _receipt_row(db, run_id, receipt_id)
        accepted = json.loads(run['result'])['accepted']
        prior = db.execute('SELECT 1 FROM handover_evidence WHERE run_id=? AND receipt_id=? AND evidence_sha256=?',
                           (run_id, receipt_id, digest)).fetchone()
        if prior is not None:
            current = _current_judgement(db, run_id, receipt_id)
            return {**json.loads(current['result']), 'seq': current['seq'],
                    'evidence_sha256': current['evidence_sha256'], 'changed': current['changed']}
        receipt = {'receipt_id': receipt_id,
                   'keys': json.loads(receipt_row['keys']),
                   'amount': json.loads(receipt_row['amount'])}
        try:
            result = evidence_judgement(receipt, entries, accepted)
        except ValueError as error:
            code = error.args[0]
            if code == 'EVIDENCE_SCOPE':
                raise DataError('EVIDENCE_SCOPE', '逐单凭据的业务键范围须与原回单完全一致')
            raise DataError('EVIDENCE_TOTAL', '逐单凭据合计与原回单金额不符')
        result['evidence_sha256'] = digest
        recorded = _now()
        db.execute('INSERT INTO handover_evidence VALUES (?,?,?,?,?)',
                   (run_id, receipt_id, digest, payload, recorded))
        return _store_judgement(db, run_id, receipt_id, result, digest)


def timeline(run_id, receipt_id):
    with connection() as db:
        lookup(db, run_id)
        _receipt_row(db, run_id, receipt_id)
        rows = db.execute('SELECT seq, evidence_sha256, result, changed FROM handover_judgements '
                          'WHERE run_id=? AND receipt_id=? ORDER BY seq DESC',
                          (run_id, receipt_id)).fetchall()
        return [{'seq': row['seq'], 'evidence_sha256': row['evidence_sha256'],
                 'changed': row['changed'], **json.loads(row['result'])} for row in rows]


def history(run_id):
    with connection() as db:
        lookup(db, run_id)
        rows = db.execute('SELECT receipt_id, keys, amount, registered FROM handover_receipts '
                          'WHERE run_id=? ORDER BY receipt_id', (run_id,)).fetchall()
        out = []
        for row in rows:
            current = _current_judgement(db, run_id, row['receipt_id'])
            signoffs = db.execute('SELECT version, scope, decision, note, changed FROM handover_signoffs '
                                  'WHERE run_id=? AND receipt_id=? ORDER BY version DESC',
                                  (run_id, row['receipt_id'])).fetchall()
            out.append({'receipt_id': row['receipt_id'], 'keys': json.loads(row['keys']),
                        'amount': row['amount'], 'registered': row['registered'],
                        'current': current and {**json.loads(current['result']),
                                                'seq': current['seq'],
                                                'evidence_sha256': current['evidence_sha256'],
                                                'changed': current['changed']},
                        'signoffs': [dict(item) for item in signoffs]})
        return out


def signoff(run_id, receipt_id, scope, decision, note):
    note = note.strip()
    if decision not in {'确认', '退回'}:
        raise DataError('REVIEW_DECISION', '复核结论无效')
    if scope not in {'TOTAL', 'ORDER'}:
        raise DataError('HANDOVER_SCOPE', '签认范围无效')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        lookup(db, run_id)
        _receipt_row(db, run_id, receipt_id)
        current = _current_judgement(db, run_id, receipt_id)
        if current is None:
            raise DataError('RECEIPT_UNKNOWN', '回单尚未完成判定', 409)
        result = json.loads(current['result'])
        total_matches = result['code'] in {'TOTAL_MATCH', 'EVIDENCE_MATCH', 'EVIDENCE_DELTA'} \
            and result['delta'] == '0'
        if scope == 'TOTAL' and decision == '确认' and not total_matches:
            raise DataError('HANDOVER_BLOCKED', '合单总额不符，不能签认有凭据的结论')
        if scope == 'ORDER':
            if result['code'] not in {'EVIDENCE_MATCH', 'EVIDENCE_DELTA'}:
                raise DataError('HANDOVER_BLOCKED', '逐单凭据未补齐，班组只能签认回单总额结论')
            if result['code'] == 'EVIDENCE_DELTA':
                raise DataError('HANDOVER_BLOCKED', '仍有锯切计划差异未消除，不能签认')
        if decision == '确认' and result['code'] == 'TOTAL_MATCH' and not note:
            raise DataError('REVIEW_NOTE', '总额相符但各单待凭据，须注明待补录范围')
        if decision == '退回' and not note:
            raise DataError('REVIEW_NOTE', '退回时须填写意见')
        version = db.execute('SELECT COALESCE(MAX(version),0) FROM handover_signoffs '
                             'WHERE run_id=? AND receipt_id=?', (run_id, receipt_id)).fetchone()[0] + 1
        changed = _now()
        db.execute('INSERT INTO handover_signoffs VALUES (?,?,?,?,?,?,?)',
                   (run_id, receipt_id, version, scope, decision, note, changed))
        return {'receipt_id': receipt_id, 'version': version, 'scope': scope,
                'decision': decision, 'note': note, 'changed': changed,
                'judgement_seq': current['seq']}
