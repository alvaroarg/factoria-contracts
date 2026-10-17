"""Unit tests without networking / provider quota."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

P = Path(__file__).resolve().parents[1] / 'automation' / 'opencode' / 'jira_gate.py'
spec = importlib.util.spec_from_file_location('jira_gate', P)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def issue(key, status='Ready', labels=None, description=None, links=None):
    if labels is None:
        labels=['agent-ready','engine-opencode']
    if description is None:
        description = 'Repository: owner/repo\n## Diseño técnico aprobado\nImplementar la feature con casos de aceptación y pruebas.\n## Dependencias\nNinguna'
    return {'key':key,'fields':{'status':{'name':status},'labels':labels,'description':description,'issuelinks': links or [], 'summary':'Test'}}


class JiraGateTests(unittest.TestCase):
    def setUp(self):
        self.e = patch.dict(os.environ, {'JIRA_PROJECT_KEY':'KAN', 'GITHUB_REPOSITORY':'owner/repo',
                                       'JIRA_READY_STATUS':'Ready', 'JIRA_DONE_STATUS':'Done'}, clear=False)
        self.e.start()
    def tearDown(self): self.e.stop()

    def test_inspect_checks_stale_github_branch(self):
        with patch.object(mod, "github_existing", side_effect=mod.GateError("Remote branch already exists")) as check:
            with self.assertRaisesRegex(mod.GateError, "already exists"):
                mod.validate('KAN-9','inspect',lambda k: issue(k),check_github=True)
            check.assert_called_once_with('KAN-9', 'agent/kan-9')

    def test_no_dep(self):
        x=mod.validate('KAN-9','inspect',lambda k: issue(k),check_github=False)
        self.assertEqual(x['blockers'],[])

    def test_inward_blocks_is_real_blocker(self):
        links=[{'type':{'name':'Blocks','inward':'is blocked by','outward':'blocks'}, 'inwardIssue':{'key':'KAN-8'}}]
        src=issue('KAN-9',links=links)
        get=lambda k: src if k=='KAN-9' else issue('KAN-8',status='Done')
        self.assertEqual(mod.validate('KAN-9','inspect',get,False)['blockers'],['KAN-8'])

    def test_outward_blocks_not_prerequisite(self):
        links=[{'type':{'name':'Blocks','inward':'is blocked by','outward':'blocks'}, 'outwardIssue':{'key':'KAN-8'}}]
        x=mod.validate('KAN-9','inspect',lambda k: issue(k,links=links),False)
        self.assertEqual(x['blockers'],[])

    def test_blocked_in_human_review(self):
        links=[{'type':{'name':'Blocks','inward':'is blocked by','outward':'blocks'}, 'inwardIssue':{'key':'KAN-8'}}]
        get=lambda k: issue(k,links=links) if k=='KAN-9' else issue('KAN-8',status='Human Review')
        with self.assertRaisesRegex(mod.GateError,'not exact'):
            mod.validate('KAN-9','inspect',get,False)

    def test_from_text_dependencies(self):
        desc='Repository: owner/repo\n## Design\nDetailed instructions and acceptance criteria.\n## Dependencias\n- KAN-4\n- KAN-5'
        get=lambda k: issue('KAN-9',description=desc) if k=='KAN-9' else issue(k,status='Done')
        self.assertEqual(mod.validate('KAN-9','inspect',get,False)['blockers'],['KAN-4','KAN-5'])

    def test_stuck_in_progress(self):
        with self.assertRaisesRegex(mod.GateError,'expected Ready'):
            mod.validate('KAN-9','inspect',lambda k:issue(k,status='En curso'),False)

    def test_labels_exclusive(self):
        with self.assertRaisesRegex(mod.GateError,'exactly one'):
            mod.validate('KAN-9','inspect',lambda k:issue(k,labels=['agent-ready','engine-claude','engine-opencode']),False)

    def test_repo_mismatch(self):
        with self.assertRaisesRegex(mod.GateError,'Repository'):
            mod.validate('KAN-9','inspect',lambda k:issue(k,description='Repository: other/foreign\nDetailed approved specification and acceptance tests.'),False)

    def test_project_key_conflict(self):
        with self.assertRaisesRegex(mod.GateError,'not in configured'):
            mod.validate('ABC-2','inspect',lambda k:issue(k),False)

    def test_missing_link_data(self):
        with self.assertRaisesRegex(mod.GateError,'links'):
            mod.blocking_links(None)

    def test_explicit_text_blocker(self):
        self.assertIn('KAN-20', mod.extract_text_blockers('Blocked by KAN-20'))

    def test_never_emit_fake_token_usage(self):
        self.assertEqual(mod.flatten_adf({'type':'doc','content':[{'type':'paragraph','content':[{'type':'text','text':'Repository: owner/repo'}]}]}), 'Repository: owner/repo')

    # Álvaro's KAN board: Ready = Listo, Done = Finalizada (equivalent names).
    def test_listo_equals_ready(self):
        x=mod.validate('KAN-9','inspect',lambda k: issue(k,status='Listo'),False)
        self.assertEqual(x['status'],'Listo')

    def test_finalizada_equals_done(self):
        links=[{'type':{'name':'Blocks','inward':'is blocked by','outward':'blocks'}, 'inwardIssue':{'key':'KAN-8'}}]
        get=lambda k: issue('KAN-9',status='Listo',links=links) if k=='KAN-9' else issue('KAN-8',status='Finalizada')
        self.assertEqual(mod.validate('KAN-9','inspect',get,False)['blockers'],['KAN-8'])

    def test_equivalence_holds_with_spanish_env(self):
        with patch.dict(os.environ, {'JIRA_READY_STATUS':'Listo','JIRA_DONE_STATUS':'Finalizada'}):
            links=[{'type':{'name':'Blocks','inward':'is blocked by','outward':'blocks'}, 'inwardIssue':{'key':'KAN-8'}}]
            get=lambda k: issue('KAN-9',status='Ready',links=links) if k=='KAN-9' else issue('KAN-8',status='Done')
            self.assertEqual(mod.validate('KAN-9','inspect',get,False)['blockers'],['KAN-8'])

    def test_comma_separated_extra_status(self):
        with patch.dict(os.environ, {'JIRA_READY_STATUS':'Listo, Selected for Development'}):
            mod.validate('KAN-9','inspect',lambda k: issue(k,status='Selected for Development'),False)

    def test_en_curso_still_blocked_with_spanish_env(self):
        with patch.dict(os.environ, {'JIRA_READY_STATUS':'Listo','JIRA_DONE_STATUS':'Finalizada'}):
            with self.assertRaisesRegex(mod.GateError,'expected Ready'):
                mod.validate('KAN-9','inspect',lambda k:issue(k,status='En curso'),False)
            links=[{'type':{'name':'Blocks','inward':'is blocked by','outward':'blocks'}, 'inwardIssue':{'key':'KAN-8'}}]
            get=lambda k: issue(k,links=links) if k=='KAN-9' else issue('KAN-8',status='Human Review')
            with self.assertRaisesRegex(mod.GateError,'not exact'):
                mod.validate('KAN-9','inspect',get,False)

if __name__=='__main__': unittest.main()
