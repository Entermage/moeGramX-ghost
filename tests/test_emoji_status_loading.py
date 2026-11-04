"""Production loading callbacks with queued fake TDLib/UI; never use a real account.

Network pages and UI delivery are controlled separately so search replacement and
popup destruction can occur before a response or between response and UI apply.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_chat_navigation import block

ROOT=Path(__file__).resolve().parents[1]
JAVA=ROOT/"app/src/main/java/org/thunderdog/challegram"
CONTROLLER=JAVA/"ui/EmojiStatusListController.java"
PAGE=JAVA/"ui/EmojiStatusSelectorEmojiPage.java"


def source_for(broken=None):
    methods="\n".join(block(CONTROLLER,s) for s in (
        "private boolean isCurrentStickerLoad (", "public void destroy (",
        "private void loadStickers (", "private void reloadStickers (", "public void search (",
        "private void setStickers (", "private void loadNextTrending (", "private void addTrendingStickers (",
        "private Client.ResultHandler stickerSetsHandler (", "private Client.ResultHandler trendingStickersHandler (",
        "private Client.ResultHandler serviceStickersHandler (", "private void getEmojiStatusList (",
        "private void getCustomEmojiStatusList (", "private void getCustomEmojiStickers (",
    ))
    page=block(PAGE,"public void destroy (")
    if broken=="empty": methods=methods.replace(" && canLoadMoreTrending", "")
    if broken=="filtered":
        methods=methods.replace("receivedCount > 0 && (!knownTotal || trendingOffset < result.totalCount)", "receivedCount > 0 && (!knownTotal || trendingOffset < result.totalCount) && !parsedStickerSets.isEmpty()")
    if broken=="generation": methods=methods.replace("generation == stickerLoadGeneration", "true")
    if broken=="owner":
        page=page.replace("emojiCustomListLayout.destroy();", "{}")
        page=page.replace("foregroundEmojiLayout.destroyEmojiLayout();", "{}")
    base="\n".join(block(JAVA/"navigation/ViewController.java",s) for s in (
        "public final void runOnUiThreadOptional (Runnable runnable)",
        "public final void runOnUiThreadOptional (Runnable runnable, @Nullable FutureBool condition, long delay)",
    ))
    source=(ROOT/"tests/EmojiStatusLoadingHarness.java").read_text()
    for marker,code in (("METHODS",methods),("PAGE_DESTROY",page),("BASE_UI",base),
                        ("LAYOUT_DESTROY",block(JAVA/"widget/EmojiLayout.java","public void destroy ()")),
                        ("FOREGROUND_DESTROY",block(PAGE,"public void destroyEmojiLayout ("))):
        source=source.replace("/* "+marker+" */",code)
    return source


def compile_harness(directory,broken=None):
    source=Path(directory)/"EmojiStatusLoadingHarness.java"
    source.write_text(source_for(broken),encoding="utf-8")
    subprocess.run(["javac","-d",directory,str(source)],check=True)


class EmojiStatusLoadingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix="emoji-status-loading-")
        compile_harness(cls.temp.name)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def run_case(self,case):
        subprocess.run(["java","-cp",self.temp.name,"EmojiStatusLoadingHarness",case],check=True,timeout=15)

    def test_raw_pages_advance_while_filtered_empty_pages_continue(self): self.run_case("pages")
    def test_empty_error_and_reliable_total_stop_without_repeating_offset(self): self.run_case("stop")
    def test_search_replacement_rejects_network_and_queued_ui_from_old_load(self): self.run_case("search")
    def test_popup_destroy_owns_hidden_controllers_and_drops_late_callbacks(self): self.run_case("destroy")

    def test_negative_controls_detect_loop_filter_generation_and_owner_regressions(self):
        for broken,case,message in (("empty","stop","raw empty page must stop"),("filtered","pages","filtered empty page must continue"),("generation","search","old trending response cannot enter new search"),("owner","destroy","hidden emoji controller must be destroyed")):
            with self.subTest(broken=broken),tempfile.TemporaryDirectory(prefix="emoji-status-loading-broken-") as directory:
                compile_harness(directory,broken)
                result=subprocess.run(["java","-cp",directory,"EmojiStatusLoadingHarness",case],capture_output=True,text=True,timeout=15)
                self.assertNotEqual(result.returncode,0)
                self.assertIn(message,result.stderr)


if __name__=="__main__":unittest.main()
