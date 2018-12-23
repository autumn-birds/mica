#!/usr/bin/python3

import logging
import traceback


# Default messages that would otherwise be hard-coded about in the code.
texts = {
    'welcome': "Welcome.  Type `connect <name> <password>' to connect.",

    'badLogin': "I'm sorry, but those credentials were not right.",
    'cmd404': "I don't understand what you mean.",
    'thing404': "I can't find any such thing as `%s'.",
    'thingOverflow': "`%s' is ambiguous -- I can't tell which thing you mean.",
    'cmdSyntax': "That command needs to be written similar to `%s'.",
    'cmdErrWithArgs': "[!!] There was a problem processing your command, but the arguments weren't as expected: %s",
    'cmdErrUnspecified': "[!!] There was a problem processing your command, but no explanation has been provided. Please bother your local developers.",
    'err': "[!!] %s",
    'noPermission': "[!!] You don't have permission to do that.",

    'youAreNowhere': "You... erm... don't seem to actually be in a location that exists.  This is, um, honestly, really embarrassing and we're not sure what to do about it.",
    'descMissing': "You see a strange and unnerving lack of emptiness.",
    'beforeListingObjects': "You can see: ",
    'beforeListingExits': "Obvious exits: ",
    'beforeListingInventory': "You are carrying:",
    'carryingNothing': "You are not carrying anything.",

    'setAttrToValSuccess': "Set %s to %s.",
    'madeThing': "Created in your inventory: %s",
    'builtThing': "Created %s with id of %d as a floating object.",
    'openedPath': "Opened path %s leading to %s.",

    'triedToGoAmbiguousWay': "There's more than one way to go `%s'.",

    'characterConnected': "[##] %s has connected.",
    'characterArrivesThruPassage': "[##] %s emerges, having entered %s elsewhere.",
    'characterDepartsByPassage': "[##] %s exits through the passage %s.",
    'characterSays': "%s says, \"%s\"",
    'characterPoses': "%s %s",
}


# These are mainly thrown by mica's database accessors.
class TooManyResultsException(Exception):
    pass

class NotEnoughResultsException(Exception):
    pass

# This is an exception thrown by command functions to report an error and exit at the same time.
class CommandProcessingError(Exception):
    pass


class Thing:
    """Represents a single object in the Mica database.
    Most methods you call on this object will access the database directly, but it is still possible to have a Thing instance that does not agree with the database; for example, one whose records in the database don't actually exist.
    If this happens, you will encounter problems."""
    def __init__(self, mica, dbref):
        assert type(mica) is Mica
        self.mica = mica

        assert type(dbref) is int
        # This might seem strange, but we need to make sure the dbref is valid; calling this function will raise a NotEnoughResultsException if it isn't.
        self.id = self.mica._one_from_db("SELECT id FROM things WHERE id=?", (dbref,))[0]

    def __getitem__(self, key):
        """Return the property named `key' set on this thing.
        Note that although this is a special function intended to allow you to use Things with the same syntax you do dicts, e.g., thing['desc'] = my_description, it does in fact access the database each time it is called."""
        try:
            (k, v) = self.mica._one_from_db("SELECT name, val FROM properties WHERE object_id=? AND name=?",
                (self.id, key))
            assert k == key
            return v
        except NotEnoughResultsException:
            # For some reason this still prints the NotEnoughResultsException in the traceback as well, and I'm not really sure why.
            raise KeyError

    def __setitem__(self, key, value):
        """Set the property named `key' on this thing to `value' on this thing, creating it if it does not exist (will never raise KeyError.)
        Note that although this is a special function intended to allow you to use Things with the same syntax you do dicts, e.g., thing['desc'] = my_description, it does in fact access the database each time it is called."""
        self.mica._calldb("INSERT INTO properties (object_id, name, val) VALUES (?,?,?) ON CONFLICT(object_id,name) DO UPDATE SET val=excluded.val", (self.id, key, value))

    def __delitem__(self, key):
        """Delete the property named `key' on this Thing.
        Note that although this is a special function intended to allow you to use Things with the same syntax you do dicts, e.g., thing['desc'] = my_description, it does in fact access the database each time it is called."""
        if self.get(key, None) is not None:
            self.mica._calldb("DELETE FROM properties WHERE object_id=? AND name=?", (self.id, key))
        else:
            raise KeyError

    def get(self, key, default):
        """Like get() of the builtin dict type, but for Things -- if `key' doesn't exist, returns `default' instead of raising KeyError."""
        try:
            return self[key]
        except KeyError:
            return default
    
    def items(self):
        """Build and return a list of (key, value) pairs representing this object's parameters."""
        return self.mica._from_db("SELECT name, val FROM properties WHERE object_id=?", (self.id,))

    def name(self):
        """Return the Thing's name."""
        return self.mica._one_from_db("SELECT name FROM things WHERE id=?", (self.id,))[0]

    def set_name(self, newname):
        """Rename this thing to `newname'."""
        assert type(newname) is str
        self.mica._calldb("UPDATE things SET name=? WHERE id=?", (newname, self.id))

    def destination(self):
        """If this Thing is not a passage, this value will be None.
        But if it IS a passage, this value will be the id of another Thing (e.g., the one it is an exit to.)"""
        result = self.mica._one_from_db("SELECT passage_to FROM things WHERE id=?", (self.id,))[0]
        if result is not None:
            return self.mica.get_thing(result)
        else:
            return None

    def set_destination(self, new_dest):
        """Set the destination to new_dest (a Thing, or None.)"""
        assert type(new_dest) is Thing or new_dest is None
        if new_dest is None:
            self.mica._calldb("UPDATE things SET passage_to=? WHERE id=?", (None, self.id))
        else:
            self.mica._calldb("UPDATE things SET passage_to=? WHERE id=?", (new_dest.id, self.id))

    def location(self):
        """Return the Thing where this Thing is located; or None if that Thing does not exist in the database."""
        # (Should this raise an exception instead?)
        try:
            results = self.mica._one_from_db("SELECT id FROM things WHERE id IN (SELECT location_id FROM things WHERE id = ?)", (self.id,))
        except NotEnoughResultsException:
            return None
        print("get_location: %d is in %d" % (self.id, results[0]))
        return self.mica.get_thing(results[0])

    def contents(self):
        """Return a list of Things that are in this Thing."""
        assert type(self.id) is int
        contents = []
        for content in self.mica._from_db("SELECT id FROM things WHERE location_id=?", (self.id,)):
            if content[0] != self.id:
                assert type(content[0] is int)
                # This should never not exist, since we just SELECTed it.
                contents.append(self.mica.get_thing(content[0]))
        return contents

    def move(self, to_thing):
        """Move this Thing into another Thing."""
        self.mica._calldb("UPDATE things SET location_id=? WHERE id=?", (to_thing.id, self.id))

    def owns_thing(self, other_thing):
        """Return True if this thing owns `other_thing', and False otherwise."""
        result = self.mica._one_from_db("SELECT owner_id FROM things WHERE id=?", (other_thing.id,))[0]
        return result == self.id

    def owner(self):
        """Return the Thing that owns this Thing, or raise NotEnoughResultsException if there isn't any such Thing to be found."""
        owner = self.mica._one_from_db("SELECT owner_id FROM things WHERE id=?", (self.id,))[0]
        return self.mica.get_thing(owner)

    def resolve_many_things(self, thing):
        """Returns a list of all the Things that the text string `thing' could possibly match, using the syntax used by commands & players to refer to objects, from the point-of-view of this object.
        That is, considers objects that are inside this object and objects that are in its current location along with it."""
        thing = thing.strip()

        # TODO: Include this object and its location in the list, so we don't get baffling messages that suggest we don't exist.
        if thing == 'me':
            # TODO: Maybe we should check this too.  Just to be extra pedantic.
            # I don't know if maybe we shouldn't just have a check_id_exists() function or something.
            return [self]

        if thing == 'here':
            l = self.location()
            if l is not None and type(l) is Thing:
                return [l]
            else:
                return []

        if thing[0] == '#':
            try:
                dbref = int(thing[1:])
            except ValueError:
                return []

            try:
                return [self.mica.get_thing(dbref)]
            except NotEnoughResultsException:
                return []

        whereami = self.location()
        if whereami is not None:
            # Consider items you're carrying.
            candidates = [(x.id, x.name()) for x in self.contents()]
            matches = [self.mica.get_thing(x[0]) for x in candidates if thing in x[1]]
            return matches

    def resolve_one_thing(self, thing):
        """Like resolve_many_things, but either returns a single id (as a number, *not* a single-item array) or raises TooManyResultsException or NotEnoughResultsException as appropriate."""
        results = self.resolve_many_things(thing)
        if results is None:
            raise NotEnoughResultsException()
        if len(results) > 1:
            raise TooManyResultsException()
        elif len(results) < 1:
            raise NotEnoughResultsException()
        else:
            assert type(results[0]) is Thing
            return results[0]

    def display_name(self):
        """Returns the Thing's name (string) as it should be displayed to users; e.g., with the database number included, for example."""
        return "%s [%d]" % (self.name(), self.id)

    def tell(self, msg):
        """Dispatch a message `msg' to self (if connected) and to all the Things with self as their location."""
        assert type(msg) is str
        msg = msg.strip()
        if len(msg) < 1:
            raise ValueError("msg should be a str with some non-whitespace content")

        for thing in self.contents() + [self]:
            if thing.id in self.mica.connected_things:
                self.mica.connected_things[thing.id].write(self.mica.line(msg))


class Mica:
    def __init__(self, db):
        """Setup the class.
        `db` should be a SQLite3 database object created with the default `sqlite3` module."""
        self.db = db

        # This list stores all the names of commands that could be run, associated with their functions.
        # It is a list and not a dict because it might need to be ordered, although if that is the case the ordering should probably be enforced internally rather than depending on callers to register their commands in a problem-free order.
        # The elements in the list are (command_name:str, command:function) tuples.
        self._commands = []

        # Some commands have a short alias that triggers them when directly prefixed with their arguments, like a single quote for say or a colon for pose; we deal with that by registering them in this list, which is in the same format as _commands but should typically be much shorter.
        self._prefix_commands = []

        # TODO: Consider trying to replace most or all of the places we are storing object-ids as bare ints, with Thing instances instead.

        # The client_states variable is indexed by 'link' objects, provided by network code, and it keeps track of state for each connection, such as what object it's logged into for a character or whether it's logged in at all.
        # Since in the future there might be more state that's needed, e.g. to implement the required functionality for editor- or puppet-driving-type systems, or since some commands might want to store state, the values in this dictionary are also dictionaries; the character object the command is connected to is stored under the 'character' key in each dictionary. 
        # TODO: Currently the 'character' key is set to -1 to indicate a connection that has not logged in yet. But really it should be None, since I think it might be theoretically possible for negative database indices to exist somehow.
        self.client_states = {}

        # We need to know who is connected to what objects at any given time, and so we keep track of them by mapping objectid-to-link as well as link-to-state; this is sort of the inverse of client_states.
        # You can go from a connected character to a state by doing client_states[connected_things[char_obj]].
        self.connected_things = {}

        # Set this to True to print tracebacks to the user.
        self.show_tracebacks = False

        # These strings are run for each user when they connect as though they were normal command lines.
        self.login_commands = []

        # This message will be shown to users when they log in, if it is not None.
        self.motd = None

    #
    # Database functions (accessing and updating objects, etc.)
    def setup_db(self):
        """Initialize the database with a minimal default template.
        The result of calling this function when the database already has data in it is undefined."""
        dbSetup = [
          "CREATE TABLE things (id INTEGER PRIMARY KEY, owner_id INTEGER, location_id INTEGER, passage_to NULLABLE INTEGER, name TEXT)",
          "CREATE TABLE accounts (id INTEGER PRIMARY KEY, character_id INTEGER, password TEXT)",
          "CREATE TABLE properties (id INTEGER PRIMARY KEY, name TEXT, val TEXT, object_id INTEGER, " +
            "CONSTRAINT noduplicates UNIQUE (object_id, name))",

          "INSERT INTO things (id, owner_id, location_id, name) VALUES (1, 1, 2, \"One\")",
          "INSERT INTO properties (object_id, name, val) VALUES (1, \"desc\", \"A nameless, faceless, ageless, gender-neutral, culturally ambiguous embodiment of... well, it's not clear, really.\")",

          "INSERT INTO things (id, owner_id, location_id, name) VALUES (2, 1, 2, \"Nexus\")",
          "INSERT INTO properties (object_id, name, val) VALUES (2, \"desc\", \"It is a place: that is about all you can be sure of.\")",
          
          # TODO: Password hashing
          "INSERT INTO accounts (character_id, password) VALUES (1, \"potrzebie\")"
        ]

        Cx_setup = self.db.cursor()
        for cmd in dbSetup:
            try:
                Cx_setup.execute(cmd)
            except:
                print("setup_db(): Error executing command << %s >>:" % cmd)
                raise
        self.db.commit()
        Cx_setup = None

    def _calldb(self, query, opts=None):
        """Execute a database query `query` with the optional tuple of data `opts` and return the cursor that was used to execute the query, on which, for example, fetchall() or similar methods can be called.
        External functionality should not use this, as the database structure is not meant to be an API."""
        Cx = self.db.cursor()
        if opts is not None:
            Cx.execute(query, opts)
        else:
            Cx.execute(query)
        return Cx

    def _commitdb(self):
        """Call the sqlite3 commit() function."""
        self.db.commit()

    def _from_db(self, query, opts=None):
        """Return the results from fetchall() of a database query; just for convenience."""
        return self._calldb(query, opts).fetchall()

    def _one_from_db(self, query, opts=None):
        """Like from_db, but guarantees there is exactly one result returned--no more, no less.
        Will raise TooManyResultsException and NotEnoughResultsException as appropriate.
        Returns the singular result on its own and not wrapped in a containing array, so watch your semantics.  But also remember the result will probably still be a tuple (of a row, even with one object.)"""
        results = self._from_db(query, opts)
        if len(results) < 1:
            raise NotEnoughResultsException()
        elif len(results) > 1:
            raise TooManyResultsException()
        else:
            logging.info("one_from_db: returning %s" % repr(results[0]))
            return results[0]

    def get_account(self, account):
        """Return a tuple of (password, objectID) for the given account name, if it exists and is not ambiguous; otherwise, return None."""
        # TODO: See if we can use some kind of join to do this in a single call.
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

    def get_thing(self, id):
        """Return a Thing instance for the id `id', or raise a NotEnoughResultsException if it doesn't exist.
        Technically might be able to raise a TooManyResultsException, but it should never in practice."""
        # Does name lookup itself. Can raise NotEnoughResultsException on inextant id
        return Thing(self, id)

    def add_thing(self, owner, name):
        """Create a new thing in the database, named `name' and owned by the Thing (expected to be a Thing instance) `owner', and return a new Thing instance."""
        Cx = self._calldb("INSERT INTO things (name, location_id, owner_id) VALUES (?,?,?)", (name, owner.id, owner.id))
        Cx.execute("SELECT last_insert_rowid()")
        results = Cx.fetchall()
        assert len(results) == 1
        return self.get_thing(results[0][0])

    #
    # Logic for connections and how users interact with the system, including logging in and command processing.
    # There is no actual network code here; instead, the networking code in the main loop calls these functions with lines of text or on relevant events, passing in objects we understand as 'links'.
    # The implementation details are unspecified, but the link objects must conform to a small API:
    # 1. The objects will always be unique among all links and will never change over the lifetime of the link, making them usable as an index (e.g. for state associated with the connection.)
    # 2. They will support a write() method which takes a chunk of UTF-8 encoded text in a single argument and writes it onto the link; this method will not need to be called multiple times to safely assume the whole text has been sent, will buffer if necessary, and should not block.
    # 3. They will support a kill() method that forcefully disconnects the client on the other end of the link. The network code should [I hope] be able to take care of calling on_disconnection() itself in that case.
    def line(self, text):
        """Encapsulates the process of adding a proper newline to the end of lines, just in case it ever needs to be changed."""
        # TODO: Get rid of this method and require the write() method to know how to encapsulate lines itself.
        return text + "\r\n"

    def on_connection(self, new_link):
        """Called by network code when a new connection is received from a client."""
        self.client_states[new_link] = {'character': -1}
        new_link.write(self.line(texts['welcome']))
        logging.info("Got link " + repr(new_link))

    def on_text(self, link, text):
        """Called by network code when some text is received from a previously connected client.
        The result of network code calling this function with a link object that has not been previously passed to on_connection is undefined."""
        assert link in self.client_states
        s = self.client_states[link]['character']

        # If s is -1 (TODO: None), the user hasn't logged in yet. So we deal with that.
        if s == -1:
            cmd = "connect"
            if text[:len(cmd)] == cmd:
                self._try_login(link, text[len(cmd)+1:])
            else:
                link.write(self.line(texts['cmd404']))
            return

        # If we get here, the user is logged in. So, we check if what they wrote matches a command, and call the appropriate command if so.
        for cmd in self._prefix_commands:
            if cmd[0] == text[:len(cmd[0])]:
                return self.call_command(link, cmd[1], text[len(cmd[0]):])

        for cmd in self._commands:
            if cmd[0] + ' ' == text[:len(cmd[0])+1] or cmd[0].strip() == text.strip():
                return self.call_command(link, cmd[1], text[len(cmd[0])+1:])

        # At this point, we haven't been able to match any command, so we consider whether there could be an exit they are trying to move through, and move them through it if it exists and is not ambiguous.
        char = self.get_thing(s)
        prospective_exits = []

        if char.location() is None:
            link.write(self.line(texts['cmd404']))
            return

        for option in [x for x in char.location().contents() if x.destination() is not None]:
            if text in option.name():
                prospective_exits.append(option)

        if len(prospective_exits) == 1:
            char.location().tell(texts['characterDepartsByPassage'] % (char.display_name(), prospective_exits[0].display_name()))

            char.move(prospective_exits[0].destination())

            char.location().tell(texts['characterArrivesThruPassage'] % (char.display_name(), prospective_exits[0].display_name()))
            # TODO: Should we avoid hard-coding this? (e.g., mechanism similar to on-connect commands)
            self.on_text(link, "look")
            return

        elif len(prospective_exits) > 1:
            link.write(texts['triedToGoAmbiguousWay'] % text)
            return

        # If we get here, it means we ran out of things to try.
        link.write(self.line(texts['cmd404']))

    def call_command(self, link, cmd, text):
        """Call the function `cmd' as a command with text argument `text' in the context of being given by link object `link', handling errors as appropriate.
        This function is used internally by on_text().
        After the command function has been executed, it calls commit() on the database if there were no exceptions and rollback() on the database if there were."""
        try:
            cmd(link, text)
        except CommandProcessingError as e:
            if len(e.args) == 1:
                link.write(self.line(e.args[0]))
            elif len(e.args) > 1:
                link.write(self.line(texts['cmdErrWithArgs'] % repr(e.args)))
            else:
                link.write(self.line(texts['cmdErrUnspecified']))

            self.db.rollback()
            return
        except:
            tx = traceback.format_exc(chain=False)
            logging.error('While processing command: %s' % text)
            logging.error(tx)

            link.write(self.line(texts['cmdErrUnspecified']))
            if self.show_tracebacks:
                link.write(self.line(texts['err'] % tx))
            else:
                link.write(self.line(texts['err'] % "Exception not printed"))

            self.db.rollback()
            return

        # We got here without exceptions, so everything is (probably sort of) okay.
        self.db.commit()
        return

    def on_disconnection(self, old_link):
        """Called by network code when a connection dies.
        The result of re-using an old link object again once it has been passed to this function is undefined."""
        assert old_link in self.client_states
        del self.client_states[old_link]

        # Get rid of any expired entries in the connected_things index.
        # Doing this is probably more expensive than just checking to see we delete the character associated with the link that just died, but is less fragile.
        self.connected_things = {k: v for k, v in self.connected_things if v in self.client_states}

        logging.info("Losing link " + repr(old_link))

    def _try_login(self, link, args):
        """Called internally to process logins."""
        # TODO: allow double-quote parsing? Maybe?
        args = args.split(' ')
        if len(args) != 2:
            link.write(self.line(texts['cmdSyntax'] % "connect <username> <password>"))
            return

        acct = self.get_account(args[0])
        if acct is None:
            link.write(self.line(texts['badLogin']))
            return False

        # Again, TODO: Password hashing
        if acct[0] == args[1]:
            #assert self.get_thing(acct[1]) is not None    # TODO: Is this really necessary? It might be a significant performance drop (more database calls, even more if the object has a lot of objects in it), which could matter since malicious users can try to sign in very frequently, and they don't need to authenticate themselves first (duh.)
            # ... It raises NotEnoughResultsException now, so I just commented it out for now.
            # Login succeeds...
            self.client_states[link]['character'] = acct[1]
            self.connected_things[acct[1]] = link

            if self.motd is not None:
                link.write(self.line(self.motd))
            for cmd in self.login_commands:
                self.on_text(link, cmd)

            char = self.get_thing(acct[1])
            where = char.location()
            if where is not None:
                where.tell(texts['characterConnected'] % char.display_name())

            return True
        else:
            # Login fails.
            link.write(self.line(texts['badLogin']))
            return False


    #
    # Interface for adding commands to the system.
    # (Note that decorators are @ immediately followed by an _expression_: If the expression is just a name, it evaluates to the function named that, but it can also be a function call, in which case python calls that function when evaluating the expression instead. The _result of evaluation_ should be a function, which is called on the function being decorated and returns a new function that effectively replaces it. So this returns a function that is called on the actual function being decorated.)
    def command(self, name):
        """Decorator function. Use like @mica_instance.command("look") on the function implementing the command."""
        # We can capture `name' in a closure.
        def add_this_command(fn):
            self._commands.append((name, fn))
            return fn # We just want the side effects.
        return add_this_command

    def prefix_command(self, prefix):
        """Like command(), but for flat prefixes like the single-quote for calling `say'."""
        def add_this_command(fn):
            self._prefix_commands.append((prefix, fn))
            return fn
        return add_this_command

    def pov_get_thing_by_name(self, link, thing):
        # TODO: This is another of those functions that could be folded into an `Account' class... maybe?
        """Resolve what Thing a user connected to `link' would be referring to.
        If no object can be found or the result is ambiguous, this function throws a CommandProcessingError; command implementations should only catch this error in order to do any necessary cleanup or revert their actions, and it is strongly encouraged that all resolution be done before doing anything that would need to be reverted in case the objects being resolved did not exist, if possible."""
        assert link in self.client_states
        pov = self.get_thing(self.client_states[link]['character'])

        try:
            result = pov.resolve_one_thing(thing)
        except NotEnoughResultsException:
            raise CommandProcessingError(texts['thing404'] % thing)
        except TooManyResultsException:
            raise CommandProcessingError(texts['thingOverflow'])

        return result
