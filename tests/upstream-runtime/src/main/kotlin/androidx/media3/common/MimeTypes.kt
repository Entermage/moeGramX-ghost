package androidx.media3.common
// Validate the argument supplied to Media3, not Media3's own implementation.
object MimeTypes {
  @JvmStatic fun getMediaMimeType(codec: String?): String? = when (codec?.substringBefore('.')) {
    "avc1", "avc3" -> "video/avc"
    "hvc1", "hev1" -> "video/hevc"
    "av01" -> "video/av01"
    "vp08" -> "video/x-vnd.on2.vp8"
    "vp09" -> "video/x-vnd.on2.vp9"
    else -> null
  }
}
