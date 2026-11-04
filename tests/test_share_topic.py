"""External file shares into a forum topic: the generated TDLib requests, JVM only.

Compiles the real TdApi with the unchanged ShareController comment/MODE_CUSTOM code,
MainController's share delegate and TD's send helpers. Nothing is sent; Android,
file generation and the chat picker are not exercised (no device or forum test).
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_history_preview import method

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "app/src/main/java/org/thunderdog/challegram/ui"
SHARE = UI_DIR / "ShareController.java"
MAIN = UI_DIR / "MainController.java"
TD = ROOT / "app/src/main/java/org/thunderdog/challegram/data/TD.java"
TDAPI = ROOT / "tdlib/src/main/java/org/drinkless/tdlib/TdApi.java"

HARNESS = r'''
import org.drinkless.tdlib.TdApi;
import java.util.*;
public class ShareTopicHarness {
  @interface Nullable {} @interface NonNull {} @interface Override {}
  static class Config { static final boolean FORCE_REPLY_WHEN_FORWARDING_WITH_COMMENT = true; }
  static class ChatId { static boolean isSecret (long chatId) { return false; } }
  static class Td {
    static boolean isEmpty (TdApi.FormattedText text) { return text == null || text.text.isEmpty(); }
    static TdApi.FormattedText textOrCaption (TdApi.MessageContent content) { return null; }
  }
  static class TdConstants { static final int MAX_MESSAGE_GROUP_SIZE = 10; }
  static class Filegen { TdApi.InputMessageContent createThumbnail (TdApi.InputMessageContent c, boolean secret) { return c; } }
  static class Tdlib { final Filegen filegen = new Filegen(); Filegen filegen () { return filegen; } int maxMessageTextLength () { return 4096; } }
  static class TD {
    static final int COMBINE_MODE_NONE = 0, COMBINE_MODE_MEDIA = 1, COMBINE_MODE_FILES = 2, COMBINE_MODE_AUDIO = 3;
    // Text splitting is not under test.
    static List<TdApi.InputMessageContent> explodeText (TdApi.InputMessageContent content, int max) { return Collections.singletonList(content); }
    /* TD_METHODS */
  }
  /* GENERATOR */
  interface ShareProviderDelegate {
    void generateFunctionsForChat (long chatId, TdApi.Chat chat, @Nullable TdApi.MessageTopic topicId, TdApi.MessageSendOptions sendOptions, ArrayList<TdApi.Function<?>> functions);
  }
  // MainController's anonymous delegate, with the captured share state as fields.
  static class Delegate implements ShareProviderDelegate {
    final Tdlib tdlib; final List<TdApi.InputMessageContent> contents; final boolean mergeAlbum;
    Delegate (Tdlib tdlib, List<TdApi.InputMessageContent> contents, boolean mergeAlbum) { this.tdlib = tdlib; this.contents = contents; this.mergeAlbum = mergeAlbum; }
    /* DELEGATE */
  }
  static class Args { ShareProviderDelegate customDelegate; boolean disallowReply; TdApi.Message[] messages; }
  static final int MODE_MESSAGES = 1, MODE_CUSTOM = 6;
  final int mode = MODE_CUSTOM; boolean needHideAuthor, needRemoveCaptions; TdApi.MessageProperties[] messageProperties;
  final Tdlib tdlib = new Tdlib();

  // The per-chat body of ShareController's send loop for MODE_CUSTOM, unchanged.
  void send (long chatId, TdApi.Chat chat, TdApi.MessageTopic xgramTopicId, TdApi.MessageSendOptions sendOptions,
             boolean hasComment, TdApi.FormattedText comment, Args args, ArrayList<TdApi.Function<?>> functions) {
    boolean messageReplyIncluded = false;
    /* COMMENT */
    switch (mode) {
      /* CUSTOM */
      default:
        return;
    }
  }

  static int checks;
  static void check (boolean value, String message) { checks++; if (!value) throw new AssertionError(message); }
  static TdApi.InputMessageContent photo () { return new TdApi.InputMessagePhoto(new TdApi.InputPhoto(new TdApi.InputFileLocal("/p.jpg"), null, null, null, 1, 1), null, false, null, false); }
  static TdApi.InputMessageContent document () { return new TdApi.InputMessageDocument(new TdApi.InputDocument(new TdApi.InputFileLocal("/d.pdf"), null, false), null); }
  static TdApi.MessageTopic topicOf (TdApi.Function<?> function) {
    if (function instanceof TdApi.SendMessage) return ((TdApi.SendMessage) function).topicId;
    return ((TdApi.SendMessageAlbum) function).topicId;
  }

  static ArrayList<TdApi.Function<?>> share (TdApi.MessageTopic topic, boolean mergeAlbum, List<TdApi.InputMessageContent> contents) {
    ShareTopicHarness controller = new ShareTopicHarness();
    Args args = new Args();
    args.customDelegate = new Delegate(controller.tdlib, contents, mergeAlbum);
    ArrayList<TdApi.Function<?>> functions = new ArrayList<>();
    controller.send(-1001L, new TdApi.Chat(), topic, new TdApi.MessageSendOptions(), true,
      new TdApi.FormattedText("comment", new TdApi.TextEntity[0]), args, functions);
    return functions;
  }

  public static void main (String[] a) {
    TdApi.MessageTopicForum topic = new TdApi.MessageTopicForum(7);
    ArrayList<TdApi.Function<?>> functions = share(topic, false, Arrays.asList(photo(), document()));
    check(functions.size() == 3 && functions.get(0) instanceof TdApi.SendMessage &&
      ((TdApi.SendMessage) functions.get(0)).inputMessageContent instanceof TdApi.InputMessageText, "comment first, then each file");
    for (TdApi.Function<?> f : functions) check(topicOf(f) == topic, "shared files must go to the picked topic, like the comment");
    List<TdApi.InputMessageContent> many = new ArrayList<>();
    for (int i = 0; i < 12; i++) many.add(photo());
    many.add(document());
    functions = share(topic, true, many);
    check(functions.size() == 4 && functions.get(1) instanceof TdApi.SendMessageAlbum &&
      ((TdApi.SendMessageAlbum) functions.get(1)).inputMessageContents.length == 10 &&
      ((TdApi.SendMessageAlbum) functions.get(2)).inputMessageContents.length == 2, "albums of ten, then the rest");
    for (TdApi.Function<?> f : functions) check(topicOf(f) == topic, "shared albums must go to the picked topic, like the comment");
    functions = share(null, true, many);
    for (TdApi.Function<?> f : functions) check(topicOf(f) == null, "ordinary chats keep no topic");
    System.out.println("share topic: " + checks + " checks passed");
  }
}
'''

ANNOTATIONS = {
    "androidx/annotation/Nullable.java": "package androidx.annotation; public @interface Nullable {}",
    "androidx/annotation/IntDef.java": "package androidx.annotation; public @interface IntDef { int[] value() default {}; boolean flag() default false; boolean open() default false; }",
}


def extract(text, signature):
    return method(text, signature)


def sources(share=None, main=None):
    share = share or SHARE.read_text(encoding="utf-8")
    main = main or MAIN.read_text(encoding="utf-8")
    td = TD.read_text(encoding="utf-8")
    td_methods = "\n".join(extract(td, s) for s in (
        "public static int getCombineMode (TdApi.InputMessageContent content)",
        "public static void processAlbum (", "public static void processSingle (",
        "public static List<TdApi.SendMessage> sendMessageText (",
    ))
    comment = extract(share, "if (hasComment) {\n        TdApi.InputMessageReplyToMessage replyTo = null;")
    custom = extract(share, "case MODE_CUSTOM: {\n          args.customDelegate.generateFunctionsForChat(")
    delegate = extract(main, "public void generateFunctionsForChat (long chatId, TdApi.Chat chat, @Nullable TdApi.MessageTopic topicId,")
    generator = extract(main, "static void generateSharedFunctions (")
    return (HARNESS.replace("/* TD_METHODS */", td_methods).replace("/* COMMENT */", comment)
            .replace("/* CUSTOM */", custom).replace("/* DELEGATE */", delegate)
            .replace("/* GENERATOR */", generator))


class ShareTopicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = tempfile.TemporaryDirectory(prefix="share-topic-tdapi-")
        src = Path(cls.api.name) / "src"
        for name, text in ANNOTATIONS.items():
            path = src / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        api = src / "org/drinkless/tdlib/TdApi.java"
        api.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TDAPI, api)
        cls.classes = Path(cls.api.name) / "classes"
        subprocess.run(["javac", "-nowarn", "-d", str(cls.classes), *map(str, src.rglob("*.java"))],
                       check=True, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.api.cleanup()

    def run_harness(self, source):
        with tempfile.TemporaryDirectory(prefix="share-topic-") as tmp:
            java = Path(tmp) / "ShareTopicHarness.java"
            java.write_text(source, encoding="utf-8")
            subprocess.run(["javac", "-cp", str(self.classes), "-d", tmp, str(java)], check=True)
            return subprocess.run(["java", "-cp", f"{tmp}:{self.classes}", "ShareTopicHarness"],
                                  capture_output=True, text=True)

    def test_files_albums_and_comment_share_one_topic(self):
        result = self.run_harness(sources())
        self.assertEqual(result.returncode, 0, result.stderr)
        print(result.stdout.strip())

    def test_negative_delegate_without_topic(self):
        share = SHARE.read_text(encoding="utf-8")
        old = "args.customDelegate.generateFunctionsForChat(chatId, chat, xgramTopicId, sendOptions, functions);"
        self.assertEqual(share.count(old), 1)
        result = self.run_harness(sources(share=share.replace(old, old.replace("xgramTopicId", "null"))))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("shared files must go to the picked topic", result.stderr)

    def test_negative_generator_drops_topic(self):
        main = MAIN.read_text(encoding="utf-8")
        old = "TD.processAlbum(tdlib, chatId, topicId, sendOptions, functions, album);\n        } else {"
        self.assertEqual(main.count(old), 1)
        result = self.run_harness(sources(main=main.replace("TD.processSingle(tdlib, chatId, topicId,", "TD.processSingle(tdlib, chatId, null,")
                                           .replace("TD.processAlbum(tdlib, chatId, topicId,", "TD.processAlbum(tdlib, chatId, null,")))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must go to the picked topic", result.stderr)


if __name__ == "__main__":
    unittest.main()
