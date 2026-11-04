"""Actual haptic placement method; device UI checks are recorded separately."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_chat_navigation import block
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'app/src/main/java/org/thunderdog/challegram/util/HapticMenuHelper.java'

class PopupAuditTest(unittest.TestCase):
    def run_method(self, broken=False):
        method=block(SOURCE,'private static int clampMenuCenter (')
        if broken:
            method='private static int clampMenuCenter(int center,int size,int start,int end){return Math.max(size/2,Math.min(1600-size/2,center));}'
        source='public class AnchorHarness {'+method+"""
 static void eq(int a,int b){if(a!=b)throw new AssertionError(a+" != "+b);}
 public static void main(String[] args){
  eq(clampMenuCenter(635,300,0,635),485);
  eq(clampMenuCenter(653,300,653,1600),803);
  eq(clampMenuCenter(753,300,753,1700),903);
  eq(clampMenuCenter(1200,300,653,1600),1200);
  eq(clampMenuCenter(749,300,0,750),600);
  eq(clampMenuCenter(3,301,0,750),150);
  eq(clampMenuCenter(-120,200,70,1000),170);
  eq(clampMenuCenter(1200,200,70,1000),900);
 }
}"""
        with tempfile.TemporaryDirectory(prefix='moex-popup-anchor-') as d:
            p=Path(d)/'AnchorHarness.java';p.write_text(source)
            subprocess.run(['javac','-d',d,str(p)],check=True)
            return subprocess.run(['java','-cp',d,'AnchorHarness'],capture_output=True,text=True)
    def test_source_bounds_screen_offset_and_fold(self):
        result=self.run_method();self.assertEqual(result.returncode,0,result.stderr)
    def test_old_window_bounds_cross_pane_negative_control(self):
        result=self.run_method(True);self.assertNotEqual(result.returncode,0);self.assertIn('AssertionError',result.stderr)

if __name__=='__main__': unittest.main()
