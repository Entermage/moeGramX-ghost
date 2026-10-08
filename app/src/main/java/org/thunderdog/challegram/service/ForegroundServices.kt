package org.thunderdog.challegram.service

import android.content.Context
import androidx.annotation.DrawableRes
import me.vkryl.core.lambda.RunnableBool
import org.thunderdog.challegram.sync.SyncTask

inline fun <reified T : BaseForegroundService> start(
  context: Context,
  task: CharSequence,
  text: CharSequence?,
  channelId: String,
  @DrawableRes iconRes: Int,
  pushId: Long,
  accountId: Int,
  after: RunnableBool
) = BaseForegroundService.startTask(
  T::class.java, context, task, text, channelId, iconRes, pushId, accountId, after
)

inline fun <reified T : BaseForegroundService> stop(
  context: Context,
  pushId: Long,
  accountId: Int
) = BaseForegroundService.stopTask(
T::class.java, context, pushId, accountId
)

class FetchNotificationService : BaseForegroundService() {
  override fun getTaskTimeoutMillis() = 60_000L

  override fun onTaskTimeout(pushId: Long, accountId: Int) {
    SyncTask.schedule(pushId, accountId)
  }

  companion object {
    @JvmStatic fun startForegroundTask(
      context: Context,
      task: CharSequence,
      text: CharSequence?,
      channelId: String,
      @DrawableRes iconRes: Int,
      pushId: Long,
      accountId: Int,
      after: RunnableBool
    ) =
      start<FetchNotificationService>(
        context,
        task,
        text,
        channelId,
        iconRes,
        pushId,
        accountId,
        after
      )

    @JvmStatic fun stopForegroundTask(
      context: Context,
      pushId: Long,
      accountId: Int,
    ) =
      stop<FetchNotificationService>(
        context,
        pushId,
        accountId
      )
  }
}

class SyncContactsService : BaseForegroundService() {
  companion object {
    @JvmStatic fun startForegroundTask(
      context: Context,
      task: CharSequence,
      text: CharSequence?,
      channelId: String,
      @DrawableRes iconRes: Int,
      pushId: Long,
      accountId: Int,
      after: RunnableBool
    ) =
      start<SyncContactsService>(
        context,
        task,
        text,
        channelId,
        iconRes,
        pushId,
        accountId,
        after
      )

    @JvmStatic fun stopForegroundTask(
      context: Context,
      pushId: Long,
      accountId: Int,
    ) =
      stop<SyncContactsService>(
        context,
        pushId,
        accountId
      )
  }
}
