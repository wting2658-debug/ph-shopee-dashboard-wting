import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import download_sheet_data as downloader


class DownloadSheetDataTests(unittest.TestCase):
    def download(self, directory, content, prefix, headers):
        response = io.BytesIO(content)
        response.status = 200
        with patch.object(downloader, 'DATA_DIR', Path(directory)), patch.object(downloader, 'urlopen', return_value=response):
            downloader.download_source('Test source', '123', 'source.csv', prefix, required_headers=headers)

    def test_multiline_header_keeps_required_columns_after_quoted_newline(self):
        content = ('\ufeffYear,Quarter,Date,"Returned/\nRefunded Orders",# of buyers,# of new buyers,Units (Add to Cart)\r\n'
                   '2026,Q4,2026/11/15,0,1820,863,100\r\n').encode('utf-8')
        with tempfile.TemporaryDirectory() as directory:
            self.download(directory, content, 'Year,Quarter', ('Date', '# of buyers', '# of new buyers', 'Units (Add to Cart)'))
            self.assertEqual((Path(directory)/'source.csv').read_bytes(), content)
            self.assertFalse((Path(directory)/'source.csv.tmp').exists())

    def test_single_line_unicode_header_still_accepts_existing_prefix(self):
        content = 'date,产品ID,汇率\r\n2026/11/15,123,8.0\r\n'.encode('utf-8')
        with tempfile.TemporaryDirectory() as directory:
            self.download(directory, content, 'date,产品ID', ('汇率',))
            self.assertEqual((Path(directory)/'source.csv').read_bytes(), content)

    def test_invalid_source_keeps_previous_download_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)/'source.csv'
            destination.write_bytes(b'previous valid data')
            with self.assertRaisesRegex(RuntimeError, '表头不符合预期'):
                self.download(directory, b'Year,Quarter,Date\r\n2026,Q4,2026/11/15\r\n', 'Year,Quarter', ('# of new buyers',))
            self.assertEqual(destination.read_bytes(), b'previous valid data')
            self.assertFalse((Path(directory)/'source.csv.tmp').exists())


if __name__ == '__main__':
    unittest.main()
