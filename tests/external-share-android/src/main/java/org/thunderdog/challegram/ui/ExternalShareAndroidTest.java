package org.thunderdog.challegram.ui;

import android.content.ClipData;
import android.content.Intent;
import android.content.IntentFilter;
import android.net.Uri;
import android.os.PatternMatcher;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

import java.io.File;
import java.io.IOException;
import java.net.URL;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import javax.xml.parsers.DocumentBuilderFactory;

public final class ExternalShareAndroidTest {
  private static final String ANDROID_NS = "http://schemas.android.com/apk/res/android";
  private static final Set<String> DEFAULT_CATEGORY = Collections.singleton(Intent.CATEGORY_DEFAULT);
  private static int assertions;

  private ExternalShareAndroidTest () { }

  public static void main (String[] args) throws Exception {
    assertAndroidFrameworkImplementation();
    Path repoRoot = Path.of(requiredProperty("repoRoot"));
    List<FilterSpec> filters = readMainActivityFilters(repoRoot.resolve("app/src/main/AndroidManifest.xml"));
    testManifestFilters(filters);
    testUriCollection();
    testMimeSelection();
    testSharedFilePaths();
    System.out.println("PASS: " + assertions + " assertions; manifest filters=" + filters.size());
  }

  private static void assertAndroidFrameworkImplementation () {
    URL source = IntentFilter.class.getProtectionDomain().getCodeSource().getLocation();
    String value = source.toString();
    check(value.contains("android-all-16-robolectric-13921718"),
      "IntentFilter must come from the Android framework implementation jar, got " + value);
    System.out.println("Android IntentFilter implementation: " + value);
  }

  private static List<FilterSpec> readMainActivityFilters (Path manifest) throws Exception {
    DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
    factory.setNamespaceAware(true);
    factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
    Document document = factory.newDocumentBuilder().parse(manifest.toFile());
    NodeList activities = document.getElementsByTagName("activity");
    for (int i = 0; i < activities.getLength(); i++) {
      Element activity = (Element) activities.item(i);
      if (".MainActivity".equals(androidAttribute(activity, "name"))) {
        return parseFilters(activity);
      }
    }
    throw new AssertionError("MainActivity not found in " + manifest);
  }

  private static List<FilterSpec> parseFilters (Element activity) throws Exception {
    ArrayList<FilterSpec> result = new ArrayList<>();
    for (Node node = activity.getFirstChild(); node != null; node = node.getNextSibling()) {
      if (node instanceof Element && "intent-filter".equals(node.getNodeName())) {
        result.add(parseFilter((Element) node));
      }
    }
    return result;
  }

  private static FilterSpec parseFilter (Element element) throws Exception {
    IntentFilter filter = new IntentFilter();
    LinkedHashSet<String> actions = new LinkedHashSet<>();
    LinkedHashSet<String> categories = new LinkedHashSet<>();
    LinkedHashSet<String> schemes = new LinkedHashSet<>();
    LinkedHashSet<String> types = new LinkedHashSet<>();
    LinkedHashSet<String> authorities = new LinkedHashSet<>();
    for (Node node = element.getFirstChild(); node != null; node = node.getNextSibling()) {
      if (!(node instanceof Element)) {
        continue;
      }
      Element child = (Element) node;
      switch (child.getNodeName()) {
        case "action": {
          String action = requiredAndroidAttribute(child, "name");
          filter.addAction(action);
          actions.add(action);
          break;
        }
        case "category": {
          String category = requiredAndroidAttribute(child, "name");
          filter.addCategory(category);
          categories.add(category);
          break;
        }
        case "data": {
          String type = androidAttribute(child, "mimeType");
          String scheme = androidAttribute(child, "scheme");
          String host = androidAttribute(child, "host");
          String port = androidAttribute(child, "port");
          if (!type.isEmpty()) {
            filter.addDataType(type);
            types.add(type);
          }
          if (!scheme.isEmpty()) {
            filter.addDataScheme(scheme);
            schemes.add(scheme);
          }
          if (!host.isEmpty()) {
            filter.addDataAuthority(host, port.isEmpty() ? null : port);
            authorities.add(host + (port.isEmpty() ? "" : ":" + port));
          }
          addDataPath(filter, child, "path", PatternMatcher.PATTERN_LITERAL);
          addDataPath(filter, child, "pathPrefix", PatternMatcher.PATTERN_PREFIX);
          addDataPath(filter, child, "pathPattern", PatternMatcher.PATTERN_SIMPLE_GLOB);
          break;
        }
        default:
          throw new AssertionError("Unsupported element in intent-filter: " + child.getNodeName());
      }
    }
    return new FilterSpec(filter, actions, categories, schemes, types, authorities);
  }

  private static void addDataPath (IntentFilter filter, Element element, String attribute, int pattern) {
    String value = androidAttribute(element, attribute);
    if (!value.isEmpty()) {
      filter.addDataPath(value, pattern);
    }
  }

  private static String androidAttribute (Element element, String name) {
    return element.getAttributeNS(ANDROID_NS, name);
  }

  private static String requiredAndroidAttribute (Element element, String name) {
    String value = androidAttribute(element, name);
    if (value.isEmpty()) {
      throw new AssertionError("Missing android:" + name + " on " + element.getNodeName());
    }
    return value;
  }

  private static void testManifestFilters (List<FilterSpec> filters) {
    Set<String> shares = Set.of(Intent.ACTION_SEND, Intent.ACTION_SEND_MULTIPLE);
    Set<String> localSchemes = Set.of("content", "file");

    FilterSpec shareWithoutData = uniqueFilter(filters, shares, Set.of(), Set.of());
    FilterSpec shareWithLocalData = uniqueFilter(filters, shares, localSchemes, Set.of());
    FilterSpec typedLocalView = uniqueFilter(filters, Set.of(Intent.ACTION_VIEW), localSchemes, Set.of("*/*"));
    FilterSpec untypedLocalView = uniqueFilter(filters, Set.of(Intent.ACTION_VIEW), localSchemes, Set.of());

    check(shareWithoutData.categories.contains(Intent.CATEGORY_DEFAULT), "MIME-less share filter must be DEFAULT");
    assertMatches(shareWithoutData, Intent.ACTION_SEND, null, null, DEFAULT_CATEGORY, true);
    assertMatches(shareWithoutData, Intent.ACTION_SEND_MULTIPLE, null, null, DEFAULT_CATEGORY, true);
    assertMatches(shareWithoutData, Intent.ACTION_SEND, "application/pdf", null, DEFAULT_CATEGORY, false);
    assertMatches(shareWithoutData, Intent.ACTION_SEND, "", null, DEFAULT_CATEGORY, false);
    assertMatches(shareWithoutData, Intent.ACTION_SEND, null, Uri.parse("content://provider/a"), DEFAULT_CATEGORY, false);

    assertMatches(shareWithLocalData, Intent.ACTION_SEND, null, Uri.parse("content://provider/a"), DEFAULT_CATEGORY, true);
    assertMatches(shareWithLocalData, Intent.ACTION_SEND_MULTIPLE, null, Uri.parse("file:///tmp/a"), DEFAULT_CATEGORY, true);
    assertMatches(shareWithLocalData, Intent.ACTION_SEND, "application/pdf", Uri.parse("content://provider/a"), DEFAULT_CATEGORY, false);
    assertMatches(shareWithLocalData, Intent.ACTION_SEND, "", Uri.parse("content://provider/a"), DEFAULT_CATEGORY, false);
    assertMatches(shareWithLocalData, Intent.ACTION_SEND, null, Uri.parse("https://example.com/a"), DEFAULT_CATEGORY, false);

    assertMatches(typedLocalView, Intent.ACTION_VIEW, "application/pdf", Uri.parse("content://provider/a"), DEFAULT_CATEGORY, true);
    assertMatches(typedLocalView, Intent.ACTION_VIEW, "image/png", Uri.parse("file:///tmp/a"), DEFAULT_CATEGORY, true);
    assertMatches(typedLocalView, Intent.ACTION_VIEW, null, Uri.parse("content://provider/a"), DEFAULT_CATEGORY, false);
    assertMatches(typedLocalView, Intent.ACTION_VIEW, "", Uri.parse("content://provider/a"), DEFAULT_CATEGORY, true);
    assertMatches(typedLocalView, Intent.ACTION_VIEW, "application/pdf", Uri.parse("https://example.com/a"), DEFAULT_CATEGORY, false);

    assertMatches(untypedLocalView, Intent.ACTION_VIEW, null, Uri.parse("content://provider/a"), DEFAULT_CATEGORY, true);
    assertMatches(untypedLocalView, Intent.ACTION_VIEW, null, Uri.parse("file:///tmp/a"), DEFAULT_CATEGORY, true);
    assertMatches(untypedLocalView, Intent.ACTION_VIEW, "application/pdf", Uri.parse("content://provider/a"), DEFAULT_CATEGORY, false);
    assertMatches(untypedLocalView, Intent.ACTION_VIEW, "", Uri.parse("content://provider/a"), DEFAULT_CATEGORY, false);
    assertMatches(untypedLocalView, Intent.ACTION_VIEW, null, Uri.parse("tg://resolve?domain=test"), DEFAULT_CATEGORY, false);

    check(anyMatches(filters, Intent.ACTION_SEND, null, null, DEFAULT_CATEGORY), "MIME-less SEND must resolve");
    check(anyMatches(filters, Intent.ACTION_SEND_MULTIPLE, null, null, DEFAULT_CATEGORY), "MIME-less SEND_MULTIPLE must resolve");
    check(anyMatches(filters, Intent.ACTION_SEND, null, Uri.parse("content://provider/a"), DEFAULT_CATEGORY),
      "MIME-less content SEND must resolve");
    check(anyMatches(filters, Intent.ACTION_SEND, "application/pdf", Uri.parse("content://provider/a"), DEFAULT_CATEGORY),
      "typed content SEND must keep resolving through the existing wildcard filter");
    check(anyMatches(filters, Intent.ACTION_VIEW, null, Uri.parse("file:///tmp/a"), DEFAULT_CATEGORY),
      "MIME-less local VIEW must resolve");
    check(anyMatches(filters, Intent.ACTION_VIEW, "application/pdf", Uri.parse("content://provider/a"), DEFAULT_CATEGORY),
      "typed local VIEW must resolve");
    check(anyMatches(filters, Intent.ACTION_SEND, "", null, DEFAULT_CATEGORY),
      "the existing wildcard SEND filter must match Android's empty-string type");
    check(anyMatches(filters, Intent.ACTION_SEND, "", Uri.parse("content://provider/a"), DEFAULT_CATEGORY),
      "the existing wildcard SEND filter must match an empty-string type with content data");
    check(anyMatches(filters, Intent.ACTION_VIEW, "", Uri.parse("content://provider/a"), DEFAULT_CATEGORY),
      "the wildcard local VIEW filter must match Android's empty-string type");
    System.out.println("Android empty MIME probe: literal empty string matches */* but not an untyped filter");

    Set<String> browsable = Set.of(Intent.CATEGORY_DEFAULT, Intent.CATEGORY_BROWSABLE);
    check(!anyMatches(filters, Intent.ACTION_VIEW, null, Uri.parse("https://example.com/a"), browsable),
      "new local filters must not capture ordinary HTTPS URLs");
    check(anyMatches(filters, Intent.ACTION_VIEW, null, Uri.parse("https://t.me/test"), browsable),
      "existing Telegram HTTPS filter must still resolve");
    check(anyMatches(filters, Intent.ACTION_VIEW, null, Uri.parse("tg://resolve?domain=test"), browsable),
      "existing tg filter must still resolve");
  }

  private static FilterSpec uniqueFilter (List<FilterSpec> filters, Set<String> actions,
                                            Set<String> schemes, Set<String> types) {
    List<FilterSpec> matches = filters.stream()
      .filter(spec -> spec.actions.equals(actions) && spec.schemes.equals(schemes) && spec.types.equals(types))
      .toList();
    check(matches.size() == 1,
      "Expected exactly one filter actions=" + actions + " schemes=" + schemes + " types=" + types + ", got " + matches.size());
    return matches.get(0);
  }

  private static boolean anyMatches (List<FilterSpec> filters, String action, String type, Uri data,
                                      Set<String> categories) {
    for (FilterSpec filter : filters) {
      if (matches(filter, action, type, data, categories)) {
        return true;
      }
    }
    return false;
  }

  private static void assertMatches (FilterSpec filter, String action, String type, Uri data,
                                     Set<String> categories, boolean expected) {
    boolean actual = matches(filter, action, type, data, categories);
    check(actual == expected,
      "Unexpected match=" + actual + " for action=" + action + " type=" + type + " data=" + data
        + " against actions=" + filter.actions + " schemes=" + filter.schemes + " types=" + filter.types);
  }

  private static boolean matches (FilterSpec filter, String action, String type, Uri data,
                                  Set<String> categories) {
    String scheme = data != null ? data.getScheme() : null;
    return filter.filter.match(action, type, scheme, data, categories, "ExternalShareAndroidTest") >= 0;
  }

  private static void testUriCollection () {
    Uri first = Uri.parse("content://provider/first");
    Uri second = Uri.parse("file:///tmp/second");
    Uri third = Uri.parse("content://provider/third");

    Intent explicitStreams = new Intent(Intent.ACTION_SEND_MULTIPLE);
    explicitStreams.putParcelableArrayListExtra(Intent.EXTRA_STREAM,
      new ArrayList<>(Arrays.asList(first, second, first)));
    explicitStreams.setClipData(clip(second, third));
    explicitStreams.setData(Uri.parse("content://provider/ignored-data"));
    checkList(ExternalShareUtils.collectUris(explicitStreams), first, second);

    Intent invalidStream = new Intent(Intent.ACTION_SEND_MULTIPLE);
    ArrayList<Object> mixed = new ArrayList<>();
    mixed.add(first);
    mixed.add(Uri.parse("https://example.com/not-local"));
    invalidStream.putExtra(Intent.EXTRA_STREAM, mixed);
    invalidStream.setClipData(clip(third));
    expectThrows(IllegalArgumentException.class, () -> ExternalShareUtils.collectUris(invalidStream),
      "an invalid explicit stream must fail the whole batch");

    Intent invalidSingle = new Intent(Intent.ACTION_SEND);
    invalidSingle.putExtra(Intent.EXTRA_STREAM, "not a Uri");
    expectThrows(IllegalArgumentException.class, () -> ExternalShareUtils.collectUris(invalidSingle),
      "a non-Uri explicit stream must be rejected");

    Intent fallback = new Intent(Intent.ACTION_SEND);
    ClipData fallbackClip = new ClipData("share", new String[] {"*/*"}, new ClipData.Item("caption only"));
    fallbackClip.addItem(new ClipData.Item(first));
    fallbackClip.addItem(new ClipData.Item(first));
    fallback.setClipData(fallbackClip);
    fallback.setData(second);
    checkList(ExternalShareUtils.collectUris(fallback), first);

    Intent textClipFallsBackToData = new Intent(Intent.ACTION_SEND);
    textClipFallsBackToData.setClipData(
      new ClipData("share", new String[] {"text/plain"}, new ClipData.Item("caption only")));
    textClipFallsBackToData.setData(third);
    checkList(ExternalShareUtils.collectUris(textClipFallsBackToData), third);

    Intent emptyExplicitStreams = new Intent(Intent.ACTION_SEND_MULTIPLE);
    emptyExplicitStreams.putParcelableArrayListExtra(Intent.EXTRA_STREAM, new ArrayList<>());
    emptyExplicitStreams.setClipData(clip(first));
    emptyExplicitStreams.setData(second);
    check(ExternalShareUtils.collectUris(emptyExplicitStreams).isEmpty(),
      "an explicitly empty stream list must not fall back to ClipData or data");

    Intent nullExplicitStream = new Intent(Intent.ACTION_SEND);
    nullExplicitStream.putExtra(Intent.EXTRA_STREAM, (Uri) null);
    nullExplicitStream.setData(first);
    expectThrows(IllegalArgumentException.class, () -> ExternalShareUtils.collectUris(nullExplicitStream),
      "an explicitly null stream must be rejected without data fallback");

    Intent badClip = new Intent(Intent.ACTION_SEND);
    badClip.setClipData(clip(Uri.parse("https://example.com/not-local")));
    expectThrows(IllegalArgumentException.class, () -> ExternalShareUtils.collectUris(badClip),
      "a non-local ClipData URI must be rejected");

    Intent dataOnly = new Intent(Intent.ACTION_SEND);
    dataOnly.setData(third);
    checkList(ExternalShareUtils.collectUris(dataOnly), third);
    check(ExternalShareUtils.collectUris(new Intent(Intent.ACTION_SEND)).isEmpty(),
      "a text-only share without a URI must stay empty");

    Intent clearedView = new Intent();
    clearedView.putExtra(Intent.EXTRA_STREAM, "invalid but irrelevant for VIEW");
    clearedView.setClipData(clip(Uri.parse("https://example.com/irrelevant")));
    clearedView.setData(first);
    checkList(ExternalShareUtils.collectUris(clearedView, Intent.ACTION_VIEW), first);

    Intent view = new Intent(Intent.ACTION_VIEW);
    view.putExtra(Intent.EXTRA_STREAM, second);
    view.setData(third);
    checkList(ExternalShareUtils.collectUris(view), third);

    check(ExternalShareUtils.isLocalFileUri(Uri.parse("CONTENT://provider/a")), "content scheme is case-insensitive");
    check(ExternalShareUtils.isLocalFileUri(second), "file URI must be local");
    check(!ExternalShareUtils.isLocalFileUri(Uri.parse("https://example.com/a")), "HTTPS URI must not be local");
    check(!ExternalShareUtils.isLocalFileUri(null), "null URI must not be local");
  }

  private static ClipData clip (Uri... uris) {
    ClipData clip = new ClipData("share", new String[] {"*/*"}, new ClipData.Item(uris[0]));
    for (int i = 1; i < uris.length; i++) {
      clip.addItem(new ClipData.Item(uris[i]));
    }
    return clip;
  }

  private static void testMimeSelection () {
    checkEquals("image/png", ExternalShareUtils.chooseMimeType(" Image/PNG ; charset=UTF-8 ", "application/pdf", null, null));
    checkEquals("application/pdf", ExternalShareUtils.chooseMimeType("*/*", " Application/PDF ", "image/png", null));
    checkEquals("image/webp", ExternalShareUtils.chooseMimeType("invalid", "text/ plain", "IMAGE/WEBP", "application/zip"));
    checkEquals("application/zip", ExternalShareUtils.chooseMimeType(null, "application/", "*/*", "APPLICATION/ZIP"));
    checkEquals("application/octet-stream", ExternalShareUtils.chooseMimeType(null, "", "*/*", "not-a-type"));
    checkEquals("text/plain", ExternalShareUtils.resolveMimeType(null, Uri.parse("file:///tmp/no-extension"),
      "TEXT/PLAIN; charset=utf-8"));
    checkEquals("image/png", ExternalShareUtils.resolveMimeType(null, Uri.parse("file:///tmp/photo.PNG"), null));

    // A source's concrete declaration is authoritative, including an explicit generic binary type.
    checkEquals("application/octet-stream",
      ExternalShareUtils.chooseMimeType("application/octet-stream", "image/png", null, null));
    checkEquals("application/octet-stream",
      ExternalShareUtils.resolveMimeType(null, Uri.parse("file:///tmp/no_suffix"), "application/octet-stream"));

    // A family declaration must not be downgraded or switched to a conflicting provider family.
    checkEquals("image/*",
      ExternalShareUtils.chooseMimeType("image/*", "application/octet-stream", null, null));
    checkEquals("image/*",
      ExternalShareUtils.chooseMimeType("image/*", "video/mp4", null, null));
    checkEquals("video/*",
      ExternalShareUtils.chooseMimeType("video/*", "application/octet-stream", null, null));
    checkEquals("audio/*",
      ExternalShareUtils.chooseMimeType("audio/*", "video/mp4", null, null));
    checkEquals("application/*",
      ExternalShareUtils.chooseMimeType("application/*", "application/octet-stream", null, null));
    checkEquals("application/pdf",
      ExternalShareUtils.chooseMimeType("application/*", "application/octet-stream", "application/pdf", null));

    // Same-family evidence may refine the wildcard so GIF/WebP and similar behavior is retained.
    checkEquals("image/png", ExternalShareUtils.chooseMimeType("image/*", "image/png", null, null));
    checkEquals("image/gif",
      ExternalShareUtils.chooseMimeType("image/*", "application/octet-stream", "image/gif", null));
    checkEquals("audio/ogg", ExternalShareUtils.chooseMimeType("audio/*", "audio/ogg", null, null));

    Uri noSuffix = Uri.parse("file:///tmp/no_suffix");
    checkEquals("image/*", ExternalShareUtils.resolveMimeType(null, noSuffix, "image/*"));
    checkEquals("image/png", ExternalShareUtils.resolveMimeType(null, Uri.parse("file:///tmp/image.PNG"), "image/*"));
    checkEquals("video/*", ExternalShareUtils.resolveMimeType(null, noSuffix, "video/*"));
    checkEquals("audio/ogg", ExternalShareUtils.resolveMimeType(null, Uri.parse("file:///tmp/track.ogg"), "audio/*"));
    checkEquals("application/*", ExternalShareUtils.resolveMimeType(null, noSuffix, "application/*"));
    checkEquals("application/pdf",
      ExternalShareUtils.resolveMimeType(null, Uri.parse("file:///tmp/file.pdf"), "application/*"));

    // A fully generic or empty declaration is inferred normally, then falls back to a document type.
    checkEquals("image/webp", ExternalShareUtils.chooseMimeType("*/*", "image/webp", null, null));
    checkEquals("application/octet-stream", ExternalShareUtils.chooseMimeType("*/*", null, null, null));
    checkEquals("application/octet-stream", ExternalShareUtils.chooseMimeType("", null, null, null));
    checkEquals("image/webp", ExternalShareUtils.resolveMimeType(null, Uri.parse("file:///tmp/image.webp"), ""));
    checkEquals("application/octet-stream", ExternalShareUtils.resolveMimeType(null, noSuffix, "*/*"));
    checkEquals("image/gif", ExternalShareUtils.resolveMimeType(null, Uri.parse("file:///tmp/animation.GIF"), "image/*"));
  }

  private static void testSharedFilePaths () throws Exception {
    Path root = Files.createTempDirectory("external-share-test-");
    try {
      Path privateDirectory = Files.createDirectory(root.resolve("app-private"));
      Path privateFile = Files.writeString(privateDirectory.resolve("secret.txt"), "secret");
      Path externalFile = Files.writeString(root.resolve("outside.txt"), "outside");
      Path prefixSibling = Files.createDirectory(root.resolve("app-private-backup"));
      Path siblingFile = Files.writeString(prefixSibling.resolve("allowed.txt"), "allowed");

      String privateCanonical = privateDirectory.toFile().getCanonicalPath();
      check(ExternalShareUtils.isPathWithinDirectory(privateCanonical, privateCanonical),
        "private directory must include itself");
      check(ExternalShareUtils.isPathWithinDirectory(privateFile.toFile().getCanonicalPath(), privateCanonical),
        "private directory must include a child");
      check(!ExternalShareUtils.isPathWithinDirectory(siblingFile.toFile().getCanonicalPath(), privateCanonical),
        "a path with the same string prefix must not count as private");

      checkEquals(externalFile.toFile().getCanonicalPath(),
        ExternalShareUtils.validateSharedFilePath(Uri.fromFile(externalFile.toFile()), privateCanonical));
      checkEquals(siblingFile.toFile().getCanonicalPath(),
        ExternalShareUtils.validateSharedFilePath(Uri.fromFile(siblingFile.toFile()), privateCanonical));
      Path missing = root.resolve("missing.txt");
      checkEquals(missing.toFile().getCanonicalPath(),
        ExternalShareUtils.validateSharedFilePath(Uri.fromFile(missing.toFile()), privateCanonical));
      checkEquals("content://provider/item/1?token=opaque",
        ExternalShareUtils.validateSharedFilePath(Uri.parse("content://provider/item/1?token=opaque"), privateCanonical));

      expectThrows(IOException.class,
        () -> ExternalShareUtils.validateSharedFilePath(Uri.fromFile(privateFile.toFile()), privateCanonical),
        "a direct private file must be rejected");

      File escaped = new File(privateDirectory.toFile(), "../outside.txt");
      checkEquals(externalFile.toFile().getCanonicalPath(),
        ExternalShareUtils.validateSharedFilePath(Uri.fromFile(escaped), privateCanonical));

      Path publicDirectory = Files.createDirectory(root.resolve("public"));
      File traversedIntoPrivate = new File(publicDirectory.toFile(), "../app-private/secret.txt");
      expectThrows(IOException.class,
        () -> ExternalShareUtils.validateSharedFilePath(Uri.fromFile(traversedIntoPrivate), privateCanonical),
        "dot-dot traversal into the private directory must be rejected");

      Path privateLink = root.resolve("private-link.txt");
      Files.createSymbolicLink(privateLink, privateFile);
      expectThrows(IOException.class,
        () -> ExternalShareUtils.validateSharedFilePath(Uri.fromFile(privateLink.toFile()), privateCanonical),
        "a symlink into the private directory must be rejected after canonicalization");

      checkEquals(externalFile.toFile().getCanonicalPath(),
        ExternalShareUtils.resolveSharedFilePath(Uri.fromFile(externalFile.toFile()), privateCanonical));
      expectThrows(IOException.class,
        () -> ExternalShareUtils.resolveSharedFilePath(Uri.fromFile(missing.toFile()), privateCanonical),
        "the worker-stage resolver must reject a missing file");
      expectThrows(IOException.class,
        () -> ExternalShareUtils.resolveSharedFilePath(Uri.fromFile(publicDirectory.toFile()), privateCanonical),
        "the worker-stage resolver must reject a directory");
      expectThrows(IOException.class,
        () -> ExternalShareUtils.validateSharedFilePath(Uri.parse("https://example.com/a"), privateCanonical),
        "remote URIs must not pass file validation");
    } finally {
      deleteTree(root);
    }
  }

  private static void deleteTree (Path root) throws IOException {
    try (var paths = Files.walk(root)) {
      for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
        Files.deleteIfExists(path);
      }
    }
  }

  private static void checkList (List<Uri> actual, Uri... expected) {
    check(actual.equals(Arrays.asList(expected)), "Expected URI list " + Arrays.toString(expected) + ", got " + actual);
  }

  private static void checkEquals (String expected, String actual) {
    check(expected.equals(actual), "Expected " + expected + ", got " + actual);
  }

  private static <T extends Throwable> void expectThrows (Class<T> expected, ThrowingRunnable action, String message) {
    try {
      action.run();
    } catch (Throwable throwable) {
      check(expected.isInstance(throwable), message + "; expected " + expected.getName() + ", got " + throwable);
      return;
    }
    throw new AssertionError(message + "; expected " + expected.getName());
  }

  private static String requiredProperty (String name) {
    String value = System.getProperty(name);
    if (value == null || value.isBlank()) {
      throw new AssertionError("Missing system property: " + name);
    }
    return value;
  }

  private static void check (boolean condition, String message) {
    assertions++;
    if (!condition) {
      throw new AssertionError(message);
    }
  }

  private record FilterSpec(IntentFilter filter, Set<String> actions, Set<String> categories,
                            Set<String> schemes, Set<String> types, Set<String> authorities) { }

  @FunctionalInterface
  private interface ThrowingRunnable {
    void run () throws Exception;
  }
}
