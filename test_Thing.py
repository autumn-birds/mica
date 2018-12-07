import mica.core
import sqlite3

mx = mica.core.Mica(sqlite3.connect(":memory:"))
mx.setup_db()

t = mica.core.Thing(mx, 1)
t['hello'] = 'world'
print(t['hello'])
del t['hello']
print(t.get('hello', 'goodbye, cruel'))