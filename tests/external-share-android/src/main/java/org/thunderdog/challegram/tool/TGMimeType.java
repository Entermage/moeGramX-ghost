package org.thunderdog.challegram.tool;

public final class TGMimeType {
  private TGMimeType () { }

  public static String mimeTypeForExtension (String extension) {
    return switch (extension) {
      case "gif" -> "image/gif";
      case "jpg", "jpeg" -> "image/jpeg";
      case "pdf" -> "application/pdf";
      case "png" -> "image/png";
      case "txt" -> "text/plain";
      case "webp" -> "image/webp";
      case "zip" -> "application/zip";
      default -> null;
    };
  }
}
