# Command definitions.
# Watch out, order may be important -- if one command's full name is the beginning of another command's name, make sure the longer command gets declared first.

# TODO: Factor the messages out into their own file so we don't need this.
# (TODO: Or make m.texts an alias to core.texts...which makes more sense and less sense at the same time...)
#import core
from core import texts
import logging

def implement(m):
    @m.command("look")
    def do_look(link, text):
        me = m.get_thing(m.client_states[link]['character'])
        assert me != -1

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
            link.write(m.line(contents))