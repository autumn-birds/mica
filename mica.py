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
    'thingOverflow': "`%s' is ambiguous -- I can't tell which you mean.",
    'cmdSyntax': "That command needs to be written similar to `%s'.",

    'youAreNowhere': "You... erm... don't seem to actually be in a location that exists.  This is, um, honestly, really embarrassing and we're not sure what to do about it.",
    'beforeListingThingsInRoom': "You can see:",
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
class TooManyResultsException(Exception):
    pass

class NotEnoughResultsException(Exception):
    pass

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

# TODO: Go through and find all the calls where it makes sense to use this instead of from_db() and fix them.
def one_from_db(query, opts=None):
    """Like from_db, but guarantees there is exactly one result returned--no more, no less.
    Will raise TooManyResultsException and NotEnoughResultsException as appropriate.
    Returns the singular result on its own and not wrapped in a containing array, so watch your semantics."""
    results = from_db(query, opts)
    if len(results) < 1:
        raise NotEnoughResultsException()
    elif len(results) > 1:
        raise TooManyResultsException()
    else:
        return results[0]

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

def where_is_thing(id):
    """Return the id of the place where the Thing with id `id' is, or None if the place doesn't exist."""
    results = from_db("SELECT id FROM things WHERE id IN (SELECT location_id FROM things WHERE id = ?)", (id,))
    assert len(results) <= 1
    if len(results) < 1:
        return None
    return results[0][0]

def resolve_many_things_for(id, thing):
    """Return either the id of the Thing that the text string `thing' would refer to from the perspective of another Thing with id `id', None if it can't find one, or -1 if there are too many possible matches.
    This basically includes: (a) referring to Things that are in the same location as the perspective-Thing by name, in whole or in unique part; (b) referring to a single Thing globally by its id; (c) referring to 'me' in which case the id is just returned unchanged.
    In the latter case, this function does make sure the Thing referred to exists when it is called.
    We follow tradition in our syntax and use a `#' character followed by numbers to express the global id in our syntax."""
    thing.strip()

    if thing == 'me':
        # TODO: Maybe we should check this too.  Just to be extra pedantic.
        # I don't know if maybe we shouldn't just have a check_id_exists() function or something.
        return [id]

    if thing[0] == '#':
        try:
            dbref = int(thing[1:])
        except ValueError():
            return None
        target = one_from_db("SELECT id FROM things WHERE id=?", (dbref,))
        return [int(target[0])]

    whereami = where_is_thing(id)
    if whereami is not None:
        candidates = from_db("SELECT name, id FROM things WHERE location_id = ?", (whereami,))
        candidates += from_db("SELECT name, id FROM things WHERE location_id = ?", (id,))  # Consider items you're carrying.
        matches = [x[1] for x in candidates if thing in x[0]]
        return matches

def resolve_one_thing_for(id, thing):
    """Like resolve_many_things_for, but either returns a single id or raises TooManyResultsException or NotEnoughResultsException as appropriate."""
    results = resolve_many_things_for(id, thing)
    if len(results) > 1:
        raise TooManyResultsException()
    elif len(results) < 1:
        raise NotEnoughResultsException()
    else:
        return results[0]


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
# The client_states dictionary indexes links to a dictionary with at least one property: 'character', a number that is either the database id of the _thing_ (e.g., character) the link is connected to, or -1 in the case that the link isn't connected to anything yet but has appeared before.
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
            cmd[1](link, text[len(cmd[0])+1:])
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


# This is a decorator builder. Note that decorators are @ immediately followed by an _expression_: If the expression is just a name, it evaluates to the function named that, but it can also be a function call, in which case python calls that function when evaluating the expression instead. The _result of evaluation_ should be a function, which is called on the function being decorated and returns a new function that effectively replaces it. This is all kind of confusing.
def command(name):
    # We can capture `name' in a closure.
    def add_this_command(fn):
        commands.append((name, fn))
        return fn # We just want the side effects.
    return add_this_command

def resolve_or_oops(link, id, thing):
    try:
        result = resolve_one_thing_for(id, thing)
    except NotEnoughResultsException:
        link.write(line(texts['thing404'] % thing))
        return None
    except TooManyResultsException:
        link.write(line(texts['thingOverflow']))
        return None
    return result

# Command definitions.
# Watch out, order may be important -- if one command's full name is the beginning of another command's name, make sure the longer command gets declared first.
@command("look")
def do_look(link, text):
    me = client_states[link]['character']
    assert me != -1

    text.strip()
    if text != '':
        tgt = resolve_or_oops(link, me, text)
        if tgt is None:
            return
        print("Got a targeted tgt: %s" % repr(tgt))
    else:
        tgt = where_is_thing(me)
        if tgt is None:
            link.write(line(texts['youAreNowhere']))
            return

    here = describe_thing(tgt)
    if here is None:
        # The functions to find out the thing from the database didn't work.
        link.write(line(texts['thing404'] % '(this is a big problem)'))

    link.write(line('%s [%d]' % (here[0], tgt)))
    link.write(here[1])
    link.write(line(''))

    if len(here[2]) > 0:
        contents = texts['beforeListingThingsInRoom']
        # There must be a shorter way to do this?
        listed_one = False
        for thing in here[2]:
            if listed_one:
                contents += '; %s' % thing[0]
            else:
                contents += ' %s' % thing[0]
                listed_one = True
        link.write(line(contents))


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