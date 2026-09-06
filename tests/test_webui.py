"""Tests for the local web GUI (multipart parsing + full check flow)."""
import unittest
import io
import sys, os, threading, time, urllib.request
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from papercheck.webui import _parse_multipart, _run_check, Handler


def _multipart(fields, fname, content):
    boundary = 'XxUnitxX'
    buf = io.BytesIO()
    for k, v in fields.items():
        buf.write(('--' + boundary + '\r\n').encode())
        buf.write(('Content-Disposition: form-data; name="' + k + '"\r\n\r\n' + v + '\r\n').encode())
    buf.write(('--' + boundary + '\r\n').encode())
    buf.write(('Content-Disposition: form-data; name="file"; filename="' + fname + '"\r\n').encode())
    buf.write(b'Content-Type: application/octet-stream\r\n\r\n')
    buf.write(content)
    buf.write(b'\r\n')
    buf.write(('--' + boundary + '--\r\n').encode())
    return buf.getvalue(), 'multipart/form-data; boundary=' + boundary


class TestMultipartParser(unittest.TestCase):
    def test_parses_fields_and_file(self):
        body, ctype = _multipart({'standard': 'national', 'venue': 'ugc_care'},
                                 'paper.docx', b'PK fake docx')
        fn, data, fields = _parse_multipart(body, ctype)
        self.assertEqual(fn, 'paper.docx')
        self.assertEqual(data, b'PK fake docx')
        self.assertEqual(fields['standard'], 'national')
        self.assertEqual(fields['venue'], 'ugc_care')

    def test_no_boundary_returns_none(self):
        fn, data, fields = _parse_multipart(b'junk', 'text/plain')
        self.assertIsNone(fn)
        self.assertIsNone(data)


class TestRunCheck(unittest.TestCase):
    def test_national_run_produces_report(self):
        # tiny valid docx built via zip (ingestion reads word/document.xml)
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('[Content_Types].xml',
                       '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                       '<Default Extension="xml" ContentType="application/xml"/></Types>')
            z.writestr('word/document.xml',
                       '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                       '<w:body><w:p><w:r><w:t>Abstract</w:t></w:r></w:p>'
                       '<w:p><w:r><w:t>We study graph clustering methods with experiments and results.</w:t></w:r></w:p></w:body></w:document>')
        out = _run_check('tiny.docx', buf.getvalue(), 'national', 'ugc_care')
        self.assertIn('/100 readiness', out)
        self.assertIn('badge', out)

    def test_international_run_produces_report(self):
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('[Content_Types].xml',
                       '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                       '<Default Extension="xml" ContentType="application/xml"/></Types>')
            z.writestr('word/document.xml',
                       '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                       '<w:body><w:p><w:r><w:t>Abstract</w:t></w:r></w:p>'
                       '<w:p><w:r><w:t>We benchmark clustering algorithms on graphs.</w:t></w:r></w:p></w:body></w:document>')
        out = _run_check('tiny.docx', buf.getvalue(), 'international', 'ieee_conference')
        self.assertIn('/100 readiness', out)


class TestServerEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from http.server import ThreadingHTTPServer
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def _url(self, path):
        return f'http://127.0.0.1:{self.port}{path}'

    def test_home_page(self):
        r = urllib.request.urlopen(self._url('/'), timeout=15)
        html = r.read().decode('utf-8')
        self.assertEqual(r.status, 200)
        self.assertIn('Drag your manuscript', html)
        self.assertIn('ugc_care', html)

    def test_check_flow_national(self):
        body, ctype = _multipart({'standard': 'national', 'venue': 'ugc_care'},
                                 'paper.docx', b'PK fake')
        req = urllib.request.Request(self._url('/check'), data=body,
                                     headers={'Content-Type': ctype})
        # fake docx will fail parse -> server returns 4xx/5xx, not a crash
        try:
            r = urllib.request.urlopen(req, timeout=60)
            self.assertEqual(r.status, 200)
        except urllib.error.HTTPError as e:
            self.assertIn(e.code, (400, 415, 422, 500))

    def test_rejects_bad_extension(self):
        body, ctype = _multipart({}, 'evil.exe', b'MZ')
        req = urllib.request.Request(self._url('/check'), data=body,
                                     headers={'Content-Type': ctype})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req, timeout=30)
        self.assertEqual(cm.exception.code, 415)

    def test_404(self):
        try:
            urllib.request.urlopen(self._url('/nope'), timeout=15)
            self.fail('expected 404')
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)


if __name__ == '__main__':
    unittest.main()
