"""Run the production MediaItem.canBeShared, MediaMessageProperties and Tdlib properties methods
against the real TdApi classes, with a scripted TDLib that answers GetMessageProperties.

The full-screen viewer's top-right More menu shows Share only when
item.canBeSaved() && item.canBeShared(). canBeShared() used to keep the first answer forever:
a photo opened while its forward was still being sent (or after one failed request) kept
"can't forward" for the whole viewer session, even after TGMessage gave the same
TdApi.Message its server id. Android rendering, real TDLib answers and the share sheet
itself still need the emulator test.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TDAPI = ROOT / 'tdlib/src/main/java/org/drinkless/tdlib/TdApi.java'
MEDIA = ROOT / 'app/src/main/java/org/thunderdog/challegram/mediaview'
ITEM = 'app/src/main/java/org/thunderdog/challegram/mediaview/data/MediaItem.java'
CACHE = MEDIA / 'data/MediaMessageProperties.java'
TDLIB = ROOT / 'app/src/main/java/org/thunderdog/challegram/telegram/Tdlib.java'
VIEWER = MEDIA / 'MediaViewController.java'
BASELINE = '800a794a6fa94b5d7b5a2b3b126eae8357804829'

ANNOTATIONS = {
  'androidx/annotation/Nullable.java': 'package androidx.annotation; public @interface Nullable {}',
  'androidx/annotation/NonNull.java': 'package androidx.annotation; public @interface NonNull {}',
  'androidx/annotation/IntDef.java': 'package androidx.annotation; public @interface IntDef { int[] value() default {}; boolean flag() default false; }',
}


def method(text, signature):
  """Source of the method starting at signature, through its matching closing brace."""
  start = text.index(signature)
  depth = 0
  for i in range(text.index('{', start), len(text)):
    if text[i] == '{':
      depth += 1
    elif text[i] == '}':
      depth -= 1
      if depth == 0:
        return text[start:i + 1]
  raise ValueError(signature)


HARNESS = r'''
package org.thunderdog.challegram.mediaview.data;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import org.drinkless.tdlib.TdApi;
import java.util.*;

public class ShareHarness {
  static void check (boolean ok, String what) { if (!ok) throw new AssertionError(what); }

  static class Tdlib {
    // Scripted TDLib answers per message id: null entry = TDLib returned an error.
    final Map<Long, Deque<TdApi.MessageProperties>> answers = new HashMap<>();
    final List<Long> asked = new ArrayList<>();

    void answer (long messageId, TdApi.MessageProperties... results) {
      answers.computeIfAbsent(messageId, k -> new ArrayDeque<>());
      for (TdApi.MessageProperties p : results) answers.get(messageId).add(p == null ? ERROR : p);
    }

    @SuppressWarnings("unchecked")
    <T extends TdApi.Object> T clientExecuteT (TdApi.Function<T> function, boolean throwErrors) {
      TdApi.GetMessageProperties f = (TdApi.GetMessageProperties) function;
      asked.add(f.messageId);
      Deque<TdApi.MessageProperties> q = answers.get(f.messageId);
      TdApi.MessageProperties p = q == null || q.isEmpty() ? ERROR : (q.size() > 1 ? q.poll() : q.peek());
      return p == ERROR ? null : (T) p;
    }

    TDLIB_METHODS
  }

  static final TdApi.MessageProperties ERROR = new TdApi.MessageProperties();

  static class Item {
    final Tdlib tdlib;
    final TdApi.Message msg;
    private TdApi.MessageProperties lastProperties; // baseline field
    private final MediaMessageProperties messageProperties = new MediaMessageProperties();
    Item (Tdlib tdlib, TdApi.Message msg) { this.tdlib = tdlib; this.msg = msg; }
    TdApi.File getShareFile () { return null; }
    boolean canBeSaved () { return msg.canBeSaved; }

    CAN_BE_SHARED
  }

  static TdApi.MessageProperties props (boolean forward) {
    TdApi.MessageProperties p = new TdApi.MessageProperties();
    p.canBeForwarded = forward;
    p.canBeSaved = forward;
    return p;
  }

  static TdApi.Message photo (long id, TdApi.MessageSendingState state) {
    TdApi.Message m = new TdApi.Message();
    m.chatId = 100; m.id = id; m.sendingState = state; m.canBeSaved = true;
    m.forwardInfo = new TdApi.MessageForwardInfo();
    m.content = new TdApi.MessagePhoto();
    return m;
  }

  // The More menu condition of MediaViewController.openMoreMenu for MODE_MESSAGES.
  static boolean menuHasShare (Item item) { return item.canBeSaved() && item.canBeShared(); }

  static final long LOCAL = 1 << 20, SERVER = 7 << 20;

  public static void main (String[] args) {
    switch (args[0]) {
      case "sent-while-open": {
        // A photo the user just forwarded: opened while pending, sent while the viewer stays open.
        Tdlib t = new Tdlib();
        t.answer(LOCAL, props(false)); // TDLib: a yet-unsent message can't be forwarded
        t.answer(SERVER, props(true));
        TdApi.Message m = photo(LOCAL, new TdApi.MessageSendingStatePending(1));
        Item item = new Item(t, m);
        check(!menuHasShare(item), "pending forward offered Share");
        // TGMessage.copyFlags on updateMessageSendSucceeded: same object, new id and state.
        m.id = SERVER; m.sendingState = null;
        check(menuHasShare(item), "sent forward still has no Share in the open viewer");
        check(t.asked.contains(SERVER), "server message was never asked about");
        break;
      }
      case "failed-request-retried": {
        Tdlib t = new Tdlib();
        t.answer(SERVER, null, props(true));
        Item item = new Item(t, photo(SERVER, null));
        check(!menuHasShare(item), "failed request offered Share");
        check(menuHasShare(item), "one failed request hid Share for the whole viewer");
        break;
      }
      case "answer-kept": {
        Tdlib t = new Tdlib();
        t.answer(SERVER, props(true));
        Item item = new Item(t, photo(SERVER, null));
        check(menuHasShare(item) && menuHasShare(item) && item.canBeShared(), "ordinary forwarded photo has no Share");
        check(t.asked.size() == 1, "same message asked again: " + t.asked);
        break;
      }
      case "protected-hidden": {
        // TDLib forbids forwarding (protected chat / noforwards): stays hidden and kept.
        Tdlib t = new Tdlib();
        t.answer(SERVER, props(false));
        TdApi.Message m = photo(SERVER, null);
        Item item = new Item(t, m);
        check(!item.canBeShared() && !item.canBeShared(), "protected photo offered Share");
        check(t.asked.size() == 1, "protected answer not kept: " + t.asked);
        m.canBeSaved = false;
        check(!menuHasShare(item), "unsaveable photo offered Share");
        break;
      }
      case "id-changed": {
        // An answer belongs to one message id, even if the shared object changes without a sending state.
        Tdlib t = new Tdlib();
        t.answer(SERVER, props(true));
        t.answer(SERVER + 1, props(false));
        TdApi.Message m = photo(SERVER, null);
        Item item = new Item(t, m);
        check(item.canBeShared(), "first message has no Share");
        m.id = SERVER + 1;
        check(!item.canBeShared(), "answer for another message id reused");
        break;
      }
      case "send-failed": {
        Tdlib t = new Tdlib();
        t.answer(LOCAL, props(true)); // even a wrong answer must not be used
        TdApi.Message m = photo(LOCAL, new TdApi.MessageSendingStateFailed());
        Item item = new Item(t, m);
        check(!menuHasShare(item), "failed message offered Share");
        check(t.asked.isEmpty(), "failed message was asked about: " + t.asked);
        break;
      }
      case "tdlib-default": {
        // Other callers keep the all-false fallback on errors.
        Tdlib t = new Tdlib();
        check(t.getMessagePropertiesSyncOrNull(100, SERVER) == null, "error reported as properties");
        TdApi.MessageProperties p = t.getMessagePropertiesSync(100, SERVER);
        check(p != null && !p.canBeForwarded && !p.canBeSaved, "sync fallback changed");
        break;
      }
      default: throw new IllegalArgumentException(args[0]);
    }
    System.out.println("ok " + args[0]);
  }
}
'''


class MediaViewerShareTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.dir = tempfile.TemporaryDirectory(prefix='media-share-')
    base = Path(cls.dir.name)
    cls.tdapi_classes = base / 'tdapi'
    src = base / 'tdapi-src'
    for name, text in ANNOTATIONS.items():
      (src / name).parent.mkdir(parents=True, exist_ok=True)
      (src / name).write_text(text)
    target = src / 'org/drinkless/tdlib/TdApi.java'
    target.parent.mkdir(parents=True)
    shutil.copy(TDAPI, target)
    subprocess.run(['javac', '-nowarn', '-encoding', 'UTF-8', '-d', str(cls.tdapi_classes)] +
                   [str(p) for p in src.rglob('*.java')], check=True, capture_output=True)

  @classmethod
  def tearDownClass(cls):
    cls.dir.cleanup()

  def build(self, item_source):
    tdlib = TDLIB.read_text()
    tdlib_methods = '\n'.join(method(tdlib, s) for s in (
      '  public @NonNull TdApi.MessageProperties getMessagePropertiesSync (TdApi.Message message)',
      '  public @NonNull TdApi.MessageProperties getMessagePropertiesSync (long chatId, long messageId)',
      '  public @Nullable TdApi.MessageProperties getMessagePropertiesSyncOrNull (long chatId, long messageId)',
      '  private static TdApi.MessageProperties defaultMessageProperties ()',
    ))
    harness = HARNESS.replace('TDLIB_METHODS', tdlib_methods).replace(
      'CAN_BE_SHARED', method(item_source, '  public boolean canBeShared ()'))
    out = Path(tempfile.mkdtemp(dir=self.dir.name))
    pkg = out / 'src/org/thunderdog/challegram/mediaview/data'
    pkg.mkdir(parents=True)
    (pkg / 'ShareHarness.java').write_text(harness)
    shutil.copy(CACHE, pkg / 'MediaMessageProperties.java')
    classes = out / 'classes'
    subprocess.run(['javac', '-Xlint:all', '-Werror', '-encoding', 'UTF-8', '-cp', str(self.tdapi_classes), '-d', str(classes)] +
                   [str(p) for p in out.rglob('*.java')], check=True, capture_output=True, text=True)
    return classes

  def run_case(self, classes, case):
    return subprocess.run(['java', '-ea', '-cp', f'{classes}:{self.tdapi_classes}',
                           'org.thunderdog.challegram.mediaview.data.ShareHarness', case],
                          capture_output=True, text=True, timeout=60)

  CASES = ('sent-while-open', 'failed-request-retried', 'answer-kept', 'protected-hidden', 'id-changed', 'send-failed', 'tdlib-default')

  def test_production_can_be_shared(self):
    classes = self.build((ROOT / ITEM).read_text())
    for case in self.CASES:
      with self.subTest(case=case):
        r = self.run_case(classes, case)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('ok ' + case, r.stdout)

  def test_baseline_kept_stale_answer(self):
    """The unfixed canBeShared fails exactly the lifecycle cases and still passes the restriction cases."""
    try:
      old = subprocess.run(['git', '-C', str(ROOT), 'show', f'{BASELINE}:{ITEM}'],
                           check=True, capture_output=True, text=True).stdout
    except subprocess.CalledProcessError:
      self.fail(f'baseline commit {BASELINE} not available; see PROJECT_GUIDE_CN.md')
    classes = self.build(old)
    expected = {
      'sent-while-open': 'sent forward still has no Share in the open viewer',
      'failed-request-retried': 'one failed request hid Share for the whole viewer',
      'id-changed': 'answer for another message id reused',
    }
    for case in self.CASES:
      with self.subTest(case=case):
        r = self.run_case(classes, case)
        if case in expected:
          self.assertNotEqual(r.returncode, 0, r.stdout)
          self.assertIn(expected[case], r.stderr)
        elif case != 'send-failed':  # the baseline asked TDLib about failed messages
          self.assertEqual(r.returncode, 0, r.stderr)

  def test_more_menu_restrictions_unchanged(self):
    viewer = VIEWER.read_text()
    more = method(viewer, '  private void openMoreMenu ()')
    self.assertIn('if (mode != MODE_SECRET && mode != MODE_GALLERY && item.canBeSaved() && item.canBeShared()) {\n'
                  '      ids.append(R.id.btn_share);', more)
    item = (ROOT / ITEM).read_text()
    saved = method(item, '  public boolean canBeSaved ()')
    self.assertIn('if (msg != null) {\n      return msg.canBeSaved;', saved)
    shared = method(item, '  public boolean canBeShared ()')
    self.assertRegex(shared, r'return properties != null && properties\.canBeForwarded;')
    self.assertNotIn('lastProperties', item)


if __name__ == '__main__':
  unittest.main()
