import importlib.util
from pathlib import Path
import unittest

P = Path(__file__).resolve().parents[1] / 'automation' / 'opencode' / 'guarded_run.py'
spec = importlib.util.spec_from_file_location('guarded_run', P)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class GuardTests(unittest.TestCase):
    def test_json_event_token_counts(self):
        m = {'event_types':{}, 'tools':{}, 'task_agents':[], 'step_events':0, 'reported_tokens':{'input':0,'output':0,'reasoning':0},'quota_error_observed':False}
        mod.event_detail('{"type":"step_finish","part":{"tokens":{"input":43,"output":4}}}',m)
        self.assertEqual(m['reported_tokens']['input'],43)
        self.assertEqual(m['step_events'],1)

    def test_no_crash_on_string_state(self):
        m = {'event_types':{}, 'tools':{}, 'task_agents':[], 'step_events':0, 'reported_tokens':{'input':0,'output':0,'reasoning':0},'quota_error_observed':False}
        mod.event_detail('{"type":"tool_use","part":{"tool":"task","state":"running"}}',m)
        self.assertEqual(m['tools']['task'],1)

    def test_json_429_detection(self):
        m = {'event_types':{}, 'tools':{}, 'task_agents':[], 'step_events':0, 'reported_tokens':{'input':0,'output':0,'reasoning':0},'quota_error_observed':False}
        mod.event_detail('{"type":"error","error":{"message":"HTTP 429 rate limit"}}',m)
        self.assertTrue(m['quota_error_observed'])

    def test_429_detection(self):
        m = {'event_types':{}, 'tools':{}, 'task_agents':[], 'step_events':0, 'reported_tokens':{'input':0,'output':0,'reasoning':0},'quota_error_observed':False}
        mod.event_detail('HTTP 429 rate limit exceeded',m)
        self.assertTrue(m['quota_error_observed'])

if __name__=='__main__': unittest.main()
