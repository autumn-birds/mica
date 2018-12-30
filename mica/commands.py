# Command definitions.
# Watch out, order may be important -- if one command's full name is the beginning of another command's name, make sure the longer command gets declared first.

from core import texts
from core import CommandProcessingError
import logging
import re

def implement(m):
    # TODO: Since we're basically grabbing our character object at the beginning of every command so far anyway, we should consider just having the Mica class pass it in to begin with.
    # (Maybe call like cmd(link, text, character, state) ?)

    # TODO: Write docstrings for everything, then implement `help'.

    #
    # Convenience functions...
    def get_int(obj, key):
        try:
            return int(obj[key])
        except ValueError:
            raise CommandProcessingError("Couldn't convert parameter %s of object %d to int" % (key, obj.id))
        except KeyError:
            return None

    def set_int(obj, key, val):
        assert type(val) is int
        obj[key] = repr(val)


    #
    # Permissions
    # I'm not sure if this is the best way to do it.
    PERMISSION_GUEST = 10
    PERMISSION_BUILDER = 20
    PERMISSION_WIZARD = 30

    def get_permission(char):
        if char.id == 1:
            return PERMISSION_WIZARD

        l = char.get('privilege_level', -1)
        if l is -1:
            l = PERMISSION_GUEST
            char['privilege_level'] = l

        return l

    def check_permission(char, level):
        if get_permission(char) < level:
            raise CommandProcessingError(texts['noPermission'])


    #
    # Basic interaction commands.
    @m.command("look")
    @m.command("l")
    def do_look(link, text):
        me = m.get_thing(m.client_states[link]['character'])
        check_permission(me, PERMISSION_GUEST)

        text = text.strip()
        if len(text) > 0:
            # This will raise a CommandProcessingError for us if it can't find anything.
            tgt = m.pov_get_thing_by_name(link, text)
        else:
            tgt = me.location()
            if tgt is None:
                link.write(texts['youAreNowhere'])
                return

        link.write(m.line(tgt.display_name()))
        link.write(m.line(tgt.get('desc', texts['descMissing'])))

        contents = tgt.contents()

        objects = []
        exits = []
        for x in contents:
            if x.destination() is None:
                objects.append(x)
            else:
                exits.append(x)

        if len(objects) > 0:
            link.write(m.line(texts['beforeListingObjects'] + ", ".join([x.display_name() for x in objects])))

        if len(exits) > 0:
            link.write(m.line(texts['beforeListingExits'] + ", ".join([x.display_name() for x in exits])))

    @m.command("say")
    @m.prefix_command('"')
    def do_say(link, text):
        me = m.get_thing(m.client_states[link]['character'])
        check_permission(me, PERMISSION_GUEST)

        text = text.strip()
        if len(text) < 1:
            raise CommandProcessingError(texts['cmdSyntax'] % 'say hello || "hello')

        where = me.location()
        if where is not None:
            where.tell(texts['characterSays'] % (me.name(), text))

    @m.command("pose")
    @m.prefix_command(":")
    def do_say(link, text):
        me = m.get_thing(m.client_states[link]['character'])
        check_permission(me, PERMISSION_GUEST)

        text = text.strip()
        if len(text) < 1:
            raise CommandProcessingError(texts['cmdSyntax'] % 'pose laughs. || :laughs.')

        where = me.location()
        if where is not None:
            where.tell(texts['characterPoses'] % (me.name(), text))

    @m.command("inventory")
    @m.command("i")
    def do_inventory(link, text):
        me = m.get_thing(m.client_states[link]['character'])
        check_permission(me, PERMISSION_GUEST)

        things = me.contents()
        if len(things) > 0:
            link.write(m.line(texts['beforeListingInventory']))
            for thing in things:
                link.write(m.line(thing.display_name()))
        else:
            link.write(m.line(texts['carryingNothing']))



    #
    # Building-related commands.
    @m.command("jump")
    def do_jump(link, text):
        me = m.get_thing(m.client_states[link]['character'])
        check_permission(me, PERMISSION_BUILDER)

        text = text.strip()
        if len(text) < 1:
            raise CommandProcessingError(texts['cmdSyntax'] % 'jump #400')

        dest = m.pov_get_thing_by_name(link, text)
        me.move(dest)
        m.on_text(link, "look")

    # Actually not a command, but called by two commands that do almost the same thing but not quite.
    def try_create_thing(text, maker):
        parsed = re.match("^([^=]+)(=[^=]+)?$", text)
        if parsed is None or len(parsed[1].strip()) < 2:
            return False # User didn't write the command right

        new_thing = m.add_thing(maker, parsed[1])
        if parsed[2] is not None:
            # parsed[2] is the =desc... part, and will always start with an =, which we don't want
            new_thing['desc'] = parsed[2][1:].strip()

        return new_thing

    @m.command("make")
    def do_make(link, text):
        me = m.get_thing(m.client_states[link]['character'])
        check_permission(me, PERMISSION_BUILDER)

        text = text.strip()
        result = try_create_thing(text, me)
        if result is False:
            raise CommandProcessingError(texts['cmdSyntax'] % 'make name of object[= desc of object]')

        link.write(m.line(texts['madeThing'] % result.display_name()))

    @m.command("build")
    def do_build(link, text):
        me = m.get_thing(m.client_states[link]['character'])
        check_permission(me, PERMISSION_BUILDER)

        do_tel = False
        if text[0:2] == '-t':
            do_tel = True
            text = text[2:].strip()

        new_thing = try_create_thing(text, me)
        if new_thing is False:
            raise CommandProcessingError(texts['cmdSyntax'] % 'build [-t] name of object[=desc of object]')

        new_thing.move(new_thing)

        if do_tel:
            me.move(new_thing)
            do_look(link, "")
        else:
            link.write(m.line(texts['builtThing'] % (new_thing.name(), new_thing.id)))

    @m.command("open")
    def do_open(link, text):
        me = m.get_thing(m.client_states[link]['character'])
        check_permission(me, PERMISSION_BUILDER)

        parsed = re.match("^([^=]+)=([^=]+)$", text)
        if parsed is None or parsed[1] is None or parsed[2] is None:
            raise CommandProcessingError(texts['cmdSyntax'] % 'open name of exit=target')

        name = parsed[1].strip()
        target = m.pov_get_thing_by_name(link, parsed[2].strip())

        new_thing = m.add_thing(me, name)
        new_thing.move(me.location())
        new_thing.set_destination(target)

        link.write(m.line(texts['openedPath'] % (new_thing.display_name(), target.display_name())))


    #
    # Administration / superuser commands
    @m.command("set")
    def do_set(link, text):
        me = m.get_thing(m.client_states[link]['character'])
        check_permission(me, PERMISSION_WIZARD)

        text = text.strip()
        parse_result = re.match("^([^:]+):([^=:]+)=(.*)$", text)
        if parse_result is None:
            raise CommandProcessingError(texts['cmdSyntax'] % 'set object:param=value')

        tgt = m.pov_get_thing_by_name(link, parse_result[1])
        attr = parse_result[2]
        val = parse_result[3]

        tgt[attr] = val
        link.write(m.line(texts['setAttrToValSuccess'] % (attr, val)))

    @m.command("examine")
    @m.command("ex")
    def do_exam(link, text):
        me = m.get_thing(m.client_states[link]['character'])
        check_permission(me, PERMISSION_WIZARD)

        tgt = m.pov_get_thing_by_name(link, text.strip())
        link.write(m.line(texts['examiningThing'] % tgt.display_name()))

        if tgt.owner() is not None:
            link.write(m.line(texts['thingOwner'] % (tgt.owner().display_name())))
        else:
            link.write(m.line(texts['thingHasNoOwner']))

        for k, v in tgt.items():
            link.write(m.line(texts['thingParameterValue'] % (k, repr(v))))


    #
    # Debugging commands.
    @m.command("crash")
    def do_badly(link, text):
        raise Exception("This isn't a good thing.")

    m.login_commands.append("look")
