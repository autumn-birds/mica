#!/usr/bin/python3

import logging
import traceback
import base64
import hashlib
import os # for urandom


# Default messages that would otherwise be hard-coded about in the code.
# TODO: Factor into a separate file.
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
    'addedUser': "[##] Added user %s (id is for character object)",

    'youAreNowhere': "You... erm... don't seem to actually be in a location that exists.  This is, um, honestly, really embarrassing and we're not sure what to do about it.",
    'youDontExist': "Oh gosh.  You don't seem to exist.  We think someone deleted you, but we're not really sure.  Um... sorry?",
    'descMissing': "You see a strange and unnerving lack of emptiness.",
    'beforeListingObjects': "You can see: ",
    'beforeListingExits': "Obvious exits: ",
    'beforeListingInventory': "You are carrying:",
    'carryingNothing': "You are not carrying anything.",

    'setAttrToValSuccess': "Set %s to %s.",
    'madeThing': "Created in your inventory: %s",
    'builtThing': "Created %s with id of %d as a floating object.",
    'openedPath': "Opened path %s leading to %s.",

    'examiningThing': "[== Examining: %s]",
    'thingHasNoOwner': "[!!] %s has no owner.",
    'thingOwner': "[##] Owner: %s",
    'thingParameterValue': "%s=%s",

    'triedToGoAmbiguousWay': "There's more than one way to go `%s'.",

    'characterConnected': "[##] %s has connected.",
    'characterDisconnected': "[##] %s has disconnected.",
    'characterArrives': "[##] %s arrives from %s.",
    'characterDeparts': "[##] %s leaves, heading towards %s.",
    'characterSays': "%s says, \"%s\"",
    'characterPoses': "%s %s",
}


class MicaException(Exception):
    """A generic class for custom exceptions thrown by the code."""
    pass

class TooManyResultsException(MicaException):
    """This exception is thrown by mica's database accessors and by other functions when there are more results than expected."""
    pass

class NotEnoughResultsException(MicaException):
    """This exception is thrown by mica's database accessors and by other functions when there are not enough results."""
    pass

class CommandProcessingError(MicaException):
    """This is an exception thrown by command functions to report an error and exit at the same time."""
    pass

class AccountNamingException(MicaException):
    """This exception is thrown when an attempt is made to create or rename an account or character that would have the same name as another, already existing account or character."""
    pass


class Thing:
    """Represents a single object in the Mica database.
    Most methods you call on this object will access the database directly, but it is still possible to have a Thing instance that does not agree with the database; for example, one whose records in the database don't actually exist.
    If this happens, you will encounter problems."""
    def __init__(self, mica, dbref):
        """Create. Called by the Mica.get_thing() function.

        Can raise NotEnoughResultsException but probably shouldn't ever raise TooManyResultsException."""
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
        """Build and return a list of (key, value) pairs representing this object's properties."""
        return self.mica._from_db("SELECT name, val FROM properties WHERE object_id=?", (self.id,))

    def name(self):
        """Return the Thing's name."""
        return self.mica._one_from_db("SELECT name FROM things WHERE id=?", (self.id,))[0]

    def set_name(self, newname):
        """Rename this thing to `newname'."""
        assert type(newname) is str
        # We want to make it impossible to ever have two Things associated with accounts with the same name.
        if self.is_character():
            if self.mica.find_account(newname) is not None:
                raise AccountNamingException("Refusing to rename character to a name shared with another character")

        self.mica._calldb("UPDATE things SET name=? WHERE id=?", (newname, self.id))

    def destination(self):
        """If this Thing is not a passage, this value will be None.
        But if it IS a passage, this value will be the id of another Thing (e.g., the one it is an exit to.)"""
        result = self.mica._one_from_db("SELECT passage_to FROM things WHERE id=?", (self.id,))[0]
        # That could raise NotEnoughResultsException, but if it does, that doesn't mean we didn't find a passage but rather that we don't exist in the database at all; thus, not catching the exception is correct here.
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
        """Return the Thing where this Thing is located, or None if that Thing does not exist in the database."""
        try:
            results = self.mica._one_from_db("SELECT id FROM things WHERE id IN (SELECT location_id FROM things WHERE id = ?)", (self.id,))
        except NotEnoughResultsException:
            return None

        return self.mica.get_thing(results[0])

    def move(self, to_thing):
        """Move this Thing into another Thing."""
        # TODO: Rename to set_location for consistency's sake
        self.mica._calldb("UPDATE things SET location_id=? WHERE id=?", (to_thing.id, self.id))

    def traverse_exit(self, exitname):
        """Try to move from this Thing's location through exit `exitname' into its target location.

        This function will notify the appropriate Things of arrival/departure using .tell().

        It returns the new location of the object, or the object's current location if movement didn't succeed; it can return None if the object isn't located in an object that exists.

        It will raise NotEnoughResultsException if there are no exits that mach the name, and TooManyResultsException if the name is ambiguous (e.g. more than one exit matches.)"""
        assert type(exitname) is str

        prospective_exits = []

        fromloc = self.location()
        if fromloc is None:
            return None

        # For all exits (an exit is just a Thing with destination set...)
        for option in [x for x in fromloc.contents() if x.destination() is not None]:
            if exitname in option.name():
                prospective_exits.append(option)

        # Only move if there's exactly one thing that could possibly be meant
        if len(prospective_exits) == 1:
            toloc = prospective_exits[0].destination()
            self.location().tell(texts['characterDeparts'] % (self.display_name(), toloc.name()), exclude=[self])
            self.move(toloc)
            self.location().tell(texts['characterArrives'] % (self.display_name(), fromloc.name()), exclude=[self])

        elif len(prospective_exits) > 1:
            raise TooManyResultsException

        elif len(prospective_exits) < 1:
            raise NotEnoughResultsException

        return toloc

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

    def owns_thing(self, other_thing):
        """Return True if this thing owns `other_thing', and False otherwise."""
        result = self.mica._one_from_db("SELECT owner_id FROM things WHERE id=?", (other_thing.id,))[0]
        return result == self.id

    def owner(self):
        """Return the Thing that owns this Thing, or None if there isn't any such Thing to be found."""
        # If WE don't exist, it is legitimately an error... so we don't try/except this call.
        owner = self.mica._one_from_db("SELECT owner_id FROM things WHERE id=?", (self.id,))[0]
        return self.mica.get_thing(owner)

    def set_owner(self, other):
        """Change the owner of this Thing to the Thing `other'."""
        self.mica._calldb("UPDATE things SET owner_id=? WHERE id=?", (other.id, self.id))

    def is_character(self):
        """Return True if this object is associated with an Account, and False otherwise."""
        if len(self.mica._from_db("SELECT id FROM accounts WHERE character_id=?", (self.id,))) > 0:
            return True
        return False

    def resolve_many_things(self, thing):
        """Returns a list of all the Things that the text string `thing' could possibly match, using the syntax used by commands & players to refer to objects, from the point-of-view of this object.
        That is, considers objects that are inside this object and objects that are in its current location along with it."""
        thing = thing.strip()
    
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

            result = self.mica.get_thing(dbref)
            if result is not None:
                return [result]
            else:
                return []

        whereami = self.location()
        if whereami is not None:
            # Consider items you're carrying.
            # We also want to add ourselves to the list, and our location to the list, as otherwise we get baffling messages that suggest those things can't be found, when, clearly, they're RIGHT THERE.
            candidates = self.contents() + [self]
            l = self.location()
            if l is not None:
                candidates += [l]

            matches = [x for x in candidates if thing in x.name()]
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
        # TODO: Fix calls to this so we have objectids only where it makes sense (e.g. not in 'has connected' methods), and maybe rename this method to something like full_name() or distinct_name() or whatever to make it clearer what it's actually doing.
        """Returns the Thing's name (string) as it should be displayed to users; e.g., with the database number included, for example."""
        return "%s [%d]" % (self.name(), self.id)

    def tell(self, msg, exclude=[]):
        """Dispatch a message `msg' to self (if connected) and to all the Things with self as their location."""
        assert type(msg) is str
        msg = msg.strip()
        if len(msg) < 1:
            raise ValueError("msg should be a str with some non-whitespace content")

        # It's much better for the caller to pass Things, but important for us to check ids (and not Things, which could be two different objects with the same database id.)
        # Transform `exclude' from an array of Things to an array of database ids of Things.
        exclude = [x.id for x in exclude]

        # Tell all the non-excluded Things the message, if they're connected.
        for thing in self.contents() + [self]:
            if thing.id in self.mica.connected_things and thing.id not in exclude:
                self.mica.connected_things[thing.id].write(self.mica.line(msg))


class Account:
    """Represents a user account in the Mica database.

    An account is basically the association of an arbitrary object in the database (usually, one that owns itself) with a password; accounts don't really have a name of their own, instead taking their name from whatever Thing they're associated with."""
    def __init__(self, mica, name=None, id=None):
        """Create. Called by the Mica.find_account method.

        Can raise NotEnoughResultsException if the account does not exist, but probably should never throw TooManyResultsException. It might, however, if there are ever two or more Things with the same name associated with an account.

        name and id are mutually exclusive, and if both are not None, an exception will be raised.
        Otherwise, the account will be looked up by name or by id depending on which value has been provided."""
        if (name is None and id is None) or (name is not None and id is not None):
            # ^^ actually just (name is None) XOR (id is None)
            raise MicaException("Caller supplied not enough or multiple ways to look up Account")

        assert type(mica) is Mica
        self.mica = mica

        if name is not None:
            # This leads to a sort of backwards-feeling lookup process, where we have to look up the character by name first, then look up the account by its character's id.
            # (Should we be caching the char_id?  Not if it's ever possible to change someone's character-id, but UNLESS there is a method on this class to change said id, which should be the canonical and only way to do it, I think doing this is okay.)
            # TODO: See if we can use some kind of join to do this in a single call?
            assert type(name) is str
            self.char_id = mica._one_from_db("SELECT id FROM things WHERE name=? AND id IN (SELECT character_id FROM accounts)", (name,))[0]
            self.id = mica._one_from_db("SELECT id FROM accounts WHERE character_id=?", (self.char_id,))[0]
        elif id is not None:
            # This is more straightforward as we just have to grab the character-id, and we can even do it in one call.
            assert type(id) is int
            (self.id, self.char_id) = mica._one_from_db("SELECT id, character_id FROM accounts WHERE id=?", (id,))

    def character(self):
        """Return the character belonging to this account, or None if it (for some reason) doesn't exist."""
        return self.mica.get_thing(self.char_id)

    def _hash(self, password, salt):
        """Return a cryptographic hash function for `password' and `salt', which must be bytes-like objects.
        Returns a bytes-like object.
        Used internally."""
        # The 250,000 is the number of iterations to run the key derivation algorithm.
        # Python3 documentation states that "at least 100,000" iterations are recommended "in 2013," so I hope 250,000 will be enough to provide some reasonable security without stalling the whole server for several seconds every time someone logs in.
        # I chose pbkdf2 because scrypt isn't present in systems that don't have recent enough Python and OpenSSL installations, and I wanted to not have to bother about that.
        return hashlib.pbkdf2_hmac('sha256', password, salt, 250000)

    def check_password(self, candidate):
        """Return True if plaintext password `candidate' is the correct password for this account, and False otherwise."""
        assert type(candidate) is str

        # Returns strings (b64encoded):
        (hashed_password, salt) = self.mica._one_from_db("SELECT password, salt FROM accounts WHERE id=?", (self.id,))

        # Returns bytes:
        hashed_password = base64.b64decode(hashed_password)
        salt = base64.b64decode(salt)

        # Takes bytes, returns bytes:
        hashed_candidate = self._hash(candidate.encode('utf-8'), salt)

        # ... bytes == bytes
        return hashed_candidate == hashed_password

    def set_password(self, password):
        """Change the account's password to `password' (given as plaintext.)"""
        assert type(password) is str

        # I think the recommended minimum value is 16, so I used a higher one.
        # These 'magic numbers' should probably be in configuration variables somewhere...
        salt = os.urandom(32)
        hashed_result = self._hash(password.encode('utf-8'), salt)

        password = base64.b64encode(hashed_result).decode('ascii')
        salt = base64.b64encode(salt).decode('ascii')

        self.mica._calldb("UPDATE accounts SET password=?, salt=? WHERE id=?", (password, salt, self.id))


# (Stub. For later)
class Connection:
    def __init__(self, mica, link):
        self.acct_id = None
        self.mica = mica
        self.link = link

    def get_state(self, var):
        # TODO
        return None

    def set_state(self, var, val):
        # TODO
        pass

    def account(self):
        return self.mica.get_account(self.acct_id())

    def character(self):
        return self.account().character()


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

        # TODO: Consider trying to replace most or all of the places we are storing object-ids as bare ints, with Thing instances instead??  Thing instances are basically an object-id plus a reference to, hopefully, the mica object that created them.

        # The client_states variable is indexed by 'link' objects, provided by network code, and it keeps track of state for each connection, such as what object it's logged into (the object acts like a character) or whether it's logged in at all.
        # Since in the future there might be more state that's needed, e.g. to implement the required functionality for editor- or puppet-driving-type systems, or since some commands might want to store state, the values in this dictionary are also dictionaries; the character object the command is connected to is stored under the 'character' key in each dictionary.
        # TODO: Currently the 'character' key is set to -1 to indicate a connection that has not logged in yet. But really it should be None, since I think it might be theoretically possible for negative database indices to exist somehow.
        # TODO: See if we can refactor so we use Connection objects to handle state in this class.
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
    # Database access-related functions.
    def setup_db(self):
        """Initialize the database with a minimal default template.
        The result of calling this function when the database already has data in it is undefined."""
        dbSetup = [
          "CREATE TABLE things (id INTEGER PRIMARY KEY, owner_id INTEGER, location_id INTEGER, passage_to NULLABLE INTEGER, name TEXT)",
          "CREATE TABLE accounts (id INTEGER PRIMARY KEY, character_id INTEGER, password TEXT, salt TEXT)",
          "CREATE TABLE properties (id INTEGER PRIMARY KEY, name TEXT, val TEXT, object_id INTEGER, " +
            "CONSTRAINT noduplicates UNIQUE (object_id, name))",

          "INSERT INTO things (id, owner_id, location_id, name) VALUES (1, 1, 2, \"One\")",
          "INSERT INTO properties (object_id, name, val) VALUES (1, \"desc\", \"A nameless, faceless, ageless, gender-neutral, culturally ambiguous embodiment of... well, it's not clear, really.\")",

          "INSERT INTO accounts (character_id, password, salt) VALUES (1, \"\", \"\")",

          "INSERT INTO things (id, owner_id, location_id, name) VALUES (2, 1, 2, \"Nexus\")",
          "INSERT INTO properties (object_id, name, val) VALUES (2, \"desc\", \"It is a place: that is about all you can be sure of.\")"
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

        # Set the password on One's account properly.
        # We have to create the initial records by hand above because One needs to be object id 1, which is expected to have implicit superuser powers.
        a_wizard = self.get_account(1)
        a_wizard.set_password("potrzebie")

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

    def _ctx_last_inserted(self, ctx):
        """For the sqlite3 context `ctx', return the rowid of the last item inserted.
        This method doesn't technically use any data from `self', and it could probably be moved elsewhere if that ever became necessary."""
        ctx.execute("SELECT last_insert_rowid()")
        results = ctx.fetchall()
        assert len(results) == 1
        return results[0][0]

    #
    # Functions to create objects in the database, or fetch existing ones, and return an appropriate instance of one of the above classes.
    def find_account(self, account):
        """Return an Account instance for the username/character name `account', if one exists, or None if one doesn't."""
        assert type(account) is str
        try:
            return Account(self, name=account)
        except NotEnoughResultsException:
            return None

    def get_account(self, id):
        """Return an Account instance for the Account with id `id', if one exists, or None if one doesn't."""
        assert type(id) is int
        try:
            return Account(self, id=id)
        except NotEnoughResultsException:
            return None

    def add_account(self, name, password):
        assert type(name) is str
        assert type(password) is str

        # Make sure no account with this name already exists; we _really_ don't want duplicates.
        if self.find_account(name) is not None:
            raise AccountNamingException("Refusing to create two accounts with the same name")

        char = self.add_thing(name)
        # Here, we set the password to an empty string first because, while we want to use the Account class's set_password method to actually set it, we need the appropriate rows to exist in the database before we can create an Account class in the first place.
        Cx = self._calldb("INSERT INTO accounts (character_id, password, salt) VALUES (?, ?, ?)", (char.id, "", ""))
        acct = self.get_account(self._ctx_last_inserted(Cx))
        acct.set_password(password)
        return acct

    def get_thing(self, id):
        """Return a Thing instance for the id `id', if one exists, or None if one doesn't."""
        try:
            return Thing(self, id)
        except NotEnoughResultsException:
            return None

    def add_thing(self, name, owner=None):
        """Create a new thing in the database, named `name' and owned by and located in the Thing (expected to be a Thing instance) `owner', and return a new Thing instance.

        If `owner' is None, the newly created Thing will own itself."""
        assert type(owner) is Thing or owner is None

        if owner is not None:
            Cx = self._calldb("INSERT INTO things (name, location_id, owner_id) VALUES (?,?,?)", (name, owner.id, owner.id))
            return self.get_thing(self._ctx_last_inserted(Cx))
        else:
            # We use fake owner and location values, then reset them when we know our id.
            Cx = self._calldb("INSERT INTO things (name, location_id, owner_id) VALUES (?,?,?)", (name, 0, 0))

            new_thing = self.get_thing(self._ctx_last_inserted(Cx))
            new_thing.set_owner(new_thing)
            new_thing.move(new_thing)
            return new_thing


    #
    # Logic for connections and how users interact with the system, including logging in and command processing.

    # There is no actual network code here; instead, the networking code in the main loop calls these functions with lines of text or on relevant events, passing in objects we understand as 'links'.
    # The implementation details are unspecified, but the link objects must conform to a small API:
    # 1. The objects will always be unique among all links and will never change over the lifetime of the link, making them usable as an index (e.g. for state associated with the connection.)
    # 2. They will support a write() method which takes a chunk of UTF-8 encoded text in a single argument and writes it onto the link; this method will not need to be called multiple times to safely assume the whole text has been sent, will buffer if necessary, and should not block.
    #       TODO: I want to extend this into a richer write() method that supports metadata (e.g., colors and urls) for implementations that can support those features, while still allowing implementations that can't to easily recover a straightforward plain-text string.
    #       TODO: I want write() to write a single line at a time thus freeing us of the need to think about calling line().
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
        if char is None:
            # TODO: Is this the kind of error handling we want?
            link.write(self.line(texts['youDontExist']))
            return False

        if char.location() is None:
            link.write(self.line(texts['cmd404']))
            return

        try:
            char.traverse_exit(text.strip())
            self.on_text(link, "look")
            return
        except NotEnoughResultsException:
            # Execution will fall through to a 'that command can't be found' in this case anyway.
            pass
        except TooManyResultsException:
            link.write(self.line(texts['triedToGoAmbiguousWay']))
            return

        # If we get here, it means we ran out of things to try: No command was found, and no exits were found either.
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

        # TODO: JUST MAKE IT A THING OR NONE ALREADY GEEZE YOU IDIOT (...maybe?)
        me = self.get_thing(self.client_states[old_link]['character'])
        if me != None:
            me.location().tell(texts['characterDisconnected'] % me.name())

        del self.client_states[old_link]

        # Get rid of any expired entries in the connected_things index.
        # Doing this is probably more expensive than just checking to see we delete the character associated with the link that just died, but is less fragile.
        self.connected_things = {k: v for k, v in self.connected_things.items() if v in self.client_states}

        logging.info("Losing link " + repr(old_link))

    def _try_login(self, link, args):
        """Called internally to process logins."""
        # TODO: allow double-quote parsing? Maybe?
        args = args.split(' ')
        if len(args) != 2:
            link.write(self.line(texts['cmdSyntax'] % "connect <username> <password>"))
            return

        acct = self.find_account(args[0])
        if acct is None:
            link.write(self.line(texts['badLogin']))
            return False

        if acct.check_password(args[1]):
            # Login succeeds...
            self.client_states[link]['character'] = acct.char_id
            self.connected_things[acct.char_id] = link

            if self.motd is not None:
                link.write(self.line(self.motd))
            for cmd in self.login_commands:
                self.on_text(link, cmd)

            # acct.character() *could* return None, but this is fairly safe because we had to look up the character in order to find the account in the first place.
            char = acct.character()
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
    # (Note that decorators are @ immediately followed by an _expression_: If the expression is just a name, it evaluates to the function named that, but it can also be a function call, in which case python calls that function when evaluating the decorator instead. The _result of evaluation_ should be a function, which is called on the function being decorated and returns a new function that effectively replaces it. So this returns a function that is called on the actual function being decorated. Confused yet?)
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
        # TODO: Move this function to Connection.pov_find_thing()
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
