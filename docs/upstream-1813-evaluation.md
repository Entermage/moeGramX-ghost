# TGX 1813 合入与升级评估

日期：2026-09-25。日常分支只合入 A、B；依赖升级在隔离工作树试验，最后两项只评估，不整包并入。

## 已交付：A、B

- A：[HLS codec 选择修复](https://github.com/TGX-Android/Telegram-X/commit/d1c2fb18bb6538453b683ee444873c04ebd67f76)。规范化 h264/h265/av1/vp8/vp9 codec，补充 sample MIME，保留已有 profile 标识。
- B：[登录页崩溃保护](https://github.com/TGX-Android/Telegram-X/commit/34f9cbdb8278d3fee048826de3216452fd82c3fb)。保护未初始化/空号码输入，限制失去焦点后的测试登录请求；不是 FCM 修复。
- 日常应用源码提交：`5c5581901223f9dcb673a0c27646b86e0ebef059`，保持原包名和正式证书，只生成 ARM64。
- [CI 运行](https://github.com/Entermage/moeGramX-ghost/actions/runs/36094146529)；[APK 下载，需登录 GitHub](https://github.com/Entermage/moeGramX-ghost/actions/runs/36094146529/artifacts/10847815923)。CI 产物保留 30 天。

本地验证：正式构建成功；17 项 Python 回归通过，HLS 生产 Kotlin 的 61 项 JVM 检查通过，外部分享 121 项检查通过，分页策略 54 项及可见未读策略 314 项检查通过。已登录的 WSL 模拟器上，聊天列表、`meiwool/371445` 目标消息定位、添加账号页面和公开视频播放正常；未发送验证码或退出原账号。测试替身和普通视频播放不能替代所有 HLS 多码率/硬件解码组合的真机验证。

CI 所有步骤成功，下载包 SHA-256 为 `01b8f9d7a69d61584a2efc48838dbde63180cbb0095d46c2b1a8053294822a51`。本机拉取 GitHub artifact 时连接超时，未完成此 CI 文件的再次安装；上述模拟器检查使用本地构建、相同应用修改的 APK，CI 文件的签名、包名、ABI 和非 debuggable 属性由 runner 验证。

## TDLib、通话库和构建链：试验通过，尚未日常合入

隔离分支 `codex/upgrade-1813` 采用 moeGramX `79e4d5d2` / TGX `9312ace3` 作为完整兼容性试编基线。本地试验提交 `732ab36040ed971988376181f058ae98870d7655`，未推送，也未用于 Release。完整上游基线还包含通知、Baseline Profile、联系人与备份改动；不应把这个试验分支直接整体合回 `moe`。

| 部分 | 试验版本/结果 |
| --- | --- |
| TDLib | wrapper `a032dcf1`，源码 `d1085f9c`；保留 Ghost 原生补丁重建成功 |
| 通话 | tgcalls `236c2d53`、WebRTC `6ecff4f`；随完整 ARM64 APK 编译、链接成功 |
| 构建 | JDK 21、Gradle 9.7.1、NDK 27.3.13750724、SDK android-37.2 |
| 媒体 | libvpx、FFmpeg、Opus 和 AndroidX Media 改由新 Gradle 任务准备 |
| 原生兼容 | 使用 `c++_shared`；TDLib 为 AArch64，LOAD 对齐 16KB，APK zipalign 检查通过 |
| 签名 | 沿用现有 release 证书，v2/v3，不换 debug 证书 |

旧 TDLib 补丁只有行号、没有上下文，在新源码上“应用成功”后会把部分插入点放错函数。已按函数上下文重新移植 7 个文件，并将试验补丁改为 3 行上下文格式；干净 Git 索引应用结果与实际源码差异完全一致。编译产物包含全部 Ghost/本地已读选项，APK 内 `libtdjni.so` 的 SHA-256 与此次重建库完全相同，不使用上游未打补丁的预编译 TDLib。

试验 APK 完整构建成功；14 项现有 Python 回归和外部分享 121 项检查通过。为避免数据库升级影响旧环境，先停机复制独立 AVD，仅在副本安装。旧账号正常加载，论坛群目标消息定位、视频进度推进及三次冷启动通过，检查期间 crash buffer 未见记录。测试结束恢复原 AVD，不连接实体手机。

仍未验证：与真实对端的语音/视频通话、Ghost 云端回执的双账号核验、真实厂商 FCM 唤醒、HLS 多编码流和 16KB 页设备运行。CI 适配完成了路径、补丁完整性、语法与防误运行检查，但升级版本尚未在 GitHub runner 完整构建。不能把上述试验表述为全面端到端验证或可直接发布的升级版。

## 最后两项

### Baseline Profile 启动优化

[上游实现](https://github.com/TGX-Android/Telegram-X/commit/bf13158db941f29554125a70eb3599591c7f68a8) 提供预生成 profile 和冷启动基准，具备优化价值，但应针对本分支重新录制和测量。普通构建可能打包预生成 profile，不能仅以未启用生成开关认定其没有生效。

其 `SnapshotApplier` / `StartupBenchmarks` 会执行 `pm clear`，清除测试包数据；本次没有在用户已登录环境运行这些基准，也不从模拟器单次启动耗时宣称性能提升。建议后续使用专用可清空 AVD/账号，分别测量有/无 profile 的多轮冷启动后决定是否采用。

### 通知兼容性

[上游厂商兼容保护](https://github.com/TGX-Android/Telegram-X/commit/3ed752402a15c52e8a4bdc046488b3497486b43e) 在 ID 之外增加账号和类别 tag，降低私聊、群组、频道通知互相覆盖/取消的风险。当前日常代码已有账号 ID 分区，不能把全部隔离逻辑都说成这次才新增。

值得单独移植，但需要检查从旧无 tag 通知到新 tag 的清理、多账号摘要取消，以及来电、音乐、位置等前台服务共存。普通 `cancel(tag, id)` 不会匹配旧的无 tag 通知，不能只机械替换调用。该改动不等于 FCM 送达保证，也不解决 Android force-stop 的停止状态。本次只做源码评估，没有将其单独合入日常分支。
