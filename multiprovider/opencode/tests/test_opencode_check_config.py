"""Static checks (no OpenCode CLI, no quota): agent files match check_config expectations."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / 'automation' / 'opencode' / 'check_config.py'
spec = importlib.util.spec_from_file_location('check_config', P)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class CheckConfigTests(unittest.TestCase):
    def test_expected_models(self):
        self.assertEqual(mod.AGENTS['factory-orchestrator'], ('primary', 'opencode-go/kimi-k3', 40))
        self.assertEqual(mod.AGENTS['feature-builder'], ('subagent', 'opencode-go/deepseek-v4-pro', None))
        self.assertEqual(mod.AGENTS['pr-reviewer'], ('subagent', 'opencode-go/kimi-k3', 15))

    def test_agent_files_match_expectations(self):
        for name, (mode, model, steps) in mod.AGENTS.items():
            fm = mod.frontmatter(ROOT / '.opencode' / 'agents' / (name + '.md'))
            self.assertEqual((fm.get('mode'), fm.get('model'), fm.get('steps')), (mode, model, None if steps is None else str(steps)), name)

    def test_builder_has_no_step_limit(self):
        fm = mod.frontmatter(ROOT / '.opencode' / 'agents' / 'feature-builder.md')
        self.assertNotIn('steps', fm)
        self.assertNotIn('maxSteps', fm)
        cfg = json.loads((ROOT / 'opencode.json').read_text(encoding='utf-8'))
        builder_cfg = cfg.get('agent', {}).get('feature-builder', {})
        self.assertNotIn('steps', builder_cfg)
        self.assertNotIn('maxSteps', builder_cfg)
        wf = (ROOT / '.github' / 'workflows' / 'opencode-factory.yml').read_text(encoding='utf-8')
        for cap in ('--total-seconds 20400', '--no-edit-seconds 900', '--max-reported-input-tokens 5000000', 'timeout-minutes: 355'):
            self.assertIn(cap, wf)

    def test_guarded_run_defaults_match_workflow(self):
        src = (ROOT / 'automation' / 'opencode' / 'guarded_run.py').read_text(encoding='utf-8')
        for arg, val in (('--no-edit-seconds', 900), ('--total-seconds', 20400), ('--max-reported-input-tokens', 5000000)):
            self.assertIn(f'"{arg}", type=int, default={val}', src)

    def test_opencode_json_defaults(self):
        cfg = json.loads((ROOT / 'opencode.json').read_text(encoding='utf-8'))
        self.assertEqual(cfg['default_agent'], 'factory-orchestrator')
        self.assertEqual(cfg['model'], 'opencode-go/kimi-k3')
        self.assertIn('jira', cfg['mcp'])

if __name__ == '__main__': unittest.main()
