package org.drinkless.tdlib
object TdApi {
  data class File(val id: Int, val size: Long = 2000)
  data class Video(val video: File, val duration: Int = 10)
  data class AlternativeVideo(val id: Long, val width: Int, val height: Int, val codec: String, val hlsFile: File, val video: File)
}
