#!/usr/bin/env python
##
##  Minecraft Chatlog Proxy by Yusuke Shinyama
##  * this program is in public domain *
##
##  usage: $ python mcproxy.py mcserver.example.com
##

import sys
import re
import time
import socket
import asyncore
from struct import unpack


def toshort(x):
    return unpack('>h', x)[0]
def toint(x):
    return unpack('>i', x)[0]
def dist((x0,y0,z0),(x1,y1,z1)):
    return abs(x0-x1)+abs(y0-y1)+abs(z0-z1)


##  MCParser
##  (for Beta protocol. cf. http://mc.kev009.com/Protocol)
##
class MCParser(object):

    debugfp = None
    
    def __init__(self):
        self._stack = [(self._main,None)]
        self._pos = 0
        return

    def feed(self, data):
        i = 0
        if self.debugfp is not None:
            print >>self.debugfp, 'feed: %r: %r' % (self._pos, self._stack)
            self.debugfp.flush()
        while i < len(data):
            (parse,arg) = self._stack[-1]
            if parse(data[i], arg):
                i += 1
        self._pos += len(data)
        return

    def _push(self, func, arg=None):
        if arg is None:
            arg = ['']
        elif isinstance(arg, int):
            arg = [arg]
        self._stack.append((func, arg))
        return
    
    def _pop(self):
        self._stack.pop()
        return

    def _bytes(self, c, arg):
        if 0 < arg[0]:
            arg[0] -= 1
            return True
        elif 0 == arg[0]:
            self._pop()
            return False
        else:
            assert 0
    
    def _str8(self, c, arg):
        arg[0] += c
        if len(arg[0]) == 2:
            self._pop()
            self._push(self._bytes, toshort(arg[0]))
        return True

    def _str16(self, c, arg):
        arg[0] += c
        if len(arg[0]) == 2:
            self._pop()
            self._push(self._bytes, toshort(arg[0])*2)
        return True

    def _chat(self, nbytes):
        self._push(self._bytes, nbytes)
        return

    def _player_pos(self, x, y, z):
        return
    
    def _mob_spawn(self, eid, t, x, y, z):
        return

    def _map_chunk(self, (x,y,z), (sx,sy,sz), nbytes):
        self._push(self._bytes, nbytes)
        return
        
    def _special_03(self, c, arg):
        arg[0] += c
        if len(arg[0]) == 2:
            self._pop()
            self._chat(toshort(arg[0])*2)
        return True
    
    def _special_0b(self, c, arg):
        arg[0] += c
        if len(arg[0]) == 33:
            self._pop()
            (x,y,s,z,ground) = unpack('>ddddB', arg[0])
            self._player_pos(x,y,z)
        return True
        
    def _special_0d(self, c, arg):
        arg[0] += c
        if len(arg[0]) == 41:
            self._pop()
            (x,y,s,z,yaw,pitch,ground) = unpack('>ddddffB', arg[0])
            self._player_pos(x,y,z)
        return True
        
    def _special_0f(self, c, arg):
        arg[0] += c
        if len(arg[0]) == 2:
            self._pop()
            if 0 <= toshort(arg[0]):
                self._push(self._bytes, 3)
        return True
    
    def _special_17(self, c, arg):
        arg[0] += c
        if len(arg[0]) == 4:
            self._pop()
            if 0 < toint(arg[0]):
                self._push(self._bytes, 6)
        return True
    
    def _special_18(self, c, arg):
        arg[0] += c
        if len(arg[0]) == 19:
            self._pop()
            (eid,t,x,y,z,yaw,pitch) = unpack('>ibiiibb', arg[0])
            self._mob_spawn(eid,t,x/32.0,y/32.0,z/32.0)
        return True
    
    def _special_33(self, c, arg):
        arg[0] += c
        if len(arg[0]) == 17:
            self._pop()
            (x,y,z,sx,sy,sz,nbytes) = unpack('>ihibbbi', arg[0])
            self._map_chunk((x,y,z), (sx,sy,sz), nbytes)
        return True

    def _special_34(self, c, arg):
        arg[0] += c
        if len(arg[0]) == 2:
            self._pop()
            n = toshort(arg[0])
            self._push(self._bytes, n*4)
        return True

    def _special_3c(self, c, arg):
        arg[0] += c
        if len(arg[0]) == 4:
            self._pop()
            n = toint(arg[0])
            self._push(self._bytes, n*3)
        return True

    def _special_66(self, c, arg):
        arg[0] += c
        if len(arg[0]) == 2:
            self._pop()
            if toshort(arg[0]) != -1:
                self._push(self._bytes, 3)
        return True

    def _special_68(self, c, arg):
        arg[0] += c
        if len(arg[0]) == 2:
            self._pop()
            self._push(self._special_68_2, toshort(arg[0]))
        return True
    def _special_68_2(self, c, arg):
        if arg[0]:
            arg[0] -= 1
            self._push(self._special_68_3)
        else:
            self._pop()
        return False
    def _special_68_3(self, c, arg):
        arg[0] += c
        if len(arg[0]) == 2:
            self._pop()
            if toshort(arg[0]) != -1:
                self._push(self._bytes, 3)
        return True

    def _special_83(self, c, arg):
        self._pop()
        self._push(self._bytes, ord(c))
        return True

    def _metadata(self, c, arg):
        c = ord(c)
        if c == 0x7f:
            self._pop()
        else:
            x = (c >> 5)
            if x == 0:
                self._push(self._bytes, 1)
            elif x == 1:
                self._push(self._bytes, 2)
            elif x == 2:
                self._push(self._bytes, 4)
            elif x == 3:
                self._push(self._bytes, 4)
            elif x == 4:
                self._push(self._str16)
            elif x == 5:
                self._push(self._bytes, 5)
            elif x == 6:
                self._push(self._bytes, 12)
            else:
                assert 0
        return True
        
    def _main(self, c, arg):
        if self.debugfp is not None:
            print >>self.debugfp, 'main: %02x' % ord(c)
        c = ord(c)
        if c == 0x00:
            self._push(self._bytes, 4)
        elif c == 0x01:
            self._push(self._bytes, 16)
            self._push(self._str16)
            self._push(self._bytes, 4)
        elif c == 0x02:
            self._push(self._str16)
        elif c == 0x03:
            self._push(self._special_03)
        elif c == 0x04:
            self._push(self._bytes, 8)
        elif c == 0x05:
            self._push(self._bytes, 10)
        elif c == 0x06:
            self._push(self._bytes, 12)
        elif c == 0x07:
            self._push(self._bytes, 9)
        elif c == 0x08:
            self._push(self._bytes, 8)
        elif c == 0x09:
            self._push(self._bytes, 13)
        elif c == 0x0a:
            self._push(self._bytes, 1)
        elif c == 0x0b:
            self._push(self._special_0b)
        elif c == 0x0c:
            self._push(self._bytes, 9)
        elif c == 0x0d:
            self._push(self._special_0d)
        elif c == 0x0e:
            self._push(self._bytes, 11)
        elif c == 0x0f:
            self._push(self._special_0f)
            self._push(self._bytes, 10)
        elif c == 0x10:
            self._push(self._bytes, 2)
        elif c == 0x11:
            self._push(self._bytes, 14)
        elif c == 0x12:
            self._push(self._bytes, 5)
        elif c == 0x13:
            self._push(self._bytes, 5)
        elif c == 0x14:
            self._push(self._bytes, 16)
            self._push(self._str16)
            self._push(self._bytes, 4)
        elif c == 0x15:
            self._push(self._bytes, 24)
        elif c == 0x16:
            self._push(self._bytes, 8)
        elif c == 0x17:
            self._push(self._special_17)
            self._push(self._bytes, 17)
        elif c == 0x18:
            self._push(self._metadata)
            self._push(self._special_18)
        elif c == 0x19:
            self._push(self._bytes, 16)
            self._push(self._str16)
            self._push(self._bytes, 4)
        elif c == 0x1a:
            self._push(self._bytes, 18)
        elif c == 0x1b:
            self._push(self._bytes, 18)
        elif c == 0x1c:
            self._push(self._bytes, 10)
        elif c == 0x1d:
            self._push(self._bytes, 4)
        elif c == 0x1e:
            self._push(self._bytes, 4)
        elif c == 0x1f:
            self._push(self._bytes, 7)
        elif c == 0x20:
            self._push(self._bytes, 6)
        elif c == 0x21:
            self._push(self._bytes, 9)
        elif c == 0x22:
            self._push(self._bytes, 18)
        elif c == 0x26:
            self._push(self._bytes, 5)
        elif c == 0x27:
            self._push(self._bytes, 8)
        elif c == 0x28:
            self._push(self._metadata)
            self._push(self._bytes, 4)
        elif c == 0x29:
            self._push(self._bytes, 8)
        elif c == 0x2a:
            self._push(self._bytes, 5)
        elif c == 0x2b:
            self._push(self._bytes, 4)
        elif c == 0x32:
            self._push(self._bytes, 9)
        elif c == 0x33:
            self._push(self._special_33)
        elif c == 0x34:
            self._push(self._special_34)
            self._push(self._bytes, 8)
        elif c == 0x35:
            self._push(self._bytes, 11)
        elif c == 0x36:
            self._push(self._bytes, 12)
        elif c == 0x3c:
            self._push(self._special_3c)
            self._push(self._bytes, 28)
        elif c == 0x3d:
            self._push(self._bytes, 17)
        elif c == 0x46:
            self._push(self._bytes, 2)
        elif c == 0x47:
            self._push(self._bytes, 17)
        elif c == 0x64:
            self._push(self._bytes, 1)
            self._push(self._str16)
            self._push(self._bytes, 2)
        elif c == 0x65:
            self._push(self._bytes, 1)
        elif c == 0x66:
            self._push(self._special_66)
            self._push(self._bytes, 7)
        elif c == 0x67:
            self._push(self._special_66)
            self._push(self._bytes, 3)
        elif c == 0x68:
            self._push(self._special_68)
            self._push(self._bytes, 1)
        elif c == 0x69:
            self._push(self._bytes, 5)
        elif c == 0x6a:
            self._push(self._bytes, 4)
        elif c == 0x6b:
            self._push(self._bytes, 8)
        elif c == 0x82:
            self._push(self._str16)
            self._push(self._str16)
            self._push(self._str16)
            self._push(self._str16)
            self._push(self._bytes, 10)
        elif c == 0x83:
            self._push(self._special_83, 4)
            self._push(self._bytes, 4)            
        elif c == 0xc8:
            self._push(self._bytes, 5)
        elif c == 0xc9:
            self._push(self._bytes, 3)
            self._push(self._str16)
        elif c == 0xfe:
            pass
        elif c == 0xff:
            self._push(self._str16)
        else:
            assert 0
        return True
    

##  MCChatLogger
##
class MCChatLogger(MCParser):

    def __init__(self, fp):
        MCParser.__init__(self)
        self.fp = fp
        if 0:
            import gdbm
            self.db = gdbm.open('chunks.db', 'c')
        return
    
    def _write(self, s):
        s = re.sub(ur'\xa7.', '', s)
        line = time.strftime('%Y-%m-%d %H:%M:%S')+' '+s.encode('utf-8')
        self.fp.write(line+'\n')
        self.fp.flush()
        print line
        return

    def _chat(self, nbytes):
        self._push(self._chat_dump, [nbytes, ''])
        return
    def _chat_dump(self, c, arg):
        if arg[0]:
            arg[0] -= 1
            arg[1] += c
            return True
        else:
            s = arg[1].decode('utf-16be')
            self._write(s)
            self._pop()
            return False
    
    def _map_chunk_0(self, (x,y,z), (sx,sy,sz), nbytes):
        key = '%d.%d.%d' % (x,y,z)
        self._push(self._map_dump, [nbytes,key,''])
        return
    def _map_dump(self, c, arg):
        arg[2] += c
        if 0 < arg[0]:
            arg[0] -= 1
            return True
        else:
            (_,key,value) = arg
            self.db[key] = value
            self._pop()
            return False
        

##  MCPosLogger
##
class MCPosLogger(MCParser):

    INTERVAL = 60

    def __init__(self, fp):
        MCParser.__init__(self)
        self.fp = fp
        self._t = -1
        self._p = None
        return
    
    def _write(self, s):
        line = time.strftime('%Y-%m-%d %H:%M:%S')+' '+s.encode('utf-8')
        self.fp.write(line+'\n')
        self.fp.flush()
        print line
        return

    def _player_pos(self, x, y, z):
        t = int(time.time())
        p = (int(x), int(y), int(z))
        if t < self._t and (self._p is not None and dist(p, self._p) < 50): return
        self._t = t + self.INTERVAL
        self._p = p
        self._write(' *** (%d, %d, %d)' % p)
        return


##  Server
##
class Server(asyncore.dispatcher):

    def __init__(self, port, destaddr, output, bindaddr="127.0.0.1"):
        asyncore.dispatcher.__init__(self)
        self.output = output
        self.destaddr = destaddr
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind((bindaddr, port))
        self.listen(1)
        self.session = 0
        print >>sys.stderr, "Listening: %s:%d" % (bindaddr, port)
        return

    def handle_accept(self):
        (conn, (addr,port)) = self.accept()
        print >>sys.stderr, "Accepted:", addr
        path = time.strftime(self.output)
        fp = file(path, 'a')
        print >>sys.stderr, "output:", path
        chatlogger = MCChatLogger(fp)
        poslogger = MCPosLogger(fp)
        proxy = Proxy(conn, self.session, poslogger, chatlogger)
        proxy.connect_remote(self.destaddr)
        self.session += 1
        return


##  Proxy
##
class Proxy(asyncore.dispatcher):

    local2remotefp = None
    remote2localfp = None

    def __init__(self, sock, session,
                 plocal2remote, premote2local):
        self.plocal2remote = plocal2remote
        self.premote2local = premote2local
        self.session = session
        self.sendbuffer = ""
        self.client = None
        self.disp("BEGIN")
        asyncore.dispatcher.__init__(self, sock)
        return

    # overridable methods
    def local2remote(self, s):
        self.plocal2remote.feed(s)
        return s
    def remote2local(self, s):
        self.premote2local.feed(s)
        return s

    def connect_remote(self, addr):
        assert not self.client, "already connected"
        self.addr = addr
        self.disp("(connecting to %s:%d)" % self.addr)
        self.client = Client(self)
        self.client.connect(addr)
        return

    def disconnect_remote(self):
        assert self.client, "not connected"
        self.client.close()
        self.client = None
        return

    def disp(self, s):
        print >>sys.stderr, "SESSION %s:" % self.session, s
        return

    def remote_connected(self):
        self.disp("(connected to remote %s:%d)" % self.addr)
        return

    def remote_closed(self):
        self.disp("(closed by remote %s:%d)" % self.addr)
        self.client = None
        if not self.sendbuffer:
            self.handle_close()
        return

    def remote_read(self, data):
        if data:
            if self.remote2localfp is not None:
                self.remote2localfp.write(data)
            data = self.remote2local(data)
            if data:
                self.sendbuffer += data
        return

    def handle_read(self):
        data = self.recv(8192)
        if data:
            data = self.local2remote(data)
            if self.local2remotefp is not None:
                self.local2remotefp.write(data)
            if data and self.client is not None:
                self.client.remote_write(data)
        return

    def writable(self):
        return 0 < len(self.sendbuffer)

    def handle_write(self):
        n = self.send(self.sendbuffer)
        self.sendbuffer = self.sendbuffer[n:]
        if not self.sendbuffer and self.client is None:
            self.handle_close()
        return

    def handle_close(self):
        if self.client is not None:
            self.disp("(closed by local)")
            self.disconnect_remote()
        self.close()
        self.disp("END")
        return


##  Client
##
class Client(asyncore.dispatcher):

    def __init__(self, proxy):
        self.proxy = proxy
        self.sendbuffer = ""
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        return

    def handle_connect(self):
        self.proxy.remote_connected()
        return

    def handle_close(self):
        self.proxy.remote_closed()
        self.close()
        return

    def handle_read(self):
        self.proxy.remote_read(self.recv(8192))
        return

    def remote_write(self, data):
        self.sendbuffer += data
        return

    def writable(self):
        return 0 < len(self.sendbuffer)

    def handle_write(self):
        n = self.send(self.sendbuffer)
        self.sendbuffer = self.sendbuffer[n:]
        return

# main
def main(argv):
    import getopt
    def usage():
        print 'usage: %s [-d] [-o output] [-p port] [-t testfile] hostname:port' % argv[0]
        return 100
    try:
        (opts, args) = getopt.getopt(argv[1:], 'do:p:t:')
    except getopt.GetoptError:
        return usage()
    debug = 0
    output = 'chatlog-%Y%m%d.txt'
    listen = 25565
    testfile = None
    for (k, v) in opts:
        if k == '-d': debug += 1
        elif k == '-o': output = v
        elif k == '-p': listen = int(v)
        elif k == '-t': testfile = file(v, 'rb')
    if testfile is not None:
        MCParser.debugfp = sys.stdout
        parser = MCChatLogger(sys.stdout)
        while 1:
            data = testfile.read(4096)
            if not data: break
            parser.feed(data)
        testfile.close()
        return
    if not args: return usage()
    x = args.pop(0)
    if ':' in x:
        (hostname,port) = x.split(':')
        port = int(port)
    else:
        hostname = x
        port = 25565
    if debug:
        MCParser.debugfp = file('parser.log', 'w')
        Proxy.local2remotefp = file('local.log', 'wb')
        Proxy.remote2localfp = file('remote.log', 'wb')
    Server(listen, (hostname, port), output)
    asyncore.loop()
    return

if __name__ == '__main__': sys.exit(main(sys.argv))
