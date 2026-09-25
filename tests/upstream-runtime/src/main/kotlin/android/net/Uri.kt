package android.net
// Android Uri accepts the app's existing tg_hls scheme; java.net.URI does not.
class Uri private constructor(private val value: String) {
  val schemeSpecificPart: String get() = value.substringAfter(':')
  companion object { @JvmStatic fun parse(value: String) = Uri(value) }
}
