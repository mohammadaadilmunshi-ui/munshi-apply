#!/usr/bin/env python3
"""MUNSHI apply-only autonomous browser worker.

Production final submission is a two-phase operation: prepare to the final
boundary without authority, atomically claim the exact Hunter-issued canonical
SubmitAuthorization, then run a narrowly scoped final-submit phase in the same
browser session.  Request/local flags are intent/configuration only.
"""
from __future__ import annotations
import argparse, hashlib, json, os, platform, re, shutil, signal, subprocess, tempfile, time, uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
try:
    from .submit_authorization import claim_submit_authorization, SubmitAuthorizationError
except ImportError:  # direct script execution
    from submit_authorization import claim_submit_authorization, SubmitAuthorizationError

RESULT_PREFIX="MUNSHI_RESULT_JSON:"
DEFAULT_CDP_PORT=9322
ALLOWED_AGENT_STATUSES={"COMPLETED","NEEDS_INPUT","BLOCKED","FAILED_SAFELY"}
ALLOWED_NEEDS_INPUT={"ANSWER_REQUIRED","SENSITIVE_ANSWER_REQUIRED","CAPTCHA","MFA","OTP","IDENTITY_VERIFICATION","AUTHENTICATION","UNSUPPORTED_CONTROL","POLICY_BLOCK"}

class WorkerError(RuntimeError): pass

@dataclass(frozen=True)
class WorkerSettings:
    model:str="sonnet"; headless:bool=False; max_turns:int=40; max_cost_usd:float=1.0; allow_final_submit:bool=False; auth_mode:str="subscription"
@dataclass
class BrowserProcess:
    process:subprocess.Popen[Any]; profile_dir:Path; port:int

def _utc_now()->str: return datetime.now(UTC).isoformat().replace("+00:00","Z")
def _load_json(path:Path)->dict[str,Any]:
    try: value=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as e: raise WorkerError(f"Unable to read JSON: {path}") from e
    if not isinstance(value,dict): raise WorkerError(f"Expected JSON object: {path}")
    return value

def _runtime_root()->Path:
    override=os.getenv("MUNSHI_APPLY_RUNTIME_ROOT")
    if override: return Path(override).expanduser().resolve()
    if platform.system()=="Darwin": return Path.home()/"Library"/"Application Support"/"MUNSHI Apply"
    if platform.system()=="Windows": return Path(os.getenv("LOCALAPPDATA",Path.home()))/"MUNSHI Apply"
    return Path(os.getenv("XDG_STATE_HOME",Path.home()/".local"/"state"))/"munshi-apply"

def _load_settings()->WorkerSettings:
    path=_runtime_root()/"settings"/"autonomous-apply.json"
    if not path.exists(): return WorkerSettings()
    p=_load_json(path)
    return WorkerSettings(model=str(p.get("model","sonnet")).strip() or "sonnet",headless=bool(p.get("headless",False)),max_turns=max(1,min(200,int(p.get("maxTurns",40)))),max_cost_usd=max(0.0,float(p.get("maxCostPerApplicationUsd",1.0))),allow_final_submit=bool(p.get("allowFinalSubmit",False)),auth_mode=str(p.get("authMode","subscription")))

def _keychain_secret(account:str,service:str)->str|None:
    if platform.system()!="Darwin": return None
    r=subprocess.run(["/usr/bin/security","find-generic-password","-a",account,"-s",service,"-w"],check=False,capture_output=True,text=True)  # noqa:S603
    return r.stdout.strip() or None if r.returncode==0 else None

def _worker_environment(settings:WorkerSettings)->dict[str,str]:
    env=os.environ.copy(); env.pop("CLAUDECODE",None); env.pop("CLAUDE_CODE_ENTRYPOINT",None)
    if settings.auth_mode=="api":
        key=_keychain_secret("ANTHROPIC_API_KEY","systems.munshi.apply.autonomous.anthropic") or env.get("ANTHROPIC_API_KEY")
        if not key: raise WorkerError("Anthropic API authentication is selected but no API key is configured")
        env["ANTHROPIC_API_KEY"]=key
    return env

def _validate_sha256(path:Path,expected:str)->None:
    if not path.exists() or not path.is_file(): raise WorkerError(f"Required artifact does not exist: {path}")
    if hashlib.sha256(path.read_bytes()).hexdigest().lower()!=expected.lower(): raise WorkerError(f"Artifact digest mismatch: {path.name}")

def _validate_authorization_binding(request:dict[str,Any])->dict[str,Any]:
    auth=request.get("submit_authorization")
    if not isinstance(auth,dict): raise WorkerError("Canonical submit authorization is required for non-synthetic final submit")
    if auth.get("version")!="munshi-submit-authorization-v1" or auth.get("synthetic") is not False or auth.get("submission_authority") is not True: raise WorkerError("Canonical submit authorization flags are invalid")
    if str(auth.get("plan_id") or "")!=str(request.get("plan_id") or "") or str(auth.get("plan_digest") or "")!=str(request.get("plan_digest") or ""): raise WorkerError("Submit authorization plan binding does not match execution request")
    provider=str(request.get("job",{}).get("provider") or "").upper()
    if provider and str(auth.get("provider") or "").upper()!=provider: raise WorkerError("Submit authorization provider does not match execution request")
    artifacts=request.get("artifacts") or {}; resume=artifacts.get("resume") or {}; cover=artifacts.get("cover_letter")
    if str(auth.get("resume_sha256") or "").lower()!=str(resume.get("sha256") or "").lower(): raise WorkerError("Submit authorization resume binding does not match execution request")
    expected_cover=None if not isinstance(cover,dict) else str(cover.get("sha256") or "").lower()
    actual_cover=None if auth.get("cover_letter_sha256") is None else str(auth.get("cover_letter_sha256") or "").lower()
    if actual_cover!=expected_cover: raise WorkerError("Submit authorization cover-letter binding does not match execution request")
    return dict(auth)

def _validate_request(request:dict[str,Any])->None:
    if request.get("schema_version")!="1.0": raise WorkerError("Unsupported execution-request schema")
    job=request.get("job")
    if not isinstance(job,dict) or not isinstance(job.get("url"),str) or urlparse(job["url"]).scheme not in {"http","https"}: raise WorkerError("Job URL must be http or https")
    permissions=request.get("permissions")
    if not isinstance(permissions,dict): raise WorkerError("Execution request is missing permissions")
    if permissions.get("security_checkpoint_bypass") is not False: raise WorkerError("Security-checkpoint bypass must remain false")
    for answer in request.get("answers",[]):
        if not isinstance(answer,dict) or answer.get("approved") is not True: raise WorkerError("Only approved MUNSHI answers may reach the browser agent")
    context=request.get("execution_context")
    if not isinstance(context,dict): raise WorkerError("Execution context is missing")
    if context.get("environment")=="production" and os.getenv("MUNSHI_ALLOW_PRODUCTION_AUTONOMOUS")!="1": raise WorkerError("Production autonomous execution is not enabled on this host")
    if context.get("synthetic") is not True:
        artifacts=request.get("artifacts")
        if not isinstance(artifacts,dict) or not isinstance(artifacts.get("resume"),dict): raise WorkerError("Execution request is missing resume artifact")
        resume=artifacts["resume"]; _validate_sha256(Path(str(resume.get("path",""))),str(resume.get("sha256","")))
        cover=artifacts.get("cover_letter")
        if isinstance(cover,dict): _validate_sha256(Path(str(cover.get("path",""))),str(cover.get("sha256","")))
        if permissions.get("final_submit") is True: _validate_authorization_binding(request)

def _chrome_path()->str:
    override=os.getenv("MUNSHI_CHROME_PATH")
    if override and Path(override).exists(): return override
    if platform.system()=="Darwin": candidates=["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome","/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge","/Applications/Chromium.app/Contents/MacOS/Chromium"]
    elif platform.system()=="Windows": candidates=[str(Path(root)/"Google"/"Chrome"/"Application"/"chrome.exe") for root in [os.getenv("PROGRAMFILES",""),os.getenv("PROGRAMFILES(X86)","")] if root]
    else: candidates=[shutil.which("google-chrome") or "",shutil.which("chromium") or "",shutil.which("chromium-browser") or "",shutil.which("microsoft-edge") or ""]
    for candidate in candidates:
        if candidate and Path(candidate).exists(): return candidate
    raise WorkerError("Chrome, Edge, or Chromium was not found")

def _kill_process_tree(process:subprocess.Popen[Any])->None:
    if process.poll() is not None: return
    try:
        if platform.system()=="Windows": subprocess.run(["taskkill","/F","/T","/PID",str(process.pid)],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)  # noqa:S603
        else:
            os.killpg(os.getpgid(process.pid),signal.SIGTERM)
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: os.killpg(os.getpgid(process.pid),signal.SIGKILL)
    except (ProcessLookupError,PermissionError): pass

def _launch_browser(port:int,headless:bool)->BrowserProcess:
    profile=_runtime_root()/"autonomous-browser"/"profile"; profile.mkdir(parents=True,exist_ok=True,mode=0o700)
    command=[_chrome_path(),f"--remote-debugging-port={port}",f"--user-data-dir={profile}","--profile-directory=Default","--no-first-run","--no-default-browser-check","--disable-notifications","--disable-save-password-bubble","--window-size=1280,900"]
    if headless: command.append("--headless=new")
    kwargs:dict[str,Any]={"stdout":subprocess.DEVNULL,"stderr":subprocess.DEVNULL}
    if platform.system()!="Windows": kwargs["start_new_session"]=True
    process=subprocess.Popen(command,**kwargs)  # noqa:S603
    time.sleep(2.5)
    if process.poll() is not None: raise WorkerError("Browser exited during startup")
    return BrowserProcess(process,profile,port)

def _mcp_config(port:int)->dict[str,Any]: return {"mcpServers":{"playwright":{"command":"npx","args":["-y","@playwright/mcp@latest",f"--cdp-endpoint=http://127.0.0.1:{port}","--viewport-size=1280x900"]}}}
def _json_text(v:Any)->str: return json.dumps(v,ensure_ascii=False,separators=(",",":"))
def _approved_answers(request:dict[str,Any])->list[dict[str,Any]]:
    return [{"question_key":x.get("question_key"),"value":x.get("value"),"sensitive":x.get("sensitive",False),"provenance":x.get("provenance")} for x in request.get("answers",[]) if isinstance(x,dict) and x.get("approved") is True]

def _prepare_prompt(request:dict[str,Any])->str:
    job=request["job"]; artifacts=request.get("artifacts",{}); resume=artifacts.get("resume") or {}; cover=artifacts.get("cover_letter") or {}
    return f"""<role>You are the bounded MUNSHI browser application executor. Use only Playwright MCP.</role>
<mission>Prepare the exact application to the final irreversible submission boundary. DO NOT submit.</mission>
<job>{_json_text(job)}</job>
<documents>resume_path={resume.get('path','')}\ncover_letter_path={cover.get('path','') if cover else ''}</documents>
<approved_answers>{_json_text(_approved_answers(request))}</approved_answers>
<hard_rules>
1. Never invent candidate facts or alter supplied truth. 2. Use only approved answers. Unknown required values => NEEDS_INPUT.
3. Upload only supplied documents. 4. Never use tools other than Playwright. 5. Never bypass CAPTCHA/MFA/OTP/identity/authentication checks; return NEEDS_INPUT.
6. NEVER activate the final employer submission control in this phase. 7. Re-read page state after important actions.
</hard_rules>
<execution>Navigate to {job['url']}. Fill and navigate ordinary application steps until the final submit boundary. Stop with the application visibly ready to submit in this same browser session.</execution>
<result_format>Output exactly one line beginning with {RESULT_PREFIX} followed by compact JSON with status (COMPLETED/NEEDS_INPUT/BLOCKED/FAILED_SAFELY), claimed_submission=false, reason, needs_input_kind, final_url, provider_application_id, submission_observation=null, observations array.</result_format>"""

def _submit_prompt(request:dict[str,Any],auth:dict[str,Any],claim:dict[str,Any])->str:
    safe_claim={"authorization_id":claim.get("authorization_id"),"authority_digest":claim.get("authority_digest"),"claim_digest":claim.get("claim_digest"),"generation":claim.get("generation")}
    return f"""<role>You are the bounded MUNSHI final-submit executor. Use only Playwright MCP and the CURRENT browser tab/session.</role>
<mission>Cross exactly one final employer submission boundary for the already-prepared application.</mission>
<job>{_json_text(request['job'])}</job>
<canonical_authority>{_json_text(safe_claim)}</canonical_authority>
<reviewed_target>{auth.get('target_url')}</reviewed_target>
<hard_rules>
1. Do not navigate back to restart or rewrite the application. 2. Re-check visible required fields and candidate identity before clicking.
3. Never invent or modify candidate facts. 4. Never bypass CAPTCHA/MFA/OTP/identity/authentication checks; return NEEDS_INPUT without clicking.
5. Activate the final employer submission control at most once. 6. If the actual submission target is observably different from the reviewed_target, return BLOCKED without submitting.
7. Do not treat a click, redirect, generic 2xx, generic success text, or arbitrary JSON id as independent verification. Report factual browser/network observations only.
</hard_rules>
<result_format>Output exactly one line beginning with {RESULT_PREFIX} followed by compact JSON with status, claimed_submission boolean, reason, needs_input_kind, final_url, provider_application_id, submission_observation object or null with method,target,http_status,provider_application_id,completion_marker,response_marker, and observations array.</result_format>"""

def _parse_agent_output(lines:list[str])->tuple[dict[str,Any],dict[str,Any]]:
    parts=[]; usage={"input_tokens":0,"output_tokens":0,"cache_read_tokens":0,"cache_create_tokens":0,"cost_usd":0.0,"turns":0}
    for raw in lines:
        line=raw.strip()
        if not line: continue
        try: event=json.loads(line)
        except json.JSONDecodeError: parts.append(line); continue
        if event.get("type")=="assistant":
            for block in event.get("message",{}).get("content",[]) if isinstance(event.get("message",{}).get("content",[]),list) else []:
                if isinstance(block,dict) and block.get("type")=="text": parts.append(str(block.get("text","")))
        elif event.get("type")=="result":
            if isinstance(event.get("result"),str): parts.append(event["result"])
            u=event.get("usage",{}) if isinstance(event.get("usage"),dict) else {}; usage.update({"input_tokens":int(u.get("input_tokens",0) or 0),"output_tokens":int(u.get("output_tokens",0) or 0),"cache_read_tokens":int(u.get("cache_read_input_tokens",0) or 0),"cache_create_tokens":int(u.get("cache_creation_input_tokens",0) or 0),"cost_usd":float(event.get("total_cost_usd",0) or 0),"turns":int(event.get("num_turns",0) or 0)})
    matches=re.findall(rf"{re.escape(RESULT_PREFIX)}\s*(\{{.*\}})","\n".join(parts))
    if not matches: raise WorkerError("Browser agent did not return a structured MUNSHI result")
    try: result=json.loads(matches[-1])
    except json.JSONDecodeError as e: raise WorkerError("Browser agent returned invalid result JSON") from e
    if not isinstance(result,dict): raise WorkerError("Browser agent result must be an object")
    return result,usage

def _run_agent(*,prompt:str,port:int,settings:WorkerSettings,max_turns:int,max_cost:float,max_wall_seconds:int)->tuple[dict[str,Any],dict[str,Any]]:
    with tempfile.TemporaryDirectory(prefix="munshi-autonomous-") as temp_dir:
        temp=Path(temp_dir); mcp=temp/"mcp.json"; mcp.write_text(json.dumps(_mcp_config(port)),encoding="utf-8")
        command=["claude","--model",settings.model,"-p","--mcp-config",str(mcp),"--permission-mode","dontAsk","--allowedTools","mcp__playwright__*","--disallowedTools","Bash,Edit,Write,NotebookEdit,WebFetch,WebSearch","--no-session-persistence","--max-turns",str(max_turns),"--max-budget-usd",str(max_cost),"--output-format","stream-json","--verbose","-"]
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace",env=_worker_environment(settings),cwd=temp)  # noqa:S603
        try: stdout,_=process.communicate(prompt,timeout=max_wall_seconds)
        except subprocess.TimeoutExpired as e: _kill_process_tree(process); raise WorkerError("Autonomous browser execution exceeded wall-time budget") from e
        result,usage=_parse_agent_output(stdout.splitlines())
        if usage.get("cost_usd",0.0)>max_cost+1e-9: raise WorkerError("Autonomous browser execution exceeded AI cost budget")
        return result,usage

def _safe_submission_observation(value:object)->dict[str,Any]|None:
    if not isinstance(value,dict): return None
    return {k:value.get(k) for k in {"method","target","http_status","provider_application_id","completion_marker","response_marker"}}

def _merge_usage(a:dict[str,Any],b:dict[str,Any])->dict[str,Any]:
    return {k:(float(a.get(k,0) or 0)+float(b.get(k,0) or 0) if k=="cost_usd" else int(a.get(k,0) or 0)+int(b.get(k,0) or 0)) for k in ("input_tokens","output_tokens","cache_read_tokens","cache_create_tokens","cost_usd","turns")}

def _envelope(request:dict[str,Any],result:dict[str,Any],usage:dict[str,Any],started:float,claim:dict[str,Any]|None=None)->dict[str,Any]:
    run_id=f"autonomous-{uuid.uuid4()}"; status=str(result.get("status","FAILED_SAFELY")); status=status if status in ALLOWED_AGENT_STATUSES else "FAILED_SAFELY"; claimed=result.get("claimed_submission") is True
    needs=[]
    if status=="NEEDS_INPUT":
        kind=str(result.get("needs_input_kind") or "ANSWER_REQUIRED"); kind=kind if kind in ALLOWED_NEEDS_INPUT else "ANSWER_REQUIRED"; needs=[{"kind":kind,"message":str(result.get("reason") or "Owner input is required"),"question_key":None}]
    observation=_safe_submission_observation(result.get("submission_observation")); provider_id=result.get("provider_application_id") or (observation or {}).get("provider_application_id")
    submission_outcome=str(result.get("submission_outcome") or ("SUBMISSION_OBSERVED" if claimed else "NOT_ATTEMPTED"))
    if submission_outcome not in {"NOT_ATTEMPTED","SUBMISSION_OBSERVED","UNKNOWN_AFTER_AUTHORITY_CLAIM"}: submission_outcome="UNKNOWN_AFTER_AUTHORITY_CLAIM" if claim is not None else "NOT_ATTEMPTED"
    out={"schema_version":"1.0","worker_run_id":run_id,"plan_id":request["plan_id"],"plan_digest":request["plan_digest"],"status":status,"final_url":result.get("final_url") or request["job"]["url"],"provider":request["job"].get("provider"),"provider_application_id":provider_id,"claimed_submission":claimed,"submission_outcome":submission_outcome,"needs_input":needs,"events":[{"sequence":1,"kind":"WORKER_REQUEST_ACCEPTED","timestamp":_utc_now(),"verified":True,"detail":f"Autonomous worker {run_id} accepted governed request."},{"sequence":2,"kind":"AGENT_EXECUTION_COMPLETE","timestamp":_utc_now(),"verified":not claimed,"detail":str(result.get("reason") or status)}],"submission_observation":observation,"cost":{"estimated_total_usd":float(usage.get("cost_usd",0) or 0),"agent_usd":float(usage.get("cost_usd",0) or 0),"captcha_usd":0.0,"input_tokens":int(usage.get("input_tokens",0) or 0),"output_tokens":int(usage.get("output_tokens",0) or 0),"agent_steps":int(usage.get("turns",0) or 0),"wall_seconds":max(0.0,time.time()-started)}}
    if claim is not None: out["submit_authorization_claim"]={k:claim.get(k) for k in ("authorization_id","authority_digest","claim_digest","generation","status","submission_authority")}
    return out

def _synthetic_result(request:dict[str,Any],started:float)->dict[str,Any]:
    return {"schema_version":"1.0","worker_run_id":f"autonomous-{uuid.uuid4()}","plan_id":request["plan_id"],"plan_digest":request["plan_digest"],"status":"COMPLETED","final_url":request["job"]["url"],"provider":request["job"].get("provider"),"provider_application_id":None,"claimed_submission":False,"needs_input":[],"events":[{"sequence":1,"kind":"WORKER_REQUEST_ACCEPTED","timestamp":_utc_now(),"verified":True,"detail":"Synthetic request validated."},{"sequence":2,"kind":"SYNTHETIC_EXECUTION_COMPLETE","timestamp":_utc_now(),"verified":True,"detail":"Browser execution intentionally skipped; no external side effect occurred."}],"submission_observation":None,"cost":{"estimated_total_usd":0.0,"agent_usd":0.0,"captcha_usd":0.0,"input_tokens":0,"output_tokens":0,"agent_steps":0,"wall_seconds":max(0.0,time.time()-started)}}

def _diagnose(settings:WorkerSettings)->dict[str,Any]:
    claude=shutil.which("claude"); npx=shutil.which("npx")
    try: chrome=_chrome_path()
    except WorkerError: chrome=None
    auth_ready=settings.auth_mode=="subscription" or bool(_keychain_secret("ANTHROPIC_API_KEY","systems.munshi.apply.autonomous.anthropic") or os.getenv("ANTHROPIC_API_KEY"))
    return {"claude_cli":claude,"npx":npx,"chrome":chrome,"auth_mode":settings.auth_mode,"auth_ready":auth_ready,"ready":bool(claude and npx and chrome and auth_ready)}

def execute(request_path:Path,*,dry_run:bool,port:int)->dict[str,Any]:
    started=time.time(); request=_load_json(request_path); _validate_request(request); settings=_load_settings(); permissions=request["permissions"]; context=request["execution_context"]
    final_intent=not dry_run and context.get("synthetic") is not True and permissions.get("final_submit") is True and settings.allow_final_submit
    if permissions.get("final_submit") is True and context.get("synthetic") is not True and not final_intent:
        # A request/local flag mismatch can prepare safely, but cannot silently grant submit authority.
        final_intent=False
    budget=request.get("budget") if isinstance(request.get("budget"),dict) else {}; requested=float(budget.get("max_ai_cost_usd",settings.max_cost_usd)); max_cost=min(settings.max_cost_usd,requested) if requested>=0 else settings.max_cost_usd; max_turns=min(settings.max_turns,int(budget.get("max_agent_steps",settings.max_turns))); max_wall=int(budget.get("max_wall_seconds",300))
    if context.get("synthetic") is True and not os.getenv("MUNSHI_RUN_SYNTHETIC_BROWSER"): return _synthetic_result(request,started)
    if not shutil.which("claude"): raise WorkerError("Claude Code CLI is not installed")
    if not shutil.which("npx"): raise WorkerError("npx is not installed")
    browser=_launch_browser(port,settings.headless)
    try:
        prepare,usage1=_run_agent(prompt=_prepare_prompt(request),port=port,settings=settings,max_turns=max_turns,max_cost=max_cost,max_wall_seconds=max_wall)
        if prepare.get("claimed_submission") is True: raise WorkerError("Preparation phase crossed the final-submit boundary without authority")
        if prepare.get("status")!="COMPLETED" or not final_intent: return _envelope(request,prepare,usage1,started)
        auth=_validate_authorization_binding(request); claimant=f"applypilot-{uuid.uuid4()}"
        try: claim=claim_submit_authorization(auth,claimant_id=claimant)
        except SubmitAuthorizationError as e: raise WorkerError(f"Canonical submit authorization claim failed: {e}") from e
        remaining_cost=max(0.0,max_cost-float(usage1.get("cost_usd",0) or 0)); remaining_turns=max(1,max_turns-int(usage1.get("turns",0) or 0)); elapsed=max(0,int(time.time()-started)); remaining_wall=max(1,max_wall-elapsed)
        try:
            final,usage2=_run_agent(prompt=_submit_prompt(request,auth,claim),port=port,settings=settings,max_turns=remaining_turns,max_cost=remaining_cost,max_wall_seconds=remaining_wall)
        except WorkerError as error:
            # Once authority is claimed, never emit a retryable "nothing happened"
            # result. The one-use claim remains consumed pending reconciliation.
            unknown={"status":"BLOCKED","claimed_submission":False,"submission_outcome":"UNKNOWN_AFTER_AUTHORITY_CLAIM","reason":f"Submission outcome requires reconciliation after authority claim: {error}","final_url":request["job"]["url"],"submission_observation":None}
            return _envelope(request,unknown,usage1,started,claim)
        if final.get("claimed_submission") is True:
            observation=_safe_submission_observation(final.get("submission_observation"))
            if not observation or str(observation.get("method") or "").upper()!="POST" or str(observation.get("target") or "")!=str(auth.get("target_url") or ""):
                unknown={"status":"BLOCKED","claimed_submission":False,"submission_outcome":"UNKNOWN_AFTER_AUTHORITY_CLAIM","reason":"Submission was reported without exact reviewed POST target evidence; reconciliation is required","final_url":final.get("final_url") or request["job"]["url"],"submission_observation":observation}
                return _envelope(request,unknown,_merge_usage(usage1,usage2),started,claim)
        return _envelope(request,final,_merge_usage(usage1,usage2),started,claim)
    finally: _kill_process_tree(browser.process)

def main()->int:
    parser=argparse.ArgumentParser(description="MUNSHI apply-only autonomous browser worker"); parser.add_argument("request",nargs="?",type=Path); parser.add_argument("--dry-run",action="store_true"); parser.add_argument("--diagnose",action="store_true"); parser.add_argument("--port",type=int,default=DEFAULT_CDP_PORT); args=parser.parse_args(); settings=_load_settings()
    if args.diagnose: print(json.dumps(_diagnose(settings),indent=2,sort_keys=True)); return 0
    if args.request is None: parser.error("request is required unless --diagnose is used")
    try: result=execute(args.request,dry_run=args.dry_run,port=args.port)
    except WorkerError as e: print(json.dumps({"schema_version":"1.0","status":"FAILED_SAFELY","reason":str(e),"claimed_submission":False},indent=2,sort_keys=True)); return 2
    print(json.dumps(result,indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
