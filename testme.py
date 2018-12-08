import subprocess
import telnetlib
import time
import traceback
import os

TEST_PORT = 1234

def run_test(filename):
    svr = subprocess.Popen(['python3', 'mica', '--port', str(TEST_PORT), '--print-io'])
    time.sleep(0.1)
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
                        return (False, "%s != %s" % (repr(line), repr(results)))
    except:
        print("test> unhandled exception...")
        t.close()
        svr.kill()
        print(traceback.format_exc(chain=True))
        return (False, "Exception in test framework")

    t.close()
    svr.kill()
    return (True, None)

def files(dir):
    # https://stackoverflow.com/questions/3207219/how-do-i-list-all-files-of-a-directory
    return [f for f in os.listdir(dir) if os.path.isfile(os.path.join(dir, f))]

results = {}

for file in files("tests"):
    results[file] = run_test(os.path.join("tests", file))
    print()

print("FINAL RESULTS:\n--------------")
for (filename, r) in results.items():
    (status, msg) = r
    if status:
        print("%s> OK" % filename)
    else:
        print("%s> NOT OK (%s)" % (filename, msg))
