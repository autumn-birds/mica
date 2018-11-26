#!/usr/bin/python3

import sys, getopt
import sqlite3
import socket
import selectors

import net_helpers

db = None

def setup_db(database):
    dbSetup = [
      "CREATE TABLE things (id INTEGER PRIMARY KEY, owner_id INTEGER, location_id INTEGER, name TEXT, desc TEXT)",
      "CREATE TABLE accounts (id INTEGER PRIMARY KEY, character_id INTEGER, password TEXT)",
      "CREATE TABLE links (id INTEGER PRIMARY KEY, name TEXT, from_id INTEGER, to_id INTEGER)",
      
      "INSERT INTO things (id, owner_id, location_id, name, desc) VALUES (1, 1, 2, \"One\", \"A nameless, faceless, ageless, gender-neutral, culturally ambiguous embodiment of... it's not clear, really.  Ultimate power over reality for one thing, but they don't seem to be trying to show this off.\")",
      "INSERT INTO things (id, owner_id, location_id, name, desc) VALUES (2, 1, 2, \"Nexus\", \"It is a place: that is about all that can be ascertained.\")",
      "INSERT INTO accounts (character_id, password) VALUES (1, \"potrzebie\")"
    ]

    try:
        Cx_setup = database.cursor()
        for cmd in dbSetup:
            Cx_setup.execute(cmd)
        database.commit()
        Cx_setup = None
    except:
        print("ERROR SETTING UP INITIAL DATABASE:\n\n")
        raise


# Convenience functions for accessing the database.
def calldb(query, opts=None):
    Cx = db.cursor()
    if opts is not None:
        Cx.execute(query, opts)
    else:
        Cx.execute(query)
    return Cx

def from_db(query, opts=None):
    """Return the results from fetchall() of a database query; just for convenience."""
    return calldb(query, opts).fetchall()

def describe_thing(id, get_in=True):
    """Call up the database and return the name and desc of a Thing along with its contents (any Things with a location_id of the requested Thing.)
    The form is a tuple: name, descs, contents (or if get_in=False, name, desc.)
    This function returns None if there is no thing with id `id'."""
    thing = from_db("SELECT name, desc FROM things WHERE id=?", (id,))
    assert len(thing) <= 1
    if len(thing) == 0:
        return None
    
    if not get_in:
        return (thing[0][0], thing[0][1])

    contents = []
    for content in from_db("SELECT id FROM things WHERE location_id=?", (id,)):
        if content[0] != id:
            contents.append(describe_thing(content[0], False))

    return (thing[0][0], thing[0][1], contents)


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
setup_db(db)

# Commands that can be run.
commands = {}
# The abstract notion of indexing a network link to a state of being either not logged in at all or connected to some object in the database.
# The client_states dictionary indexes links to a number that is either the database id of the _thing_ (e.g., character) the link is connected to, or -1 in the case that the link isn't connected to anything yet but has appeared before.
client_states = {}
# Network code provides a few guarantees about the link objects it sends to on_connection() and on_text():
# 1. The objects will always be unique among all links and will never change over the lifetime of the link, making them usable as an index.
# 2. They will support a write() method which takes a chunk of UTF-8 encoded text in a single argument and writes it onto the link; this method will do any buffering, etc., that is required, only giving up if the link itself fails.
# 3. They will support a kill() method that forcefully disconnects the client on the other end of the link.

def line(text):
    """Encapsulates the process of adding a proper newline to the end of lines, just in case it ever needs to be changed."""
    return text + "\r\n"

def on_connection(new_link):
    client_states[new_link] = -1
    #new_link.write("Welcome.  Type `connect <name> <password>' to connect.\n")
    print("Got link", new_link)

def on_text(link, text):
    assert link in client_states
    # TODO
    link.write(line(text))

def on_disconnection(old_link):
    assert old_link in client_states
    del client_states[old_link]
    print("Losing link", old_link)


# The horrible, ugly world of networking code.
# TODO: SSL support?
def main():
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.setblocking(0)
    
    (host, port) = (opts.get("host", "localhost"), int(opts.get("port", "7072")))
    print("Listening on %s:%d" % (host, port))

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
                print("Got socket", connection, "with address", address)
                wrappedSockets[connection] = net_helpers.LineBufferingSocketContainer(connection)
                on_connection(wrappedSockets[connection])
                sel.register(connection, selectors.EVENT_READ)
            else:
                assert s in wrappedSockets
                link = wrappedSockets[s]
                assert link.socket == s
                (lines, eof) = link.read()

                for line in lines:
                    on_text(link, line.replace("\r\n", ""))

                if eof:
                    on_disconnection(link)
                    sel.unregister(link)
                    link.handle_disconnect()
                    del wrappedSockets[wrappedSockets.indexOf(link)]

main()