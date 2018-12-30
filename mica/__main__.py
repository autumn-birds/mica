#!/usr/bin/python3

import sys, getopt
import sqlite3
import socket, selectors

import net_helpers
import core
import commands

import logging
# Change to INFO or DEBUG for more messages
logging.basicConfig(level=logging.WARNING)

DEFAULT_HOST="localhost"
DEFAULT_PORT="7072"

# Options parsing, other initialization, and higher-level server logic.

options_accepted = {
    'host=': 'Specify address to listen on (e.g., localhost, or 0.0.0.0 for everything; default: %s)' % DEFAULT_HOST,
    'port=': 'Specify port to listen on (default: %s)' % DEFAULT_PORT,
    'print-io': "Print input/output.",
    'hide-tracebacks': "Don't show actual tracebacks to users on the MUCK when an error occurs.",
    'initDB': "Set up first-time records in the database (do not run on an existing database.)",
    'help': "This message.",
}

def print_help(stat=0):
    print("Usage: python3 mica [options ...] <database>")
    print("   <database> may be a filename or anything sqlite3 accepts, including :memory:.")
    print("   <database> of :memory: implies --initDB.")
    print("")
    print("Options:")
    for k in sorted(options_accepted.keys()):
        if k[-1] == '=':
            print("   --%s<value>: %s" % (k, options_accepted[k]))
        else:
            print("   --%s: %s" % (k, options_accepted[k]))

    exit(stat)

(opts, args) = getopt.getopt(sys.argv[1:], '', options_accepted.keys())

_opts = {}
for pair in opts:
    # Making sure to strip out the '--'.
    _opts[pair[0][2:]] = pair[1]
opts = _opts
del _opts

if 'help' in opts:
    print_help()

if len(args) == 1:
    targetDB = args[0]
else:
    print_help(1)

db = sqlite3.connect(args[0].strip())
mica = core.Mica(db)
if args[0].strip() == ':memory:' or 'initDB' in opts:
    # TODO: Check and automatically initialize if it's a new file ....
    print("Setting up database...")
    mica.setup_db()
    print("Done.")

commands.implement(mica)
if "hide-tracebacks" not in opts:
    mica.show_tracebacks = True

# The horrible, ugly world of networking code.
# TODO: SSL support?
def main():
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.setblocking(0)

    (host, port) = (opts.get("host", DEFAULT_HOST), int(opts.get("port", DEFAULT_PORT)))
    logging.info("Listening on %s:%d" % (host, port))

    server.bind((host, port))
    server.listen(100)

    sel = selectors.DefaultSelector()
    sel.register(server, selectors.EVENT_READ)

    # A dict of socket objects, pointing to the LineBufferingSocketContainer (see net_helpers.py) that deals with that particular socket.
    wrappedSockets = {}

    # We can be instructed to print everything that gets received or sent, to make it easier to see what's going on when running tests or debugging.
    DO_PRINT_IO = 'print-io' in opts

    while True:
        events = sel.select()
        for key, mask in events:
            s = key.fileobj

            if s == server:
                (connection, address) = s.accept()
                logging.info("Got socket " + repr(connection) + "with address" + repr(address))
                wrappedSockets[connection] = net_helpers.LineBufferingSocketContainer(connection)
                if DO_PRINT_IO:
                    wrappedSockets[connection].on_write = lambda x: print("server> %s" % x.rstrip())
                mica.on_connection(wrappedSockets[connection])
                sel.register(connection, selectors.EVENT_READ)
            else:
                assert s in wrappedSockets
                link = wrappedSockets[s]
                assert link.socket == s
                (lines, eof) = link.read()

                for line in lines:
                    text = line.replace("\r\n", "").replace("\n", "")
                    if DO_PRINT_IO:
                        print("client> %s" % text)
                    mica.on_text(link, text)

                if eof:
                    sel.unregister(s)
                    mica.on_disconnection(link)
                    link.handle_disconnect()
                    del wrappedSockets[s]

main()
