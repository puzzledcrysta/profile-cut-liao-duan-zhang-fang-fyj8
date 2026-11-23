from app.errors import DataError
from app.settings import KEY, UNIT
from app.modules.domain.values import number
from app.modules.intake.reader import decode, records


def canonical(receipt_id, keys, amount):
    return f'{receipt_id}|{";".join(keys)}|{amount}'

RECEIPT_HEADER = ['领料回单', '合单锯切计划', f'合单记录值({UNIT})']
EVIDENCE_HEADER = [KEY, f'补录记录值({UNIT})']


def _table(payload, expected_header):
    text, _ = decode(payload)
    rows = iter(records(text))
    _, header = next(rows, (0, []))
    if header != expected_header:
        raise DataError('HEADER', '表头或计量单位不符')
    return rows


def parse_receipts(payload):
    """仓库把多张锯切计划并开的领料回单，一行一张回单。"""
    rows = _table(payload, RECEIPT_HEADER)
    receipts, seen = [], set()
    for line, row in rows:
        if not row or not any(value.strip() for value in row):
            continue
        if len(row) != 3 or not all(cell.strip() for cell in row):
            raise DataError('WIDTH', f'领料回单第 {line} 行列数或字段不完整')
        receipt_id, key_text, amount_text = (cell.strip() for cell in row)
        if receipt_id in seen:
            raise DataError('RECEIPT_CONFLICT', f'领料回单 {receipt_id} 重复登记')
        seen.add(receipt_id)
        keys = [key.strip() for key in key_text.split(';') if key.strip()]
        if not keys:
            raise DataError('WIDTH', f'领料回单 {receipt_id} 没有合单锯切计划')
        if len(keys) != len(set(keys)):
            raise DataError('WIDTH', f'领料回单 {receipt_id} 合单锯切计划重复')
        amount = number(amount_text)
        receipts.append({'line': line, 'receipt_id': receipt_id, 'keys': keys,
                         'amount': amount, 'canonical': canonical(receipt_id, keys, amount)})
    if not receipts:
        raise DataError('HEADER_ONLY', '领料回单只有表头')
    return receipts


def parse_evidence(payload):
    """仓库补齐的逐单凭据，每个锯切计划一行。"""
    rows = _table(payload, EVIDENCE_HEADER)
    entries, seen = [], set()
    for line, row in rows:
        if not row or not any(value.strip() for value in row):
            continue
        if len(row) != 2 or not all(cell.strip() for cell in row):
            raise DataError('WIDTH', f'逐单凭据第 {line} 行列数或字段不完整')
        key, amount_text = (cell.strip() for cell in row)
        if key in seen:
            raise DataError('EVIDENCE_CONFLICT', f'逐单凭据第 {line} 行重复业务键 {key}')
        seen.add(key)
        entries.append({'line': line, 'key': key, 'amount': number(amount_text)})
    if not entries:
        raise DataError('HEADER_ONLY', '逐单凭据只有表头')
    return entries
