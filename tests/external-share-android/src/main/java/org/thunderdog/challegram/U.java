package org.thunderdog.challegram;

public final class U {
  private U () { }

  public static String getExtension (String path) {
    int slash = Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\'));
    String fileName = slash >= 0 ? path.substring(slash + 1) : path;
    int dot = fileName.lastIndexOf('.');
    if (dot < 0) {
      return null;
    }
    String extension = fileName.substring(dot + 1);
    if (extension.equalsIgnoreCase("crdownload")) {
      return getExtension(fileName.substring(0, dot));
    }
    return extension;
  }
}
