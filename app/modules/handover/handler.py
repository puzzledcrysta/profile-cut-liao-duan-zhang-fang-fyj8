from fastapi import APIRouter
from app.inputs import Receipts, Evidence, HandoverSign
from . import service

router = APIRouter()

@router.post('/api/handover/{run_id}/receipts')
def register(run_id: str, payload: Receipts):
    return service.register(run_id, payload.raw())

@router.post('/api/handover/{run_id}/receipts/{receipt_id}/evidence')
def supplement(run_id: str, receipt_id: str, payload: Evidence):
    return service.supplement(run_id, receipt_id, payload.raw())

@router.get('/api/handover/{run_id}')
def history(run_id: str):
    return {'receipts': service.history(run_id)}

@router.get('/api/handover/{run_id}/receipts/{receipt_id}/timeline')
def timeline(run_id: str, receipt_id: str):
    return {'judgements': service.timeline(run_id, receipt_id)}

@router.post('/api/handover/{run_id}/receipts/{receipt_id}/signoff')
def signoff(run_id: str, receipt_id: str, form: HandoverSign):
    return service.signoff(run_id, receipt_id, form.scope, form.decision, form.note)
