"""Bubble grouping after local chat list updates.

Compiles the production TGMessage merge methods and the MessagesAdapter update
paths (replace, delete, page seams, de-duplication, sorted/top insertion and the
unread separator of a newer page) into a JVM harness. Sender, date, TDLib and
RecyclerView APIs are minimal stand-ins; layout and drawing are not executed.

After every local update the whole list is compared with a fresh chronological
merge of the same messages (what MessagesLoader does for a new page), covering
group tail, header, date, badge, padding, forward-merge flags and the
cumulative merge time/index.
"""
import os, pathlib, re, subprocess, tempfile, unittest

ROOT = pathlib.Path(os.environ.get('MGX_GROUPING_SOURCE_ROOT') or pathlib.Path(__file__).resolve().parents[1])
SRC = ROOT / 'app/src/main/java/org/thunderdog/challegram'
MESSAGE = SRC / 'data/TGMessage.java'
ADAPTER = SRC / 'component/chat/MessagesAdapter.java'

MESSAGE_METHODS = (
    'mergeWith', 'clearMerge', 'remergeItems', 'setIsBottom', 'isBottomMessage', 'setHeaderEnabled',
    'setShowUnreadBadge', 'updateShowBadge', 'getMergeIndex', 'getMergeTime', 'setMergeBottom',
    'setNeedExtraPadding', 'setNeedExtraPresponsoredPadding', 'hasBadge', 'hasUnreadBadge',
    'isFirstUnread', 'isBelowHeader', 'hasDate', 'isForward', 'compareTo',
)
ADAPTER_METHODS = (
    'replaceItem', 'removeItem', 'addMessages', 'addMessageImpl', 'hasUnreadSeparator',
    'getMessage', 'getMessageCount', 'getBottomMessage',
)


def methods(text, names):
    """All production methods (every overload) with the given names; missing names are skipped."""
    lines = text.split('\n')
    offsets, pos = [], 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1
    out = []
    for i, line in enumerate(lines):
        if not re.match(r'  [a-zA-Z@]', line) or not line.rstrip().endswith('{') or '=' in line.split('(')[0]:
            continue
        m = re.search(r' (\w+) \(', line)
        if not m or m.group(1) not in names:
            continue
        start = offsets[i]
        brace = text.index('{', start)
        depth, end = 1, brace + 1
        while depth:
            depth += (text[end] == '{') - (text[end] == '}')
            end += 1
        body = text[start:end]
        for annotation in ('@Nullable ', '@NonNull ', '@Override\n'):
            body = body.replace(annotation, '')
        out.append(body)
    return '\n'.join(out)


def constants(text):
    out = []
    for line in text.split('\n'):
        m = re.match(r'  private static final int ([A-Z0-9_]+) = ([A-Z0-9_ |<()]+);$', line)
        if m:
            out.append(line)
    return '\n'.join(out)


HARNESS = r'''
import java.util.*;

class TdApi {
  static class Chat { int unreadCount = 1; }
  static class MessageOrigin { int getConstructor () { return 0; } }
  static class MessageOriginUser { static final int CONSTRUCTOR = 1; }
  static class MessageForwardInfo { MessageOrigin origin = new MessageOrigin(); }
  static class Message { long id, sender, viaBotUserId, mediaAlbumId; int date, source; String authorSignature = ""; MessageForwardInfo forwardInfo; }
}
class BitwiseUtils {
  static boolean hasFlag (int n, int f) { return (n & f) != 0; }
  static int setFlag (int n, int f, boolean on) { return on ? n | f : n & ~f; }
}
class StringUtils { static boolean equalsOrBothEmpty (String a, String b) { return Objects.equals(a == null ? "" : a, b == null ? "" : b); } }
class DateUtils {
  static boolean isSameDay (int a, int b) { return a / 86400 == b / 86400; }
  static boolean isSameHour (int a, int b) { return a / 3600 == b / 3600; }
}
class TD { static boolean isSameSource (TdApi.Message a, TdApi.Message b, boolean force) { return a.source == b.source && (a.forwardInfo == null) == (b.forwardInfo == null); } }
class Library {
  boolean isSameSender (TdApi.Message a, TdApi.Message b) { return a.sender == b.sender; }
  TdApi.Chat chat (long id) { return new TdApi.Chat(); }
}
class ThreadInfo { boolean hasUnreadMessages (TdApi.Chat chat) { return true; } }
class Controller {
  boolean areScheduledOnly () { return false; }
  ThreadInfo getMessageThread () { return null; }
  void highlightMessage (Object id) { }
}
class Manager {
  boolean dedup, sort;
  boolean needRemoveDuplicates () { return dedup; }
  boolean needSort () { return sort; }
  Controller controller () { return new Controller(); }
}
class Config { static final boolean TEST_MULTI_SPONSORED_MESSAGES = false; }
class U { static void notifyItemsReplaced (MessagesAdapter adapter, int oldCount) { adapter.replaced = true; } }

class TGMessage implements Comparable<TGMessage> {
  __CONSTANTS__
  private int flags;
  protected int mergeTime, mergeIndex;
  protected int height;
  private boolean needSponsorSmallPadding;
  protected TdApi.Message msg = new TdApi.Message();
  private final Library tdlib = new Library();
  boolean threadHeader, headerOff, mergeOff, outgoing;
  static boolean bubbles = true;
  static long lastReadId;
  static int rebuilds, merges;

  TGMessage (long id, int date, long sender) {
    msg.id = id; msg.date = date; msg.sender = sender;
    flags |= FLAG_LAYOUT_BUILT;
  }

  TGMessage copySpec () {
    TGMessage c = new TGMessage(msg.id, msg.date, msg.sender);
    c.msg.source = msg.source; c.msg.mediaAlbumId = msg.mediaAlbumId; c.msg.viaBotUserId = msg.viaBotUserId;
    c.msg.authorSignature = msg.authorSignature; c.msg.forwardInfo = msg.forwardInfo;
    c.threadHeader = threadHeader; c.headerOff = headerOff; c.mergeOff = mergeOff; c.outgoing = outgoing;
    if (isFirstUnread()) c.setShowUnreadBadge(true);
    return c;
  }

  boolean groupTail () { return (flags & MESSAGE_FLAG_IS_BOTTOM) != 0; }
  boolean headerFlag () { return (flags & FLAG_HEADER_ENABLED) != 0; }

  String state () {
    int mask = MESSAGE_FLAG_IS_BOTTOM | MESSAGE_FLAG_HAS_OLDER_MESSAGE | MESSAGE_FLAG_BELOW_HEADER | MESSAGE_FLAG_FIRST_UNREAD |
      FLAG_MERGE_FORWARD | FLAG_MERGE_BOTTOM | FLAG_HEADER_ENABLED | FLAG_SHOW_TICKS | FLAG_SHOW_BADGE | FLAG_SHOW_DATE | FLAG_EXTRA_PADDING;
    int f = flags & mask;
    return "#" + msg.id + "{tail=" + ((f & MESSAGE_FLAG_IS_BOTTOM) != 0) + ",header=" + ((f & FLAG_HEADER_ENABLED) != 0) +
      ",date=" + ((f & FLAG_SHOW_DATE) != 0) + ",badge=" + ((f & FLAG_SHOW_BADGE) != 0) + ",pad=" + ((f & FLAG_EXTRA_PADDING) != 0) +
      ",fwd=" + ((f & FLAG_MERGE_FORWARD) != 0) + ",fwdBottom=" + ((f & FLAG_MERGE_BOTTOM) != 0) + ",older=" + ((f & MESSAGE_FLAG_HAS_OLDER_MESSAGE) != 0) +
      ",ticks=" + ((f & FLAG_SHOW_TICKS) != 0) + ",time=" + getMergeTime() + ",index=" + getMergeIndex() + "}";
  }

  // Stand-ins for message type, layout and controller
  boolean isSponsoredMessage () { return false; }
  boolean isThreadHeader () { return threadHeader; }
  boolean isEventLog () { return false; }
  boolean needHideEventDate () { return false; }
  protected boolean headerDisabled () { return headerOff; }
  boolean isScheduled () { return false; }
  boolean isNotSent () { return false; }
  boolean useBubbles () { return bubbles; }
  boolean isChannel () { return false; }
  boolean forceForwardOrImportInfo () { return false; }
  protected boolean mergeDisabled () { return mergeOff; }
  boolean isOutgoingBubble () { return outgoing; }
  boolean isOutgoing () { return outgoing; }
  boolean isSending () { return false; }
  boolean isUnread () { return false; }
  boolean isOld () { return true; }
  void markAsBeingAdded (boolean value) { }
  int getComparingDate () { return msg.date; }
  int getDate () { return msg.date; }
  TdApi.Message getMessage () { return msg; }
  Controller messagesController () { return new Controller(); }
  Library tdlib () { return tdlib; }
  long getId () { return msg.id; }
  long getChatId () { return 1; }
  Object toMessageId () { return null; }
  boolean isDescendantOrSelf (long id) { return msg.id == id; }
  boolean checkIsUnread (boolean ignored) { return msg.id > lastReadId; }
  private String genDate () { return ""; }
  void setDate (String date) { }
  private boolean updateBadgeText () { merges++; return false; }
  protected final void buildBubble (boolean force) { }
  public int computeHeight () { return 0; }
  public void rebuildLayout () { rebuilds++; }
  public void prepareLayout () { rebuilds++; }
  void requestLayout () { }
  void invalidate () { }
  void onDestroy () { }

  __MESSAGE_METHODS__
}

class MessagesAdapter {
  static final int INITIAL_CAPACITY = 20;
  final Manager manager = new Manager();
  ArrayList<TGMessage> items = new ArrayList<>();
  boolean replaced;
  final List<int[]> changed = new ArrayList<>();
  int getItemCount () { return items == null ? 0 : items.size(); }
  int indexOfMessageContainer (long id) { for (int i = 0; i < getItemCount(); i++) if (items.get(i).getId() == id) return i; return -1; }
  void notifyItemRangeChanged (int start, int count) { changed.add(new int[] {start, count}); }
  void notifyItemChanged (int index) { }
  void notifyItemRemoved (int index) { }
  void notifyItemInserted (int index) { }
  void notifyItemRangeInserted (int start, int count) { }

  __ADAPTER_METHODS__
}

public class Harness {
  static final Random random = new Random(1813);
  static long nextId = 1000;
  static int checks;

  static void check (boolean ok, String message) { if (!ok) throw new AssertionError(message); }

  static List<TGMessage> canonical (List<TGMessage> items) {
    ArrayList<TGMessage> fresh = new ArrayList<>();
    for (TGMessage item : items) fresh.add(item.copySpec());
    TGMessage previous = null;
    for (int i = fresh.size() - 1; i >= 0; i--) {
      fresh.get(i).mergeWith(previous, i == 0);
      previous = fresh.get(i);
    }
    return fresh;
  }

  static void expectCanonical (MessagesAdapter adapter, String label) {
    List<TGMessage> expected = canonical(adapter.items);
    for (int i = 0; i < adapter.items.size(); i++) {
      String actual = adapter.items.get(i).state(), wanted = expected.get(i).state();
      check(actual.equals(wanted), label + ": index " + i + " is " + actual + ", chronological merge gives " + wanted);
    }
    for (int[] range : adapter.changed) {
      check(range[0] >= 0 && range[1] >= 1 && range[0] + range[1] <= adapter.getItemCount(), label + ": bad changed range " + Arrays.toString(range));
    }
    adapter.changed.clear();
    checks++;
  }

  static String tails (List<TGMessage> items) {
    StringJoiner j = new StringJoiner(",", "[", "]");
    for (TGMessage m : items) j.add(Boolean.toString(m.groupTail()));
    return j.toString();
  }

  static TGMessage m (long id, int date, long sender) { return new TGMessage(id, date, sender); }

  /** Newest first, merged from oldest to newest like MessagesLoader. */
  static ArrayList<TGMessage> page (List<TGMessage> chronological) {
    ArrayList<TGMessage> items = new ArrayList<>();
    TGMessage top = null;
    for (int i = 0; i < chronological.size(); i++) {
      TGMessage cur = chronological.get(i);
      cur.mergeWith(top, i == chronological.size() - 1);
      items.add(0, cur);
      top = cur;
    }
    return items;
  }

  static ArrayList<TGMessage> run (long firstId, int firstDate, int step, int count, long sender) {
    ArrayList<TGMessage> list = new ArrayList<>();
    for (int i = 0; i < count; i++) list.add(m(firstId + i * 10L, firstDate + i * step, sender));
    return list;
  }

  static MessagesAdapter adapter (List<TGMessage> chronological) {
    MessagesAdapter adapter = new MessagesAdapter();
    adapter.items = page(chronological);
    return adapter;
  }

  static void scenarios () {
    TGMessage.bubbles = true;
    TGMessage.lastReadId = Long.MAX_VALUE;

    MessagesAdapter replace = adapter(run(10, 1000, 10, 4, 1));
    replace.replaceItem(2, m(20, 1010, 1));
    System.out.println("replace_middle=" + tails(replace.items));
    expectCanonical(replace, "replace middle message");

    MessagesAdapter remove = adapter(run(10, 1000, 10, 4, 1));
    remove.removeItem(2);
    System.out.println("remove_middle=" + tails(remove.items));
    expectCanonical(remove, "remove middle message");

    MessagesAdapter older = adapter(run(30, 1020, 10, 2, 1));
    older.addMessages(page(run(10, 1000, 10, 2, 1)), true);
    System.out.println("load_older_page=" + tails(older.items));
    expectCanonical(older, "older page seam");

    MessagesAdapter newer = adapter(run(10, 1000, 10, 2, 1));
    newer.addMessages(page(run(30, 1020, 10, 2, 1)), false);
    System.out.println("load_newer_page=" + tails(newer.items));
    expectCanonical(newer, "newer page seam");

    // Unread separator placed inside an already merged newer page; another sender above keeps the seam stable
    TGMessage.lastReadId = 20;
    MessagesAdapter unread = adapter(List.of(m(10, 1000, 2)));
    unread.addMessages(page(run(20, 1010, 10, 3, 1)), false);
    TGMessage marked = unread.items.get(1);
    System.out.println("unread_separator_present=" + marked.hasUnreadBadge() + ",unread_message_has_header=" + marked.headerFlag() + ",above_is_tail=" + unread.items.get(2).groupTail());
    check(marked.getId() == 30 && marked.hasUnreadBadge(), "unread separator must stay on the first unread message");
    expectCanonical(unread, "unread separator inside new page");
    // A content-type replacement creates a fresh TGMessage; the existing separator must survive.
    unread.replaceItem(1, m(30, 1020, 1));
    check(unread.items.get(1).isFirstUnread(), "replacement must preserve the existing unread separator");
    check(unread.items.get(1).headerFlag(), "replacement at unread separator must remain a group head");
    expectCanonical(unread, "replace first unread message");
    TGMessage.lastReadId = Long.MAX_VALUE;

    // Merge time is cumulative: once the group head is gone the next message joins the group
    MessagesAdapter window = adapter(List.of(m(10, 1000, 1), m(20, 1100, 1), m(30, 1950, 1), m(40, 1960, 1)));
    check(window.items.get(1).headerFlag(), "control: 1950 starts a new group 950s after 1000");
    window.removeItem(3);
    System.out.println("remove_group_head=" + tails(window.items) + ",joined=" + !window.items.get(1).headerFlag());
    expectCanonical(window, "group head removed, merge time window");

    // Thread header added on top must not turn the oldest message into a group tail
    MessagesAdapter thread = adapter(run(10, 1000, 10, 3, 1));
    TGMessage header = m(1, 1000, 9); header.threadHeader = true;
    thread.addMessageImpl(header, true, false);
    System.out.println("thread_header_on_top=" + tails(thread.items));
    expectCanonical(thread, "thread header inserted on top");

    // Sorted insertion between merged messages
    MessagesAdapter sorted = adapter(run(10, 1000, 10, 4, 1));
    sorted.manager.sort = true;
    sorted.addMessageImpl(m(25, 1015, 1), false, false);
    expectCanonical(sorted, "sorted insertion");

    // Duplicates removed from a page before it is joined
    MessagesAdapter dedup = adapter(run(40, 1030, 10, 2, 1));
    dedup.manager.dedup = true;
    ArrayList<TGMessage> overlap = run(10, 1000, 10, 4, 1); // #40 is already shown
    dedup.addMessages(page(overlap), true);
    expectCanonical(dedup, "duplicate removed from older page");
    MessagesAdapter dedupNewest = adapter(run(10, 1000, 10, 2, 1));
    dedupNewest.manager.dedup = true;
    ArrayList<TGMessage> newerOverlap = new ArrayList<>(List.of(m(20, 1010, 1), m(30, 1020, 1), m(40, 1030, 1))); // #20 is already shown
    dedupNewest.addMessages(page(newerOverlap), false);
    expectCanonical(dedupNewest, "duplicate removed from newer page");

    // Single message, last message and empty list boundaries
    MessagesAdapter single = adapter(run(10, 1000, 10, 1, 1));
    single.replaceItem(0, m(10, 1000, 2));
    expectCanonical(single, "replace only message");
    single.removeItem(0);
    check(single.items.isEmpty(), "list must be empty");
    single.addMessages(page(run(50, 1050, 10, 2, 1)), false);
    expectCanonical(single, "page into emptied list");
    MessagesAdapter last = adapter(run(10, 1000, 10, 3, 1));
    last.removeItem(0);
    expectCanonical(last, "remove newest message");
    last.removeItem(last.items.size() - 1);
    expectCanonical(last, "remove oldest message");

    // Deleting the newest forwarded message leaves no newer neighbour to clear its link.
    for (boolean bubbles : new boolean[] {false, true}) {
      TGMessage.bubbles = bubbles;
      ArrayList<TGMessage> forwards = run(10, 1000, 10, 3, 1);
      for (TGMessage message : forwards) message.msg.forwardInfo = new TdApi.MessageForwardInfo();
      MessagesAdapter forwarded = adapter(forwards);
      forwarded.removeItem(0);
      expectCanonical(forwarded, "newest forwarded message removed, bubbles=" + bubbles);
    }

    // Non-bubble mode: merge count limit cascades after a deletion; albums only merge with each other
    TGMessage.bubbles = false;
    MessagesAdapter count = adapter(run(10, 1000, 1, 32, 1));
    count.removeItem(25);
    expectCanonical(count, "merge count limit after deletion");
    ArrayList<TGMessage> album = run(10, 1000, 1, 4, 1);
    album.get(1).msg.mediaAlbumId = 7; album.get(2).msg.mediaAlbumId = 7;
    MessagesAdapter albums = adapter(album);
    albums.removeItem(1);
    expectCanonical(albums, "album neighbour removed");
    TGMessage.bubbles = true;
  }

  static void cost () {
    // Local updates must not re-layout the whole list
    TGMessage.bubbles = true;
    TGMessage.lastReadId = Long.MAX_VALUE;
    ArrayList<TGMessage> mixed = new ArrayList<>();
    for (int i = 0; i < 400; i++) mixed.add(m(10 + i * 10L, 1000 + i * 5, i % 3 == 0 ? 2 : 1));
    MessagesAdapter adapter = adapter(mixed);
    TGMessage.rebuilds = 0; TGMessage.merges = 0;
    adapter.removeItem(200);
    adapter.replaceItem(100, m(adapter.items.get(100).getId(), adapter.items.get(100).getDate(), 1));
    int rebuilds = TGMessage.rebuilds, merges = TGMessage.merges;
    System.out.println("cost_mixed_400 rebuilds=" + rebuilds + " merges=" + merges);
    check(rebuilds <= 6 && merges <= 8, "local updates must stay local, got " + rebuilds + " rebuilds / " + merges + " merges");
    expectCanonical(adapter, "large mixed list");

    // One sender, one long group: the merge index shifts for the newer part, layouts stay untouched
    MessagesAdapter burst = adapter(run(10, 1000, 1, 300, 1));
    TGMessage.rebuilds = 0; TGMessage.merges = 0;
    burst.removeItem(150);
    rebuilds = TGMessage.rebuilds; merges = TGMessage.merges;
    System.out.println("cost_group_300 rebuilds=" + rebuilds + " merges=" + merges);
    check(rebuilds <= 1, "merge index updates must not rebuild layouts, got " + rebuilds);
    check(merges <= 151, "propagation must stay inside the changed group, got " + merges);
    expectCanonical(burst, "long group");
  }

  static TGMessage randomMessage (long id, int date) {
    TGMessage message = m(id, date, 1 + random.nextInt(3));
    message.outgoing = message.msg.sender == 1;
    if (random.nextInt(10) == 0) message.mergeOff = true;
    if (random.nextInt(25) == 0) message.headerOff = true;
    if (random.nextInt(6) == 0) { message.msg.forwardInfo = new TdApi.MessageForwardInfo(); message.msg.source = random.nextInt(2); }
    if (random.nextInt(5) == 0) message.msg.mediaAlbumId = 1 + random.nextInt(2);
    if (random.nextInt(30) == 0) message.msg.authorSignature = "a";
    return message;
  }

  static int step () {
    int[] steps = {1, 30, 200, 450, 700, 901, 3600, 86400};
    return steps[random.nextInt(steps.length)];
  }

  static ArrayList<TGMessage> chain (long firstId, int firstDate, int count) {
    ArrayList<TGMessage> list = new ArrayList<>();
    int date = firstDate;
    for (int i = 0; i < count; i++) { list.add(randomMessage(firstId + i * 10L, date)); date += step(); }
    return list;
  }

  static void randomized (int trials) {
    for (int trial = 0; trial < trials; trial++) {
      TGMessage.bubbles = random.nextInt(4) != 0;
      int date = 1_000_000;
      long minId = 100_000;
      ArrayList<TGMessage> start = chain(minId, date, 1 + random.nextInt(8));
      long maxId = start.get(start.size() - 1).getId();
      int minDate = date, maxDate = start.get(start.size() - 1).getDate();
      TGMessage.lastReadId = maxId + random.nextInt(3) * 20L;
      MessagesAdapter adapter = adapter(start);
      expectCanonical(adapter, "trial " + trial + " initial");
      boolean headerOnTop = false;
      for (int op = 0; op < 14; op++) {
        String label = "trial " + trial + " op " + op;
        int size = adapter.items.size();
        int kind = random.nextInt(8);
        adapter.manager.dedup = false; adapter.manager.sort = false;
        if (kind == 0 && size > 0) {
          int index = random.nextInt(size);
          if (adapter.items.get(index).isThreadHeader()) continue;
          TGMessage old = adapter.items.get(index);
          TGMessage replacement = randomMessage(old.getId(), old.getDate());
          adapter.replaceItem(index, replacement);
          label += " replace " + index;
        } else if (kind == 1 && size > 0) {
          int index = random.nextInt(size);
          adapter.removeItem(index);
          label += " remove " + index;
        } else if (kind == 2 && !headerOnTop) {
          int count = 1 + random.nextInt(5);
          minId -= (count + 1) * 10L;
          ArrayList<TGMessage> list = chain(minId, 0, count);
          int shift = minDate - step() - list.get(count - 1).getDate();
          for (TGMessage message : list) message.msg.date += shift;
          minDate = list.get(0).getDate();
          boolean overlap = random.nextBoolean() && size > 0;
          if (overlap) {
            adapter.manager.dedup = true;
            TGMessage oldest = adapter.items.get(size - 1);
            list.add(oldest.copySpec());
          }
          adapter.addMessages(page(list), true);
          label += " older page " + count + (overlap ? " overlap" : "");
        } else if (kind == 3) {
          int count = 1 + random.nextInt(5);
          ArrayList<TGMessage> list = new ArrayList<>();
          boolean overlap = random.nextBoolean() && size > 0;
          if (overlap) {
            adapter.manager.dedup = true;
            TGMessage newest = adapter.items.get(0).copySpec();
            newest.setShowUnreadBadge(false);
            list.add(newest);
          }
          for (int i = 0; i < count; i++) { maxDate += step(); maxId += 10; list.add(randomMessage(maxId, maxDate)); }
          adapter.addMessages(page(list), false);
          label += " newer page " + count + (overlap ? " overlap" : "");
        } else if (kind == 4) {
          maxDate += step(); maxId += 10;
          adapter.addMessageImpl(randomMessage(maxId, maxDate), false, random.nextBoolean());
          label += " new message";
        } else if (kind == 5 && size > 1) {
          int index = 1 + random.nextInt(size - 1);
          TGMessage newerMessage = adapter.items.get(index - 1), olderMessage = adapter.items.get(index);
          if (olderMessage.isThreadHeader() || newerMessage.getId() - olderMessage.getId() < 2) continue;
          adapter.manager.sort = true;
          long id = olderMessage.getId() + 1;
          int insertDate = olderMessage.getDate() + Math.max(0, (newerMessage.getDate() - olderMessage.getDate()) / 2);
          adapter.addMessageImpl(randomMessage(id, insertDate), false, false);
          label += " sorted insert below " + index;
        } else if (kind == 6 && !headerOnTop && size > 0 && random.nextInt(3) == 0) {
          TGMessage header = m(minId - 5, adapter.items.get(size - 1).getDate(), 99);
          header.threadHeader = true;
          adapter.addMessageImpl(header, true, false);
          headerOnTop = true;
          label += " thread header";
        } else {
          continue;
        }
        expectCanonical(adapter, label);
      }
    }
  }

  public static void main (String[] args) {
    String mode = args.length > 0 ? args[0] : "all";
    if (mode.equals("all") || mode.equals("scenarios")) scenarios();
    if (mode.equals("all") || mode.equals("cost")) cost();
    if (mode.equals("all") || mode.equals("random")) randomized(400);
    System.out.println(checks + " canonical list comparisons passed");
  }
}
'''


def harness_source(message_text, adapter_text):
    return (HARNESS
            .replace('__CONSTANTS__', constants(message_text))
            .replace('__MESSAGE_METHODS__', methods(message_text, MESSAGE_METHODS))
            .replace('__ADAPTER_METHODS__', methods(adapter_text, ADAPTER_METHODS)))


class MessageBubbleGroupingTest(unittest.TestCase):
    def run_harness(self, message_text=None, adapter_text=None, mode='all'):
        message_text = message_text if message_text is not None else MESSAGE.read_text()
        adapter_text = adapter_text if adapter_text is not None else ADAPTER.read_text()
        with tempfile.TemporaryDirectory() as folder:
            d = pathlib.Path(folder)
            (d / 'Harness.java').write_text(harness_source(message_text, adapter_text))
            r = subprocess.run(['javac', '-nowarn', '-d', str(d), str(d / 'Harness.java')], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            return subprocess.run(['java', '-cp', str(d), 'Harness', mode], capture_output=True, text=True, timeout=300)

    def test_local_updates_match_chronological_merge(self):
        r = self.run_harness(mode='scenarios')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('replace_middle=[true,false,false,false]', r.stdout)
        self.assertIn('remove_middle=[true,false,false]', r.stdout)
        self.assertIn('load_older_page=[true,false,false,false]', r.stdout)
        self.assertIn('load_newer_page=[true,false,false,false]', r.stdout)
        self.assertIn('unread_separator_present=true,unread_message_has_header=true,above_is_tail=true', r.stdout)
        self.assertIn('remove_group_head=[true,false,false],joined=true', r.stdout)
        self.assertIn('thread_header_on_top=[true,false,false,true]', r.stdout)

    def test_local_update_cost_is_bounded(self):
        r = self.run_harness(mode='cost')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_randomized_update_sequences(self):
        r = self.run_harness(mode='random')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('canonical list comparisons passed', r.stdout)

    # Negative controls: put the old behaviour back into the production text

    def test_unconditional_group_tail_fails(self):
        text = MESSAGE.read_text()
        old = '    if (!keepBottomState) {\n      setIsBottom(true);\n    }\n'
        self.assertIn(old, text)
        r = self.run_harness(message_text=text.replace(old, '    setIsBottom(true);\n'), mode='scenarios')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('replace middle message', r.stderr)

    def test_missing_unread_remerge_fails(self):
        text = ADAPTER.read_text()
        old = '        TGMessage.remergeItems(this.items, unreadIndex, unreadIndex);\n'
        self.assertIn(old, text)
        r = self.run_harness(adapter_text=text.replace(old, ''), mode='scenarios')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('unread separator inside new page', r.stderr)

    def test_missing_propagation_fails(self):
        text = MESSAGE.read_text()
        old = 'if (index == 0 || (index <= toIndex && !chainChanged)) {'
        self.assertIn(old, text)
        r = self.run_harness(message_text=text.replace(old, 'if (index == 0 || index <= toIndex) {'), mode='scenarios')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('remove middle message', r.stderr)

    def test_stale_forward_tail_fails(self):
        text = MESSAGE.read_text()
        old = '        message.setMergeBottom(false);\n'
        self.assertIn(old, text)
        r = self.run_harness(message_text=text.replace(old, ''), mode='scenarios')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('newest forwarded message removed', r.stderr)

    def test_stale_merge_state_fails(self):
        text = MESSAGE.read_text()
        old = '    mergeTime = mergeIndex = 0;\n    flags &= ~(FLAG_MERGE_FORWARD | FLAG_SHOW_TICKS);\n'
        self.assertIn(old, text)
        r = self.run_harness(message_text=text.replace(old, ''), mode='random')
        self.assertNotEqual(r.returncode, 0)


if __name__ == '__main__':
    unittest.main()
