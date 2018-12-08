import subprocess
import unittest
import telnetlib
import time

TEST_PORT = 1234

class TestServer(unittest.TestCase):
    def setUp(self):
        self.svr = subprocess.Popen(['python3', 'mica', '--port', str(TEST_PORT), '--print-io'])
        # We apparently have to wait a minute for the server to come up.
        # Otherwise, there's an error, and it also just hangs around for a bit because I guess the error stops .kill() from ever happening.
        # It might be ideal to start the server fewer times, but doing it this way does make the tests more like a pure function.
        time.sleep(0.1)
        assert self.svr.poll() is None

        self.t = telnetlib.Telnet()
        self.t.open("localhost", TEST_PORT)

    def test_basic(self):
        # Depend on a [1] object existing, and producing the number 1 somewhere in the output when we write `look #1'.
        self.t.write(b'connect One potrzebie\n')
        self.t.write(b'look me\n')

        results = self.t.expect([b'One \[1\]'], 1.0)
        self.assertNotEqual(results[1], None)

        # This should be done after most tests, or the inverse, to make sure the server didn't die (or did if that was expected.)
        self.assertTrue(self.svr.poll() is None)

    def tearDown(self):
        self.t.close()
        del self.t
        self.svr.kill()

if __name__ == '__main__':
    unittest.main()