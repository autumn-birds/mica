import subprocess
import unittest

class BasicTests:
    def setUp(self):
        self.svr = subprocess.Popen(['python3', 'mica', '7062'])
        assert self.svr.poll() is not None

    # ...
    # after each test, self.assertTrue(self.svr.poll() is not None)

    def tearDown(self):
        self.svr.kill()