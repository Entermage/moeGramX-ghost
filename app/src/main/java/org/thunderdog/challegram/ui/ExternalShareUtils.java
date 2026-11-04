/*
 * This file is a part of moegramX.
 * Licensed under the GNU General Public License, version 3 or later.
 */
package org.thunderdog.challegram.ui;

import android.content.ClipData;
import android.content.ContentResolver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.ProviderInfo;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.OpenableColumns;

import androidx.annotation.Nullable;

import org.thunderdog.challegram.Log;
import org.thunderdog.challegram.U;
import org.thunderdog.challegram.tool.TGMimeType;
import org.thunderdog.challegram.util.OfferedUris;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

final class ExternalShareUtils {
  private ExternalShareUtils () { }

  static boolean isLocalFileUri (@Nullable Uri uri) {
    return uri != null && ("content".equalsIgnoreCase(uri.getScheme()) || "file".equalsIgnoreCase(uri.getScheme()));
  }

  // Both arguments must already be canonical paths; the separator prevents prefix collisions.
  static boolean isPathWithinDirectory (String path, String directory) {
    return path.equals(directory) || path.startsWith(directory.endsWith(File.separator) ? directory : directory + File.separator);
  }

  /**
   * What an outside app may not make this app read on its behalf: its own content providers (logs, secret
   * chat media, TDLib files, which only this app can open) and its private directories, including the
   * app-specific external ones that other apps cannot read since Android 11.
   */
  static final class SharePolicy {
    final String packageName;
    final Set<String> ownAuthorities;
    final List<String> privateDirectories;

    private SharePolicy (String packageName, Set<String> ownAuthorities, List<String> privateDirectories) {
      this.packageName = packageName;
      this.ownAuthorities = ownAuthorities;
      this.privateDirectories = privateDirectories;
    }

    static SharePolicy create (String packageName, Collection<String> providerAuthorities, Collection<String> dataDirectories,
                               Collection<File> appSpecificDirectories) throws IOException {
      Set<String> authorities = new HashSet<>();
      for (String value : providerAuthorities) {
        if (value == null) continue;
        for (String authority : value.split(";")) {
          if (!authority.isEmpty()) authorities.add(authority.toLowerCase(Locale.ROOT));
        }
      }
      LinkedHashSet<String> directories = new LinkedHashSet<>();
      for (String dataDirectory : dataDirectories) {
        directories.add(new File(dataDirectory).getCanonicalPath());
      }
      for (File directory : appSpecificDirectories) {
        File root = appSpecificRoot(directory, packageName);
        if (root != null) directories.add(root.getCanonicalPath());
      }
      return new SharePolicy(packageName.toLowerCase(Locale.ROOT), Collections.unmodifiableSet(authorities),
        Collections.unmodifiableList(new ArrayList<>(directories)));
    }

    static SharePolicy forContext (Context context) throws IOException {
      return forContext(context, Build.VERSION.SDK_INT >= Build.VERSION_CODES.N);
    }

    static SharePolicy forContext (Context context, boolean hasDeviceProtectedStorage) throws IOException {
      String packageName = context.getPackageName();
      List<String> authorities = new ArrayList<>();
      try {
        PackageInfo info = context.getPackageManager().getPackageInfo(packageName, PackageManager.GET_PROVIDERS);
        if (info.providers != null) {
          for (ProviderInfo provider : info.providers) authorities.add(provider.authority);
        }
      } catch (PackageManager.NameNotFoundException | RuntimeException e) {
        Log.w("Cannot list own providers; the package prefix still applies", e);
      }
      List<File> directories = new ArrayList<>();
      Collections.addAll(directories, context.getExternalFilesDirs(null));
      Collections.addAll(directories, context.getExternalCacheDirs());
      Collections.addAll(directories, context.getExternalMediaDirs());
      Collections.addAll(directories, context.getObbDirs());
      List<String> dataDirectories = new ArrayList<>();
      dataDirectories.add(context.getApplicationInfo().dataDir);
      // Android 7+ keeps a second private root, device-protected storage (/data/user_de/<user>/<package>).
      if (hasDeviceProtectedStorage) dataDirectories.add(deviceProtectedDataDir(context));
      return create(packageName, authorities, dataDirectories, directories);
    }

    static String deviceProtectedDataDir (Context context) throws IOException {
      try {
        return context.createDeviceProtectedStorageContext().getDataDir().getPath();
      } catch (RuntimeException e) {
        throw new IOException("Cannot locate device-protected storage", e); // Refuse rather than allow it.
      }
    }

    boolean isOwnAuthority (String authority) {
      // "<userId>@authority" reaches the same provider (ContentProvider.getAuthorityWithoutUserId).
      String name = authority.substring(authority.lastIndexOf('@') + 1).toLowerCase(Locale.ROOT);
      return ownAuthorities.contains(name) || name.equals(packageName) || name.startsWith(packageName + ".");
    }
  }

  /** {@code Android/data/<package>}, {@code Android/media/<package>} or {@code Android/obb/<package>}. */
  @Nullable
  static File appSpecificRoot (@Nullable File directory, String packageName) {
    for (File current = directory; current != null; current = current.getParentFile()) {
      if (packageName.equals(current.getName())) return current;
    }
    return null;
  }

  static String resolveSharedFilePath (Uri uri, SharePolicy policy) throws IOException {
    String path = validateSharedFilePath(uri, policy);
    if ("file".equals(uri.getScheme()) && !new File(path).isFile()) {
      throw new IOException("Shared path is not a file");
    }
    return path;
  }

  // Permission preflight must not require stat/read access to the external file.
  static String validateSharedFilePath (Uri uri, SharePolicy policy) throws IOException {
    if ("content".equals(uri.getScheme())) {
      String authority = uri.getAuthority();
      if (authority == null || authority.isEmpty()) {
        throw new IOException("Shared URI names no provider");
      }
      // Choosing this app in its own share sheet returns exactly the URI it just offered.
      if (policy.isOwnAuthority(authority) && !OfferedUris.wasOffered(uri)) {
        throw new IOException("Shared URI belongs to this app");
      }
      // Never trust a foreign provider's _data column.
      return uri.toString();
    }
    if (!"file".equals(uri.getScheme()) || uri.getPath() == null) {
      throw new IOException("Unsupported shared URI");
    }
    File file = new File(uri.getPath()).getCanonicalFile();
    for (String privatePath : policy.privateDirectories) {
      if (isPathWithinDirectory(file.getPath(), privatePath)) {
        throw new IOException("Shared path is private");
      }
    }
    return file.getPath();
  }

  private static void addUri (LinkedHashSet<Uri> uris, Object value) {
    if (value instanceof Uri && isLocalFileUri((Uri) value)) {
      uris.add(((Uri) value).normalizeScheme());
    }
  }

  private static void addRequiredUri (LinkedHashSet<Uri> uris, Object value) {
    if (!(value instanceof Uri) || !isLocalFileUri((Uri) value)) {
      throw new IllegalArgumentException("Shared stream is not a local file URI");
    }
    uris.add(((Uri) value).normalizeScheme());
  }

  static ArrayList<Uri> collectUris (Intent intent) {
    return collectUris(intent, intent.getAction());
  }

  @SuppressWarnings("deprecation")
  static ArrayList<Uri> collectUris (Intent intent, @Nullable String originalAction) {
    LinkedHashSet<Uri> uris = new LinkedHashSet<>();
    if (Intent.ACTION_VIEW.equals(originalAction)) {
      addUri(uris, intent.getData());
      return new ArrayList<>(uris);
    }
    try {
      Bundle extras = intent.getExtras();
      if (extras != null && extras.containsKey(Intent.EXTRA_STREAM)) {
        Object stream = extras.get(Intent.EXTRA_STREAM);
        if (stream instanceof Iterable<?>) {
          for (Object item : (Iterable<?>) stream) {
            addRequiredUri(uris, item);
          }
        } else {
          addRequiredUri(uris, stream);
        }
        // Other URI fields can exist only to carry grants or context for these streams.
        return new ArrayList<>(uris);
      }
    } catch (RuntimeException e) {
      throw new IllegalArgumentException("Cannot read shared stream extra", e);
    }
    try {
      ClipData clipData = intent.getClipData();
      if (clipData != null) {
        for (int i = 0; i < clipData.getItemCount(); i++) {
          Uri uri = clipData.getItemAt(i).getUri();
          if (uri != null) {
            addRequiredUri(uris, uri);
          }
        }
      }
    } catch (RuntimeException e) {
      throw new IllegalArgumentException("Cannot read shared ClipData", e);
    }
    if (uris.isEmpty()) {
      addUri(uris, intent.getData());
    }
    return new ArrayList<>(uris);
  }

  @Nullable
  private static String concreteMimeType (@Nullable String value) {
    return normalizeMimeType(value, false);
  }

  @Nullable
  private static String normalizeMimeType (@Nullable String value, boolean allowSubtypeWildcard) {
    if (value == null) {
      return null;
    }
    int parameters = value.indexOf(';');
    String type = (parameters >= 0 ? value.substring(0, parameters) : value).trim().toLowerCase(Locale.ROOT);
    int separator = type.indexOf('/');
    int wildcard = type.indexOf('*');
    boolean validWildcard = wildcard == -1 || (allowSubtypeWildcard && separator == type.length() - 2 && wildcard == type.length() - 1);
    return separator > 0 && separator < type.length() - 1 && separator == type.lastIndexOf('/') && validWildcard && type.indexOf(' ') == -1 ? type : null;
  }

  static String chooseMimeType (@Nullable String declaredType, @Nullable String providerType, @Nullable String nameType, @Nullable String pathType) {
    String sourceType = normalizeMimeType(declaredType, true);
    if (sourceType != null && !sourceType.endsWith("/*")) {
      return sourceType;
    }
    // A sender's image/* (etc.) is a media category, not an unknown */* type.
    String sourcePrefix = sourceType != null ? sourceType.substring(0, sourceType.length() - 1) : null;
    for (String candidate : new String[] {providerType, nameType, pathType}) {
      String type = concreteMimeType(candidate);
      if (type != null && (sourcePrefix == null || (!type.equals("application/octet-stream") && type.startsWith(sourcePrefix)))) {
        return type;
      }
    }
    return sourceType != null ? sourceType : "application/octet-stream";
  }

  // Opening a media file should honor its resolved type, just like sharing it.
  // Other opened files stay documents, preserving names and avoiding vCard conversion.
  static boolean shouldSendAsDocument (String originalAction, @Nullable String resolvedMimeType) {
    String type = normalizeMimeType(resolvedMimeType, true);
    return Intent.ACTION_VIEW.equals(originalAction) &&
      (type == null || !(type.startsWith("image/") || type.startsWith("video/") || type.startsWith("audio/")));
  }

  @Nullable
  static String getDisplayName (ContentResolver resolver, Uri uri) {
    if ("content".equalsIgnoreCase(uri.getScheme())) {
      try (Cursor cursor = resolver.query(uri, new String[] {OpenableColumns.DISPLAY_NAME}, null, null, null)) {
        if (cursor != null && cursor.moveToFirst()) {
          int column = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
          if (column >= 0) {
            String name = cursor.getString(column);
            if (name != null && !name.isEmpty()) {
              return name;
            }
          }
        }
      } catch (RuntimeException e) {
        Log.w("Cannot read shared file name", e);
      }
    }
    return null;
  }

  private static String mimeTypeForName (@Nullable String name) {
    String extension = name != null ? U.getExtension(name) : null;
    return extension != null ? TGMimeType.mimeTypeForExtension(extension.toLowerCase(Locale.ROOT)) : null;
  }

  static String resolveMimeType (ContentResolver resolver, Uri uri, @Nullable String declaredType) {
    String sourceType = normalizeMimeType(declaredType, true);
    if (sourceType != null && !sourceType.endsWith("/*")) {
      return sourceType;
    }
    String providerType = null;
    if ("content".equalsIgnoreCase(uri.getScheme())) {
      try {
        providerType = resolver.getType(uri);
      } catch (RuntimeException e) {
        Log.w("Cannot read shared MIME type", e);
      }
    }
    String providerConcreteType = concreteMimeType(providerType);
    if (providerConcreteType != null && (sourceType == null || (!providerConcreteType.equals("application/octet-stream") && providerConcreteType.startsWith(sourceType.substring(0, sourceType.length() - 1))))) {
      return providerConcreteType;
    }
    return chooseMimeType(sourceType, providerType, mimeTypeForName(getDisplayName(resolver, uri)), mimeTypeForName(uri.getLastPathSegment()));
  }
}
