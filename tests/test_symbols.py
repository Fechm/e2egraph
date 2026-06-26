import unittest
from lib.symbols import extract_symbols_fallback, ctags_available

class TestSymbols(unittest.TestCase):
    def test_fallback_finds_py_and_ts_symbols(self):
        py = "def foo():\n    pass\nclass Bar:\n    pass\n"
        ts = "export function baz() {}\nclass Qux {}\n"
        py_syms = {s["name"] for s in extract_symbols_fallback("a.py", "py", py)}
        ts_syms = {s["name"] for s in extract_symbols_fallback("b.ts", "ts", ts)}
        self.assertEqual(py_syms, {"foo", "Bar"})
        self.assertEqual(ts_syms, {"baz", "Qux"})

    def test_ctags_available_returns_bool(self):
        self.assertIn(ctags_available(), (True, False))

if __name__ == "__main__":
    unittest.main()
