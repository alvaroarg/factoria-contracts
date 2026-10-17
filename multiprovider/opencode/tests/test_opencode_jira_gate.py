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
        # Claude/Cursor contract rule: "Any other name is not Ready/Done". The
        # variables can no longer widen the accepted names.
        with patch.dict(os.environ, {'JIRA_READY_STATUS':'Listo, Selected for Development'}):
            with self.assertRaisesRegex(mod.GateError,'expected Ready'):
                mod.validate('KAN-9','inspect',lambda k: issue(k,status='Selected for Development'),False)

    def test_en_curso_still_blocked_with_spanish_env(self):
        with patch.dict(os.environ, {'JIRA_READY_STATUS':'Listo','JIRA_DONE_STATUS':'Finalizada'}):
            with self.assertRaisesRegex(mod.GateError,'expected Ready'):
                mod.validate('KAN-9','inspect',lambda k:issue(k,status='En curso'),False)
            links=[{'type':{'name':'Blocks','inward':'is blocked by','outward':'blocks'}, 'inwardIssue':{'key':'KAN-8'}}]
            get=lambda k: issue(k,links=links) if k=='KAN-9' else issue('KAN-8',status='Human Review')
            with self.assertRaisesRegex(mod.GateError,'not exact'):
                mod.validate('KAN-9','inspect',get,False)


CLAUDE_RULE = ('**Localized status names:** Jira may return translated `status.name` values depending on the '
               'account language. Treat `Ready` and `Listo` as the same status, and `Done` and `Finalizada` as the '
               'same status, in every check of this contract (candidate selection, dependency gate and re-checks). '
               'Any other name is not `Ready`/`Done`.')
ROOT = Path(__file__).resolve().parents[1]
NO_VARS = ('JIRA_READY_STATUS', 'JIRA_DONE_STATUS', 'JIRA_HUMAN_REVIEW_STATUS', 'JIRA_PROJECT_KEY',
           'JIRA_REPOSITORY_FIELD_ID', 'JIRA_DEPENDENCIES_FIELD_ID', 'ENABLE_OPENCODE_FACTORY_PILOT')
BLOCKS = {'name':'Blocks','inward':'is blocked by','outward':'blocks'}
PLAIN = 'Diseño técnico aprobado: implementar la feature con criterios de aceptación y pruebas unitarias.'


def no_vars_env(**extra):
    env = {k: v for k, v in os.environ.items() if k not in NO_VARS}
    env.update({'GITHUB_REPOSITORY': 'owner/repo'}, **extra)
    return patch.dict(os.environ, env, clear=True)


class ZeroConfigTests(unittest.TestCase):
    """Works like the previous pilot: no GitHub Variables, no issue_key, no story edits."""

    def test_without_any_variable(self):
        with no_vars_env():
            links=[{'type':BLOCKS,'inwardIssue':{'key':'KAN-8'}}]
            get=lambda k: issue('KAN-9',status='Listo',links=links) if k=='KAN-9' else issue('KAN-8',status='Finalizada')
            x=mod.validate('KAN-9','inspect',get,False)
            self.assertEqual((x['status'],x['blockers']),('Listo',['KAN-8']))
            self.assertEqual(mod.project_key(), 'KAN')
            self.assertEqual(mod.project_key('ABC-3'), 'ABC')

    def test_status_rule_is_exactly_the_claude_rule(self):
        self.assertEqual(mod.STATUS_EQUIVALENTS, {'ready':('Ready','Listo'),'done':('Done','Finalizada')})
        for name in ('ready','READY',' Listo ','listo'):
            self.assertTrue(mod.status_is(name,'ready'))
        for name in ('En curso','In Progress','Selected for Development','Human Review'):
            self.assertFalse(mod.status_is(name,'ready'))
        for name in ('Human Review','Resolved','Cerrada','AI Review'):
            self.assertFalse(mod.status_is(name,'done'))
        with no_vars_env(JIRA_DONE_STATUS='Resolved'):
            links=[{'type':BLOCKS,'inwardIssue':{'key':'KAN-8'}}]
            get=lambda k: issue('KAN-9',links=links) if k=='KAN-9' else issue('KAN-8',status='Resolved')
            with self.assertRaisesRegex(mod.GateError,'not exact'):
                mod.validate('KAN-9','inspect',get,False)

    def test_contracts_copy_claude_rule_verbatim(self):
        for rel in ('.opencode/agents/factory-orchestrator.md', 'automation/opencode/pilot-prompt.md'):
            self.assertIn(CLAUDE_RULE, (ROOT/rel).read_text(encoding='utf-8'), rel)
            self.assertNotIn('En curso', (ROOT/rel).read_text(encoding='utf-8'), rel)

    def test_repo_defaults_to_current_repo(self):
        with no_vars_env():
            x=mod.validate('KAN-9','inspect',lambda k: issue(k,description=PLAIN),False)
            self.assertEqual((x['repo'],x['repo_source']),('owner/repo','default GITHUB_REPOSITORY'))

    def test_repositorio_destino_line(self):
        with no_vars_env():
            d='**Repositorio destino:** `owner/repo` (rama base `master`)\n'+PLAIN
            self.assertEqual(mod.validate('KAN-9','inspect',lambda k: issue(k,description=d),False)['repo_source'],'story')
            d='Repositorio: https://github.com/owner/repo.git\n'+PLAIN
            mod.validate('KAN-9','inspect',lambda k: issue(k,description=d),False)

    def test_repositorio_destino_mismatch_fails(self):
        with no_vars_env():
            for d in ('Repositorio destino: other/foreign\n'+PLAIN, 'Repositorio: other/foreign\n'+PLAIN):
                with self.assertRaisesRegex(mod.GateError,'does not match'):
                    mod.validate('KAN-9','inspect',lambda k: issue(k,description=d),False)

    def test_kan_adf_first_paragraph(self):
        adf={'type':'doc','content':[{'type':'paragraph','content':[
            {'type':'text','text':'Repositorio destino:','marks':[{'type':'strong'}]},{'type':'text','text':' '},
            {'type':'text','text':'owner/repo','marks':[{'type':'code'}]},{'type':'text','text':' (rama base '},
            {'type':'text','text':'master','marks':[{'type':'code'}]},{'type':'text','text':')'},{'type':'hardBreak'},
            {'type':'text','text':'Dependencias (is blocked by):','marks':[{'type':'strong'}]},{'type':'text','text':' KAN-8, KAN-7'}]},
            {'type':'paragraph','content':[{'type':'text','text':PLAIN}]}]}
        text=mod.flatten_adf(adf)
        self.assertIn('Repositorio destino: owner/repo (rama base master)\n', text)
        self.assertEqual(mod.declared_repositories(text), ['owner/repo'])
        self.assertEqual(mod.extract_text_blockers(text), {'KAN-7','KAN-8'})
        with no_vars_env():
            get=lambda k: issue('KAN-9',status='Listo',description=adf) if k=='KAN-9' else issue(k,status='Finalizada')
            self.assertEqual(mod.validate('KAN-9','inspect',get,False)['blockers'],['KAN-7','KAN-8'])

    def _backlog(self):
        return {
            'KAN-1': issue('KAN-1', status='En curso'),
            'KAN-2': issue('KAN-2', labels=['agent-ready','engine-claude']),
            'KAN-3': issue('KAN-3', links=[{'type':BLOCKS,'inwardIssue':{'key':'KAN-90'}}]),
            'KAN-90': issue('KAN-90', status='Human Review'),
            'KAN-4': issue('KAN-4', status='Listo', description=PLAIN),
            'KAN-5': issue('KAN-5'),
        }

    def test_without_issue_key_selects_first_eligible_by_rank(self):
        data=self._backlog(); seen=[]
        def search(jql, limit=50):
            seen.append(jql); return ['KAN-1','KAN-2','KAN-3','KAN-4','KAN-5']
        with no_vars_env():
            result, skipped = mod.select('inspect', data.__getitem__, search, check_github=False)
        self.assertEqual(result['issue'], 'KAN-4')
        self.assertEqual(result['branch'], 'agent/kan-4')
        self.assertEqual([s['issue'] for s in skipped], ['KAN-1','KAN-2','KAN-3'])
        self.assertIn('project = "KAN"', seen[0]); self.assertIn('engine-opencode', seen[0])
        self.assertIn('agent-ready', seen[0]); self.assertTrue(seen[0].endswith('ORDER BY Rank ASC'))

    def test_selection_skips_existing_agent_branch(self):
        data=self._backlog()
        def existing(key, branch):
            if key=='KAN-4': raise mod.GateError('Remote branch agent/kan-4 already exists')
        with no_vars_env(), patch.object(mod,'github_existing',side_effect=existing):
            result, skipped = mod.select('inspect', data.__getitem__, lambda j,l=50: ['KAN-4','KAN-5'])
        self.assertEqual(result['issue'],'KAN-5'); self.assertEqual(skipped[0]['issue'],'KAN-4')

    def test_selection_infra_error_fails_closed(self):
        data=self._backlog()
        with no_vars_env(), patch.object(mod,'github_existing',side_effect=mod.GateInfraError('gh down')):
            with self.assertRaises(mod.GateInfraError):
                mod.select('inspect', data.__getitem__, lambda j,l=50: ['KAN-4'])

    def test_no_eligible_is_green_no_work(self):
        import tempfile
        data=self._backlog()
        with tempfile.NamedTemporaryFile('r', delete=False) as out, no_vars_env(GITHUB_OUTPUT=out.name), \
                patch.object(mod,'jira_client',return_value=data.__getitem__), \
                patch.object(mod,'jira_search_client',return_value=lambda j,l=50: ['KAN-1','KAN-2','KAN-3']):
            self.assertEqual(mod.main(['--issue','','--mode','build']), 0)
            self.assertEqual(mod.main(['--mode','inspect']), 0)
            self.assertIn('has_work=false', Path(out.name).read_text())
        os.unlink(out.name)

    def test_main_with_explicit_key_still_works(self):
        import tempfile
        with tempfile.NamedTemporaryFile('r', delete=False) as out, no_vars_env(GITHUB_OUTPUT=out.name), \
                patch.object(mod,'jira_client',return_value=lambda k: issue(k,status='Listo')), \
                patch.object(mod,'github_existing',return_value=None):
            self.assertEqual(mod.main(['--issue','kan-9','--mode','inspect']), 0)
            txt=Path(out.name).read_text()
        os.unlink(out.name)
        self.assertIn('issue=KAN-9', txt); self.assertIn('branch=agent/kan-9', txt); self.assertIn('has_work=true', txt)


class WorkflowZeroConfigTests(unittest.TestCase):
    wf = (ROOT/'.github'/'workflows'/'opencode-factory.yml').read_text(encoding='utf-8')

    def test_issue_key_optional(self):
        block = self.wf.split('issue_key:',1)[1].split('mode:',1)[0]
        self.assertIn('required: false', block)
        self.assertNotIn('required: true', block)

    def test_no_mandatory_pilot_variable(self):
        self.assertNotIn('!= "true"', self.wf)
        self.assertIn('if [ "$ENABLE_PILOT" = "false" ]', self.wf)

    def test_defaults_without_variables(self):
        self.assertIn("vars.JIRA_PROJECT_KEY || 'KAN'", self.wf)
        self.assertIn("vars.JIRA_HUMAN_REVIEW_STATUS || 'Human Review'", self.wf)
        self.assertNotIn('JIRA_READY_STATUS', self.wf)
        self.assertNotIn('JIRA_DONE_STATUS', self.wf)

    def test_quota_controls_kept(self):
        for needle in ('timeout-minutes: 50', '--no-edit-seconds 360', '--total-seconds 2700',
                       '--max-reported-input-tokens 800000', 'postflight.py', 'check_config.py',
                       'git fetch origin "$DEFAULT_BRANCH"', 'DEFAULT_BRANCH="master"', '- inspect', '- build'):
            self.assertIn(needle, self.wf)
        self.assertEqual(self.wf.count("steps.gate.outputs.has_work == 'true'"), 5)


    def test_diff_artifact_step(self):
        steps = self.wf.split('\n      - name: ')
        guarded = next(i for i, s in enumerate(steps) if s.startswith('One guarded'))
        save_i = next(i for i, s in enumerate(steps) if s.startswith('Save working-tree diff'))
        up_i = next(i for i, s in enumerate(steps) if s.startswith('Upload diff artifact'))
        self.assertTrue(guarded < save_i < up_i)
        save, up = steps[save_i], steps[up_i]
        for s in (save, up):
            self.assertIn('if: always()', s)
            self.assertIn('continue-on-error: true', s)
        self.assertIn('git add -A', save)
        self.assertIn('git diff --cached --binary "$BASE_SHA"', save)
        self.assertIn('.patch', save)
        self.assertIn('exit 0', save)
        self.assertNotIn('set -e\n', save)
        self.assertNotIn('git push', save)
        self.assertNotIn('git commit', save)
        self.assertNotIn('gh pr', save)
        self.assertIn('uses: actions/upload-artifact@v4', up)
        self.assertIn('name: opencode-factory-diff', up)
        self.assertIn('retention-days: 7', up)
        self.assertIn('if-no-files-found: ignore', up)
        self.assertNotIn('--total-seconds 1800', self.wf)
        self.assertNotIn('timeout-minutes: 35', self.wf)

if __name__=='__main__': unittest.main()
