"""Compile and exercise the production file copier using real JVM file IO.

Only the application logger is replaced. Channel wrappers force short/zero
transfers and failures. Set MGX_LARGE_COPY_TEST=1 for a real >2 GiB SHA-256 check.
Android gallery saving and decoding require the separate emulator test.
"""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app/src/main/java/org/thunderdog/challegram/util/FileCopyUtils.java"


class FileCopyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = tempfile.TemporaryDirectory(prefix="file-copy-classes-")
        logger = Path(cls.classes.name) / "Log.java"
        logger.write_text("""package org.thunderdog.challegram;
public final class Log {
  public static void e(String message, Throwable error) { }
  public static void w(String message) { }
}
""")
        subprocess.run(["javac", "-Xlint:all", "-d", cls.classes.name,
                        str(logger), str(SOURCE), str(ROOT / "tests/FileCopyUtilsTest.java")], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.classes.cleanup()

    def run_case(self, scenario):
        with tempfile.TemporaryDirectory(prefix="file-copy-data-") as data:
            subprocess.run(["java", "-ea", "-cp", self.classes.name,
                            "org.thunderdog.challegram.util.FileCopyUtilsTest", scenario, data],
                           check=True, timeout=180)

    def test_overwrite_has_exact_bytes_and_no_old_tail(self): self.run_case("overwrite")
    def test_empty_file(self): self.run_case("empty")
    def test_partial_transfer_is_retried(self): self.run_case("short-transfer")
    def test_zero_transfer_uses_buffered_copy(self): self.run_case("zero-transfer")
    def test_zero_then_partial_transfer_preserves_offsets(self): self.run_case("zero-then-short")
    def test_unexpected_end_of_source_fails(self): self.run_case("early-eof")
    def test_no_write_progress_fails(self): self.run_case("stalled-write")
    def test_negative_control_exposes_single_transfer_bug(self): self.run_case("single-transfer-control")
    def test_same_file_is_not_truncated(self): self.run_case("same-file")
    def test_missing_source_preserves_existing_destination(self): self.run_case("missing-source")
    def test_directory_destination_is_preserved(self): self.run_case("directory-target")

    @unittest.skipUnless(os.environ.get("MGX_LARGE_COPY_TEST") == "1", "opt-in real >2 GiB disk IO")
    def test_real_file_over_2_gib_matches_full_sha256(self): self.run_case("large")


if __name__ == "__main__":
    unittest.main()
