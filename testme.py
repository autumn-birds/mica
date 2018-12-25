import subprocess
import telnetlib
import time
import traceback
import os
import sys

TEST_PORT = 1234

# (https://stackoverflow.com/questions/287871/print-in-terminal-with-colors)
class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def run_test(filename):
    svr = subprocess.Popen(['python3', 'mica', '--port', str(TEST_PORT), '--print-io', ':memory:'])
    time.sleep(0.2)
    assert svr.poll() is None

    t = telnetlib.Telnet()
    t.open("localhost", TEST_PORT)

    try:
        with open(filename, 'r') as file:
            for line in file.readlines():
                line = line.strip()
                if line[0] == '>':
                    t.write(line[1:].encode("utf-8") + b'\n')
                else:
                    line = line.encode("utf-8")
                    results = t.read_until(line, 1.0)
                    if line not in results:
                        print("test> expected %s, got %s" % (repr(line), repr(results)))
                        t.close()
                        svr.kill()
                        time.sleep(0.1)
                        return (False, "%s != %s" % (repr(line), repr(results)))
    except:
        print("test> unhandled exception...")
        t.close()
        svr.kill()
        print(traceback.format_exc(chain=True))
        return (False, "Exception in test framework")

    t.close()
    svr.kill()
    time.sleep(0.1)
    return (True, None)

def files(dir):
    # https://stackoverflow.com/questions/3207219/how-do-i-list-all-files-of-a-directory
    return [f for f in os.listdir(dir) if os.path.isfile(os.path.join(dir, f))]

results = {}

if len(sys.argv) > 1:
    to_run = sys.argv[1:]
else:
    to_run = [os.path.join("tests", x) for x in files("tests")]

for file in to_run:
    if os.path.exists(file) and os.path.isfile(file):
        results[file] = run_test(file)
    else:
        print("File not found, or is a directory: %s" % file)
        results[file] = (False, "file not found")
    print()

print("FINAL RESULTS:\n--------------")
for (filename, r) in results.items():
    (status, msg) = r
    if status:
        print(("%s> " + bcolors.OKGREEN + "OK" + bcolors.ENDC) % filename)
    else:
        print(("%s> " + bcolors.FAIL + "NOT OK" + bcolors.ENDC + " (%s)") % (filename, msg))
