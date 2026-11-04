"""Unit tests without networking or provider quota."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / 'automation' / 'codex' / 'jira_gate.py'
spec = importlib.util.spec_from_file_location('codex_jira_gate', P)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

OPENCODE = Path(__file__).resolve().parents[2] / 'opencode' / 'automation' / 'opencode' / 'jira_gate.py'
ospec = importlib.util.spec_from_file_location('opencode_jira_gate_labels', OPENCODE)
omod = importlib.util.module_from_spec(ospec)
ospec.loader.exec_module(omod)

PLAIN = 'Diseño técnico aprobado: implementar la feature con criterios de aceptación y pruebas unitarias.'
BLOCKS = {'name': 'Blocks', 'inward': 'is blocked by', 'outward': 'blocks'}
NO_VARS = ('JIRA_READY_STATUS', 'JIRA_DONE_STATUS', 'JIRA_HUMAN_REVIEW_STATUS', 'JIRA_PROJECT_KEY',
           'JIRA_REPOSITORY_FIELD_ID', 'JIRA_DEPENDENCIES_FIELD_ID')


def issue(key, status='Ready', labels=None, description=None, links=None):
    if labels is None:
        labels = ['agent-ready', 'engine-openai']
    if description is None:
        description = 'Repository: owner/repo\n## Diseño técnico aprobado\nImplementar la feature con casos de aceptación y pruebas.\n## Dependencias\nNinguna'
    return {'key': key, 'fields': {'status': {'name': status}, 'labels': labels, 'description': description, 'issuelinks': links or [], 'summary': 'Test'}}


def no_vars_env(**extra):
    env = {k: v for k, v in os.environ.items() if k not in NO_VARS}
    env.update({'GITHUB_REPOSITORY': 'owner/repo'}, **extra)
    return patch.dict(os.environ, env, clear=True)


class CodexJiraGateTests(unittest.TestCase):
    def setUp(self):
        self._env = patch.dict(os.environ, {'JIRA_PROJECT_KEY': 'KAN', 'GITHUB_REPOSITORY': 'owner/repo'}, clear=False)
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def test_engine_set_matches_opencode_and_requires_openai(self):
        self.assertEqual(mod.ENGINE_LABELS, omod.ENGINE_LABELS)
        self.assertEqual(mod.REQUIRED_ENGINE, 'engine-openai')
        self.assertEqual(omod.REQUIRED_ENGINE, 'engine-opencode')
        self.assertEqual(mod.BRANCH_PREFIX, 'codex')
        self.assertIn('engine-openai', mod.ENGINE_LABELS)

    def test_accepts_listo_and_finalizada(self):
        links = [{'type': BLOCKS, 'inwardIssue': {'key': 'KAN-8'}}]
        get = lambda k: issue('KAN-9', status='Listo', links=links) if k == 'KAN-9' else issue('KAN-8', status='Finalizada')
        found = mod.validate('KAN-9', 'inspect', get, False)
        self.assertEqual(found['blockers'], ['KAN-8'])
        self.assertEqual(found['branch'], 'codex/kan-9')
        self.assertEqual(found['status'], 'Listo')

    def test_human_review_blocker_is_not_done(self):
        links = [{'type': BLOCKS, 'inwardIssue': {'key': 'KAN-8'}}]
        get = lambda k: issue('KAN-9', links=links) if k == 'KAN-9' else issue('KAN-8', status='Human Review')
        with self.assertRaisesRegex(mod.GateError, 'not exact'):
            mod.validate('KAN-9', 'inspect', get, False)

    def test_other_engines_and_two_labels_are_blocked(self):
        for labels in (
            ['agent-ready', 'engine-opencode'],
            ['agent-ready', 'engine-claude'],
            ['agent-ready', 'engine-cursor'],
            ['agent-ready', 'engine-openai', 'engine-opencode'],
            ['agent-ready'],
        ):
            with self.assertRaisesRegex(mod.GateError, 'exactly one'):
                mod.validate('KAN-9', 'inspect', lambda k, labels=labels: issue(k, labels=labels), False)

    def test_repo_defaults_and_foreign_repo_fails(self):
        with no_vars_env():
            found = mod.validate('KAN-9', 'inspect', lambda k: issue(k, description=PLAIN), False)
            self.assertEqual(found['repo_source'], 'default GITHUB_REPOSITORY')
            with self.assertRaisesRegex(mod.GateError, 'does not match'):
                mod.validate('KAN-9', 'inspect', lambda k: issue(k, description='Repositorio destino: other/foreign\n' + PLAIN), False)

    def test_default_select_stops_at_one_by_rank(self):
        data = {
            'KAN-1': issue('KAN-1', status='En curso'),
            'KAN-2': issue('KAN-2', labels=['agent-ready', 'engine-claude']),
            'KAN-3': issue('KAN-3', status='Listo', description=PLAIN),
            'KAN-4': issue('KAN-4', status='Listo', description=PLAIN),
        }
        with no_vars_env():
            chosen, skipped = mod.select('inspect', data.__getitem__, lambda j, l=50: ['KAN-1', 'KAN-2', 'KAN-3', 'KAN-4'], check_github=False)
        self.assertEqual([item['issue'] for item in chosen], ['KAN-3'])
        self.assertEqual(chosen[0]['branch'], 'codex/kan-3')
        self.assertEqual([item['issue'] for item in skipped], ['KAN-1', 'KAN-2'])

    def test_max_issues_three_keeps_rank_and_rejects_four(self):
        keys = ['KAN-1', 'KAN-2', 'KAN-3']
        data = {key: issue(key, status='Listo', description=PLAIN) for key in keys}
        with no_vars_env():
            chosen, _skipped = mod.select('inspect', data.__getitem__, lambda j, l=50: keys, check_github=False, max_issues=3)
        self.assertEqual([item['issue'] for item in chosen], keys)
        with self.assertRaisesRegex(mod.GateError, '1 to 3'):
            mod.select('inspect', data.__getitem__, lambda j, l=50: keys, check_github=False, max_issues=4)

    def test_explicit_key_does_not_search_and_ignores_max(self):
        def boom(*_a, **_k):
            raise AssertionError('search must not run when issue_key is set')
        with tempfile.NamedTemporaryFile('r', delete=False) as handle, no_vars_env(GITHUB_OUTPUT=handle.name), \
                patch.object(mod, 'jira_client', return_value=lambda k: issue(k, status='Listo')), \
                patch.object(mod, 'jira_search_client', side_effect=boom), \
                patch.object(mod, 'github_existing', return_value=None):
            self.assertEqual(mod.main(['--issue', 'kan-9', '--max-issues', '3', '--mode', 'build']), 0)
            text = Path(handle.name).read_text(encoding='utf-8')
        os.unlink(handle.name)
        self.assertIn('issue=KAN-9', text)
        self.assertIn('branch=codex/kan-9', text)
        self.assertIn('issues=["KAN-9"]', text)

    def test_no_eligible_is_green_no_work(self):
        data = {'KAN-1': issue('KAN-1', labels=['agent-ready', 'engine-opencode'])}
        with tempfile.NamedTemporaryFile('r', delete=False) as handle, no_vars_env(GITHUB_OUTPUT=handle.name), \
                patch.object(mod, 'jira_client', return_value=data.__getitem__), \
                patch.object(mod, 'jira_search_client', return_value=lambda j, l=50: ['KAN-1']):
            self.assertEqual(mod.main(['--mode', 'inspect']), 0)
            text = Path(handle.name).read_text(encoding='utf-8')
        os.unlink(handle.name)
        self.assertIn('has_work=false', text)
        self.assertIn('issues=[]', text)

    def test_jql_filters_engine_openai_and_rank(self):
        seen = []
        def search(jql, limit=50):
            seen.append(jql)
            return []
        with no_vars_env():
            mod.select('inspect', {}, search, check_github=False)
        self.assertIn('engine-openai', seen[0])
        self.assertNotIn('engine-opencode', seen[0])
        self.assertTrue(seen[0].endswith('ORDER BY Rank ASC'))


if __name__ == '__main__':
    unittest.main()
