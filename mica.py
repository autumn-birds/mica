#!/usr/bin/python3

import sys, getopt
import sqlite3
import socket, selectors
import net_helpers

import logging
logging.basicConfig(level=logging.INFO)

db = None

# Default messages that would otherwise be hard-coded about in the code.
texts = {
    'welcome': "Welcome.  Type `connect <name> <password>' to connect.",
    'badLogin': "I'm sorry, but those credentials were not right.",
    'cmd404': "I don't understand what you mean.",
    'thing404': "I can't find any such thing as `%s'.",
    'cmdSyntax': "That command needs to be written similar to `%s'.",
}


def setup_db(database):
    dbSetup = [
      "CREATE TABLE things (id INTEGER PRIMARY KEY, owner_id INTEGER, location_id INTEGER, name TEXT, desc TEXT)",
      "CREATE TABLE accounts (id INTEGER PRIMARY KEY, character_id INTEGER, password TEXT)",
      "CREATE TABLE links (id INTEGER PRIMARY KEY, name TEXT, from_id INTEGER, to_id INTEGER)",
      
      "INSERT INTO things (id, owner_id, location_id, name, desc) VALUES (1, 1, 2, \"One\", \"A nameless, faceless, ageless, gender-neutral, culturally ambiguous embodiment of... well, it's not clear, really.\")",
      "INSERT INTO things (id, owner_id, location_id, name, desc) VALUES (2, 1, 2, \"Nexus\", \"It is a place: that is about all you can be sure of.\")",
      # TODO: Password hashing
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

def find_account(account):
    """Return a tuple of (password, objectID) for the given account name, if it exists."""
    candidates = from_db("SELECT id FROM things WHERE name=? AND id IN (SELECT character_id FROM accounts)", (account,))
    if len(candidates) != 1:
        return None

    acct = from_db("SELECT password, character_id FROM accounts WHERE id=?", (candidates[0][0],))
    if len(acct) == 0:
        return None
    assert(len(acct) == 1)
    return acct[0]

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

commands = []

def line(text):
    """Encapsulates the process of adding a proper newline to the end of lines, just in case it ever needs to be changed."""
    return text + "\r\n"

def on_connection(new_link):
    client_states[new_link] = {'character': -1}
    new_link.write(line(texts['welcome']))
    logging.info("Got link " + repr(new_link))

def on_text(link, text):
    assert link in client_states
    s = client_states[link]['character']

    if s == -1:
        cmd = "connect"
        print("On connect, text=%s and clipped, %s" % (text, text[:len(cmd)]))
        if text[:len(cmd)] == cmd:
            try_login(link, text[len(cmd)+1:])
        else:
            link.write(line(texts['cmd404']))
        return

    for cmd in commands:
        if cmd[0] == text[:len(cmd[0])]:
            cmd[1](text[len(cmd[0])+1:], link)
            return

    link.write(line(texts['cmd404']))

def on_disconnection(old_link):
    assert old_link in client_states
    del client_states[old_link]
    logging.info("Losing link " + repr(old_link))

def try_login(link, args):
    # TODO: allow double-quote parsing? Maybe?
    print("try_login: got %s" % args)
    args = args.split(' ')
    if len(args) != 2:
        link.write(line(texts['cmdSyntax'] % "connect <username> <password>"))
        return
    acct = find_account(args[0])

    # Again, TODO: Password hashing
    if acct[0] == args[1]:
        assert describe_thing(acct[1]) is not None    # TODO: Is this really necessary? It might be a significant performance drop (more database calls, even more if the object has a lot of objects in it), which could matter since malicious users can try to sign in very frequently, and they don't need to authenticate themselves first (duh.)
        client_states[link]['character'] = acct[1]
        return True
    else:
        link.write(line(texts['badLogin']))
        return False


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
                    sel.unregister(s)
                    on_disconnection(link)
                    link.handle_disconnect()
                    del wrappedSockets[s]

main()