"""Generate sample_paper.docx from sample_paper.txt (stdlib only).

A .docx is a zip of XML, so we can write a minimal but valid one with
zipfile + string templates. This intentionally mixes two fonts in one
paragraph so the compliance engine's font check has something to find.
"""

import os
import re
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "sample_paper.txt")
DST = os.path.join(ROOT, "sample_paper.docx")

NS_DECL = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
)

def run(text: str, font: str = "Times New Roman", accent_font: str = "Calibri") -> str:
    paras = []
    para_index = 0
    for para in re.split(r"\n\s*\n", text.strip()):
        p = para.strip()
        if not p:
            continue
        # One <w:p> per line so headings stay standalone (like a real document).
        # Alternate fonts every other paragraph to simulate copy-pasted text.
        for line in p.splitlines():
            line = line.strip()
            if not line:
                continue
            f = font if (para_index // 2) % 2 == 0 else accent_font
            escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            paras.append(
                f'<w:p><w:r><w:rPr><w:rFonts w:ascii="{f}" w:hAnsi="{f}"/></w:rPr>'
                f"<w:t xml:space=\"preserve\">{escaped}</w:t></w:r></w:p>"
            )
            para_index += 1
    body = "".join(paras)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<w:document {NS_DECL}><w:body>{body}</w:body></w:document>'
    )


def main() -> None:
    with open(SRC, encoding="utf-8") as fh:
        text = fh.read()
    document_xml = run(text)
    with zipfile.ZipFile(DST, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>")
        zf.writestr("_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>')
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("docProps/core.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/">'
            "<dc:title>A Novel Framework for Intelligent Cloud-Based Data Analytics</dc:title>"
            "<dc:creator>Sample Generator</dc:creator></cp:coreProperties>")
    print(f"Wrote {DST}")


if __name__ == "__main__":
    main()