# TGX 1813 合入与升级评估

日期：2026-09-25。日常分支只合入 A、B；依赖升级在隔离工作树试验，最后两项只评估，不整包并入。

## 已交付：A、B

- A：[HLS codec 选择修复](https://github.com/TGX-Android/Telegram-X/commit/d1c2fb18bb6538453b683ee444873c04ebd67f76)。规范化 h264/h265/av1/vp8/vp9 codec，补充 sample MIME，保留已有 profile 标识。
- B：[登录页崩溃保护](https://github.com/TGX-Android/Telegram-X/commit/34f9cbdb8278d3fee048826de3216452fd82c3fb)。保护未初始化/空号码输入，限制失去焦点后的测试登录请求；不是 FCM 修复。
- 复查修复：[日常源码 `43a6ada0`](https://github.com/Entermage/moeGramX-ghost/commit/43a6ada01b25344f42d7d21bc03034a7d6ea529b)，保持原包名、正式证书和 ARM64。修复手动已读全局放行竞态、连接替换后的跨 Client 请求、HLS 别名/MIME 不一致及码率为零/溢出。
- [本轮 CI 与下载入口](https://github.com/Entermage/moeGramX-ghost/actions/runs/36098528026)：回归、完整 ARM64 编译、签名检查及上传均已通过。APK 产物需登录 GitHub 下载，保留 30 天。

本轮本地验证：重建 Ghost TDLib 和正式 APK；21 项 Python 回归重复通过，真实 Media3 MIME/Android Uri 下的 HLS 检查 85 项、外部分享 121 项、分页策略 54 项、可见未读策略 314 项通过。新增测试先复现失败再验证修复，覆盖错误会话/消息、单次令牌、旧连接回调、请求失败清理、编码别名和码率边界。

在已登录 WSL 模拟器中确认：聊天列表、`meiwool/371445` 精确定位、论坛群跳到底部、消息主菜单和 More 分工、Read until 点击返回、公开视频进度推进至 3 秒，以及三次冷启动；crash buffer 为空。Ghost 三类开关保持开启，未发送聊天消息或表情、未退出账号、未接触实体手机。为通过系统弹窗暂时拒绝的模拟器通知权限已恢复到原先未授权/未选择状态。

本地稳定 APK SHA-256：`20925aff0f9779d93bf8b26834a1f1fe2f7cdf4308dc1f60e7851201bee21c35`。随后已下载并实际安装 GitHub runner 产物，CI APK 和模拟器已安装 `base.apk` 的 SHA-256 均为 `68b58bf41d896052fc5774b6010b0cd45f84662345e4513c8a56c66739568e2c`；确认正式证书、v2/v3、非 debuggable、仅 ARM64，以及原生库包含新会话/消息令牌而不含旧全局放行标记。

CI 下载包单独复测了论坛消息精确定位、Read until 点击返回、主菜单/More 分工和表情栏、从首条新消息继续跳到最新消息、公开视频播放至 3 秒及三次冷启动，最终聊天列表正常加载，crash buffer 为空。未修改屏蔽列表、未发送消息或表情，也未接触实体手机。点击返回不等于云端回执已由第二账号确认；普通视频播放也不等于覆盖真实 HLS 多编码/硬件解码组合。

## TDLib、通话库和构建链：试验通过，尚未日常合入

隔离分支 `codex/upgrade-1813` 采用 moeGramX `79e4d5d2` / TGX `9312ace3` 作为完整兼容性试编基线。复查后的本地试验提交 `8b5f01c75a2beb02426cb186d47cff83e39a2fea`，未推送，也未用于 Release。完整上游基线还包含通知、Baseline Profile、联系人与备份改动；不应把这个试验分支直接整体合回 `moe`。

| 部分 | 试验版本/结果 |
| --- | --- |
| TDLib | wrapper `a032dcf1`，源码 `d1085f9c`；保留 Ghost 原生补丁重建成功 |
| 通话 | tgcalls `236c2d53`、WebRTC `6ecff4f`；随完整 ARM64 APK 编译、链接成功 |
| 构建 | JDK 21、Gradle 9.7.1、NDK 27.3.13750724、SDK android-37.2 |
| 媒体 | libvpx、FFmpeg、Opus 和 AndroidX Media 改由新 Gradle 任务准备 |
| 原生兼容 | 使用 `c++_shared`；TDLib 为 AArch64，LOAD 对齐 16KB，APK zipalign 检查通过 |
| 签名 | 沿用现有 release 证书，v2/v3，不换 debug 证书 |

旧 TDLib 补丁只有行号、没有上下文，在新源码上“应用成功”后会把部分插入点放错函数。当前补丁涉及 8 个文件，稳定和试验两边均保留 3 行上下文；在各自固定源码上应用、反向检查及完整 diff 比较通过。两边 APK 内的 `libtdjni.so` 均与各自此次重建库逐字节一致，不使用上游未打补丁的预编译 TDLib。

复查还发现 Application 插件的 primary/legacy NDK 条件反置：默认初始值错误地选择 NDK 23，之后又被 app 脚本覆盖为 NDK 27，因此此前完整编译成功并不能证明初始配置正确。已修复；新增 Gradle 配置审计验证默认 NDK 27、legacy NDK 23，以及 libvpx/FFmpeg 任务的 NDK 一致性，不编译 ARMv7。

试验 APK 再次完整构建成功；18 项 Python 回归重复通过、真实 Media3 的 HLS 检查 85 项及外部分享 121 项通过。在独立 AVD 副本覆盖安装后，旧账号正常加载，论坛群目标消息定位、Read until 点击返回、跳到底部、公开视频进度推进至 4 秒及三次冷启动通过，crash buffer 为空。测试后恢复原 AVD，不连接实体手机。试验 APK SHA-256：`d3510adb1cbdb82dc55ac00d3dd318ab7743e7139b97e1073e3e9a7820dd7137`。

仍未验证：与真实对端的语音/视频通话、Ghost 云端回执的双账号核验、真实厂商 FCM 唤醒、HLS 多编码流和 16KB 页设备运行。CI 适配完成了路径、补丁完整性、语法与防误运行检查，但升级版本尚未在 GitHub runner 完整构建。不能把上述试验表述为全面端到端验证或可直接发布的升级版。

## 最后两项

### Baseline Profile 启动优化

[上游实现](https://github.com/TGX-Android/Telegram-X/commit/bf13158db941f29554125a70eb3599591c7f68a8) 提供预生成 profile 和冷启动基准，具备优化价值，但应针对本分支重新录制和测量。普通构建可能打包预生成 profile，不能仅以未启用生成开关认定其没有生效。

其 `SnapshotApplier` / `StartupBenchmarks` 会执行 `pm clear`，清除测试包数据；本次没有在用户已登录环境运行这些基准，也不从模拟器单次启动耗时宣称性能提升。建议后续使用专用可清空 AVD/账号，分别测量有/无 profile 的多轮冷启动后决定是否采用。

### 通知兼容性

[上游厂商兼容保护](https://github.com/TGX-Android/Telegram-X/commit/3ed752402a15c52e8a4bdc046488b3497486b43e) 在 ID 之外增加账号和类别 tag，降低私聊、群组、频道通知互相覆盖/取消的风险。当前日常代码已有账号 ID 分区，不能把全部隔离逻辑都说成这次才新增。

值得单独移植，但需要检查从旧无 tag 通知到新 tag 的清理、多账号摘要取消，以及来电、音乐、位置等前台服务共存。普通 `cancel(tag, id)` 不会匹配旧的无 tag 通知，不能只机械替换调用。该改动不等于 FCM 送达保证，也不解决 Android force-stop 的停止状态。本次只做源码评估，没有将其单独合入日常分支。
