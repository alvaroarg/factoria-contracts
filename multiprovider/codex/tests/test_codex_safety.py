"""Offline checks for prompts, review publication, paths, and secrets."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    path = ROOT / 'automation' / 'codex' / (name + '.py')
    spec = importlib.util.spec_from_file_location('codex_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


safety = load('safety')
render = load('render_prompt')
home = load('prepare_codex_home')
review = load('prepare_review')
postflight = load('postflight')
publish = load('publish_review')


class SafetyTests(unittest.TestCase):
    def test_protected_factory_paths(self):
        paths = [
            'src/app.py',
            'AGENTS.md',
            '.github/workflows/codex-factory.yml',
            '.codex/config.toml',
            'automation/codex/jira_gate.py',
            '.review/pr.diff',
            'CLAUDE.md',
            '.env',
            'pkg/.env.local',
        ]
        blocked = safety.protected_paths(paths)
        self.assertEqual(blocked, [
            '.github/workflows/codex-factory.yml',
            '.codex/config.toml',
            'automation/codex/jira_gate.py',
            '.review/pr.diff',
            'CLAUDE.md',
            '.env',
            'pkg/.env.local',
        ])

    def test_secret_categories_do_not_echo_values(self):
        token = 'sk-' + ('a' * 24)
        hits = safety.secret_categories('leaked ' + token + ' and ghp_' + ('b' * 24), {'JIRA_API_TOKEN': 'jira-token-value'})
        self.assertIn('openai-key-pattern', hits)
        self.assertIn('github-token-pattern', hits)
        self.assertNotIn(token, hits)
        self.assertEqual(safety.secret_categories('clean diff', {'JIRA_API_TOKEN': 'jira-token-value'}), [])
        self.assertEqual(safety.secret_categories('jira-token-value', {'JIRA_API_TOKEN': 'jira-token-value'}), ['JIRA_API_TOKEN'])

    def test_status_rename(self):
        self.assertEqual(safety.status_paths('M  src/a.py\nA  old.py -> new.py\n'), ['src/a.py', 'new.py'])


class RenderAndHomeTests(unittest.TestCase):
    def test_render_replaces_and_fails_closed(self):
        text = render.render('Story __ISSUE_KEY__ on __BRANCH__', ISSUE_KEY='KAN-9', BRANCH='codex/kan-9')
        self.assertEqual(text, 'Story KAN-9 on codex/kan-9')
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            render.render('missing __HEAD_SHA__', ISSUE_KEY='KAN-9')

    def test_prepare_home_trusts_workspace_and_copies_agents(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = home.prepare(ROOT / '.codex' / 'config.toml', ROOT / '.codex' / 'agents', Path(tmp) / 'home', '/work/repo')
            text = (dest / 'config.toml').read_text(encoding='utf-8')
            self.assertIn('[projects."/work/repo"]', text)
            self.assertIn('trust_level = "trusted"', text)
            self.assertIn('approval_policy = "never"', text)
            self.assertTrue((dest / 'agents' / 'feature-builder.toml').is_file())
            self.assertNotIn('sk-', text)

    def test_review_context_points_at_the_diff_file(self):
        body = review.build_context(
            issue='KAN-9', repo='owner/repo', pr_url='https://github.com/owner/repo/pull/4',
            head='a' * 40, base='master', description='Diseño aprobado ' * 8,
        )
        self.assertIn('KAN-9', body)
        self.assertIn('.review/pr.diff', body)
        self.assertIn('a' * 40, body)


class ReviewPublicationTests(unittest.TestCase):
    def test_pass_requires_the_current_head(self):
        head = 'b' * 40
        verdict = {'verdict': 'PASS', 'jira_key': 'KAN-9', 'head_sha': head, 'summary': 'ok'}
        self.assertEqual(publish.classify(verdict, 'KAN-9', head), 'pass')
        self.assertEqual(publish.classify({**verdict, 'verdict': 'CHANGES_REQUESTED'}, 'KAN-9', head), 'stop')
        with self.assertRaises(publish.ReviewError):
            publish.classify({**verdict, 'head_sha': 'c' * 40}, 'KAN-9', head)
        with self.assertRaises(publish.ReviewError):
            publish.classify({**verdict, 'jira_key': 'KAN-8'}, 'KAN-9', head)

    def test_comments_keep_the_pass_marker_exclusive(self):
        passed = publish.pass_comment('d' * 40, 'looks good')
        self.assertIn('Factory Review: PASS', passed)
        self.assertIn('Factory Review Head: ' + ('d' * 40), passed)
        self.assertIn('Factory Reviewer: pr-reviewer', passed)
        stopped = publish.stop_comment('CHANGES_REQUESTED', 'fix the null check')
        self.assertNotIn('Factory Review: PASS', stopped)
        self.assertIn('Factory Review: CHANGES_REQUESTED', stopped)
        redacted = publish.safe_summary('token ' + ('e' * 12), {'JIRA_API_TOKEN': 'e' * 12})
        self.assertNotIn('e' * 12, redacted)

    def test_postflight_accepts_draft_and_rejects_secrets_or_protected_files(self):
        head = 'f' * 40
        pr = {
            'isDraft': True,
            'body': 'Factory Engine: openai\nFactory Jira: KAN-9\n',
            'baseRefName': 'master',
            'headRefOid': head,
            'url': 'https://github.com/owner/repo/pull/9',
        }
        comments = ['Factory Review: PASS\nFactory Review Head: ' + head + '\nFactory Reviewer: pr-reviewer\n']
        result = postflight.evaluate(
            issue='KAN-9', pr=pr, comments=comments, jira_status='Human Review',
            paths=['src/app.py'], blobs=comments, secrets={}, expected_status='Human Review',
        )
        self.assertTrue(result['secrets_ok'])
        with self.assertRaisesRegex(RuntimeError, 'Protected'):
            postflight.evaluate(
                issue='KAN-9', pr=pr, comments=comments, jira_status='Human Review',
                paths=['.github/workflows/codex-factory.yml'], blobs=comments, secrets={}, expected_status='',
            )
        with self.assertRaisesRegex(RuntimeError, 'Secret'):
            postflight.evaluate(
                issue='KAN-9', pr=pr, comments=comments, jira_status='Human Review',
                paths=['src/app.py'], blobs=['sk-' + ('a' * 24)], secrets={}, expected_status='Human Review',
            )
        with self.assertRaisesRegex(RuntimeError, 'not master'):
            postflight.evaluate(
                issue='KAN-9', pr={**pr, 'baseRefName': 'main'}, comments=comments, jira_status='Human Review',
                paths=['src/app.py'], blobs=comments, secrets={}, expected_status='Human Review',
            )


class ConfigTests(unittest.TestCase):
    def test_check_config_passes_without_calling_a_model(self):
        check = load('check_config')
        drop = ('OPENAI_API_KEY', 'JIRA_URL', 'JIRA_USERNAME', 'JIRA_API_TOKEN',
                'CODEX_VERSION', 'CODEX_ORCHESTRATOR_MODEL', 'CODEX_BUILDER_MODEL', 'CODEX_REVIEWER_MODEL')
        env = {key: value for key, value in os.environ.items() if key not in drop}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(check.main([]), 0)
            self.assertEqual(check.main(['--require-secrets']), 2)

    def test_pinned_cli_parser(self):
        check = load('check_config')

        class Result:
            returncode = 0
            stdout = 'codex-cli 0.166.0\n'
            stderr = ''

        check.require_codex_version(lambda _args: Result())
        bad = Result()
        bad.stdout = 'codex-cli 0.167.0-alpha.4\n'
        with self.assertRaises(ValueError):
            check.require_codex_version(lambda _args: bad)

    def test_workflow_is_pilot_only(self):
        text = (ROOT / '.github' / 'workflows' / 'codex-factory.yml').read_text(encoding='utf-8')
        self.assertIn('workflow_dispatch:', text)
        self.assertNotIn('cron:', text)
        self.assertNotIn('schedule:', text)
        self.assertIn('safety-strategy: drop-sudo', text)
        self.assertIn('permission-profile: factory-build', text)
        self.assertIn('openai/codex-action@v1', text)
        self.assertIn('--sandbox read-only', text)
        self.assertIn('--ask-for-approval never', text)
        self.assertNotIn('--yolo', text)
        self.assertNotIn('danger-full-access', text)
        self.assertNotIn('dangerously-bypass', text)
        self.assertIn('max-parallel: 3', text)
        self.assertIn('fail-fast: false', text)
        self.assertIn('codex-factory-diff-${{ matrix.issue }}', text)
        self.assertIn('codex-factory-summary-${{ matrix.issue }}', text)
        self.assertIn('CODEX_ORCHESTRATOR_MODEL: gpt-6.1-sol', text)
        self.assertIn('CODEX_BUILDER_MODEL: gpt-6.1-sol', text)
        self.assertIn('CODEX_REVIEWER_MODEL: gpt-6.1-sol', text)
        self.assertIn('default: "1"', text)
        self.assertIn('default: inspect', text)
        self.assertNotRegex(text, r'(?m)^[\s-]*OPENAI_API_KEY:')
        schema = json.loads((ROOT / 'automation' / 'codex' / 'review-schema.json').read_text(encoding='utf-8'))
        self.assertEqual(schema['properties']['verdict']['enum'], ['PASS', 'CHANGES_REQUESTED', 'BLOCKED'])


if __name__ == '__main__':
    unittest.main()
