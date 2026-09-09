"""Reproduce the GUI 'bad operand type for unary -: str' crash.

Runs the full pipeline (all engines + render) across every venue preset and
several document formats, printing the exact traceback for any failure.
"""
import os
import sys
import tempfile
import traceback
import io
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from papercheck.webui import _run_check  # noqa: E402
from papercheck.venues import PRESETS  # noqa: E402

RICH = """# Title of the Study

## Abstract
This study examines effect of method X on outcome Y with n=150 participants.
Results were significant (t(28) = 2.45, p = .021). The mean was 3.5 (SD = 1.2).
Keywords: machine learning, deep learning

## 1. Introduction
Machine learning has transformed many domains. Prior work [1] showed gains.
We refer to Figure 3 and Table 2 for details. Random forest models were used.
As an AI language model, this text contains artifacts. Furthermore, moreover.
This is a groundbreaking revolutionary unprecedented approach [2][3][4][5].

## 2. Methods
We trained a 70B parameter model on 4 GPUs with AdamW for 100 epochs.
Participants completed a 7-point Likert scale (M = 4.2, SD = 0.9, N = 30).
Data available on request from the authors. Ethics approval was obtained.
We measured latency of 1.2 ms between US and EU datacenters.

## 3. Results
Accuracy was 97%. p = 0.048, p = 0.049, p = 0.046 without correction.
The sample was heated to 300 K. baseline accuracy 88.2% vs 89.1%.
See https://github.com/user/repo/tree/main for code. Error! Reference source not found.

## 4. Discussion
This proves causally that method X cures the condition. Trivially, the proof follows.
Limitations are minimal. ?? appears when refs break.

## References
[1] Smith, J. (2020). On learning. Journal of Things. doi: 10.1000/fake-doi-xx
[2] Doe, A. (2019). More things. doi: 10.1000/fake-doi-yy
[3] Roe, B. (2018). Even more. doi: 10.1000/fake-doi-zz
[4] Coe, C. (2017). Things again. doi: 10.1000/fake-doi-ww
[5] Woe, D. (2016). Final things. doi: 10.1000/fake-doi-vv
""" * 4  # pad past 200-word gates

PAD = "Additional context sentence for length. " * 200


def make_txt():
    return RICH + PAD, ".txt"


def make_docx():
    try:
        import docx  # python-docx
        d = docx.Document()
        for line in (RICH + PAD).splitlines():
            d.add_paragraph(line)
        buf = io.BytesIO()
        d.save(buf)
        return buf.getvalue(), ".docx"
    except ImportError:
        # minimal OOXML by hand
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            z.writestr("[Content_Types].xml",
                       '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                       '<Default Extension="xml" ContentType="application/xml"/></Types>')
            body = "".join(f"<w:p><w:r><w:t>{l}</w:t></w:r></w:p>"
                           for l in (RICH + PAD).splitlines())
            z.writestr("word/document.xml",
                       f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                       f'<w:body>{body}</w:body></w:document>')
        return out.getvalue(), ".docx"


def make_pdf():
    from fpdf import FPDF
    def latin(s):
        return s.encode("latin-1", "replace").decode("latin-1")
    pdf = FPDF(format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(True, 15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_xy(20, 20)
    pdf.cell(170, 6, latin("Title of the Study"))
    pdf.set_font("Helvetica", "", 9)
    y = 32
    for line in RICH.splitlines()[:40]:
        pdf.set_xy(20, y)
        pdf.cell(75, 5, latin(line[:70]))
        pdf.set_xy(320 - 280, y)  # right column
        pdf.cell(75, 5, latin(("RIGHT: " + line)[:70]))
        y += 6
        if y > 270:
            pdf.add_page()
            y = 20
    return bytes(pdf.output()), ".pdf"


MAKERS = [("txt", make_txt), ("docx", make_docx), ("pdf", make_pdf)]


def main():
    fails = 0
    total = 0
    for maker_name, maker in MAKERS:
        try:
            payload, ext = maker()
        except Exception as exc:  # noqa: BLE001
            print(f"[skip] {maker_name}: maker failed: {exc}")
            continue
        for venue in sorted(PRESETS):
            for standard in ("international", "national"):
                total += 1
                fd, path = tempfile.mkstemp(suffix=ext)
                with os.fdopen(fd, "wb") as f:
                    f.write(payload if isinstance(payload, bytes) else payload.encode("utf-8"))
                try:
                    html = _run_check(os.path.basename(path),
                                      payload if isinstance(payload, bytes) else payload.encode("utf-8"),
                                      standard, venue)
                    if "Checking failed" in html:
                        fails += 1
                        print(f"[FAIL-render] {maker_name} {standard}/{venue}: report contains error page")
                except Exception:  # noqa: BLE001
                    fails += 1
                    print(f"\n===== CRASH {maker_name} standard={standard} venue={venue} =====")
                    traceback.print_exc()
                finally:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass

    print(f"\n{total - fails}/{total} preset x format combos OK, {fails} failures")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
