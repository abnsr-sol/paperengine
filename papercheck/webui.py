"""Local web GUI: drag-and-drop manuscript checking in the browser.

Zero dependencies beyond PaperEngine itself (stdlib http.server). The uploaded
file never leaves your machine - it is parsed in memory, checked by all
engines, and the temporary copy is deleted as soon as the report is rendered
(no retention, every request).

    papercheck --gui              # serve on http://localhost:8765
    papercheck --gui --port 9000  # custom port

Security posture:
    - binds 127.0.0.1 only (not reachable from the network)
    - size cap: 25 MB per upload
    - only .docx/.txt/.md/.markdown/.tex/.pdf accepted
    - multipart/form-data parsing done manually (no dependencies)
    - X-Frame-Options: DENY, Cache-Control: no-store, no persistence
    - before/after comparison lives in the CLI (`--compare`), not the GUI
"""
from __future__ import annotations

import html as _html
import io
import os
import re
import tempfile
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .checks import ALL_ENGINES, CheckContext, run_all_engines
from .ingestion import (PdfExtractionError, UnsupportedFormatError,
                        load_document)
from .report import render_html
from .risk import RiskReport
from .venues import PRESETS, describe, get_rules, list_venues

_MAX_UPLOAD = 25 * 1024 * 1024  # 25 MB
_ALLOWED_EXT = (".docx", ".txt", ".md", ".markdown", ".tex", ".pdf")
_BOUNDARY_RE = re.compile(r'boundary="?([^";]+)"?', re.IGNORECASE)


def _venue_options(selected: str = "generic") -> str:
    groups = list_venues()
    opts = ['<option value="generic">generic (no venue rules)</option>']
    for std in ("international", "national"):
        label = "International" if std == "international" else "National (India)"
        opts.append(f'<optgroup label="{label}">')
        for name in groups.get(std, []):
            sel = " selected" if name == selected else ""
            opts.append(f'<option value="{name}"{sel}>{name} — {_html.escape(describe(name))}</option>')
        opts.append("</optgroup>")
    return "\n".join(opts)


def _venue_hint(venue: str) -> str:
    """One-line human summary of a preset's key rules for the dropdown hint."""
    p = PRESETS.get(venue)
    if not p:
        return "No venue rules — generic sanity checks only."
    bits = []
    if p.get("page_limit"):
        bits.append(f"≤{p['page_limit']} pages")
    if p.get("word_limit"):
        bits.append(f"≤{p['word_limit']:,} words")
    if p.get("abstract_word_limit"):
        bits.append(f"abstract ≤{p['abstract_word_limit']} words")
    if p.get("columns"):
        bits.append(f"{p['columns']}-column")
    if p.get("min_references"):
        bits.append(f"≥{p['min_references']} references")
    if p.get("double_blind"):
        bits.append("double-blind (anonymize!)")
    thr = p.get("plagiarism_threshold")
    if isinstance(thr, dict) and thr.get("level_0_max") is not None:
        bits.append(f"UGC similarity ≤{thr['level_0_max']}%")
    elif p.get("plagiarism_threshold"):
        bits.append("similarity limit enforced")
    stmts = p.get("required_statements") or []
    if stmts:
        bits.append(f"statements: {', '.join(stmts[:4])}{'…' if len(stmts) > 4 else ''}")
    if p.get("rules_last_verified"):
        bits.append(f"limits verified {p['rules_last_verified']}")
    return " · ".join(bits) if bits else "Standard venue checks."


def _venue_hints_js() -> str:
    import json as _json
    mapping = {name: _venue_hint(name) for name in PRESETS}
    mapping["generic"] = _venue_hint("generic")
    return _json.dumps(mapping)


def _page(form_html: str = "", result_html: str = "", error: str = "") -> str:
    banner = ""
    if error:
        banner = f'<div class="error">{_html.escape(error)}</div>'
    n_engines = len(ALL_ENGINES)
    try:
        from .intel import db_status
        _st = db_status()
        _n = _st.get("retraction_db")
        _src = _st.get("retraction_db_source", "")
        intel_chip = (f"Retraction Watch: {int(_n):,} papers cached"
                      if _src == "downloaded" and isinstance(_n, int)
                      else "Retraction Watch: seed list (run papercheck --sync-all)")
    except Exception:
        intel_chip = "Open-intelligence cache"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PaperEngine — local paper checker</title>
<style>
  :root {{
    --bg:#f6f7fb; --card:#ffffff; --ink:#151a28; --muted:#5d6478;
    --accent:#3b5bdb; --accent-2:#7048e8; --ok:#0b7a45; --ok-bg:#e6f6ee;
    --bad:#c92a2a; --bad-bg:#fdecec; --line:#e3e6ef; --warn-bg:#fff9e6;
    --radius:14px; --shadow:0 1px 3px rgba(21,26,40,.07),0 8px 24px rgba(21,26,40,.06);
  }}
  * {{ box-sizing:border-box; }}
  html {{ font-size:clamp(15px, 0.55vw + 12.6px, 19px); }}  /* em-scale: whole UI grows with viewport */
  body {{ font-family:'Segoe UI',system-ui,-apple-system,Roboto,sans-serif;
         margin:0; background:var(--bg); color:var(--ink);
         line-height:1.55; -webkit-font-smoothing:antialiased; }}

  /* ---------- header ---------- */
  header {{ background:linear-gradient(120deg,#1a2140 0%,#232b54 55%,#3b2f77 100%);
            color:#fff; padding:2.2rem 1.5rem 2.4rem; text-align:center; }}
  header .inner {{ max-width:62rem; margin:0 auto; }}
  header .logo {{ display:inline-flex; align-items:center; gap:.6rem; font-size:1.9rem;
                  font-weight:700; letter-spacing:.3px; }}
  header .logo .mark {{ width:2.1rem; height:2.1rem; border-radius:.55rem;
      background:linear-gradient(135deg,var(--accent),var(--accent-2));
      display:inline-flex; align-items:center; justify-content:center; font-size:1.15rem; }}
  header .tag {{ margin:.45rem auto 0; opacity:.78; font-size:.92rem; max-width:44rem; }}
  header .chips {{ margin-top:1rem; display:flex; gap:.5rem; justify-content:center; flex-wrap:wrap; }}
  .chip {{ background:rgba(255,255,255,.13); border:1px solid rgba(255,255,255,.22);
           border-radius:999px; padding:.28rem .85rem; font-size:.78rem; }}

  main {{ max-width:62rem; margin:0 auto; padding:1.8rem 1.25rem 2.5rem; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:var(--radius);
           box-shadow:var(--shadow); padding:1.6rem; }}

  /* ---------- drop zone ---------- */
  .drop {{ border:2px dashed #b9c1d4; border-radius:var(--radius); background:#fafbfe;
           padding:2.6rem 1.4rem; text-align:center; cursor:pointer; transition:all .18s ease; }}
  .drop:hover {{ border-color:var(--accent); background:#f4f6ff; }}
  .drop.over {{ border-color:var(--accent); background:#edf1ff; transform:scale(1.005); }}
  .drop input {{ display:none; }}
  .drop .icon {{ font-size:2rem; display:block; margin-bottom:.5rem; }}
  .drop .big {{ font-size:1.08rem; font-weight:600; margin-bottom:.3rem; }}
  .drop .small {{ color:var(--muted); font-size:.83rem; }}
  .drop.selected {{ border:2px solid var(--ok); background:var(--ok-bg); }}
  .drop.selected .big {{ color:var(--ok); font-size:1.15rem; }}
  .drop .fileline {{ display:flex; align-items:center; justify-content:center; gap:.7rem;
                     flex-wrap:wrap; margin-top:.2rem; }}
  .drop .fname {{ font-family:Consolas,'Cascadia Mono',monospace; font-size:1rem;
                  background:#fff; border:1px solid #bfe3cd; border-radius:.6rem;
                  padding:.4rem 1rem; max-width:100%; overflow-wrap:anywhere;
                  box-shadow:0 1px 2px rgba(11,122,69,.12); }}
  button.clear {{ background:#fff; border:1px solid #e3b4b4; color:var(--bad);
                  border-radius:.55rem; padding:.3rem .8rem; font-size:.8rem; cursor:pointer;
                  transition:background .12s; }}
  button.clear:hover {{ background:var(--bad-bg); }}

  /* ---------- controls ---------- */
  .row {{ display:flex; gap:1rem; margin:1.2rem 0 .6rem; flex-wrap:wrap; }}
  .row > div {{ flex:1 1 14rem; }}
  label {{ font-size:.8rem; font-weight:600; text-transform:uppercase; letter-spacing:.06em;
           color:var(--muted); display:block; margin-bottom:.35rem; }}
  select {{ width:100%; padding:.65rem .8rem; border:1px solid #c3c9d9; border-radius:.6rem;
            font-size:.95rem; background:#fff; color:var(--ink); }}
  select:focus {{ outline:2px solid var(--accent); outline-offset:1px; }}
  button.go {{ width:100%; background:linear-gradient(135deg,var(--accent),var(--accent-2));
               color:#fff; border:0; padding:.85rem 2rem; font-size:1.02rem; font-weight:600;
               border-radius:.7rem; cursor:pointer; box-shadow:0 4px 14px rgba(59,91,219,.35);
               transition:transform .12s, box-shadow .12s; margin-top:1.35rem; }}
  button.go:hover {{ transform:translateY(-1px); box-shadow:0 6px 18px rgba(59,91,219,.45); }}
  button.go:disabled {{ opacity:.55; cursor:wait; transform:none; }}
  .status {{ color:var(--muted); font-size:.87rem; margin-top:.7rem; min-height:1.3em; }}
  .privacy {{ display:flex; gap:.55rem; align-items:flex-start; background:var(--ok-bg);
              border:1px solid #bfe3cd; color:#0a5c36; border-radius:.7rem;
              padding:.7rem .95rem; font-size:.84rem; margin-top:1.2rem; }}
  .error {{ background:var(--bad-bg); color:var(--bad); border:1px solid #f2b8b5;
            padding:.8rem 1.1rem; border-radius:.7rem; margin:0 0 1.1rem; }}
  .disclaimer {{ background:var(--warn-bg); border:1px solid #eadfa0; padding:.75rem 1rem;
                 border-radius:.7rem; font-size:.8rem; color:#665c1e; margin-top:1.4rem; }}
  footer {{ color:#8891a5; font-size:.78rem; text-align:center; padding:1.4rem; }}
  footer a {{ color:inherit; }}
  @media (max-width:640px) {{ header .logo {{ font-size:1.5rem; }} .card {{ padding:1.1rem; }} }}
</style></head>
<body>
<header><div class="inner">
  <span class="logo"><span class="mark">📄</span>PaperEngine</span>
  <p class="tag">Pre-submission rejection-risk screening for research papers —
     the checks editors, reviewers and integrity desks actually run.</p>
  <div class="chips">
    <span class="chip">{n_engines} check engines</span>
    <span class="chip">International + Indian statutory standards</span>
    <span class="chip">Statcheck · GRIM · SPRITE · UGC 2018</span>
    <span class="chip">{intel_chip}</span>
    <span class="chip">100% local — zero telemetry</span>
  </div>
</div></header>
<main>
{banner}
{form_html}
{result_html}
<div class="disclaimer"><b>Honest limits:</b> overlap is a signal, not plagiarism. AI-risk is probabilistic, not proof.
Venue limits are typical values — confirm the venue's current guide. The readiness score is informational, never a verdict.</div>
</main>
<footer>PaperEngine · {n_engines} engines · statcheck p-value verification · GRIM consistency ·
UGC statutory similarity · <a href="https://github.com/abnsr-sol/paperengine">source</a></footer>
</body></html>"""


def _upload_form(selected: str = "generic") -> str:
    n = len(ALL_ENGINES)
    return f"""
<div class="card">
<form id="f" method="post" action="/check" enctype="multipart/form-data">
  <div class="drop" id="drop">
    <input type="file" id="file" name="file" accept=".docx,.txt,.md,.markdown,.tex,.pdf">
    <div id="drop-empty">
      <span class="icon">📄</span>
      <div class="big">Drag your manuscript here — or click to choose</div>
      <div class="small">.docx · .txt · .md · .tex · .pdf (max 25 MB)</div>
    </div>
    <div id="drop-filled" style="display:none">
      <span class="icon">✅</span>
      <div class="big">Manuscript selected</div>
      <div class="fileline"><span class="fname" id="picked-name"></span><button type="button" class="clear" id="clear-file">✕ change</button></div>
      <div class="small" style="margin-top:.5rem">Click anywhere in this box to pick a different file</div>
    </div>
  </div>
  <div class="row">
    <div>
      <label for="standard">Standard</label>
      <select id="standard" name="standard" onchange="syncVenues()">
        <option value="international" selected>International (IEEE/Elsevier/ACM…)</option>
        <option value="national">National (India: UGC/AICTE/NAAC)</option>
      </select>
    </div>
    <div>
      <label for="venue">Venue preset</label>
      <select id="venue" name="venue">{_venue_options(selected)}</select>
      <p id="venue-hint" style="margin:.4rem 0 0;font-size:.78rem;color:var(--muted);line-height:1.45;
         background:var(--bg);border:1px solid var(--line);border-radius:.5rem;padding:.45rem .6rem;
         min-height:2.4em;"></p>
    </div>
  </div>
  <button class="go" id="go" type="submit">Check my paper →</button>
  <div class="status" id="status"></div>
  <div class="privacy">🔒&nbsp;<span><b>Nothing is stored.</b> Your file is parsed in memory,
  checked by all {n} engines, and the temporary copy is deleted the moment your report is
  rendered — every time, no exceptions. The server is localhost-only and no data ever
  leaves this machine.</span></div>
</form>
</div>
<script>
  const VENUE_HINTS = {_venue_hints_js()};
  const drop = document.getElementById('drop'), file = document.getElementById('file');
  drop.addEventListener('click', () => file.click());
  ['dragover','dragenter'].forEach(e => drop.addEventListener(e, ev => {{ ev.preventDefault(); drop.classList.add('over'); }}));
  ['dragleave','drop'].forEach(e => drop.addEventListener(e, ev => {{ ev.preventDefault(); drop.classList.remove('over'); }}));
  drop.addEventListener('drop', ev => {{ if (ev.dataTransfer.files.length) {{ file.files = ev.dataTransfer.files; showName(); }} }});
  file.addEventListener('change', showName);
  function setPicked(zoneId, emptyId, filledId, nameId, f) {{
    const zone = document.getElementById(zoneId);
    const empty = document.getElementById(emptyId), filled = document.getElementById(filledId);
    if (f) {{
      zone.classList.add('selected');
      empty.style.display = 'none';
      filled.style.display = '';
      document.getElementById(nameId).textContent = f.name;
    }} else {{
      zone.classList.remove('selected');
      filled.style.display = 'none';
      empty.style.display = '';
    }}
  }}
  function showName() {{
    setPicked('drop', 'drop-empty', 'drop-filled', 'picked-name', file.files[0] || null);
    document.getElementById('status').textContent = '';
  }}
  document.getElementById('clear-file').addEventListener('click', ev => {{
    ev.stopPropagation();   // don't re-open the picker when clearing
    file.value = '';
    showName();
  }});
  function syncVenues() {{
    const std = document.getElementById('standard').value;
    const venue = document.getElementById('venue');
    document.querySelectorAll('#venue optgroup').forEach(g => {{
      g.style.display = (std === 'national') === (g.label.startsWith('National')) ? '' : 'none';
    }});
    // reset a stale selection from the other standard so the submitted
    // venue always agrees with the chosen standard
    const opt = venue.options[venue.selectedIndex];
    if (opt && opt.parentElement.tagName === 'OPTGROUP' && opt.parentElement.style.display === 'none') {{
      venue.selectedIndex = 0;  // back to generic
    }}
    updateHint();
  }}
  document.getElementById('venue').addEventListener('change', updateHint);
  document.getElementById('f').addEventListener('submit', () => {{
    document.getElementById('go').disabled = true;
    document.getElementById('go').textContent = 'Running {n} engines…';
    document.getElementById('status').textContent = 'Parsing, checking, scoring — this takes a few seconds…';
  }});
  syncVenues();  // also calls updateHint() once
</script>"""


def _run_check(filename: str, data: bytes, standard: str, venue: str) -> str:
    """Parse + run all engines + render the HTML report body."""
    ext = os.path.splitext(filename)[1].lower()
    suffix = ext if ext in _ALLOWED_EXT else ".txt"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(data)
        tmp.close()
        doc = load_document(tmp.name)
        rules = get_rules(venue)
        ctx = CheckContext(venue=describe(venue), rules=rules, online=False,
                           max_online_checks=0)
        report = RiskReport(document_name=doc.name, venue=describe(venue))
        report.stats = {"words": f"{doc.word_count:,}",
                        "standard": "National (Indian)" if standard == "national" else "International"}
        findings, engine_errors = run_all_engines(doc, ctx)
        if engine_errors:
            report.stats["engine warnings"] = ", ".join(
                e.split(":")[0] for e in engine_errors)
        report.extend(findings)
        return render_html(report)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _parse_multipart(body: bytes, content_type: str):
    """Minimal multipart/form-data parser: returns (files, fields) where files
    maps form field name -> (filename, bytes) for every uploaded file."""
    m = _BOUNDARY_RE.search(content_type or "")
    if not m:
        return {}, {}
    boundary = ("--" + m.group(1)).encode()
    parts = body.split(boundary)
    files, fields = {}, {}
    for part in parts:
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        if b"\r\n\r\n" not in part:
            continue
        raw_headers, content = part.split(b"\r\n\r\n", 1)
        headers = raw_headers.decode("utf-8", "replace").lower()
        name_m = re.search(r'name="([^"]+)"', headers)
        if not name_m:
            continue
        name = name_m.group(1)
        if 'filename="' in headers:
            fn = re.search(r'filename="([^"]*)"', headers)
            filename = fn.group(1) if fn else "upload"
            files[name] = (filename, content)
        else:
            fields[name] = content.decode("utf-8", "replace").strip()
    return files, fields


class Handler(BaseHTTPRequestHandler):
    server_version = "PaperEngine/1.4"

    def log_message(self, fmt, *args):  # quieter logs
        pass

    def _send_html(self, body: str, code: int = 200):
        payload = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send_html(_page(form_html=_upload_form()))
        else:
            self._send_html(_page(error="Page not found."), code=404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path != "/check":
            self._send_html(_page(error="Unknown action."), code=404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > _MAX_UPLOAD + 65536:
            # Drain a bounded amount so the client can finish SENDING and
            # cleanly receive the 413 — responding while the client is still
            # mid-upload resets the connection (raw WinError/browser error)
            # instead of showing our friendly limit page.
            remaining = min(length, 64 * 1024 * 1024)
            while remaining > 0:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
            self._send_html(_page(form_html=_upload_form(),
                                  error="Upload missing or too large (25 MB limit)."), code=413)
            return
        body = self.rfile.read(length)
        files, fields = _parse_multipart(body, self.headers.get("Content-Type", ""))
        main_file = files.get("file")
        if not main_file:
            self._send_html(_page(form_html=_upload_form(),
                                  error="No file received — please choose a manuscript."), code=400)
            return
        filename, filebytes = main_file
        if not filename.lower().endswith(_ALLOWED_EXT):
            self._send_html(_page(form_html=_upload_form(),
                                  error="Unsupported file type — use .docx, .txt, .md, .tex or .pdf."), code=415)
            return
        standard = fields.get("standard", "international")
        if standard not in ("international", "national"):
            standard = "international"
        venue = fields.get("venue", "generic")
        if venue != "generic" and venue not in PRESETS:
            venue = "generic"
        # Server-side coherence: the venue's own standard always wins. If the
        # form's standard select disagrees (stale UI state), follow the venue
        # so the applied ruleset and the displayed standard can never diverge.
        venue_std = (PRESETS.get(venue) or {}).get("standard", "international")
        if venue != "generic":
            standard = venue_std
        # honor the national/international choice when venue is generic
        if standard == "national" and venue == "generic":
            venue = "ugc_care"
        elif standard == "international" and venue == "generic":
            venue = "ieee_conference"
        # (before/after comparison is CLI-only: `papercheck --compare`)
        try:
            result = _run_check(filename, filebytes, standard, venue)
        except (UnsupportedFormatError, PdfExtractionError) as exc:
            self._send_html(_page(form_html=_upload_form(venue),
                                  error=f"Could not read the manuscript: {exc}"), code=422)
            return
        except Exception as exc:  # noqa: BLE001 — one bad paper must not kill the server
            self._send_html(_page(form_html=_upload_form(venue),
                                  error=f"Checking failed: {exc}"), code=500)
            return
        self._send_html(result)


def serve(port: int = 8765, open_browser: bool = True) -> None:
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as exc:
        if getattr(exc, "errno", None) in (98, 10048) or "in use" in str(exc).lower():
            print(f"Port {port} is already in use — try:  papercheck --gui --port {port + 1}")
            return
        raise
    url = f"http://localhost:{port}"
    print(f"PaperEngine GUI running at {url}")
    print("The window stays open until you press Ctrl+C (then it prints 'Stopped.' and exits)")
    print(f"If your browser did not open by itself, paste this into it:  {url}")
    print("Local only — nothing is uploaded to the internet.")
    if open_browser:
        try:
            opened = webbrowser.open(url)
        except Exception:
            opened = False
        if not opened:
            print("(Automatic browser open failed — use the URL above.)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
