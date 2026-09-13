"""Authenticated handoff of a signed VERIFIED production receipt to Hunter."""
from __future__ import annotations
import hashlib, hmac, json, os, time, urllib.error, urllib.request, uuid
from typing import Any, Mapping

REQUEST_VERSION="munshi-application-execution-request-v1"
RESPONSE_VERSION="munshi-application-execution-response-v1"
PURPOSE="PRODUCTION_RECEIPT_INGEST"
class ReceiptHandoffError(RuntimeError): pass

def _canonical(v:Mapping[str,Any])->bytes:
    return json.dumps(dict(v),sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()

def _secret()->bytes:
    v=str(os.getenv("MUNSHI_APPLY_HANDOFF_HMAC_SECRET") or "")
    if len(v)<16: raise ReceiptHandoffError("Apply handoff HMAC secret is not configured")
    return v.encode()

def _base_url()->str:
    v=str(os.getenv("MUNSHI_HUNTER_BASE_URL") or "").strip().rstrip("/")
    if not v: raise ReceiptHandoffError("MUNSHI_HUNTER_BASE_URL is not configured")
    if not (v.startswith("https://") or v.startswith("http://127.0.0.1") or v.startswith("http://localhost")): raise ReceiptHandoffError("Hunter receipt endpoint must use HTTPS except on localhost")
    return v

def ingest_verified_receipt(receipt:Mapping[str,Any],*,timeout:float=10.0)->dict[str,Any]:
    r=dict(receipt); event_id=f"receipt-ingest-{uuid.uuid4()}"; plan_digest=str(r.get("plan_digest") or "")
    req={"version":REQUEST_VERSION,"request_id":event_id,"purpose":PURPOSE,"tenant_id":r.get("tenant_id"),"user_id":r.get("user_id"),"application_id":r.get("application_id"),"plan_id":r.get("plan_id"),"plan_digest":plan_digest,"payload":{"receipt":r}}
    body=_canonical(req); digest=hashlib.sha256(body).hexdigest(); ts=str(int(time.time())); sig=hmac.new(_secret(),f"{event_id}.{ts}.{digest}".encode(),hashlib.sha256).hexdigest()
    request=urllib.request.Request(_base_url()+"/api/application-execution/plan-current",data=body,headers={"Content-Type":"application/json","X-Munshi-Event-Id":event_id,"X-Munshi-Timestamp":ts,"X-Munshi-Content-SHA256":digest,"X-Munshi-Signature":f"sha256={sig}"},method="POST")
    try:
        with urllib.request.urlopen(request,timeout=timeout) as response:  # noqa: S310
            raw=response.read(); headers=dict(response.headers.items())
    except (urllib.error.URLError,TimeoutError,OSError) as e: raise ReceiptHandoffError("Unable to hand verified production receipt to Hunter") from e
    response_digest=hashlib.sha256(raw).hexdigest()
    def hv(name:str)->str:
        for k,v in headers.items():
            if str(k).casefold()==name.casefold(): return str(v)
        return ""
    expected=hmac.new(_secret(),f"{event_id}.{PURPOSE}.{response_digest}.{plan_digest}".encode(),hashlib.sha256).hexdigest()
    if hv("X-Munshi-Response-Event-Id")!=event_id or hv("X-Munshi-Response-Purpose")!=PURPOSE or hv("X-Munshi-Response-SHA256")!=response_digest or hv("X-Munshi-Plan-Digest")!=plan_digest or not hmac.compare_digest(hv("X-Munshi-Response-Signature"),f"sha256={expected}"):
        raise ReceiptHandoffError("Hunter production-receipt response signature/binding is invalid")
    try: value=json.loads(raw)
    except json.JSONDecodeError as e: raise ReceiptHandoffError("Hunter production-receipt response is invalid JSON") from e
    result=value.get("result") if isinstance(value,dict) else None
    if not isinstance(result,dict) or result.get("status")!="INGESTED" or result.get("verification_status")!="VERIFIED" or result.get("receipt_id")!=r.get("receipt_id"):
        raise ReceiptHandoffError("Hunter did not acknowledge the exact verified production receipt")
    return dict(result)
