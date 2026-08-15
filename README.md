<div align="center">
<a href="https://moegramx.t.me/">
        <picture>
          <source media="(prefers-color-scheme: dark)" srcset="https://files.kiri.su/moeGramX_dark.svg">
          <img src="https://files.kiri.su/moeGramX.svg">
        </picture>
    </a>

the **moest** client based on [Telegram-X](https://github.com/TGX-Android/Telegram-X) and [TDLib](https://core.telegram.org/tdlib) ~

[![Issues](https://img.shields.io/github/issues/moeCrafters/moeGramX?style=flat-square&color=red)](https://github.com/moeCrafters/moeGramX/issues)
[![Forks](https://img.shields.io/github/forks/moeCrafters/moeGramX?style=flat-square&color=blue)](https://github.com/moeCrafters/moeGramX/network/members)
[![Stars](https://img.shields.io/github/stars/moeCrafters/moeGramX?style=flat-square&color=yellow)](https://github.com/moeCrafters/moeGramX/stargazers)

[![Channel](https://img.shields.io/badge/Channel-%40moeGramX-blue?style=flat-square&logo=telegram&label=Channel)](https://t.me/moegramx)
[![Chat](https://img.shields.io/badge/Chat-%40moex__log-blue?style=flat-square&logo=telegram&label=Updates)](https://t.me/moe_chat)
[![Updates](https://img.shields.io/badge/Release-%40moe__chat-blue?style=flat-square&logo=telegram&label=Discussion)](https://t.me/moe_log)
</div>

## This fork

Adds configurable Ghost Mode, **Read until**, message filters, and local shadow bans to moeGramX. Feature behavior is inspired by [AyuGram](https://github.com/AyuGram/AyuGram4A); the Telegram X/TDLib implementation is independent.

## Features

- Message details
- Ability to replace mobile number<sup>(with username/userid/hidden label)</sub></sup>
- Hide reactions
- Hide new messages counter<sup><sup>(in the drawer burger)</sup></sup>
- Sent photos with high resolution <sup>(800px/1280px/2560px)</sup>
- Blur drawer background
- Square avatars
- Message panel buttons hiding
- Remember message options <sup>(copy/silent/sound)
- Do not send **choosing** sticker status<sup>typing status will be sent instead</sup>
- Copy photo or document<sup><sup>(with photo)</sup></sup> option
- and a bit more...
---
## Build (WSL/Linux, arm64)

Requires Git, Git LFS, OpenJDK 21, at least 4 GB RAM, and about 6 GB of free space. Windows users should build inside WSL.

```bash
git lfs install
git clone --recursive --depth=1 --shallow-submodules https://github.com/Entermage/moeGramX-ghost.git
cd moeGramX-ghost
ABIS=arm64-v8a scripts/setup.sh
./gradlew assembleLatestArm64Release
```

`setup.sh` is interactive. It asks for Telegram API credentials, the package/application information, and a path to a signing settings file stored outside the repository:

```properties
keystore.file=/absolute/path/to/app.jks
keystore.password=...
key.alias=...
key.password=...
```

For FCM push notifications, use an `app/google-services.json` matching your package ID. Never commit signing files, passwords, Telegram credentials, or private Firebase configuration.

The APK is written to:

```text
app/build/outputs/apk/latestArm64/release/
```

The `assembleLatestArm64Release` command has been verified in WSL. A completely fresh interactive setup has not been re-tested.

---

## Contributing

This is a thing you can do without any special skills!

Here are a few things you can do:

- [Test and report issues](https://github.com/moeCrafters/moeGramX/issues/new/choose)
- [Translate the moegram strings into your language](https://crowdin.com/project/moex) -
  **moeGramX** is a fork of **Telegram-X** and most of the localizations follow the translations of **Telegram-X**, check it out [here](https://translations.telegram.org/en/android_x/). As for specialized strings for **moeGramX**, we use **Crowdin** to translate client.
---

## Third-party dependencies

List of third-party components used in **moeGramX** can be found [here](/docs/THIRDPARTY.md). Additionally, you can check the specific commit of the third-party component used, for example, [here](/app/jni/thirdparty) and [here](/thirdparty).

---

## License

`moeGramX` is licensed under the terms of the GNU General Public License v3.0.

License of components and third-party dependencies it relies on might differ, check `LICENSE` file in the corresponding folder.

[![License: GPLv3](https://img.shields.io/badge/License-GPL%20v3-red.svg?style=for-the-badge&color=E87777)](https://github.com/moeCrafters/moeGramX/blob/main/LICENSE)
