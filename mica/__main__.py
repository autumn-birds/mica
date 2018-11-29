#!/usr/bin/python3

import sys, getopt
import sqlite3
import socket, selectors

import net_helpers
import core
import commands

import logging
logging.basicConfig(level=logging.INFO)


# Options parsing, other initialization, and higher-level server logic.
# TODO: --help
(opts, args) = getopt.getopt(sys.argv[1:], '', ['host=', 'port=', 'initDB'])

_opts = {}
for pair in opts:
    # Making sure to strip out the '--'.
    _opts[pair[0][2:]] = pair[1]
opts = _opts
del _opts

# TODO: Implement manual switch for creating database to file, + loading arbitrary file on start
db = sqlite3.connect(":memory:")

mica = core.Mica(db)
mica.setup_db()
commands.implement(mica)

# The horrible, ugly world of networking code.
# TODO: SSL support?
def main():
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.setblocking(0)

    (host, port) = (opts.get("host", "localhost"), int(opts.get("port", "7072")))
    logging.info("Listening on %s:%d" % (host, port))

    server.bind((host, port))
    server.listen(100)

    sel = selectors.DefaultSelector()
    sel.register(server, selectors.EVENT_READ)

    # A dict of socket objects, pointing to the LineBufferingSocketContainer (see liner_helpers.py) that deals with that particular socket.
    wrappedSockets = {}

    while True:
        events = sel.select()
        for key, mask in events:
            s = key.fileobj

            if s == server:
                (connection, address) = s.accept()
                logging.info("Got socket " + repr(connection) + "with address" + repr(address))
                wrappedSockets[connection] = net_helpers.LineBufferingSocketContainer(connection)
                mica.on_connection(wrappedSockets[connection])
                sel.register(connection, selectors.EVENT_READ)
            else:
                assert s in wrappedSockets
                link = wrappedSockets[s]
                assert link.socket == s
                (lines, eof) = link.read()

                for line in lines:
                    mica.on_text(link, line.replace("\r\n", ""))

                if eof:
                    sel.unregister(s)
                    mica.on_disconnection(link)
                    link.handle_disconnect()
                    del wrappedSockets[s]

main()