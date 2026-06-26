import os, tempfile, unittest
from lib.io_utils import read_text_safe

class TestIoUtils(unittest.TestCase):
    def test_reads_utf8(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write("hola mundo")
            self.assertEqual(read_text_safe(p), "hola mundo")

    def test_missing_file_returns_empty(self):
        self.assertEqual(read_text_safe(os.path.join("no", "such", "file_xyz.txt")), "")

    def test_bad_bytes_do_not_raise(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "b.bin")
            with open(p, "wb") as f:
                f.write(b"\xff\xfe\x00bad\x80bytes")
            result = read_text_safe(p)
            self.assertIsInstance(result, str)  # must not raise

if __name__ == "__main__":
    unittest.main()
