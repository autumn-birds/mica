#!/usr/bin/python3

import sys, getopt
import sqlite3
import socket, selectors

import net_helpers

import logging
logging.basicConfig(level=logging.INFO)

# Default messages that would otherwise be hard-coded about in the code.
texts = {
    'welcome': "Welcome.  Type `connect <name> <password>' to connect.",

    'badLogin': "I'm sorry, but those credentials were not right.",
    'cmd404': "I don't understand what you mean.",
    'thing404': "I can't find any such thing as `%s'.",
    'thingOverflow': "`%s' is ambiguous -- I can't tell which thing you mean.",
    'cmdSyntax': "That command needs to be written similar to `%s'.",

    'youAreNowhere': "You... erm... don't seem to actually be in a location that exists.  This is, um, honestly, really embarrassing and we're not sure what to do about it.",
    'beforeListingContents': "You can see: ",
}

# These are mainly thrown by mica's database accessors.
class TooManyResultsException(Exception):
    pass

class NotEnoughResultsException(Exception):
    pass


class Mica:
    def __init__(self, db=None):
        """Setup the class.
        `db` should be a SQLite3 database object created with the default `sqlite3` module; if `db` is None, a database will be created in-memory, and there will be no data persistence.
        If `db` is not None, the caller is responsible for determining whether setup_db() needs to be called (e.g., whether it's a new database or an old one.)"""
        self.db = db
        if self.db is None:
            self.setup_db()

        # This list stores all the names of commands that could be run, associated with their functions.
        # It is a list and not a dict because it might need to be ordered, although if that is the case the ordering should probably be enforced internally rather than depending on callers to register their commands in a problem-free order.
        # The elements in the list are (command_name:str, command:function) tuples.
        self._commands = []

        # The client_states variable is indexed by 'link' objects, provided by network code, and it keeps track of state for each connection, such as what object it's logged into for a character or whether it's logged in at all.
        # Since in the future there might be more state that's needed, e.g. to implement the required functionality for editor- or puppet-driving-type systems, or since some commands might want to store state, the values in this dictionary are also dictionaries; the character object the command is connected to is stored under the 'character' key in each dictionary. 
        # TODO: Currently the 'character' key is set to -1 to indicate a connection that has not logged in yet. But really it should be None, since I think it might be theoretically possible for negative database indices to exist somehow.
        self.client_states = {}


    #
    # Database functions (accessing and updating objects, etc.)
    def setup_db():
        """Initialize the database with a minimal default template.
        The result of calling this function when the database already has data in it is undefined."""
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
            Cx_setup = self.db.cursor()
            for cmd in dbSetup:
                Cx_setup.execute(cmd)
            self.db.commit()
            Cx_setup = None
        except:
            print("ERROR SETTING UP INITIAL DATABASE:\n\n")
            raise

    def _calldb(query, opts=None):
        """Execute a database query `query` with the optional tuple of data `opts` and return the cursor that was used to execute the query, on which, for example, fetchall() or similar methods can be called.
        External functionality should not use this, as the database structure is not meant to be an API."""
        Cx = self.db.cursor()
        if opts is not None:
            Cx.execute(query, opts)
        else:
            Cx.execute(query)
        return Cx

    def _from_db(query, opts=None):
        """Return the results from fetchall() of a database query; just for convenience."""
        return self._calldb(query, opts).fetchall()

    def _one_from_db(query, opts=None):
        """Like from_db, but guarantees there is exactly one result returned--no more, no less.
        Will raise TooManyResultsException and NotEnoughResultsException as appropriate.
        Returns the singular result on its own and not wrapped in a containing array, so watch your semantics."""
        results = self._from_db(query, opts)
        if len(results) < 1:
            raise NotEnoughResultsException()
        elif len(results) > 1:
            raise TooManyResultsException()
        else:
            print("one_from_db: returning %s" % repr(results[0]))
            return results[0]

    def find_account(account):
        """Return a tuple of (password, objectID) for the given account name, if it exists and is not ambiguous."""
        assert type(account) is str
        try:
            thingid = self._one_from_db("SELECT id FROM things WHERE name=? AND id IN (SELECT character_id FROM accounts)", (account,))
        except (NotEnoughResultsException, TooManyResultsException):
            return None

        try:
            acct = self._one_from_db("SELECT password, character_id FROM accounts WHERE id=?", (thingid[0],))
        except NotEnoughResultsException:
            return None

        return acct

    def get_thing(id):
        """Call up the database and return the name and desc of a Thing (in a tuple), or None if there is none with that id."""
        assert type(id) is int
        try:
            thing = self._one_from_db("SELECT name, desc FROM things WHERE id=?", (id,))
        except NotEnoughResultsException:
            return None

        return thing

    def get_contents(id):
        """Return a list of ids of Things whose location is set to the `id' given; or more prosaically, a list of things that are in the Thing with id `id'.
        This function doesn't check that the id given actually exists, but the ids returned should exist."""
        assert type(id) is int
        contents = []
        for content in self._from_db("SELECT id FROM things WHERE location_id=?", (id,)):
            if content[0] != id:
                assert type(content[0] is int)
                contents.append(content[0])
        return contents

    def get_location(id):
        """Return the id of the place where the Thing with id `id' is, or None if the place doesn't exist."""
        try:
            results = self._one_from_db("SELECT id FROM things WHERE id IN (SELECT location_id FROM things WHERE id = ?)", (id,))
        except NotEnoughResultsException:
            return None
        print("get_location: %d is in %d" % (id, results[0]))
        return results[0]

    def resolve_many_things_for(id, thing):
        """Returns a list of all the Thing ids that the text string `thing' could possibly match, using the syntax used by commands & players to refer to objects, from the point-of-view of the Thing with id `id'; that is, it will include objects contained by that Thing as well as objects in the same location as it."""
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

            try:
                target = self._one_from_db("SELECT id FROM things WHERE id=?", (dbref,))
                return [int(target[0])]
            except NotEnoughResultsException:
                return None

        whereami = self.get_location(id)
        if whereami is not None:
            # Consider items you're carrying.
            candidates = [(x, self.get_thing(x)[0]) for x in self.get_contents(whereami) + self.get_contents(id)]
            matches = [x[0] for x in candidates if thing in x[1]]
            return matches

    def resolve_one_thing_for(id, thing):
        """Like resolve_many_things_for, but either returns a single id or raises TooManyResultsException or NotEnoughResultsException as appropriate."""
        results = self.resolve_many_things_for(id, thing)
        if len(results) > 1:
            raise TooManyResultsException()
        elif len(results) < 1:
            raise NotEnoughResultsException()
        else:
            return results[0]

    def thing_displayname(id, name):
        """Returns a string showing a Thing's name with its database number appended, as appropriate for output to users; this is purely a formatting function and no checking is done."""
        return "%s [%d]" % (id, name)


    #
    # Logic for connections and how users interact with the system, including logging in and command processing.
    # There is no actual network code here; instead, the networking code in the main loop calls these functions with lines of text or on relevant events, passing in objects we understand as 'links'.
    # The implementation details are unspecified, but the link objects must conform to a small API:
    # 1. The objects will always be unique among all links and will never change over the lifetime of the link, making them usable as an index (e.g. for state associated with the connection.)
    # 2. They will support a write() method which takes a chunk of UTF-8 encoded text in a single argument and writes it onto the link; this method will not need to be called multiple times to safely assume the whole text has been sent, will buffer if necessary, and should not block.
    # 3. They will support a kill() method that forcefully disconnects the client on the other end of the link. The network code should [I hope] be able to take care of calling on_disconnection() itself in that case.
    def line(text):
        """Encapsulates the process of adding a proper newline to the end of lines, just in case it ever needs to be changed."""
        return text + "\r\n"

    def on_connection(new_link):
        """Called by network code when a new connection is received from a client."""
        client_states[new_link] = {'character': -1}
        new_link.write(line(texts['welcome']))
        logging.info("Got link " + repr(new_link))

    def on_text(link, text):
        """Called by network code when some text is received from a previously connected client.
        The result of network code calling this function with a link object that has not been previously passed to on_connection is undefined."""
        assert link in client_states
        s = client_states[link]['character']

        if s == -1:
            cmd = "connect"
            if text[:len(cmd)] == cmd:
                self._try_login(link, text[len(cmd)+1:])
            else:
                link.write(line(texts['cmd404']))
            return

        for cmd in commands:
            if cmd[0] == text[:len(cmd[0])]:
                cmd[1](link, text[len(cmd[0])+1:])
                return

        link.write(line(texts['cmd404']))

    def on_disconnection(old_link):
        """Called by network code when a connection dies.
        The result of re-using an old link object again once it has been passed to this function is undefined."""
        assert old_link in client_states
        del client_states[old_link]
        logging.info("Losing link " + repr(old_link))

    def _try_login(link, args):
        """Called internally to process logins."""
        # TODO: allow double-quote parsing? Maybe?
        args = args.split(' ')
        if len(args) != 2:
            link.write(line(texts['cmdSyntax'] % "connect <username> <password>"))
            return
        acct = self.find_account(args[0])

        # Again, TODO: Password hashing
        if acct[0] == args[1]:
            assert self.get_thing(acct[1]) is not None    # TODO: Is this really necessary? It might be a significant performance drop (more database calls, even more if the object has a lot of objects in it), which could matter since malicious users can try to sign in very frequently, and they don't need to authenticate themselves first (duh.)
            client_states[link]['character'] = acct[1]
            return True
        else:
            link.write(line(texts['badLogin']))
            return False


    #
    # Interface for adding commands to the system.
    # (Note that decorators are @ immediately followed by an _expression_: If the expression is just a name, it evaluates to the function named that, but it can also be a function call, in which case python calls that function when evaluating the expression instead. The _result of evaluation_ should be a function, which is called on the function being decorated and returns a new function that effectively replaces it. So this returns a function that is called on the actual function being decorated.)
    def command(name):
        """Decorator function. Use like @mica_instance.command("look") on the function implementing the command."""
        # We can capture `name' in a closure.
        def add_this_command(fn):
            commands.append((name, fn))
            return fn # We just want the side effects.
        return add_this_command

    def pov_get_thing_by_name(link, thing):
        """Resolve what Thing a user connected to `link' would be referring to.
        If no object can be found or the result is ambiguous, this function throws a CommandProcessingError; command implementations should only catch this error in order to do any necessary cleanup or revert their actions, and it is strongly encouraged that all resolution be done before doing anything that would need to be reverted in case the objects being resolved did not exist, if possible."""
        assert link in self.client_states
        pov = self.client_states[link]['character']

        try:
            result = self.resolve_one_thing_for(pov, thing)
        except NotEnoughResultsException:
            link.write(line())
            raise CommandProcessingError(texts['thing404'] % thing)
        except TooManyResultsException:
            raise CommandProcessingError(texts['thingOverflow'])

        return result












# Command definitions.
# Watch out, order may be important -- if one command's full name is the beginning of another command's name, make sure the longer command gets declared first.
@command("look")
def do_look(link, text): #Should we be passing in the state object, instead of looking it up in client_states every time?
    me = client_states[link]['character']
    assert me != -1

    text.strip()
    if text != '':
        tgt = resolve_or_oops(link, me, text)
        if tgt is None:
            return
    else:
        tgt = self.get_location(me)
        if tgt is None:
            link.write(line(texts['youAreNowhere']))
            return

    here = self.get_thing(tgt)
    print("here = %s", repr(here))
    if here is None:
        # The functions to find out the thing from the database didn't work.
        link.write(line(texts['thing404'] % '(this is a big problem)'))

    link.write(line(self.thing_displayname(here[0], tgt)))
    link.write(here[1] + line(''))

    print("to get_contents: %s" % repr(here[0]))
    contents = ", ".join([self.thing_displayname(self.get_thing(x)[0], x) for x in self.get_contents(tgt)])
    if len(contents) > 0:
        link.write(line(texts['beforeListingContents'] + contents))










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