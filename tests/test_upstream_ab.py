"""Production login method tests; framework fixtures are not Android E2E."""
from pathlib import Path
import unittest
from test_chat_navigation import block
from test_preview_filter import run_java

ROOT = Path(__file__).resolve().parents[1]
PHONE = ROOT / 'app/src/main/java/org/thunderdog/challegram/ui/PhoneController.java'

class UpstreamAbTest(unittest.TestCase):
    def test_phone_validation_before_views_exist(self):
        method = block(PHONE, 'private boolean hasValidNumber (')
        run_java({'LoginHarness.java': '''
public class LoginHarness {
  static class Edit { CharSequence text; Edit(CharSequence t) { text=t; } CharSequence getText() { return text; } }
  static class StringUtils { static boolean isEmpty(CharSequence s) { return s==null || s.length()==0; } }
  Edit codeView, numberView;
  __METHOD__
  static void check(boolean value) { if(!value) throw new AssertionError(); }
  public static void main(String[] args) {
    LoginHarness p=new LoginHarness();
    check(!p.hasValidNumber());
    p.codeView=new Edit("81"); check(!p.hasValidNumber());
    p.numberView=new Edit(null); check(!p.hasValidNumber());
    p.numberView.text=""; check(!p.hasValidNumber());
    p.numberView.text="123456789"; check(p.hasValidNumber());
    p.codeView.text=null; check(!p.hasValidNumber());
    p.codeView.text=""; check(!p.hasValidNumber());
    p.codeView=null; check(!p.hasValidNumber());
    System.out.println("Login production checks passed: 8");
  }
}
'''.replace('__METHOD__', method)}, 'LoginHarness')

    def test_test_mode_requires_focused_page(self):
        method = block(PHONE, 'public void onAuthorizationReady (')
        self.assertIn('UI.inTestMode() && recyclerView != null && isFocused()', method)

    def test_hls_extractor_uses_normalized_codec_and_mime(self):
        source = (ROOT / 'app/src/main/java/org/thunderdog/challegram/U.java').read_text()
        self.assertIn('.setCodecs(HlsVideo.toRfc6381CodecString(alternativeVideo.codec))', source)
        self.assertIn('.setSampleMimeType(HlsVideo.toSampleMimeType(alternativeVideo.codec))', source)
