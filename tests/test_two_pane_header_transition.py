"""Run the production header setup with real navigation mode constants."""
from pathlib import Path
import re
import subprocess
import unittest
from test_preview_filter import run_java

JAVA = Path(__file__).resolve().parents[1] / 'app/src/main/java/org/thunderdog/challegram/navigation'


class HeaderTransitionTest(unittest.TestCase):
    def run_header(self, mismatched_mode=False, stale_position=False):
        header = (JAVA / 'HeaderView.java').read_text()
        nav = (JAVA / 'NavigationController.java').read_text()
        constants = '\n'.join(re.findall(r'^  static final int MODE_\w+ = \d+;', header, re.M))
        nav_constants = '\n'.join(re.findall(r'^  private static final int TRANSLATION_\w+ = [^;]+;', nav, re.M))
        if mismatched_mode:
            nav_constants = nav_constants.replace('TRANSLATION_NONE = HeaderView.MODE_NONE', 'TRANSLATION_NONE = 4')
        start = header.index('  void openPreview (')
        end = header.index('    // boolean isInSelectMode', start)
        setup = header[start:end] + '  }\n'
        if stale_position:
            setup = setup.replace('preview.setTranslationX(0f);', '').replace('preview.setTranslationY(0f);', '')
        harness = r'''
public class HeaderTransitionHarness {
  static class View {
    float alpha=0f,x=180f,y=-154f;
    void setAlpha(float a){alpha=a;}
    void setTranslationX(float v){x=v;}
    void setTranslationY(float v){y=v;}
  }
  static class ViewController<T> {
    View header=new View(); boolean popup;
    boolean usePopupMode(){return popup;}
    int getHeaderHeight(){return 56;}
  }
  static class HeaderView {
    CONSTANTS
    boolean previewOpened,forceRtlAnimation;
    float currentX,currentY,translationFactor;
    int translationMode;
    static final float TRANSLATION_FACTOR=.3f;
    View preview;
    ViewController<?> previewItem,baseItem;
    int getMeasuredWidth(){return 947;}
    int getEffectiveTopOffset(){return 70;}
    int getCurrentHeight(){return 56;}
    void genPreview(ViewController<?> left,ViewController<?> right,boolean forward){
      previewItem=forward?right:left;baseItem=forward?left:right;preview=previewItem.header;
    }
    SETUP
  }
  NAV_CONSTANTS
  static void check(boolean ok,String reason){if(!ok)throw new AssertionError(reason);}
  public static void main(String[] args){
    HeaderView h=new HeaderView();ViewController<?> list=new ViewController<>(),topic=new ViewController<>();
    check(TRANSLATION_NONE==HeaderView.MODE_NONE,"navigation/header mode contract mismatch");
    for(boolean forward:new boolean[]{true,false}){
      View expected=forward?topic.header:list.header;
      for(int repeat=0;repeat<5;repeat++){
        expected.alpha=0;expected.x=-280;expected.y=154;
        h.openPreview(list,topic,forward,TRANSLATION_NONE,forward?1:0,false);
        check(h.preview==expected,"wrong reused title");
        check(expected.alpha==1&&expected.x==0&&expected.y==0,"instant title remains invisible or displaced");
      }
    }
    h.openPreview(list,topic,true,TRANSLATION_HORIZONTAL,1,false);
    check(topic.header.alpha==0&&topic.header.x>0&&topic.header.y==0,"native horizontal start changed");
    h.openPreview(list,topic,false,TRANSLATION_VERTICAL,0,false);
    check(list.header.alpha==0&&list.header.x==0&&list.header.y<0,"native popup start changed");
    h.openPreview(list,topic,true,TRANSLATION_FADE,1,false);
    check(topic.header.alpha==0&&topic.header.x==0&&topic.header.y==0,"native fade start changed");
    h.openPreview(list,topic,true,TRANSLATION_NONE,1,false);
    check(topic.header.alpha==1&&topic.header.x==0&&topic.header.y==0,"fade to immediate reuse");
    System.out.println("header reuse and native transition checks passed");
  }
}
'''.replace('NAV_CONSTANTS', nav_constants).replace('CONSTANTS', constants).replace('SETUP', setup)
        run_java({'HeaderTransitionHarness.java': harness}, 'HeaderTransitionHarness')

    def test_production_header_reuse(self):
        self.run_header()

    def test_old_mode_mismatch_rejected(self):
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            self.run_header(mismatched_mode=True)
        self.assertEqual(caught.exception.cmd[0], 'java')

    def test_stale_header_position_rejected(self):
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            self.run_header(stale_position=True)
        self.assertEqual(caught.exception.cmd[0], 'java')


if __name__ == '__main__':
    unittest.main()
