import psycopg2, json, re, urllib.parse, requests

DB_URL = "postgresql://algo:algo_password@localhost:5433/algo_diagnostic"
CONTENT_SERVICE_URL = "http://localhost:8004"

def canonical_answer_key(val):
    if not val: return ""
    s = str(val).strip().replace("$$", "").replace("$", "")
    s = s.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
    s = re.sub(r"\\?(?:left|right|displaystyle|limits)\b", "", s)
    s = re.sub(r"\\?text\s*\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\?(?:emptyset|varnothing|empty)\b|[∅⌀Ø]", "emptyset", s)
    s = re.sub(r"нет\s*(?:действительных\s*)?(?:корней|решений)|(?:корней|решений)\s*нет", "emptyset", s, flags=re.IGNORECASE)
    while re.search(r"\\?sqrt\s*\{([^{}]+)\}", s):
        s = re.sub(r"\\?sqrt\s*\{([^{}]+)\}", r"sqrt(\1)", s)
    s = re.sub(r"\\?sqrt", "sqrt", s).replace("√", "sqrt")
    while re.search(r"\\?(?:dfrac|frac)\s*\{([^{}]+)\}\s*\{([^{}]+)\}", s):
        s = re.sub(r"\\?(?:dfrac|frac)\s*\{([^{}]+)\}\s*\{([^{}]+)\}", r"(\1)/(\2)", s)
    s = re.sub(r"\\?(?:dfrac|frac)\b", "/", s)
    s = re.sub(r"\\?(?:cdot|times)\b|\*|·", "", s)
    s = s.replace("{,}", ".").replace(",", ".")
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    s = re.sub(r"[{}]", "", s)
    s = re.sub(r"\s+", "", s)
    return s.lower()

def are_answers_equivalent(a, b):
    if not a or not b: return False
    ka = canonical_answer_key(a)
    kb = canonical_answer_key(b)
    if not ka or not kb: return False
    if ka == kb: return True
    strip_parens = lambda x: re.sub(r"[()]", "", x)
    return strip_parens(ka) == strip_parens(kb)

conn = psycopg2.connect(DB_URL, options='-c timezone=UTC')  # session TimeZone=UTC (ROADMAP #49)
cur = conn.cursor()
cur.execute("SELECT id, report_json FROM diag_reports;")
reports = cur.fetchall()

updated = 0
for rep_id, rep in reports:
    if not rep or not isinstance(rep, dict): continue
    eps = rep.get("error_patterns") or []
    if not eps: continue
    
    rep_changed = False
    for ep in eps:
        tid = ep.get("task_id")
        if not tid: continue
        
        encoded = urllib.parse.quote(str(tid), safe="")
        resp = requests.get(f"{CONTENT_SERVICE_URL}/api/v1/content/tasks/{encoded}", timeout=5)
        if resp.status_code != 200: continue
        tdata = resp.json()
        
        ca = tdata.get("correct_answer")
        ca_l = tdata.get("correct_answer_latex") or ca
        ep["correct_answer"] = ca
        ep["correct_answer_latex"] = ca_l
        
        d_meta = tdata.get("distractor_meta") or []
        sa = str(ep.get("student_answer") or "").strip()
        
        # If student answer was recorded as index "0", "1", etc. and distractor_meta exists
        if sa.isdigit() and d_meta:
            d_idx = int(sa)
            if 0 <= d_idx < len(d_meta):
                dm = d_meta[d_idx]
                if isinstance(dm, dict):
                    v = dm.get("value") or dm.get("text")
                    vl = dm.get("value_latex") or v
                    if v:
                        ep["student_answer"] = v
                        ep["student_answer_latex"] = vl
                        sa = str(v).strip()
                        rep_changed = True
        
        # Match distractor explanation
        if sa and d_meta:
            for dm in d_meta:
                if isinstance(dm, dict):
                    v_val = str(dm.get("value") or dm.get("text") or "").strip()
                    v_lat = str(dm.get("value_latex") or v_val).strip()
                    if are_answers_equivalent(sa, v_val) or are_answers_equivalent(sa, v_lat):
                        ep["distractor_explanation"] = dm.get("explanation") or dm.get("error_logic") or None
                        break
        
        # Options
        task_opts = tdata.get("answer_options")
        task_opts_l = tdata.get("answer_options_latex")
        if task_opts and len(task_opts) > 1:
            ep["answer_options"] = task_opts
            ep["answer_options_latex"] = task_opts_l or task_opts
        else:
            raw_opts = [ca] if ca else []
            latex_opts = [ca_l] if ca_l else []
            for dm in d_meta:
                if isinstance(dm, dict):
                    v = dm.get("value") or dm.get("text") or ""
                    vl = dm.get("value_latex") or v
                    if v and v not in raw_opts:
                        raw_opts.append(v)
                        latex_opts.append(vl)
            if len(raw_opts) > 1:
                ep["answer_options"] = raw_opts
                ep["answer_options_latex"] = latex_opts
        
        rep_changed = True
    
    if rep_changed:
        cur.execute("UPDATE diag_reports SET report_json = %s::jsonb WHERE id = %s;", (json.dumps(rep), rep_id))
        updated += 1

conn.commit()
print(f"Successfully rehydrated and cleaned {updated} reports in PostgreSQL!")
