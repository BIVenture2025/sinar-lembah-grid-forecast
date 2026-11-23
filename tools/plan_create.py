# P37 Build exit (adapted from W12_PLAN_CREATE.py, SETTLED S250): the P37 estate from a fresh clone of the Git repo
# sinarlembah-fabric-estate into the EMPTY SinarLembah-Scratch by Bulk Import (beta) in dependency waves; the last wave
# carries deployment plan DP_P37_Create whose post-action runs NB_SinarLembah_Seed (the seed builds the KQL data). Rebinds
# from the repo's own parameter.yml before each wave, so no dev id is ever sent. Nothing is deleted. Prints no token.
# Usage: TARGET_WORKSPACE_ID=<empty workspace id> python plan_create.py <repo dir> [verify]. Log beside it.
import base64, datetime, json, os, re, subprocess, sys, time, urllib.request, urllib.error
HERE = os.path.dirname(os.path.abspath(__file__)); LOG = os.path.join(HERE, "plan_create_log.txt")
open(LOG, "w", encoding="utf-8").write("")
T0 = time.time()
def L(m):
    s = f"[{datetime.datetime.now():%H:%M:%S}] {m}"; print(s, flush=True); open(LOG, "a", encoding="utf-8").write(s + "\n")
WS = os.environ["TARGET_WORKSPACE_ID"]; API = "https://api.fabric.microsoft.com/v1"
CLONE = sys.argv[1]; EST = os.path.join(CLONE, "fabric")
PARAM = os.path.join(EST, "parameter.yml")
SEED = ("Notebook", "NB_SinarLembah_Seed")
tok = subprocess.run("az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv", shell=True, capture_output=True, text=True).stdout.strip()
L(f"token {'ok' if len(tok) > 100 else 'FAILED'} ({len(tok)} chars)")
if len(tok) < 100: sys.exit(2)
def call(method, url, body=None):
    for attempt in range(6):    # P37: retry a GET on a transport error (WinError 10060/10061 seen); never a POST
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
        try:
            r = urllib.request.urlopen(req, timeout=180); raw = r.read().decode() or "{}"
            return r.status, dict(r.headers), (json.loads(raw) if raw.strip()[:1] in "{[" else raw)
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read().decode()[:3000]
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if method != "GET" or attempt == 5: raise
            L(f"transport error on GET, retry {attempt + 1}: {e}"); time.sleep(15 * (attempt + 1))
LASTERR = [""]
def lro(st, hd, res, what):
    if st in (200, 201): return res
    LASTERR[0] = res if isinstance(res, str) else json.dumps(res)
    if st != 202: L(f"{what}: HTTP {st} {res if isinstance(res, str) else json.dumps(res)[:2500]}"); return None
    loc = hd.get("Location") or hd.get("location")
    for i in range(120):
        time.sleep(int(hd.get("Retry-After", 5) or 5))
        s2, _, r2 = call("GET", loc); stt = r2.get("status") if isinstance(r2, dict) else r2
        if stt == "Succeeded":
            s3, _, r3 = call("GET", loc.rstrip("/") + "/result"); return r3 if s3 == 200 else {"_noresult": s3}
        if stt == "Failed": LASTERR[0] = json.dumps(r2); L(f"{what}: FAILED {json.dumps(r2)[:2500]}"); return None
    L(f"{what}: timed out"); return None
def target():
    st, _, it = call("GET", f"{API}/workspaces/{WS}/items"); return it.get("value", []) if isinstance(it, dict) else []
head = subprocess.run(f'git -C "{CLONE}" rev-parse --short HEAD', shell=True, capture_output=True, text=True).stdout.strip()
L(f"clone {CLONE} at {head}; target {WS}")
before = target(); L(f"target items before: {len(before)}" + (" (NOT EMPTY: " + ", ".join(i['displayName'] for i in before) + ")" if before else " (empty)"))
txt = open(PARAM, encoding="utf-8").read()
pairs = re.findall(r'find_value:\s*"([0-9a-f-]{36})"\s*\n\s*replace_value:\s*\n\s*_ALL_:\s*"([^"]+)"', txt)
expr = dict(pairs); L(f"parameter entries {len(pairs)}")
if len(pairs) != 4: L("STOP: expected 4 entries"); sys.exit(2)
def need(e):   # the (type, name) an expression waits for, or None
    if e == "$workspace.$id": return None
    m = re.match(r"\$items\.(\w+)\.([\w-]+)\.\$(id|sqlendpointid)$", e)
    return (m.group(1), m.group(2)) if m else ("?", e)
# --- repo items and their files
repo = {}
for folder in sorted(os.listdir(EST)):
    full = os.path.join(EST, folder)
    if not os.path.isdir(full) or "." not in folder: continue
    name, typ = folder.rsplit(".", 1)
    files = []
    for dp, dn, fn in os.walk(full):
        for f in fn:
            p = os.path.join(dp, f); files.append(("/" + os.path.relpath(p, EST).replace("\\", "/"), open(p, "rb").read()))
    text = "\n".join(d.decode("utf-8", "replace") for _, d in files)
    devs = sorted(k for k in expr if k in text)
    deps = set(need(expr[k]) for k in devs) - {None}
    if typ == "Report":
        m = re.search(r'"path"\s*:\s*"\.\./([^"]+)\.SemanticModel"', text)
        if m: deps.add(("SemanticModel", m.group(1)))
    repo[(typ, name)] = {"folder": folder, "files": files, "devs": devs, "deps": deps,
                        "logical": json.loads(dict(files)["/" + folder + "/.platform"].decode("utf-8-sig"))["config"]["logicalId"]}
L(f"repo items {len(repo)}")
for k, v in repo.items(): L(f"  {k[0]:16} {k[1]:32} dev ids {len(v['devs'])}, waits for {sorted(f'{a}.{b}' for a, b in v['deps']) or '-'}")
# P37: a child item (Fabric Git format: <parent>/.children/<name>.<Type>) travels inside its parent's files; a dependency
# on the child waits for the parent's wave, and the child's id is resolved from the target listing after that wave.
CHILD = {}
for k, v in repo.items():
    ch = os.path.join(EST, v["folder"], ".children")
    if os.path.isdir(ch):
        for c in os.listdir(ch):
            if "." in c:
                cn, ct = c.rsplit(".", 1); CHILD[(ct, cn)] = k; L(f"  child {ct} {cn} travels with {k[0]} {k[1]}")
for k, v in repo.items():
    v["deps"] = {CHILD.get(d, d) for d in v["deps"]} - {k}
selfref = [k for k, v in repo.items() if k in v["deps"]]
if selfref: L(f"VERDICT: KILL - item(s) name their own dev id: {selfref}"); sys.exit(1)
bad = [d for v in repo.values() for d in v["deps"] if d not in repo]
if bad: L(f"STOP: dependency on an item not in the repo: {bad}"); sys.exit(2)
# --- levels. Run 1 (16:57) showed the importer resolves in-workspace references by logicalId inside one payload
# (DependenciesCouldNotBeResolved for the pipeline). So items linked by a logicalId (or a report's byPath) share a wave;
# dev ids (parameter.yml) are resolved by this script between waves.
lg = {v["logical"]: k for k, v in repo.items()}
parent = {k: k for k in repo}
def find(k):
    while parent[k] != k: k = parent[k]
    return k
for k, v in repo.items():
    text = "\n".join(d.decode("utf-8", "replace") for _, d in v["files"])
    links = {lg[l] for l in lg if l in text and lg[l] != k}
    if k[0] == "Report": links |= {d for d in v["deps"] if d[0] == "SemanticModel"}
    v["links"] = links
    for t in links: parent[find(k)] = find(t)
for k, v in repo.items():
    if v["links"]: L(f"  logicalId links {k[1]} -> {sorted(t[1] for t in v['links'])}")
lvl = {k: 0 for k in repo}
for _ in range(len(repo) + 2):
    changed = False
    for k, v in repo.items():
        want = max([lvl[d] + 1 for d in v["deps"] if find(d) != find(k)] + [lvl[k]])
        if want != lvl[k]: lvl[k] = want; changed = True
    for k in repo:
        g = max(lvl[j] for j in repo if find(j) == find(k))
        if g != lvl[k]: lvl[k] = g; changed = True
    if max(lvl.values()) > len(repo): break
    if not changed: break
same = [k for k, v in repo.items() for d in v["deps"] if find(d) == find(k) and not (k[0] == "Report" and d[0] == "SemanticModel")]
if same or max(lvl.values()) > len(repo): L(f"VERDICT: KILL - a dev-id dependency inside one logicalId group (cannot resolve ahead): {same}"); sys.exit(1)
lvl[SEED] = max(lvl.values())   # the post-action notebook must travel in the plan's payload (logicalId inside one payload)
waves = sorted(set(lvl.values()))
for w in waves: L(f"wave {w}: " + ", ".join(f"{n}.{t}" for (t, n), x in sorted(lvl.items()) if x == w))
# --- resolve against the target
sqlep_cache = {}
def resolver(items):
    by = {(i["type"], i["displayName"]): i["id"] for i in items}
    def res(e):
        if e == "$workspace.$id": return WS
        m = re.match(r"\$items\.(\w+)\.([\w-]+)\.\$(id|sqlendpointid)$", e)
        if not m: return None
        iid = by.get((m.group(1), m.group(2)))
        if not iid or m.group(3) == "id": return iid
        if iid not in sqlep_cache:
            for i in range(36):
                st, _, p = call("GET", f"{API}/workspaces/{WS}/lakehouses/{iid}")
                sp = (p.get("properties", {}).get("sqlEndpointProperties") or {}) if isinstance(p, dict) else {}
                if sp.get("id"): sqlep_cache[iid] = sp["id"]; L(f"sql endpoint {sp['id']} ({sp.get('provisioningStatus')}) after {i * 5} s"); break
                time.sleep(5)
        return sqlep_cache.get(iid)
    return res
def parts_for(keys, rep):
    out, n = [], 0
    for k in keys:
        for path, data in repo[k]["files"]:
            try:
                s = data.decode("utf-8")
                for a, b in rep.items():
                    if a in s: n += s.count(a); s = s.replace(a, b)
                data = s.encode("utf-8")
            except UnicodeDecodeError: pass
            out.append({"path": path, "payload": base64.b64encode(data).decode(), "payloadType": "InlineBase64"})
    return out, n
ML = {"MLModel", "MLExperiment"}; ml_refused = False; details = []
PLAN_LOGICAL = "37a00000-0000-4000-8000-0000000000d1"; SEED_LOGICAL = repo[SEED]["logical"]
VERIFY_ONLY = len(sys.argv) > 2 and sys.argv[2] == "verify"
if VERIFY_ONLY: L("VERIFY ONLY: no wave is sent; reading the target back")
for w in ([] if VERIFY_ONLY else waves):
    keys = [k for k, x in sorted(lvl.items()) if x == w]
    if ml_refused: keys = [k for k in keys if k[0] not in ML]
    res = resolver(target())
    rep = {k: res(expr[k]) for k in sorted({d for kk in keys for d in repo[kk]["devs"]})}
    un = [k for k, v in rep.items() if not v]
    if un: L(f"VERDICT: KILL - wave {w}: rebind unresolved for {[(k, expr[k]) for k in un]}"); sys.exit(1)
    parts, n = parts_for(keys, rep)
    opts = {"allowPairingByName": True}
    last = (w == waves[-1])
    if last:   # plan: the seed notebook first, then the wave's other items; post-action on the last group runs the seed
        y = ["$schema: https://developer.microsoft.com/json-schemas/fabric/item/deploymentPlan/definition/plan/1.0.0/schema.json", "version: 1.0.0", "groups:",
             "  - name: Seed_NB_SinarLembah_Seed", f"    logicalId: {SEED_LOGICAL}"]
        # groups in link order: an item after the items it links to by logicalId (notebooks before the pipeline, the
        # model before the report); each group depends on the seed group and on the groups it links to (P37 run 2:
        # DependenciesCouldNotBeResolved for the pipeline listed before its notebooks)
        rest = [k for k in keys if k != SEED]; keys_g = []
        while rest:
            nxt = [k for k in rest if not ({t for t in repo[k]["links"] if t in rest})]
            if not nxt: L("VERDICT: KILL - circular logicalId links in the last wave"); sys.exit(1)
            keys_g += sorted(nxt); rest = [k for k in rest if k not in nxt]
        for i, k in enumerate(keys_g):
            y += [f"  - name: {k[0]}_{k[1]}", f"    logicalId: {repo[k]['logical']}", "    dependsOn:", "      - groupName: Seed_NB_SinarLembah_Seed"]
            y += [f"      - groupName: {t[0]}_{t[1]}" for t in sorted(repo[k]["links"]) if t in keys_g]
            if i == len(keys_g) - 1:
                y += ["    postActions:", "      - name: runSeedNotebook", "        job:", "          type: Execute", f"          logicalId: {SEED_LOGICAL}"]
        plan_yml = "\n".join(y) + "\n"; open(os.path.join(HERE, "plan_P37_create.yml"), "w", encoding="utf-8").write(plan_yml)
        plat = {"$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
                "metadata": {"type": "DeploymentPlan", "displayName": "DP_P37_Create", "description": "P37 Build exit: last wave of the create run; post-action runs NB_SinarLembah_Seed"},
                "config": {"version": "2.0", "logicalId": PLAN_LOGICAL}}
        parts += [{"path": "/DP_P37_Create.DeploymentPlan/plan.yml", "payload": base64.b64encode(plan_yml.encode()).decode(), "payloadType": "InlineBase64"},
                  {"path": "/DP_P37_Create.DeploymentPlan/.platform", "payload": base64.b64encode(json.dumps(plat, indent=2).encode()).decode(), "payloadType": "InlineBase64"}]
        opts["deploymentPlan"] = {"referenceType": "ByLogicalId", "logicalId": PLAN_LOGICAL}
    L(f"wave {w}: {len(keys)} item(s), {len(parts)} parts, {n} id replacements, {sum(len(p['payload']) for p in parts):,} b64 chars" + (", WITH PLAN" if last else ""))
    t1 = time.time()
    st, hd, r = call("POST", f"{API}/workspaces/{WS}/items/bulkImportDefinitions?beta=true", {"definitionParts": parts, "options": opts})
    out = lro(st, hd, r, f"wave {w} bulkImport")
    errtxt = LASTERR[0]
    ml_logicals = [repo[k]["logical"] for k in keys if k[0] in ML]
    if not out and ml_logicals and ("MLModel" in errtxt or "MLExperiment" in errtxt or any(l in errtxt for l in ml_logicals)):
        L(f"wave {w}: refused with ML item(s) in it -> ML fallback (owner's answer): resend without them")
        ml_refused = True; keys2 = [k for k in keys if k[0] not in ML]
        if keys2 and not last:
            parts, n = parts_for(keys2, rep)
            st, hd, r = call("POST", f"{API}/workspaces/{WS}/items/bulkImportDefinitions?beta=true", {"definitionParts": parts, "options": {"allowPairingByName": True}})
            out = lro(st, hd, r, f"wave {w} bulkImport (no ML)")
        elif not keys2: out = {"importItemDefinitionsDetails": []}
    L(f"wave {w}: took {time.time() - t1:.0f} s")
    if out is None: L(f"VERDICT: KILL - wave {w} refused (details above)"); sys.exit(1)
    for d in out.get("importItemDefinitionsDetails", []):
        details.append(d); L(f"  {d.get('operationType'):6} {d.get('operationStatus'):10} {d.get('itemType'):16} {d.get('itemDisplayName')}")
if ml_refused:
    have = {(i["type"], i["displayName"]) for i in target()}
    for k in [k for k in repo if k[0] in ML and k not in have]:
        st, hd, r = call("POST", f"{API}/workspaces/{WS}/items", {"displayName": k[1], "type": k[0]})
        L(f"ML fallback: create {k[0]} {k[1]} empty by REST -> HTTP {st}"); lro(st, hd, r, f"create {k[1]}")
# --- read back
after = target(); have = {(i["type"], i["displayName"]): i["id"] for i in after}
missing = [f"{n}.{t}" for (t, n) in list(repo) + list(CHILD) if (t, n) not in have]
L(f"target items after: {len(after)}; repo items present {len(repo) - len(missing)} of {len(repo)}" + (f"; MISSING {missing}" if missing else ""))
withdef = {"SemanticModel", "Notebook", "Report", "DataPipeline", "VariableLibrary", "CopyJob"}
fail = idleft = read = 0
for (t, n), iid in sorted(have.items()):
    if t not in withdef or (t, n) not in repo: continue
    st, hd, r = call("POST", f"{API}/workspaces/{WS}/items/{iid}/getDefinition" + ("?format=TMDL" if t == "SemanticModel" else ""), {})
    d = lro(st, hd, r, f"getDefinition {n}")
    if not d: fail += 1; continue
    read += 1; ps = d["definition"]["parts"]; text = "\n".join(base64.b64decode(p["payload"]).decode("utf-8", "replace") for p in ps)
    msg = f"CONTENT {t:16} {n}: {len(ps)} part(s)"
    if t == "SemanticModel":
        got = len([p for p in ps if p["path"].startswith("definition/tables/") and p["path"].endswith(".tmdl")])
        want = len([f for f in os.listdir(os.path.join(EST, n + ".SemanticModel", "definition", "tables")) if f.endswith(".tmdl")])
        msg += f", tables {got} of {want}"; fail += (got != want)
    hits = [k for k in expr if k in text]
    if hits: idleft += 1; msg += f", DEV ID LEFT {hits}"
    unr = sorted(set(re.findall(r"\$(?:items|workspace)\.[A-Za-z0-9_.$]+", text)))
    if unr: fail += 1; msg += f", UNRESOLVED {unr}"
    L(msg + f", target ws id x{text.count(WS)}")
nb = have.get(SEED); runs = []
for i in range(120):          # the seed runs about 370 KQL commands: wait up to 40 min for the post-action job to end
    time.sleep(20)
    if nb:
        st, _, j = call("GET", f"{API}/workspaces/{WS}/items/{nb}/jobs/instances"); runs = j.get("value", []) if isinstance(j, dict) else []
    if runs and all(x.get("status") in ("Completed", "Failed", "Cancelled", "Deduped") for x in runs): break
L(f"NB_SinarLembah_Seed job instances: {len(runs)} " + json.dumps([{k: x.get(k) for k in ('status', 'startTimeUtc', 'endTimeUtc', 'failureReason')} for x in runs[:2]])[:3000])
notok = [d for d in details if d.get("operationStatus") != "Succeeded"]
L(f"content check: {read} read, {fail} failed, {idleft} with a dev id; import ops {len(details)}, not succeeded {len(notok)}; ML refused {ml_refused}")
ok = not missing and not notok and fail == 0 and idleft == 0 and read > 0 and any(x.get("status") == "Completed" for x in runs)
L("VERDICT: " + ("PASS" if ok else "FAIL") + f" - plan route CREATE run in {len(waves)} wave(s), {len(details)} import ops, total {time.time() - T0:.0f} s")
L("DONE")
