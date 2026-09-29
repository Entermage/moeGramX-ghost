"""Check source-link wiring and optionally the real generated BuildConfig."""
import argparse
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "https://github.com/Entermage/moeGramX-ghost"


def verify_build_config(content, repository, commit):
    expected = {
        "SOURCES_URL": repository,
        "REMOTE_URL": repository,
        "COMMIT_URL": f"{repository}/tree/{commit}",
        "COMMIT_FULL": commit,
    }
    for field, value in expected.items():
        match = re.search(r"public static final String " + field + r" = (\"[^\n]*\");", content)
        if not match or json.loads(match[1]) != value:
            raise AssertionError(f"Generated {field} does not match the expected repository/commit")


class SourceRepositoryTest(unittest.TestCase):
    def test_defaults_and_actual_menu_share_config(self):
        defaults = (ROOT / "local.properties.sample").read_text()
        self.assertIn(f"app.sources_url={REPOSITORY}\n", defaults)
        config = (ROOT / "buildSrc/src/main/kotlin/tgx/gradle/source/AppConfigurationSource.kt").read_text()
        self.assertIn('properties.getProperty("app.sources_url")?.takeIf { it.isNotBlank() }', config)
        self.assertIn('defaults.getProperty("app.sources_url", "")', config)
        menu = (ROOT / "app/src/main/java/moe/kirao/mgx/ui/SettingsMoexController.java").read_text()
        self.assertIn("openUrl(this, BuildConfig.SOURCES_URL,", menu)
        self.assertNotIn("R.string.MoexSourceLink", menu)

    def test_app_links_use_fork_but_dependency_links_stay_original(self):
        build = (ROOT / "app/build.gradle.kts").read_text()
        self.assertIn('buildConfigString("REMOTE_URL", sourcesUrl)', build)
        self.assertIn('buildConfigString("SOURCES_URL", sourcesUrl)', build)
        self.assertIn('buildConfigString("COMMIT_URL", "$sourcesUrl/tree/${tgxGit.commitHashLong}")', build)
        self.assertNotIn('buildConfigString("COMMIT_URL", tgxGit.commitUrl)', build)
        for field, source in (("OPENSSL", "openSsl"), ("WEBRTC", "webrtc"), ("TGCALLS", "tgcalls"),
                              ("FFMPEG", "ffmpeg"), ("WEBP", "webp")):
            self.assertIn(f'buildConfigString("{field}_COMMIT_URL", {source}Git.commitUrl)', build)

    def test_generated_metadata_validator_rejects_old_source_or_commit(self):
        commit = "1" * 40
        values = {"SOURCES_URL": REPOSITORY, "REMOTE_URL": REPOSITORY,
                  "COMMIT_URL": f"{REPOSITORY}/tree/{commit}", "COMMIT_FULL": commit}

        def render(fields):
            return "\n".join(f"public static final String {key} = {json.dumps(value)};"
                             for key, value in fields.items())

        verify_build_config(render(values), REPOSITORY, commit)
        for field in values:
            invalid = {**values, field: "https://github.com/moeCrafters/moeGramX"}
            with self.subTest(field=field), self.assertRaises(AssertionError):
                verify_build_config(render(invalid), REPOSITORY, commit)
        with self.assertRaises(AssertionError):
            verify_build_config("", REPOSITORY, commit)


if __name__ == "__main__":
    if "--build-config" in sys.argv:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--build-config", type=Path, required=True)
        parser.add_argument("--repository", default=REPOSITORY)
        parser.add_argument("--commit", required=True)
        args = parser.parse_args()
        verify_build_config(args.build_config.read_text(), args.repository, args.commit)
        print("Generated repository, source and commit links verified")
    else:
        unittest.main()
