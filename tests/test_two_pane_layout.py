"""Run real two-pane threshold/geometry production code without Android stubs."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class TwoPaneLayoutTest(unittest.TestCase):
    def test_window_thresholds_and_pane_geometry(self):
        with tempfile.TemporaryDirectory(prefix="moex-two-pane-") as output:
            subprocess.run([
                "javac", "-d", output,
                str(ROOT / "app/src/main/java/moe/kirao/mgx/layout/MoexTwoPaneLayoutPolicy.java"),
                str(ROOT / "tests/MoexTwoPaneLayoutPolicyTest.java"),
            ], check=True)
            subprocess.run(["java", "-cp", output, "MoexTwoPaneLayoutPolicyTest"], check=True)


if __name__ == "__main__":
    unittest.main()
