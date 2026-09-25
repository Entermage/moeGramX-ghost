#!/usr/bin/env bash
# Prepare patched TDLib for latest/arm64-v8a in an ephemeral GitHub Actions checkout.
# The upgraded Gradle tasks build and patch VPX, FFmpeg, Opus and AndroidX Media.
# Never run the full setup/reset scripts, or reuse an unpatched TDLib binary.
set -eo pipefail

die() { printf 'native CI: %s\n' "$*" >&2; exit 1; }

[[ "${GITHUB_ACTIONS:-}" == true ]] || die 'Refusing to modify a non-GitHub-Actions checkout.'
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
[[ -n "${GITHUB_WORKSPACE:-}" && -d "$GITHUB_WORKSPACE" ]] || die 'GITHUB_WORKSPACE is required.'
[[ "$(cd -- "$GITHUB_WORKSPACE" && pwd -P)" == "$repo_root" ]] || die 'Workspace does not match this repository.'
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || die 'Use an x86_64 Linux runner to cross-compile ARM64.'
cd -- "$repo_root"
[[ -d "${ANDROID_SDK_ROOT:-}" ]] || die 'ANDROID_SDK_ROOT must name an installed SDK.'
[[ "${CI_BUILD_JOBS:-2}" =~ ^[1-9][0-9]*$ ]] || die 'CI_BUILD_JOBS must be a positive integer.'
export TERM=xterm
# set-env.sh reads unset legacy variables; enable nounset only after it finishes.
source scripts/set-env.sh
set -u
export FLAVORS=latest ABIS=arm64-v8a CPU_COUNT="${CI_BUILD_JOBS:-2}"

for tool in git cmake ninja make perl gperf sha256sum readelf; do
  command -v "$tool" > /dev/null || die "Missing required tool: $tool"
done
ndk="$ANDROID_SDK_ROOT/ndk/$ANDROID_NDK_VERSION_PRIMARY"
[[ -f "$ndk/build/cmake/android.toolchain.cmake" ]] || die 'The pinned Android NDK is not installed.'
[[ -x "$ANDROID_SDK_ROOT/cmake/$CMAKE_VERSION/bin/cmake" ]] || die 'The pinned Android CMake is not installed.'
submodule_state=$(git submodule status --recursive)
if printf '%s\n' "$submodule_state" | grep -Eq '^[+U-]'; then
  die 'Initialize all recursive submodules at their recorded commits before preparing native libraries.'
fi

td_source="$repo_root/tdlib/source/td"
td_patch="$repo_root/patches/tdlib-ghost-mode.patch"
[[ -f "$td_source/example/android/CMakeLists.txt" && -s "$td_patch" ]] || die 'TDLib source or Ghost patch is missing.'
git -C "$td_source" diff --cached --quiet || die 'TDLib has unexpected staged changes.'
if git -C "$td_source" diff --quiet; then
  git -C "$td_source" apply --check "$td_patch" || die 'Ghost patch does not apply to this TDLib revision.'
  git -C "$td_source" apply "$td_patch"
fi
# Reverse applicability alone is insufficient: reject any additional tracked edits.
cmp -s "$td_patch" <(git -C "$td_source" diff --no-color --no-ext-diff --no-textconv --src-prefix=a/ --dst-prefix=b/ --unified=3) ||
  die 'TDLib changes must exactly match patches/tdlib-ghost-mode.patch.'
git -C "$td_source" apply --reverse --check "$td_patch" || die 'Ghost patch verification failed.'

verify_openssl() {
  local path="$1" pointer expected_hash expected_size actual_hash
  pointer=$(git -C tdlib show "HEAD:$path")
  expected_hash=$(printf '%s\n' "$pointer" | sed -n 's/^oid sha256://p')
  expected_size=$(printf '%s\n' "$pointer" | sed -n 's/^size //p')
  [[ "$expected_hash" =~ ^[0-9a-f]{64}$ && "$expected_size" =~ ^[0-9]+$ ]] || die "Expected a tracked LFS pointer for $path."
  [[ -f "tdlib/$path" && "$(stat -c %s "tdlib/$path")" == "$expected_size" ]] || die "Fetch TDLib LFS objects before building: $path"
  actual_hash=$(sha256sum "tdlib/$path")
  [[ "${actual_hash%% *}" == "$expected_hash" ]] || die "OpenSSL LFS checksum mismatch: $path"
}
openssl_root="$repo_root/tdlib/openssl/$ANDROID_NDK_VERSION_PRIMARY/arm64-v8a"
verify_openssl "openssl/$ANDROID_NDK_VERSION_PRIMARY/arm64-v8a/lib/libcryptox.so"
verify_openssl "openssl/$ANDROID_NDK_VERSION_PRIMARY/arm64-v8a/lib/libsslx.so"
[[ -f "$openssl_root/lib/libcrypto.so" && -f "$openssl_root/lib/libssl.so" ]] || die 'OpenSSL linker symlinks are missing.'

# Cache only final libraries/headers. Toolchain, scripts and every submodule commit
# are part of the fingerprint; never accept an older binary merely because it exists.
cache="$repo_root/.ci/native-cache"
[[ ! -L "$repo_root/.ci" && ! -L "$cache" ]] || die 'Native cache directories must not be symlinks.'
mkdir -p "$cache"
input_hash=$({
  git ls-files -z -- version.properties .gitmodules scripts patches | xargs -0 sha256sum
  printf '%s\n' "$submodule_state" 'latest arm64-v8a TD-android-23 RelWithDebInfo c++_shared flexible-page-sizes'
  cmake --version
  sha256sum "$ndk/source.properties"
} | sha256sum)
input_hash=${input_hash%% *}

verify_tdjni() {
  local library="$1" option
  [[ -s "$library" ]] || return 1
  readelf -h "$library" | grep -q 'Machine:.*AArch64' || return 1
  for option in x_moex_ghost_read_private x_moex_ghost_read_groups x_moex_ghost_read_channels x_moex_ghost_read_once x_moex_ghost_online x_moex_ghost_actions x_moex_shadow_local_read; do
    grep -aqF "$option" "$library" || return 1
  done
}
td_cache_valid() {
  [[ -f "$cache/td-input.sha256" && "$(< "$cache/td-input.sha256")" == "$input_hash" && -s "$cache/td-output.sha256" ]] || return 1
  sha256sum --check --status "$cache/td-output.sha256" && verify_tdjni "$cache/libtdjni.so"
}
if td_cache_valid; then
  printf 'native CI: using verified Ghost TDLib cache\n'
else
  [[ -d "${RUNNER_TEMP:-}" ]] || die 'RUNNER_TEMP is required for an uncached TDLib build.'
  # The runner owns and removes this directory. Do not cache large intermediate files.
  td_build=$(mktemp -d "$RUNNER_TEMP/moex-tdlib.XXXXXXXX")
  cmake -S "$td_source/example/android" -B "$td_build/host" -G 'Unix Makefiles' \
    -DTD_GENERATE_SOURCE_FILES=ON -DTD_ENABLE_JNI=ON
  cmake --build "$td_build/host" --target prepare_cross_compiling --parallel "$CPU_COUNT"
  cmake -S "$td_source/example/android" -B "$td_build/arm64" -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$ndk/build/cmake/android.toolchain.cmake" \
    -DOPENSSL_ROOT_DIR="$openssl_root" \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo -DANDROID_ABI=arm64-v8a \
    -DANDROID_STL=c++_shared -DANDROID_PLATFORM=android-23 \
    -DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON -DTD_ENABLE_JNI=ON
  cmake --build "$td_build/arm64" --target tdjni --parallel "$CPU_COUNT"
  verify_tdjni "$td_build/arm64/libtdjni.so" || die 'Built TDLib is not an ARM64 Ghost library.'
  install -m 644 "$td_build/arm64/libtdjni.so" "$cache/libtdjni.so"
  sha256sum .ci/native-cache/libtdjni.so > "$cache/td-output.sha256"
  printf '%s\n' "$input_hash" > "$cache/td-input.sha256"
fi
install -m 644 "$cache/libtdjni.so" "tdlib/src/main/libs/$ANDROID_NDK_VERSION_PRIMARY/arm64-v8a/libtdjni.so"
printf 'native CI: latest/arm64-v8a libraries are ready\n'
