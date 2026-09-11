# 外部分享与“打开方式”Android 框架测试

该夹具直接读取应用的 `app/src/main/AndroidManifest.xml`，把 `MainActivity` 的实际
`intent-filter` 重建为 Android 框架的 `android.content.IntentFilter`，再调用框架的
`IntentFilter.match(...)`。它同时直接编译项目中的 `ExternalShareUtils.java`，测试 URI
收集、MIME 选择和私有路径边界，没有复制生产实现。

这是一个 Android 框架/纯逻辑集成夹具，不是应用端到端测试。为了隔离该单个生产 helper，
测试源码提供了最小的 `Log`、`U.getExtension`、`TGMimeType` 和 `@Nullable` 桩。普通 JVM
中的 `android-all` 无法实例化 `ContentResolver`（其初始化依赖 Android 原生
`SystemProperties`），因此 provider 返回值通过生产 `chooseMimeType` 入口覆盖，生产
`resolveMimeType` 入口使用无需 resolver 的 `file:` URI 覆盖。真实第三方 provider IPC、
文件名查询，以及 `MainActivity`、`MainController`、文件授权对话框和 TDLib 发送流程均不在
该夹具的验证范围内。

运行：

```bash
./gradlew -p tests/external-share-android runChecks
```

首次运行会从 Maven Central 下载
`org.robolectric:android-all:16-robolectric-13921718`（约 188 MiB）。这是 Android 16
框架实现；测试启动时会校验并打印 `IntentFilter` 的实际代码来源，避免误用 Android SDK
中只会抛出 `RuntimeException("Stub!")` 的编译桩。该测试不需要 AVD、ADB 或设备，也不把
依赖加入主应用。

覆盖范围：

- 无 MIME 的 `SEND` / `SEND_MULTIPLE`，以及 `content:` / `file:` 数据 URI；
- 区分真正缺失的 MIME（`null`）和异常的空字符串 MIME（`""`）；Android 框架让前者
  命中无类型过滤器，而把空字符串视为可由 `*/*` 命中的已声明类型；
- 有 MIME 和无 MIME 的本地 `VIEW`，并验证新增过滤器不会接管普通 HTTP 或 `tg:` URL；
- `EXTRA_STREAM`、`ClipData`、`Intent.data` 的优先级、拒绝和去重规则；
- 声明、provider、文件名和路径 MIME 候选的选择：具体声明优先；`image/*`、`video/*`、
  `audio/*` 等类别声明只允许同类别证据细化，冲突或通用 provider 类型不能将其降为文档；
  `*/*` 和空声明继续推断，并在没有可靠证据时回退为 `application/octet-stream`；
- `file:` canonical path、应用私有目录、前缀碰撞、`..` 和符号链接边界。
