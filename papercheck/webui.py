"""Local web GUI: drag-and-drop manuscript checking in the browser.

Zero dependencies beyond PaperCheck itself (stdlib http.server). The uploaded
file never leaves your machine - it is parsed in memory, checked by the same
65 engines as the CLI, and rendered as the standard HTML report.

    papercheck --gui              # serve on http://localhost:8765
    papercheck --gui --port 9000  # custom port

Security posture:
    - binds 127.0.0.1 only (not reachable from the network)
    - size cap: 25 MB per upload
    - only .docx/.txt/.md/.markdown/.tex/.pdf accepted
    - multipart/form-data parsing done manually (no dependencies)
    - X-Frame-Options: DENY, no caching of report pages
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

from .checks import ALL_ENGINES, CheckContext
from .compare import compare as compare_reports
from .compare import render_html as render_compare_html
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


def _page(form_html: str = "", result_html: str = "", error: str = "") -> str:
    banner = ""
    if error:
        banner = f'<div class="error">{_html.escape(error)}</div>'
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PaperEngine — local paper checker</title>
<style>
  :root {{ --ink:#1a2233; --accent:#2456d6; --bad:#c62828; --ok:#1b7f4d; }}
  * {{ box-sizing:border-box; }}
  body {{ font-family:Georgia,'Times New Roman',serif; margin:0; background:#f4f4ef; color:var(--ink); }}
  header {{ background:var(--ink); color:#fff; padding:18px 28px; }}
  header h1 {{ margin:0; font-size:1.35rem; letter-spacing:.5px; }}
  header p {{ margin:4px 0 0; opacity:.75; font-size:.85rem; }}
  main {{ max-width:900px; margin:0 auto; padding:24px; }}
  .drop {{ border:2px dashed #9aa3b5; border-radius:12px; background:#fff; padding:38px 20px; text-align:center; cursor:pointer; transition:.15s; }}
  .drop.over {{ border-color:var(--accent); background:#eef3ff; }}
  .drop input {{ display:none; }}
  .drop .big {{ font-size:1.1rem; margin-bottom:6px; }}
  .drop .small {{ color:#667; font-size:.85rem; }}
  .drop.selected {{ border-color:var(--ok); border-style:solid; background:#e9f7ee; }}
  .drop.selected .big {{ color:var(--ok); font-size:1.3rem; }}
  .drop .fileline {{ display:flex; align-items:center; justify-content:center; gap:10px; flex-wrap:wrap; }}
  .drop .fname {{ font-family:Consolas,monospace; font-size:1.05rem; color:var(--ink); background:#fff; border:1px solid #cfe3d6; border-radius:8px; padding:6px 14px; max-width:100%; overflow-wrap:anywhere; }}
  button.clear {{ background:#fff; border:1px solid #d66; color:#c62828; border-radius:6px; padding:4px 12px; font-size:.8rem; cursor:pointer; }}
  button.clear:hover {{ background:#fdecea; }}
  .row {{ display:flex; gap:14px; margin:16px 0; flex-wrap:wrap; }}
  label {{ font-size:.85rem; color:#445; display:block; margin-bottom:4px; }}
  select {{ padding:8px 10px; border:1px solid #b9c0cf; border-radius:8px; font-size:.95rem; min-width:260px; background:#fff; }}
  button.go {{ background:var(--accent); color:#fff; border:0; padding:12px 30px; font-size:1rem; border-radius:8px; cursor:pointer; }}
  button.go:disabled {{ opacity:.5; cursor:wait; }}
  .error {{ background:#fdecea; color:var(--bad); border:1px solid #f2b8b5; padding:12px 16px; border-radius:8px; margin:14px 0; }}
  .status {{ color:#667; font-size:.85rem; margin-top:10px; min-height:1.2em; }}
  footer {{ color:#889; font-size:.78rem; text-align:center; padding:18px; }}
  .disclaimer {{ background:#fffbe6; border:1px solid #eadfa0; padding:10px 14px; border-radius:8px; font-size:.82rem; color:#665c1e; margin-top:14px; }}
</style></head>
<body>
<header><h1>PaperEngine</h1>
<p>65 rejection-risk engines · international + Indian standards · 100% local — your paper never leaves this machine</p></header>
<main>
{banner}
{form_html}
{result_html}
<div class="disclaimer"><b>Honest limits:</b> overlap is a signal, not plagiarism. AI-risk is probabilistic, not proof.
Venue limits are typical values — confirm the venue's current guide. The readiness score is informational, never a verdict.</div>
</main>
<footer>PaperEngine v1.1 — runs offline by default · now with before/after revision comparison · <a href="https://github.com/abnsr-sol/paperengine" style="color:inherit">source</a></footer>
</body></html>"""


def _upload_form(selected: str = "generic") -> str:
    return f"""
<form id="f" method="post" action="/check" enctype="multipart/form-data">
  <div class="drop" id="drop">
    <input type="file" id="file" name="file" accept=".docx,.txt,.md,.markdown,.tex,.pdf">
    <div id="drop-empty">
      <div class="big">📄 Drag your manuscript here — or click to choose</div>
      <div class="small">.docx · .txt · .md · .tex · .pdf (max 25 MB)</div>
    </div>
    <div id="drop-filled" style="display:none">
      <div class="big">✅ Manuscript selected</div>
      <div class="fileline"><span class="fname" id="picked-name"></span><button type="button" class="clear" id="clear-file">✕ change</button></div>
      <div class="small" style="margin-top:6px">Click anywhere in this box to pick a different file</div>
    </div>
  </div>
  <div class="drop" id="drop2" style="padding:16px 20px;background:#fbfbf7">
    <input type="file" id="revised" name="revised" accept=".docx,.txt,.md,.markdown,.tex,.pdf">
    <div id="drop2-empty">
      <div class="big" style="font-size:.95rem">🔁 Optional: drop the <b>revised</b> version too → before/after comparison</div>
      <div class="small">Shows what you fixed, what is still open, and what is new</div>
    </div>
    <div id="drop2-filled" style="display:none">
      <div class="big" style="font-size:.95rem">✅ Revised version selected</div>
      <div class="fileline"><span class="fname" id="picked-name2"></span><button type="button" class="clear" id="clear-file2">✕ change</button></div>
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
    </div>
    <div style="align-self:flex-end">
      <button class="go" id="go" type="submit">Check my paper</button>
    </div>
  </div>
  <div class="status" id="status"></div>
</form>
<script>
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
  const drop2 = document.getElementById('drop2'), rev = document.getElementById('revised');
  drop2.addEventListener('click', () => rev.click());
  ['dragover','dragenter'].forEach(e => drop2.addEventListener(e, ev => {{ ev.preventDefault(); drop2.classList.add('over'); }}));
  ['dragleave','drop'].forEach(e => drop2.addEventListener(e, ev => {{ ev.preventDefault(); drop2.classList.remove('over'); }}));
  drop2.addEventListener('drop', ev => {{ if (ev.dataTransfer.files.length) {{ rev.files = ev.dataTransfer.files; showName2(); }} }});
  rev.addEventListener('change', showName2);
  function showName2() {{
    setPicked('drop2', 'drop2-empty', 'drop2-filled', 'picked-name2', rev.files[0] || null);
  }}
  document.getElementById('clear-file2').addEventListener('click', ev => {{
    ev.stopPropagation();
    rev.value = '';
    showName2();
  }});
  function syncVenues() {{
    const std = document.getElementById('standard').value;
    document.querySelectorAll('#venue optgroup').forEach(g => {{
      g.style.display = (std === 'national') === (g.label.startsWith('National')) ? '' : 'none';
    }});
  }}
  document.getElementById('f').addEventListener('submit', () => {{
    document.getElementById('go').disabled = true;
    document.getElementById('status').textContent = 'Running 65 engines — this takes a few seconds…';
  }});
  syncVenues();
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
        for engine in ALL_ENGINES:
            report.extend(engine(doc, ctx))
        return render_html(report)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _save_temp(filename: str, data: bytes) -> str:
    ext = os.path.splitext(filename)[1].lower()
    suffix = ext if ext in _ALLOWED_EXT else ".txt"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(data)
        tmp.close()
        return tmp.name
    except Exception:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


def _run_compare(orig_name: str, orig_bytes: bytes, rev_name: str, rev_bytes: bytes,
                 standard: str, venue: str) -> str:
    """Before/after flow: run all engines on both versions and diff findings."""
    p1 = p2 = None
    try:
        p1 = _save_temp(orig_name, orig_bytes)
        p2 = _save_temp(rev_name, rev_bytes)
        cmp = compare_reports(p1, p2, venue=venue, standard=standard)
        return render_compare_html(cmp)
    finally:
        for p in (p1, p2):
            if p:
                try:
                    os.unlink(p)
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
    server_version = "PaperEngine/1.1"

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
        revised = files.get("revised")
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
        # honor the national/international choice even when venue says otherwise
        if standard == "national" and venue == "generic":
            venue = "ugc_care"
        elif standard == "international" and venue == "generic":
            venue = "ieee_conference"
        # Comparison flow: a revised version was also uploaded.
        if revised:
            try:
                result = _run_compare(filename, filebytes, revised[0], revised[1],
                                      standard, venue)
            except (UnsupportedFormatError, PdfExtractionError) as exc:
                self._send_html(_page(form_html=_upload_form(venue),
                                      error=f"Could not read a manuscript: {exc}"), code=422)
                return
            except Exception as exc:  # noqa: BLE001 — one bad pair must not kill the server
                self._send_html(_page(form_html=_upload_form(venue),
                                      error=f"Comparison failed: {exc}"), code=500)
                return
            self._send_html(result)
            return
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
