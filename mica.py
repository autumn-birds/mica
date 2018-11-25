import sqlite3
import os

# TODO: Manual switch for creating database to file, + option to load arbitrary file

db = sqlite3.connect(":memory:")

dbSetup = [
  "CREATE TABLE things (id INTEGER PRIMARY KEY, owner_id INTEGER, location_id INTEGER, name TEXT, desc TEXT)",
  "CREATE TABLE accounts (id INTEGER PRIMARY KEY, character_id INTEGER, password TEXT)",
  "CREATE TABLE links (id INTEGER PRIMARY KEY, name TEXT, from_id INTEGER, to_id INTEGER)",
  
  "INSERT INTO things (id, owner_id, location_id, name, desc) VALUES (1, 1, 2, \"One\", \"A nameless, faceless, ageless, gender-neutral, culturally ambiguous embodiment of... it's not clear, really.  Ultimate power over reality for one thing, but they don't seem to be trying to show this off.\")",
  "INSERT INTO things (id, owner_id, location_id, name, desc) VALUES (2, 1, 2, \"Nexus\", \"It is a place: that is about all that can be ascertained.\")",
  "INSERT INTO accounts (character_id, password) VALUES (1, \"potrzebie\")"
]

try:
    Cx_setup = db.cursor()
    for cmd in dbSetup:
        Cx_setup.execute(cmd)
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

print(describe_thing(1))
print(describe_thing(2))