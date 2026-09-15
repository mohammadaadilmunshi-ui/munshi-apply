"""JIT claim client for Hunter-issued canonical submit authorization.

Supports two control-request purposes over the existing authenticated
Apply->Hunter bridge (`POST /api/application-execution/plan-current`):

* ``SUBMIT_AUTHORIZATION_READ`` — fetch the still-ISSUED authority envelope
  for exact bindings. The returned envelope is the same ``munshi-submit-
  authorization-v1`` shape that ``SUBMIT_AUTHORIZATION_CLAIM`` consumes; the
  purpose is purpose-sniffed via the existing ``X-Munshi-Response-Purpose``
  response header and the response payload's ``purpose`` field.
* ``SUBMIT_AUTHORIZATION_CLAIM`` — atomically convert the ISSUED authority to
  a one-time CLAIMED envelope (existing behaviour, preserved verbatim).

The READ path is read-only and never grants authority; the CLAIM path keeps
every existing guard (synthetic=False, submission_authority=True, all
required identifier fields non-blank, the HTTPS-or-localhost base-URL rule,
and the exact one-time claim verification in ``_verify_response``).
"""
from __future__ import annotations
import hashlib, hmac, json, os, time, urllib.error, urllib.request, uuid
from typing import Any, Mapping

REQUEST_VERSION="munshi-application-execution-request-v1"
RESPONSE_VERSION="munshi-application-execution-response-v1"
PURPOSE_CLAIM="SUBMIT_AUTHORIZATION_CLAIM"
PURPOSE_READ="SUBMIT_AUTHORIZATION_READ"

class SubmitAuthorizationError(RuntimeError):
    pass

def _canonical(v:Mapping[str,Any])->bytes:
    return json.dumps(dict(v),sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()

def _secret()->bytes:
    v=str(os.getenv("MUNSHI_APPLY_HANDOFF_HMAC_SECRET") or "")
    if len(v)<16: raise SubmitAuthorizationError("Apply handoff HMAC secret is not configured")
    return v.encode()

def _base_url()->str:
    v=str(os.getenv("MUNSHI_HUNTER_BASE_URL") or "").strip().rstrip("/")
    if not v: raise SubmitAuthorizationError("MUNSHI_HUNTER_BASE_URL is not configured")
    if not (v.startswith("https://") or v.startswith("http://127.0.0.1") or v.startswith("http://localhost")):
        raise SubmitAuthorizationError("Hunter control endpoint must use HTTPS except on localhost")
    return v

def _signed_headers(body:bytes,event_id:str)->dict[str,str]:
    digest=hashlib.sha256(body).hexdigest(); ts=str(int(time.time()))
    sig=hmac.new(_secret(),f"{event_id}.{ts}.{digest}".encode(),hashlib.sha256).hexdigest()
    return {"Content-Type":"application/json","X-Munshi-Event-Id":event_id,"X-Munshi-Timestamp":ts,"X-Munshi-Content-SHA256":digest,"X-Munshi-Signature":f"sha256={sig}"}

def _verify_response(body:bytes,headers:Mapping[str,str],*,event_id:str,plan_digest:str,expected_purpose:str)->dict[str,Any]:
    digest=hashlib.sha256(body).hexdigest()
    def hv(name:str)->str:
        for k,v in headers.items():
            if str(k).casefold()==name.casefold(): return str(v)
        return ""
    if hv("X-Munshi-Response-Event-Id")!=event_id or hv("X-Munshi-Response-Purpose")!=expected_purpose or hv("X-Munshi-Response-SHA256")!=digest or hv("X-Munshi-Plan-Digest")!=plan_digest:
        raise SubmitAuthorizationError("Hunter submit-authorization response binding is invalid")
    expected=hmac.new(_secret(),f"{event_id}.{expected_purpose}.{digest}.{plan_digest}".encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(hv("X-Munshi-Response-Signature"),f"sha256={expected}"):
        raise SubmitAuthorizationError("Hunter submit-authorization response signature is invalid")
    try: value=json.loads(body)
    except json.JSONDecodeError as e: raise SubmitAuthorizationError("Hunter submit-authorization response is invalid JSON") from e
    if not isinstance(value,dict) or value.get("version")!=RESPONSE_VERSION or value.get("request_id")!=event_id or value.get("purpose")!=expected_purpose or value.get("plan_digest")!=plan_digest:
        raise SubmitAuthorizationError("Hunter submit-authorization response payload is invalid")
    return value

def _required_auth_fields(*,with_claimant:bool)->tuple[str,...]:
    base=("authorization_id","tenant_id","user_id","application_id","plan_id","session_id","review_id","approval_id","plan_digest","authority_digest","signature")
    if with_claimant:
        return base
    return base

def read_submit_authorization(envelope:Mapping[str,Any],*,timeout:float=10.0)->dict[str,Any]:
    """Fetch the still-ISSUED canonical authority envelope.

    The envelope argument supplies the exact plan/user/application context that
    Hunter uses to look up the still-ISSUED authority; the returned payload is
    the same ``munshi-submit-authorization-v1`` shape consumed by the inbox
    (``synthetic=False``, ``submission_authority=True``, full digest set).
    """
    auth=dict(envelope)
    for key in _required_auth_fields(with_claimant=False):
        if not str(auth.get(key) or "").strip():
            raise SubmitAuthorizationError("Submit authorization envelope is incomplete")
    if auth.get("synthetic") is not False or auth.get("submission_authority") is not True:
        raise SubmitAuthorizationError("Submit authorization flags are invalid")
    event_id=f"submit-auth-read-{uuid.uuid4()}"
    request={
        "version":REQUEST_VERSION,
        "request_id":event_id,
        "purpose":PURPOSE_READ,
        "tenant_id":auth["tenant_id"],
        "user_id":auth["user_id"],
        "application_id":auth["application_id"],
        "plan_id":auth["plan_id"],
        "plan_digest":auth["plan_digest"],
        "payload":{
            "tenant_id":auth["tenant_id"],
            "user_id":auth["user_id"],
            "application_id":auth["application_id"],
            "plan_id":auth["plan_id"],
            "plan_digest":auth["plan_digest"],
            "session_id":auth["session_id"],
        },
    }
    body=_canonical(request)
    req=urllib.request.Request(_base_url()+"/api/application-execution/plan-current",data=body,headers=_signed_headers(body,event_id),method="POST")
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:  # noqa: S310
            raw=response.read(); headers=dict(response.headers.items())
    except (urllib.error.URLError,TimeoutError,OSError) as e:
        raise SubmitAuthorizationError("Unable to read canonical submit authorization") from e
    value=_verify_response(raw,headers,event_id=event_id,plan_digest=str(auth["plan_digest"]),expected_purpose=PURPOSE_READ)
    result=value.get("result")
    if not isinstance(result,dict) or result.get("status")!="ISSUED" or result.get("submission_authority") is not True or result.get("authorization_id")!=auth["authorization_id"] or result.get("authority_digest")!=auth["authority_digest"]:
        raise SubmitAuthorizationError("Hunter did not return the exact ISSUED submit authorization")
    return dict(result)

def claim_submit_authorization(envelope:Mapping[str,Any],*,claimant_id:str,timeout:float=10.0)->dict[str,Any]:
    auth=dict(envelope)
    for key in _required_auth_fields(with_claimant=True):
        if not str(auth.get(key) or "").strip(): raise SubmitAuthorizationError("Submit authorization envelope is incomplete")
    if auth.get("synthetic") is not False or auth.get("submission_authority") is not True: raise SubmitAuthorizationError("Submit authorization flags are invalid")
    event_id=f"submit-auth-claim-{uuid.uuid4()}"
    request={"version":REQUEST_VERSION,"request_id":event_id,"purpose":PURPOSE_CLAIM,"tenant_id":auth["tenant_id"],"user_id":auth["user_id"],"application_id":auth["application_id"],"plan_id":auth["plan_id"],"plan_digest":auth["plan_digest"],"payload":{"authorization":auth,"claimant_id":str(claimant_id)}}
    body=_canonical(request)
    req=urllib.request.Request(_base_url()+"/api/application-execution/plan-current",data=body,headers=_signed_headers(body,event_id),method="POST")
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:  # noqa: S310
            raw=response.read(); headers=dict(response.headers.items())
    except (urllib.error.URLError,TimeoutError,OSError) as e:
        raise SubmitAuthorizationError("Unable to claim canonical submit authorization") from e
    value=_verify_response(raw,headers,event_id=event_id,plan_digest=str(auth["plan_digest"]),expected_purpose=PURPOSE_CLAIM)
    result=value.get("result")
    if not isinstance(result,dict) or result.get("status")!="CLAIMED" or result.get("submission_authority") is not True or result.get("authorization_id")!=auth["authorization_id"] or result.get("authority_digest")!=auth["authority_digest"] or not str(result.get("claim_digest") or ""):
        raise SubmitAuthorizationError("Hunter did not grant an exact one-time submit claim")
    return dict(result)