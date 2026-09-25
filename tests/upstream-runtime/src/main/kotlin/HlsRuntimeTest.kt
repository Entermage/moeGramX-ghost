import android.net.Uri
import android.os.Build
import androidx.media3.decoder.vp9.VpxLibrary
import org.drinkless.tdlib.TdApi
import tgx.td.data.HlsPath
import tgx.td.data.HlsVideo

private var checks = 0
private fun expect(value: Boolean, name: String) { check(value) { name }; checks++ }
fun main() {
  val codecs = mapOf("h264" to "avc1", "h265" to "hvc1", "av1" to "av01", "vp8" to "vp08", "vp9" to "vp09")
  codecs.forEach { (input, output) ->
    expect(HlsVideo.toRfc6381CodecString(input) == output, "codec $input")
    expect(HlsVideo.toSampleMimeType(input) != null, "MIME argument $input")
  }
  for (codec in listOf("avc1.640028", "hvc1.1.6.L93.B0", "vp09.00.10.08", "av01.0.08M.08", "unknown", "")) {
    expect(HlsVideo.toRfc6381CodecString(codec) == codec, "preserve $codec")
  }
  expect(HlsVideo.toRfc6381CodecString(null) == null, "null codec")
  expect(HlsVideo.toSampleMimeType(null) == null, "null MIME")
  expect(HlsVideo.toSampleMimeType("avc1.640028") == "video/avc", "profile MIME")
  val minimums = mapOf("h264" to 11, "avc1.640028" to 11, "avc3" to 11,
    "h265" to 21, "hevc" to 21, "hvc1.1.6.L93.B0" to 21, "hev1" to 21,
    "vp8" to 14, "vp08" to 14, "vp9" to 19, "vp09.00.10.08" to 19,
    "av1" to 29, "av01.0.08M.08" to 29)
  minimums.forEach { (codec, minimum) ->
    Build.VERSION.SDK_INT = minimum - 1
    expect(!HlsVideo.isCodecSupported(codec, true), "unsupported $codec")
    Build.VERSION.SDK_INT = minimum
    expect(HlsVideo.isCodecSupported(codec, true), "supported $codec")
  }
  Build.VERSION.SDK_INT = 18
  VpxLibrary.available = true
  expect(HlsVideo.isCodecSupported("vp09.00.10.08", true), "native VP9 fallback")
  VpxLibrary.available = false
  expect(HlsVideo.isCodecSupported("future-codec", false), "permissive unknown")
  expect(runCatching { HlsVideo.isCodecSupported("future-codec", true) }.isFailure, "strict unknown")
  val videos = codecs.keys.mapIndexed { i, codec ->
    TdApi.AlternativeVideo(i.toLong() + 1, 640, 360, codec, TdApi.File(i + 100), TdApi.File(i + 200))
  }.toTypedArray()
  Build.VERSION.SDK_INT = 35
  val hls = HlsVideo(TdApi.Video(TdApi.File(10)), videos)
  val playlist = hls.multivariantPlaylistData(true)
  codecs.values.forEach { expect(playlist.contains("CODECS=\"$it\""), "playlist $it") }
  expect(playlist.startsWith("#EXTM3U\n") && playlist.endsWith("#EXT-X-ENDLIST\n"), "playlist boundaries")
  expect(playlist.split("#EXT-X-STREAM-INF:").size - 1 == 5, "all variants")
  expect(hls.findVideoFileIdByStreamId(2) == 201, "stream lookup")
  expect(HlsPath.fromUri(Uri.parse(HlsPath(videos[0]).toString())) == HlsPath(videos[0]), "path round trip")
  Build.VERSION.SDK_INT = 28
  expect(!hls.multivariantPlaylistData(true).contains("CODECS=\"av01\""), "exclude unsupported AV1")
  val onlyAv1 = HlsVideo(TdApi.Video(TdApi.File(10)), arrayOf(videos[2]))
  expect(!onlyAv1.hasSupportedCodecs(), "no supported variants")
  expect(runCatching { onlyAv1.multivariantPlaylistData(true) }.isFailure, "reject unsupported variants")
  expect(HlsVideo(TdApi.Video(TdApi.File(1), 0), arrayOf(videos[0])).multivariantPlaylistData(true).contains("BANDWIDTH=1000000"), "zero duration")
  println("HLS production checks passed: $checks (JVM doubles, not media decoding)")
}
