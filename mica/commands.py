# Command definitions.
# Watch out, order may be important -- if one command's full name is the beginning of another command's name, make sure the longer command gets declared first.

# TODO: Factor the messages out into their own file so we don't need this.
# (TODO: Or make m.texts an alias to core.texts...which makes more sense and less sense at the same time...)
from core import texts
import logging
import re

def implement(m):
    # TODO: Since we're basically grabbing our character object at the beginning of every command so far anyway, we should consider just having the Mica class pass it in to begin with.
    # TODO: Write docstrings for everything, then implement `help'.
    @m.command("look")
    @m.command("l")
    def do_look(link, text):
        me = m.get_thing(m.client_states[link]['character'])

        text = text.strip()
        if text != '':
            # This will raise a CommandProcessingError for us if it can't find anything.
            tgt = m.pov_get_thing_by_name(link, text)
        else:
            tgt = me.location()
            if tgt is None:
                link.write(texts['youAreNowhere'])
                return

        link.write(m.line(tgt.display_name()))
        link.write(m.line(tgt.get('desc', texts['descMissing'])))
        contents = ", ".join([x.display_name() for x in tgt.contents()])
        if len(contents) > 0:
            link.write(m.line(texts['beforeListingContents'] + contents))

    @m.command("make")
    def do_make(link, text):
        me = m.get_thing(m.client_states[link]['character'])

        text = text.strip()
        if len(text) < 0:
            raise CommandProcessingError(texts['cmdSyntax'] % 'make name of object')

        result = m.add_thing(me, text)
        link.write(m.line(texts['madeThing'] % result.display_name()))

    @m.command("set")
    def do_set(link, text):
        me = m.get_thing(m.client_states[link]['character'])

        text = text.strip()
        parse_result = re.match("^([^:]+):([^=:]+)=(.*)$", text)
        if parse_result is None:
            raise CommandProcessingError(texts['cmdSyntax'] % 'set object=param:value')

        tgt = m.pov_get_thing_by_name(parse_result[1])
        attr = parse_result[2]
        val = parse_result[3]

        tgt[attr] = val
        link.write(m.line(texts['setAttrToValSuccess'] % (attr, val)))

    @m.command("inventory")
    @m.command("i")
    def do_inventory(link, text):
        me = m.get_thing(m.client_states[link]['character'])

        things = me.contents()
        if len(things) > 0:
            link.write(m.line(texts['beforeListingInventory']))
            for thing in things:
                link.write(m.line(thing.display_name()))
        else:
            link.write(m.line(texts['carryingNothing']))

    @m.command("crash")
    def do_badly(link, text):
        raise Exception("This isn't a good thing.")
