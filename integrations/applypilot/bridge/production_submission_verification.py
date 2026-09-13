"""Strict production verification and signed receipt creation.

Browser success text, a button click, a generic 2xx, or an arbitrary JSON id are
never sufficient.  A receipt is created only when an independent provider
observation confirms the exact reviewed target and provider application id.
"""
from __future__ import annotations
import hashlib, hmac, json, os
from datetime import UTC, datetime
from typing import Any, Mapping
from uuid import uuid4

RECEIPT_VERSION="munshi-production-submission-receipt-v1"
class ProductionVerificationError(RuntimeError): pass

def _canonical(v:Mapping[str,Any])->bytes:
    return json.dumps(dict(v),sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()

def _secret()->bytes:
    v=str(os.getenv("MUNSHI_PRODUCTION_RECEIPT_HMAC_SECRET") or "")
    if len(v)<32: raise ProductionVerificationError("Production receipt HMAC secret is not configured")
    return v.encode()

def _digest(v:Any,label:str)->str:
    s=str(v or "").strip().lower()
    if len(s)!=64 or any(c not in "0123456789abcdef" for c in s): raise ProductionVerificationError(f"{label} is not a SHA-256 digest")
    return s

def _text(v:Any,label:str)->str:
    s=" ".join(str(v or "").split())
    if not s: raise ProductionVerificationError(f"{label} is required")
    return s

def build_verified_receipt(*,authorization:Mapping[str,Any],claim:Mapping[str,Any],execution:Mapping[str,Any],provider_observation:Mapping[str,Any])->dict[str,Any]:
    auth=dict(authorization); claimed=dict(claim); result=dict(execution); proof=dict(provider_observation)
    if auth.get("synthetic") is not False or auth.get("submission_authority") is not True: raise ProductionVerificationError("Production authority flags are invalid")
    if claimed.get("status")!="CLAIMED" or claimed.get("submission_authority") is not True: raise ProductionVerificationError("A one-time canonical authority claim is required")
    if claimed.get("authorization_id")!=auth.get("authorization_id") or claimed.get("authority_digest")!=auth.get("authority_digest"): raise ProductionVerificationError("Authority claim does not match authorization")
    if result.get("status")!="COMPLETED" or result.get("claimed_submission") is not True: raise ProductionVerificationError("Browser execution did not claim a completed submission")
    if str(result.get("plan_id") or "")!=str(auth.get("plan_id") or "") or str(result.get("plan_digest") or "")!=str(auth.get("plan_digest") or ""): raise ProductionVerificationError("Execution plan binding does not match authorization")
    if str(result.get("provider") or "").upper()!=str(auth.get("provider") or "").upper(): raise ProductionVerificationError("Execution provider does not match authorization")
    observation=result.get("submission_observation")
    if not isinstance(observation,Mapping): raise ProductionVerificationError("Browser submission observation is missing")
    if str(observation.get("method") or "").upper()!="POST": raise ProductionVerificationError("Only an exact observed POST can support production verification")
    if str(observation.get("target") or "")!=str(auth.get("target_url") or ""): raise ProductionVerificationError("Observed submission target changed after review")
    browser_id=_text(result.get("provider_application_id") or observation.get("provider_application_id"),"Provider application id")
    if proof.get("lookup_confirmed") is not True: raise ProductionVerificationError("Independent provider lookup did not confirm submission")
    if _text(proof.get("provider_application_id"),"Verified provider application id")!=browser_id: raise ProductionVerificationError("Provider lookup application id conflicts with browser evidence")
    if str(proof.get("provider") or "").upper()!=str(auth.get("provider") or "").upper(): raise ProductionVerificationError("Provider lookup provider conflicts with authorization")
    if str(proof.get("target_url") or "")!=str(auth.get("target_url") or ""): raise ProductionVerificationError("Provider lookup target conflicts with authorization")
    evidence_id=_text(proof.get("external_observation_id"),"Independent observation id")
    evidence_material={"provider":str(proof["provider"]).upper(),"provider_application_id":browser_id,"target_url":str(proof["target_url"]),"external_observation_id":evidence_id,"lookup_confirmed":True,"observed_status":_text(proof.get("observed_status"),"Observed provider status")}
    evidence_digest=hashlib.sha256(_canonical(evidence_material)).hexdigest()
    now=datetime.now(UTC).isoformat().replace("+00:00","Z")
    material={
      "version":RECEIPT_VERSION,"receipt_id":f"production-receipt-{uuid4()}",
      "tenant_id":_text(auth.get("tenant_id"),"Tenant id"),"user_id":_text(auth.get("user_id"),"User id"),"application_id":_text(auth.get("application_id"),"Application id"),
      "authorization_id":_text(auth.get("authorization_id"),"Authorization id"),"authority_digest":_digest(auth.get("authority_digest"),"Authority digest"),"claim_digest":_digest(claimed.get("claim_digest"),"Claim digest"),
      "plan_id":_text(auth.get("plan_id"),"Plan id"),"plan_digest":_digest(auth.get("plan_digest"),"Plan digest"),"session_id":_text(auth.get("session_id"),"Session id"),"review_id":_text(auth.get("review_id"),"Review id"),"approval_id":_text(auth.get("approval_id"),"Approval id"),
      "provider":str(auth.get("provider") or "").upper(),"provider_application_id":browser_id,"target_url":_text(auth.get("target_url"),"Target URL"),
      "verification_method":"INDEPENDENT_PROVIDER_LOOKUP","verification_evidence_digest":evidence_digest,"verified_at":now,
      "synthetic":False,"verification_status":"VERIFIED"
    }
    receipt_digest=hashlib.sha256(_canonical(material)).hexdigest(); signature=hmac.new(_secret(),receipt_digest.encode(),hashlib.sha256).hexdigest()
    return {**material,"receipt_digest":receipt_digest,"signature":f"sha256={signature}"}
