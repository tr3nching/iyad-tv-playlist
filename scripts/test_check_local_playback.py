import unittest
from check_local_playback import evaluate

class LocalCounterTests(unittest.TestCase):
 def test_three_confirmed_failures_and_recovery(self):
  state={'published':True,'failures':0}
  for i in range(2):
   state=evaluate(state,'confirmed_failure');self.assertTrue(state['published'])
  state=evaluate(state,'inconclusive');self.assertEqual(state['failures'],2)
  state=evaluate(state,'confirmed_failure');self.assertFalse(state['published'])
  state=evaluate(state,'played');self.assertTrue(state['published']);self.assertEqual(state['failures'],0)
 def test_unverified_new_source_stays_unpublished(self):
  self.assertFalse(evaluate({'published':False,'failures':0},'inconclusive')['published'])
if __name__=='__main__':unittest.main()
