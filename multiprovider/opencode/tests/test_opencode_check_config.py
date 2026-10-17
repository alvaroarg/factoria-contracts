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
        self.assertEqual(mod.AGENTS['feature-builder'], ('subagent', 'opencode-go/deepseek-v4-pro', 80))
        self.assertEqual(mod.AGENTS['pr-reviewer'], ('subagent', 'opencode-go/kimi-k3', 15))

    def test_agent_files_match_expectations(self):
        for name, (mode, model, steps) in mod.AGENTS.items():
            fm = mod.frontmatter(ROOT / '.opencode' / 'agents' / (name + '.md'))
            self.assertEqual((fm.get('mode'), fm.get('model'), fm.get('steps')), (mode, model, str(steps)), name)

    def test_opencode_json_defaults(self):
        cfg = json.loads((ROOT / 'opencode.json').read_text(encoding='utf-8'))
        self.assertEqual(cfg['default_agent'], 'factory-orchestrator')
        self.assertEqual(cfg['model'], 'opencode-go/kimi-k3')
        self.assertIn('jira', cfg['mcp'])

if __name__ == '__main__': unittest.main()
