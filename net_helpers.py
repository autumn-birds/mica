import logging

# Socket handler, lifted from my other project
RECV_MAX = 4096 # bytes

class LineBufferingSocketContainer:
   """A base class that helps handle reading from and writing to a socket.
   The I/O is buffered to lines, and telnet control codes (i.e. IAC ...) are dropped."""
   def __init__(self, socket = None):
      self.__b_send_buffer = b''
      self.__b_recv_buffer = b''

      self.connected = False

      self.socket = None

      self.encoding = "utf-8"
      self.linesep = 10         # ASCII/UTF-8 newline

      if socket != None:
         self.attach_socket(socket)

   def write_str(self, data):
      """Write a string to the underlying socket."""
      assert type(data) == str
      self.__b_send_buffer += data.encode(self.encoding)
      self.flush()

   def write_line(self, line):
      """Write a TextLine to the underlying socket."""
      assert type(line) == TextLine
      self.__b_send_buffer += line.as_bytes()
      self.flush()

   def write(self, data):
      """Write some bytes to the underlying socket."""
      if type(data) is str:
        data = data.encode(self.encoding)

      assert type(data) == bytes
      self.__b_send_buffer += data
      self.flush()

   def flush(self):
      """Send as much buffered input as the socket will allow, but only attempt to do so up to the end of the last complete line."""
      assert self.socket != None
      assert self.connected

      while len(self.__b_send_buffer) > 0 and self.linesep in self.__b_send_buffer:
         try:
            t = self.__b_send_buffer.index(self.linesep)
            n_bytes = self.socket.send(self.__b_send_buffer[:t+1])
            self.__b_send_buffer = self.__b_send_buffer[n_bytes:]

         except (BlockingIOError):
            logging.info("Note: BlockingIOError in flush() call")
            break

         except OSError:
            logging.error("Got an OSError in flush() call")
            break

   def read(self):
      """Read as much data as the socket will provide.
      Returns a pair like `([list of TextLine's or empty], found_eof?)'.
      If found_eof? is true, the connection has probably died."""
      assert self.connected
      assert self.socket != None

      has_eof = False

      try:
         data = b''
         while True:
            data = self.socket.recv(RECV_MAX)
            self.__b_recv_buffer += data
            if len(data) < RECV_MAX:
               # If the length of data returned by a read() call is 0, that actually means the
               # remote side closed the connection.  If there's actually no data to be read,
               # you get a BlockingIOError or one of its SSL-based cousins instead.
               if len(data) == 0:
                  has_eof = True
               break
            data = b''

      except BlockingIOError: #, ssl.SSLWantReadError, ssl.SSLWantWriteError):
         pass

      except OSError:
         logging.error("Got an OSError in read() call")
         raise

      except ConnectionResetError:
         has_eof = True

      q = []

      # Telnet codes are a problem.  TODO: Improve this super hacky solution, which just involves
      # ... completely removing them from the input stream (except for IAC IAC / 255 255.)

      stripped = b''

      IAC = 255
      DONT = 254
      DO = 253
      WONT = 252
      WILL = 251

      in_command = False

      # Speaking of awful hacks, this is probably not very efficient at all:

      x = 0
      while x < len(self.__b_recv_buffer):
         if in_command:
            if self.__b_recv_buffer[x] == IAC:
               stripped += bytes([IAC])
               in_command = False
            elif self.__b_recv_buffer[x] <= DONT and self.__b_recv_buffer[x] >= WILL:
               pass
            else:
               # TODO: Figure out if there are Telnet codes that will be baffled by this
               # (are they all guaranteed to be 2 bytes long except for IAC <DODONTWILLWONT> XYZ?)
               in_command = False
         else:
            if self.__b_recv_buffer[x] == IAC:
               in_command = True
            else:
               stripped += self.__b_recv_buffer[x:x+1]
         x += 1

      # The best we can do for a record separator in this case is a byte or byte sequence that
      # means 'newline'. We go with one byte for now for simplicity & because it works with
      # UTF-8/ASCII at least, which comprises most things we're interested in.

      while self.linesep in stripped:
         t = stripped.index(self.linesep)
         q += [stripped[:t+1].decode('utf-8')]
         stripped = stripped[t+1:]

      self.__b_recv_buffer = stripped

      # Make sure it starts in in_command mode again next time around in case the read() call
      # left us in the middle of a command, which I don't think is *likely* but could happen.
      # (The rest of the command will get tacked on after the IAC, which will ensure
      # the thing goes back into command mode immediately prior.)

      if in_command:
         self.__b_recv_buffer += bytes([IAC])     # Was __send_buffer in the original.  Terrifying bug lurking in wait?  Not sure.

      return (q, has_eof)

   def attach_socket(self, socket):
      """Set up `self' to work with `socket'."""
      socket.setblocking(False)
      self.socket = socket
      self.connected = True

   def handle_disconnect(self):
      """Call this function when the remote end closed the connection to nullify and make false the appropriate variables."""
      self.socket = None
      self.connected = False