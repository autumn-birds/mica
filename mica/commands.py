# Command definitions.
# Watch out, order may be important -- if one command's full name is the beginning of another command's name, make sure the longer command gets declared first.

# TODO: Factor the messages out into their own file so we don't need this.
# (TODO: Or make m.texts an alias to core.texts...which makes more sense and less sense at the same time...)
import core

def implement(m):
    @m.command("look")
    def do_look(link, text): #Should we be passing in the state object, instead of looking it up in client_states every time?
        me = m.client_states[link]['character']
        assert me != -1

        text.strip()
        if text != '':
            tgt = m.pov_get_thing_by_name(link, text)
        else:
            tgt = m.get_location(me)
            if tgt is None:
                link.write(m.line(core.texts['youAreNowhere']))
                return

        here = m.get_thing(tgt)
        print("here = %s", repr(here))
        if here is None:
            # The functions to find out the thing from the database didn't work.
            link.write(m.line(core.texts['thing404'] % '(this is a big problem)'))

        link.write(m.line(m.thing_displayname(here[0], tgt)))
        link.write(here[1] + m.line(''))

        print("to get_contents: %s" % repr(here[0]))
        contents = ", ".join([m.thing_displayname(m.get_thing(x)[0], x) for x in self.get_contents(tgt)])
        if len(contents) > 0:
            link.write(m.line(core.texts['beforeListingContents'] + contents))