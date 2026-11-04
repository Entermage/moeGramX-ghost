"""Host builds of the changed native code; NOT the ARM64 library or a device test.

* app/jni: the WebP failure message and the device-info formatter run under GCC's
  AddressSanitizer with the JDK's jni.h; the old code's 1-byte overflow is a negative control.
* app/jni/voice.c: getWaveform with an opusfile double (persistent read error, short file).
* TDLib: ForumTopicManager::on_delete_forum_topic / delete_all_dialog_topics run with a
  key/value double for the per-account binlog store; no topic is deleted on a server.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from test_chat_navigation import block

ROOT = Path(__file__).resolve().parents[1]
JNI = ROOT / "app/jni"
TD_SOURCE = ROOT / "tdlib/source/td"
TOPICS = "td/telegram/ForumTopicManager.cpp"


def jdk_include():
    home = os.environ.get("JAVA_HOME")
    base = Path(home) if home else Path(shutil.which("javac")).resolve().parents[1]
    return base / "include"


def asan(compiler, source, suffix, tmp, *flags):
    path = Path(tmp) / f"test{suffix}"
    path.write_text(source)
    binary = Path(tmp) / "test"
    subprocess.run([compiler, "-fsanitize=address", "-fno-omit-frame-pointer", "-g", "-O0", *flags, str(path), "-o", str(binary)],
                   check=True, capture_output=True, text=True)
    return subprocess.run([str(binary)], capture_output=True, text=True,
                          env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0"})


WEBP = r'''
#include <jni.h>
#include <stdio.h>
#include <string.h>
typedef int VP8StatusCode;
#define VP8_STATUS_OK 0
static jclass jclass_RuntimeException;
static char thrown[64];
static jint capture (JNIEnv *env, jclass c, const char *message) { strncpy(thrown, message, sizeof(thrown) - 1); return 0; }
static jboolean fail (JNIEnv *env, VP8StatusCode resultCode) {
  /* WEBP_BLOCK */
  return 1;
}
int main (void) {
  struct JNINativeInterface_ table; memset(&table, 0, sizeof(table)); table.ThrowNew = capture;
  const struct JNINativeInterface_ *functions = &table; JNIEnv *env = &functions;
  for (int code = 1; code <= 7; code++) {
    if (fail(env, code) != 0) return 2;
    char expected[64]; snprintf(expected, sizeof(expected), "WebPGetFeatures failed: %d", code);
    if (strcmp(expected, thrown) != 0) { fprintf(stderr, "wrong message: %s\n", thrown); return 3; }
  }
  puts("webp failure message ok");
  return 0;
}
'''

DEVICE = r'''
#include <cstdio>
#include <string>
#include <iostream>
#define __ANDROID_API__ 23
static std::string app_version_signature = "0.29.1.1813", sdk_version_name = "16", os_arch = "arm64-v8a",
  device_manufacturer = "Maker", device_model = "Model", device_brand = "Brand", device_display = "Display",
  device_product = "Product", device_fingerprint = "brand/product/device:16/ID/1:user/release-keys";
static int sdk_version = 36, screen_width = 1080, screen_height = 2400;
static float screen_density = 2.625f;
/* FORMAT_MACRO */
/* DEVICE_FUNCTION */
int main () {
  std::string info = sprintf_device_info();
  char expected[4096]; std::snprintf(expected, sizeof(expected), APP_INFO_FORMAT);
  if (info != expected) { std::cerr << "device info truncated: [" << info << "]\n"; return 3; }
  if (info.empty() || info.back() != '\n') { std::cerr << "missing final newline\n"; return 4; }
  std::cout << "device info ok\n";
}
'''

TOPICS_HARNESS = r'''
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <iostream>
#include <stdexcept>
#include <utility>
namespace td {
struct Unit {};
struct Status { bool error = false; bool is_error () const { return error; } };
template <class T> struct Promise { int *values = nullptr; void set_value (T) { if (values) ++*values; } template <class E> void set_error (E &&) { } };
struct Auto {};
struct DialogId { long long id = 0; DialogId () = default; explicit DialogId (long long v) : id(v) { } long long get () const { return id; }
  bool operator< (DialogId o) const { return id < o.id; } };
inline std::ostream &operator<< (std::ostream &s, DialogId d) { return s << d.id; }
struct ForumTopicId { int id = 0; ForumTopicId () = default; explicit ForumTopicId (int v) : id(v) { } int get () const { return id; }
  bool is_valid () const { return id > 0; } bool operator< (ForumTopicId o) const { return id < o.id; } };
inline std::ostream &operator<< (std::ostream &s, ForumTopicId t) { return s << t.id; }
struct StringStream { std::ostringstream out; template <class T> StringStream &operator<< (const T &v) { out << v; return *this; }
  operator std::string () const { return out.str(); } };
#define PSTRING() ::td::StringStream()
#define CHECK(x) if (!(x)) throw std::runtime_error("CHECK")
#define LOG(level) std::ostringstream()
#define TRY_STATUS_PROMISE(promise, status) if ((status).is_error()) { (promise).set_error(1); return; }
struct BinlogPmc {
  std::map<std::string, std::string> values;
  void set (const std::string &k, std::string v) { values[k] = std::move(v); }
  void erase (const std::string &k) { values.erase(k); }
  void erase_by_prefix (const std::string &p) { for (auto it = values.begin(); it != values.end();) it = it->first.rfind(p, 0) == 0 ? values.erase(it) : std::next(it); }
};
struct MessageThreadDbAsync { void delete_all_dialog_message_threads (DialogId, Auto) { } void delete_message_thread (DialogId, ForumTopicId, Promise<Unit>) { } };
struct TdDb { BinlogPmc pmc; BinlogPmc *get_binlog_pmc () { return &pmc; } MessageThreadDbAsync *get_message_thread_db_async () { return nullptr; } };
struct Global { TdDb db; Status closing; TdDb *td_db () { return &db; } Status close_status () const { return closing; } };
inline Global *G () { static Global g; return &g; }
struct Topic {};
struct DialogTopics { std::map<ForumTopicId, Topic> topics_; std::set<ForumTopicId> deleted_topic_ids_; };
struct TopicsMap { std::map<DialogId, DialogTopics> map; DialogTopics *get_pointer (DialogId d) { auto it = map.find(d); return it == map.end() ? nullptr : &it->second; }
  void erase (DialogId d) { map.erase(d); } };
struct ForumTopicManager {
  TopicsMap dialog_topics_;
  void on_delete_forum_topic (DialogId dialog_id, ForumTopicId forum_topic_id, Promise<Unit> &&promise);
  void delete_all_dialog_topics (DialogId dialog_id);
  // Its own message-thread table is disabled in this TDLib revision; covered elsewhere.
  void delete_topic_from_database (DialogId, ForumTopicId, Promise<Unit> &&promise) { promise.set_value(Unit()); }
};
/* TOPIC_METHODS */
}
using namespace td;
static void check (bool b, const char *m) { if (!b) throw std::runtime_error(m); }
static std::string key (long long chat, int topic) { return "moex_topic_read:" + std::to_string(chat) + ":" + std::to_string(topic); }
int main () {
  auto &pmc = G()->td_db()->get_binlog_pmc()->values;
  ForumTopicManager manager;
  pmc[key(-100, 5)] = "state"; pmc[key(-100, 6)] = "state"; pmc[key(-100, 55)] = "state"; pmc[key(-200, 5)] = "state";
  pmc["other"] = "kept";
  manager.dialog_topics_.map[DialogId(-100)].topics_[ForumTopicId(5)] = Topic();
  int done = 0; Promise<Unit> promise; promise.values = &done;
  manager.on_delete_forum_topic(DialogId(-100), ForumTopicId(5), std::move(promise));
  check(done == 1, "promise completed");
  check(pmc.count(key(-100, 5)) == 0, "deleted topic keeps its local read key");
  check(pmc.count(key(-100, 6)) && pmc.count(key(-100, 55)) && pmc.count(key(-200, 5)) && pmc.count("other"), "other topics keep their keys");
  check(manager.dialog_topics_.map[DialogId(-100)].deleted_topic_ids_.count(ForumTopicId(5)) == 1, "topic remembered as deleted");
  Promise<Unit> again; again.values = &done;
  manager.on_delete_forum_topic(DialogId(-100), ForumTopicId(5), std::move(again));
  check(done == 2 && pmc.size() == 4, "deleting again is harmless");
  Promise<Unit> unloaded; unloaded.values = &done;
  manager.on_delete_forum_topic(DialogId(-200), ForumTopicId(5), std::move(unloaded));
  check(pmc.count(key(-200, 5)) == 0, "a topic of a chat that is not loaded is cleaned up too");
  G()->closing.error = true; pmc[key(-100, 7)] = "state";
  Promise<Unit> closing; closing.values = &done;
  manager.on_delete_forum_topic(DialogId(-100), ForumTopicId(7), std::move(closing));
  check(pmc.count(key(-100, 7)) == 1 && done == 3, "nothing happens while closing");
  G()->closing.error = false;
  manager.delete_all_dialog_topics(DialogId(-100));
  check(pmc.count(key(-100, 6)) == 0 && pmc.count(key(-100, 55)) == 0 && pmc.count(key(-100, 7)) == 0 && pmc.count("other") == 1, "whole forum cleanup");
  std::cout << "native topic delete cleanup ok\n";
}
'''


WAVEFORM = r'''
#include <jni.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define logw(...) ((void) 0)
#define TAG_VOICE 0
#define OPUS_OK 0
/* MACROS */
typedef struct OggOpusFile { int mode, calls; } OggOpusFile;
static OggOpusFile file;
static OggOpusFile *op_open_file (const char *path, int *error) { *error = OPUS_OK; file.calls = 0; file.mode = path[0] - '0'; return &file; }
static int64_t op_pcm_total (OggOpusFile *f, int link) { return 48000; }
static int op_read (OggOpusFile *f, int16_t *pcm, int size, int *link) {
  if (++f->calls > 10000) { fprintf(stderr, "op_read busy loop\n"); exit(9); }
  if (f->mode == 1) return -128; /* OP_EREAD every time */
  if (f->calls > 1) return 0;
  for (int i = 0; i < 500; i++) pcm[i] = (int16_t) (i * 10);
  return 500; /* a short file: 500 of 48000 samples */
}
static void op_free (OggOpusFile *f) { }
// The old allocation left unread samples as heap garbage; make that visible.
static void *dirty_malloc (size_t n) { void *p = malloc(n); if (p) memset(p, 0x7b, n); return p; }
#define malloc(n) dirty_malloc(n)
int16_t *sampleBuffer = NULL;
/* SET_BITS */
/* FUNCTION */
static const char *path_of (JNIEnv *env, jstring s, jboolean *copy) { return (const char *) s; }
static void release_path (JNIEnv *env, jstring s, const char *c) { }
static jbyte array[64];
static jbyteArray new_array (JNIEnv *env, jsize n) { memset(array, 0, sizeof(array)); return (jbyteArray) array; }
static jbyte *array_elements (JNIEnv *env, jbyteArray a, jboolean *copy) { return array; }
static void release_array (JNIEnv *env, jbyteArray a, jbyte *e, jint mode) { }
int main (void) {
  struct JNINativeInterface_ t; memset(&t, 0, sizeof(t));
  t.GetStringUTFChars = path_of; t.ReleaseStringUTFChars = release_path; t.NewByteArray = new_array;
  t.GetByteArrayElements = array_elements; t.ReleaseByteArrayElements = release_array;
  const struct JNINativeInterface_ *functions = &t; JNIEnv *env = &functions;
  if (Java_org_thunderdog_challegram_N_getWaveform(env, NULL, (jstring) "1") == NULL) return 2;
  puts("persistent read error ends the scan");
  Java_org_thunderdog_challegram_N_getWaveform(env, NULL, (jstring) "2");
  // 500 samples at one bar per 480 samples: bar 0 and bar 1 have data, bars 2..99 are silent.
  for (int i = 2; i < 100; i++) {
    int offset = i * 5, value = (((uint8_t) array[offset / 8] | ((uint8_t) array[offset / 8 + 1] << 8)) >> (offset % 8)) & 31;
    if (value != 0) { fprintf(stderr, "uninitialized waveform bar %d = %d\n", i, value); return 3; }
  }
  puts("short file leaves the rest of the waveform silent");
  return 0;
}
'''


def waveform_source(text=None):
    text = text or (JNI / "voice.c").read_text()
    macros = "\n".join(re.findall(r"^#define (?:max|min)\(x, y\) .*$", text, re.M))
    macros = "\n".join("#define " + m.split("#define ", 1)[1] for m in macros.splitlines())
    return (WAVEFORM.replace("/* MACROS */", macros)
            .replace("/* SET_BITS */", block_text(text, "static inline void set_bits("))
            .replace("/* FUNCTION */", block_text(text, "JNIEXPORT jbyteArray Java_org_thunderdog_challegram_N_getWaveform(")))


def webp_source(text=None):
    text = text or (JNI / "image.c").read_text()
    return WEBP.replace("/* WEBP_BLOCK */", block_text(text, "if (resultCode != VP8_STATUS_OK) {"))


def device_source(text=None):
    text = text or (JNI / "log.cpp").read_text()
    fmt = re.search(r"^#define APP_INFO_FORMAT .*$", text, re.M).group(0)
    return DEVICE.replace("/* FORMAT_MACRO */", fmt).replace("/* DEVICE_FUNCTION */", block_text(text, "inline std::string sprintf_device_info () {"))


def patched_topics():
    """ForumTopicManager.cpp with the Ghost patch applied to a copy: CI runs this before it patches the TDLib checkout."""
    patch = ROOT / "patches/tdlib-ghost-mode.patch"
    with tempfile.TemporaryDirectory(prefix="native-topics-patched-") as tmp:
        for name in re.findall(r"^--- a/(.+)$", patch.read_text(), re.M):
            target = Path(tmp) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(subprocess.check_output(["git", "-C", str(TD_SOURCE), "show", "HEAD:" + name]))
        subprocess.run(["git", "apply", str(patch)], cwd=tmp, check=True)
        return (Path(tmp) / TOPICS).read_text()


def topics_source(text=None):
    text = text or patched_topics()
    methods = "\n".join(block_text(text, s) for s in (
        "void ForumTopicManager::on_delete_forum_topic(", "void ForumTopicManager::delete_all_dialog_topics("))
    return TOPICS_HARNESS.replace("/* TOPIC_METHODS */", methods)


def block_text(text, signature):
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        f.write(text)
    try:
        return block(Path(f.name), signature)
    finally:
        os.unlink(f.name)


class NativeFixesTest(unittest.TestCase):
    def test_webp_failure_message_without_overflow(self):
        with tempfile.TemporaryDirectory(prefix="jni-webp-") as tmp:
            include = jdk_include()
            r = asan("gcc", webp_source(), ".c", tmp, f"-I{include}", f"-I{include / 'linux'}")
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])

    def test_negative_webp_overflow_detected(self):
        text = (JNI / "image.c").read_text().replace("    char buffer[count + 1];\n    snprintf(buffer, count + 1, fmt, code);",
                                                     "    char buffer[count + 1];\n    buffer[count + 1] = '\\0';\n    snprintf(buffer, count + 1, fmt, code);")
        with tempfile.TemporaryDirectory(prefix="jni-webp-old-") as tmp:
            include = jdk_include()
            r = asan("gcc", webp_source(text), ".c", tmp, f"-I{include}", f"-I{include / 'linux'}")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("stack-buffer-overflow", r.stderr)

    def test_device_info_complete_without_overflow(self):
        with tempfile.TemporaryDirectory(prefix="jni-log-") as tmp:
            r = asan("g++", device_source(), ".cpp", tmp, "-std=c++17")
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])

    def test_negative_device_info_overflow_and_truncation(self):
        text = (JNI / "log.cpp").read_text().replace("  char buffer[count + 1];\n  snprintf(buffer, count + 1, APP_INFO_FORMAT);",
                                                     "  char buffer[count + 1];\n  buffer[count + 1] = '\\0';\n  snprintf(buffer, count, APP_INFO_FORMAT);")
        with tempfile.TemporaryDirectory(prefix="jni-log-old-") as tmp:
            r = asan("g++", device_source(text), ".cpp", tmp, "-std=c++17")
        self.assertNotEqual(r.returncode, 0)
        self.assertRegex(r.stderr, "stack-buffer-overflow|device info truncated")

    def run_waveform(self, text=None):
        with tempfile.TemporaryDirectory(prefix="jni-waveform-") as tmp:
            include = jdk_include()
            path = Path(tmp) / "test.c"
            path.write_text(waveform_source(text))
            binary = Path(tmp) / "test"
            subprocess.run(["gcc", "-fsanitize=address", "-g", "-O0", "-Wno-int-conversion", "-Wno-incompatible-pointer-types",
                            f"-I{include}", f"-I{include / 'linux'}", str(path), "-o", str(binary)],
                           check=True, capture_output=True, text=True)
            return subprocess.run([str(binary)], capture_output=True, text=True, timeout=60,
                                  env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0"})

    def test_waveform_read_error_and_short_file(self):
        r = self.run_waveform()
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])

    def test_negative_waveform_previous_loop_and_buffer(self):
        text = (JNI / "voice.c").read_text()
        loop = "        if (readSamples < 0) {\n            break; // A decoding error repeats forever; keep what was read.\n        }\n"
        self.assertEqual(text.count(loop), 1)
        r = self.run_waveform(text.replace(loop, ""))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("op_read busy loop", r.stderr)
        alloc = "    uint16_t *samples = calloc(100, sizeof(uint16_t));\n    if (samples == NULL) {"
        self.assertEqual(text.count(alloc), 1)
        r = self.run_waveform(text.replace(alloc, "    uint16_t *samples = malloc(100 * 2);\n    if (samples == NULL) {"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("uninitialized waveform bar", r.stderr)

    def test_topic_delete_erases_local_read_key(self):
        with tempfile.TemporaryDirectory(prefix="native-topic-delete-") as tmp:
            r = asan("g++", topics_source(), ".cpp", tmp, "-std=c++17")
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])

    def test_negative_topic_delete_keeps_key(self):
        text = patched_topics()
        old = ("  G()->td_db()->get_binlog_pmc()->erase(PSTRING() << \"moex_topic_read:\" << dialog_id.get() << ':'\n"
               "                                                  << forum_topic_id.get());\n")
        self.assertEqual(text.count(old), 1)
        with tempfile.TemporaryDirectory(prefix="native-topic-delete-old-") as tmp:
            r = asan("g++", topics_source(text.replace(old, "")), ".cpp", tmp, "-std=c++17")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("deleted topic keeps its local read key", r.stderr)


if __name__ == "__main__":
    unittest.main()
