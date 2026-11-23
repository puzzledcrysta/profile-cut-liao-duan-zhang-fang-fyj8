from decimal import Decimal
from hashlib import sha256


def _actual_map(accepted):
    return {row['key']: Decimal(row['amount']) for row in accepted}


def receipt_judgement(receipt, accepted):
    """回单层级判定：只凭合单总额能证明什么，就给班组签什么。"""
    actual = _actual_map(accepted)
    actual_sum = sum((actual.get(key, Decimal(0)) for key in receipt['keys']), Decimal(0))
    delta = actual_sum - receipt['amount']
    pending = [key for key in receipt['keys'] if key in actual]
    missing_result = [key for key in receipt['keys'] if key not in actual]
    return {
        'receipt_id': receipt['receipt_id'],
        'keys': list(receipt['keys']),
        'actual_total': str(actual_sum),
        'book_total': str(receipt['amount']),
        'delta': str(delta),
        'code': 'TOTAL_DELTA' if delta else 'TOTAL_MATCH',
        'pending': pending,
        'missing_result': missing_result,
        'evidence_sha256': None,
        'rows': [{'key': key,
                  'amount': str(actual[key]) if key in actual else None,
                  'reference': None, 'delta': None,
                  'code': 'PENDING_EVIDENCE' if key in actual else 'MISSING_RESULT'}
                 for key in receipt['keys']],
    }


def evidence_judgement(receipt, entries, accepted):
    """逐单凭据层级判定：凭据必须与原回单范围和总额相符，再重判各单差异。"""
    actual = _actual_map(accepted)
    by_key = {item['key']: item['amount'] for item in entries}
    receipt_keys = set(receipt['keys'])
    evidence_keys = set(by_key)
    missing = sorted(receipt_keys - evidence_keys)
    extra = sorted(evidence_keys - receipt_keys)
    if missing or extra:
        raise ValueError('EVIDENCE_SCOPE')
    evidence_sum = sum(by_key.values(), Decimal(0))
    if evidence_sum != receipt['amount']:
        raise ValueError('EVIDENCE_TOTAL')
    rows, matched = [], 0
    for key in receipt['keys']:
        value = actual.get(key)
        book = by_key[key]
        delta = (value or Decimal(0)) - book
        code = ('MISSING_RESULT' if value is None else
                'AMOUNT_DELTA' if delta else 'MATCH')
        matched += code == 'MATCH'
        rows.append({'key': key,
                     'amount': str(value) if value is not None else None,
                     'reference': str(book), 'delta': str(delta), 'code': code})
    return {
        'receipt_id': receipt['receipt_id'],
        'keys': list(receipt['keys']),
        'actual_total': str(sum((actual.get(key, Decimal(0)) for key in receipt['keys']), Decimal(0))),
        'book_total': str(receipt['amount']),
        'delta': str(sum((actual.get(key, Decimal(0)) for key in receipt['keys']), Decimal(0)) - receipt['amount']),
        'code': 'EVIDENCE_MATCH' if matched == len(rows) else 'EVIDENCE_DELTA',
        'pending': [],
        'missing_result': [key for key in receipt['keys'] if key not in actual],
        'rows': rows,
    }


def fingerprint(receipt_id, payload):
    return sha256(f'{receipt_id}:'.encode() + payload).hexdigest()
