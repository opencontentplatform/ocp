#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    A pure python ping implementation using raw sockets.

    Compatibility:
        OS: Linux, Windows, MacOSX
        Python: 2.6 - 3.5

    Note that due to the usage of RAW sockets root/Administrator
    privileges are required.

    Derived from ping.c distributed in Linux's netkit. That code is
    copyright (c) 1989 by The Regents of the University of California.
    That code is in turn derived from code written by Mike Muuss of the
    US Army Ballistic Research Laboratory in December, 1983 and
    placed in the public domain. They have my thanks.

    Copyright (c) Matthew Dixon Cowles, <http://www.visi.com/~mdc/>.
    Distributable under the terms of the GNU General Public License
    version 2. Provided with no warranties of any sort.

    website: https://github.com/l4m3rx/python-ping

"""
from __future__ import division, print_function

# TODO Remove any calls to time.sleep
# This would enable extension into larger frameworks that aren't multi threaded.
import os
import sys
import traceback
import time
import array
import socket
import struct
import select
import signal

if __name__ == '__main__':
    import argparse


try:
    from _thread import get_ident
except ImportError:
    def get_ident(): return 0

if sys.platform == "win32":
    # On Windows, the best timer is time.clock()
    default_timer = time.clock
else:
    # On most other platforms the best timer is time.time()
    default_timer = time.time

# ICMP parameters

ICMP_ECHOREPLY = 0  # Echo reply (per RFC792)
ICMP_ECHO = 8  # Echo request (per RFC792)
ICMP_ECHO_IPV6 = 128  # Echo request (per RFC4443)
ICMP_ECHO_IPV6_REPLY = 129  # Echo request (per RFC4443)
ICMP_MAX_RECV = 2048  # Max size of incoming buffer

MAX_SLEEP = 1000


class MStats2(object):

    def __init__(self):
        self._this_ip = '0.0.0.0'
        self.reset()

    def reset(self):
        self._timing_list = []
        self._packets_sent = 0
        self._packets_rcvd = 0

        self._reset_statistics()

    @property
    def thisIP(self):
        return self._this_ip

    @thisIP.setter
    def thisIP(self, value):
        self._this_ip = value

    @property
    def pktsSent(self):
        return self._packets_sent

    @property
    def pktsRcvd(self):
        return self._packets_rcvd

    @property
    def pktsLost(self):
        return self._packets_sent - self._packets_rcvd

    @property
    def minTime(self):
        return min(self._timing_list) if self._timing_list else None

    @property
    def maxTime(self):
        return max(self._timing_list) if self._timing_list else None

    @property
    def totTime(self):
        if self._total_time is None:
            self._total_time = sum(self._timing_list)
        return self._total_time

    def _get_mean_time(self):
        if self._mean_time is None:
            if len(self._timing_list) > 0:
                self._mean_time = self.totTime / len(self._timing_list)
        return self._mean_time
    mean_time = property(_get_mean_time)
    avrgTime = property(_get_mean_time)

    @property
    def median_time(self):
        if self._median_time is None:
            self._median_time = self._calc_median_time()
        return self._median_time

    @property
    def pstdev_time(self):
        """Returns the 'Population Standard Deviation' of the set."""
        if self._pstdev_time is None:
            self._pstdev_time = self._calc_pstdev_time()
        return self._pstdev_time

    @property
    def fracLoss(self):
        if self._frac_loss is None:
            if self.pktsSent > 0:
                self._frac_loss = self.pktsLost / self.pktsSent
        return self._frac_loss

    def packet_sent(self, n=1):
        self._packets_sent += n

    def packet_received(self, n=1):
        self._packets_rcvd += n

    def record_time(self, value):
        self._timing_list.append(value)
        self._reset_statistics()

    def _reset_statistics(self):
        self._total_time = None
        self._mean_time = None
        self._median_time = None
        self._pstdev_time = None
        self._frac_loss = None

    def _calc_median_time(self):
        n = len(self._timing_list)
        if n == 0:
            return None
        if n & 1 == 1:  # Odd number of samples? Return the middle.
            return sorted(self._timing_list)[n//2]
        else:  # Even number of samples? Return the mean of the two middle samples.
            halfn = n // 2
            return sum(sorted(self._timing_list)[halfn:halfn+2]) / 2

    def _calc_sum_square_time(self):
        mean = self.mean_time
        return sum(((t - mean)**2 for t in self._timing_list))

    def _calc_pstdev_time(self):
        pvar = self._calc_sum_square_time() / len(self._timing_list)
        return pvar**0.5


# Used as 'global' variale so we can print
# stats when exiting by signal
#myStats = MStats2()


def _checksum(source_string):
    """
    A port of the functionality of in_cksum() from ping.c
    Ideally this would act on the string as a series of 16-bit ints (host
    packed), but this works.
    Network data is big-endian, hosts are typically little-endian
    """
    if (len(source_string) % 2):
        source_string += "\x00"
    converted = array.array("H", source_string)
    if sys.byteorder == "big":
        converted.bytewap()
    val = sum(converted)

    val &= 0xffffffff  # Truncate val to 32 bits (a variance from ping.c, which
    # uses signed ints, but overflow is unlikely in ping)

    val = (val >> 16) + (val & 0xffff)  # Add high 16 bits to low 16 bits
    val += (val >> 16)  # Add carry from above (if any)
    answer = ~val & 0xffff  # Invert and truncate to 16 bits
    answer = socket.htons(answer)

    return answer


def single_ping(destIP, hostname, timeout, mySeqNumber, numDataBytes,
                myStats=None, ipv6=False, verbose=True, sourceIP=None, logger=None):
    """
    Returns either the delay (in ms) or None on timeout.
    """
    delay = None

    if ipv6:
        try:  # One could use UDP here, but it's obscure
            mySocket = socket.socket(socket.AF_INET6, socket.SOCK_RAW,
                                     socket.getprotobyname("ipv6-icmp"))
            if sourceIP is not None:
                mySocket.bind((sourceIP, 0))
            mySocket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except OSError as e:
            if verbose:
                if logger:
                    logger.debug("failed. (socket error: '{}')".format(str(e)))
                    logger.debug('Note that python-ping uses RAW sockets and requires root rights.')
                else:
                    print("failed. (socket error: '%s')" % str(e))
                    print('Note that python-ping uses RAW sockets'
                          'and requires root rights.')
            raise  # raise the original error
    else:

        try:  # One could use UDP here, but it's obscure
            mySocket = socket.socket(socket.AF_INET, socket.SOCK_RAW,
                                     socket.getprotobyname("icmp"))
            if sourceIP is not None:
                mySocket.bind((sourceIP, 0))
            mySocket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except OSError as e:
            if verbose:
                if logger:
                    logger.debug("failed. (socket error: '{}')".format(str(e)))
                    logger.debug('Note that python-ping uses RAW sockets and requires root rights.')
                else:
                    print("failed. (socket error: '%s')" % str(e))
                    print('Note that python-ping uses RAW sockets'
                          'and requires root rights.')
            raise  # raise the original error

    my_ID = (os.getpid() ^ get_ident()) & 0xFFFF

    sentTime = _send(mySocket, destIP, my_ID, mySeqNumber, numDataBytes, ipv6,
                     verbose, logger)
    if sentTime is None:
        mySocket.close()
        return delay, (None,)

    if myStats is not None:
        myStats.packet_sent()

    recvTime, dataSize, iphSrcIP, icmpSeqNumber, iphTTL \
        = _receive(mySocket, my_ID, timeout, ipv6)

    mySocket.close()

    if recvTime:
        delay = (recvTime-sentTime)*1000
        if ipv6:
            host_addr = hostname
        else:
            try:
                host_addr = socket.inet_ntop(socket.AF_INET, struct.pack(
                    "!I", iphSrcIP))
            except AttributeError:
                # Python on windows dosn't have inet_ntop.
                host_addr = hostname

        if verbose:
            if logger:
                    logger.debug("{} bytes from {}: icmp_seq={} ttl={} time={} ms".format(dataSize, destIP, icmpSeqNumber, iphTTL, delay))
            else:
                print("%d bytes from %s: icmp_seq=%d ttl=%d time=%.2f ms" % (
                      dataSize, host_addr, icmpSeqNumber, iphTTL, delay)
                      )

        if myStats is not None:
            assert isinstance(myStats, MStats2)
            myStats.packet_received()
            myStats.record_time(delay)
    else:
        delay = None
        if verbose:
            if logger:
                    logger.debug("{} Request timed out.".format(destIP))
            else:
                print("Request timed out.")

    return delay, (recvTime, dataSize, iphSrcIP, icmpSeqNumber, iphTTL)


def _send(mySocket, destIP, myID, mySeqNumber, numDataBytes, ipv6=False,
          verbose=True, logger=None):
    """
    Send one ping to the given >destIP<.
    """
    # destIP  =  socket.gethostbyname(destIP)

    # Header is type (8), code (8), checksum (16), id (16), sequence (16)
    # (numDataBytes - 8) - Remove header size from packet size
    myChecksum = 0

    # Make a dummy header with a 0 checksum.
    if ipv6:
        header = struct.pack(
            "!BbHHh", ICMP_ECHO_IPV6, 0, myChecksum, myID, mySeqNumber
        )
    else:
        header = struct.pack(
            "!BBHHH", ICMP_ECHO, 0, myChecksum, myID, mySeqNumber
        )

    padBytes = []
    startVal = 0x42
    for i in range(startVal, startVal + (numDataBytes - 8)):
        padBytes += [(i & 0xff)]  # Keep chars in the 0-255 range
    # data = bytes(padBytes)
    data = bytearray(padBytes)

    # Calculate the checksum on the data and the dummy header.
    myChecksum = _checksum(header + data)  # Checksum is in network order

    # Now that we have the right checksum, we put that in. It's just easier
    # to make up a new header than to stuff it into the dummy.
    if ipv6:
        header = struct.pack(
            "!BbHHh", ICMP_ECHO_IPV6, 0, myChecksum, myID, mySeqNumber
        )
    else:
        header = struct.pack(
            "!BBHHH", ICMP_ECHO, 0, myChecksum, myID, mySeqNumber
        )

    packet = header + data

    sendTime = default_timer()

    try:
        mySocket.sendto(packet, (destIP, 1))  # Port number is irrelevant
    except OSError as e:
        if verbose:
            if logger:
                    logger.debug("General failure: {}".format(str(e)))
            else:
                print("General failure (%s)" % str(e))
        return
    except socket.error as e:
        if verbose:
            if logger:
                    logger.debug("General failure: {}".format(str(e)))
            else:
                print("General failure (%s)" % str(e))
        return

    return sendTime


def _receive(mySocket, myID, timeout, ipv6=False):
    """
    Receive the ping from the socket. Timeout = in ms
    """
    timeLeft = timeout/1000

    while True:  # Loop while waiting for packet or timeout
        startedSelect = default_timer()
        whatReady = select.select([mySocket], [], [], timeLeft)
        howLongInSelect = (default_timer() - startedSelect)
        if whatReady[0] == []:  # Timeout
            return None, 0, 0, 0, 0

        timeReceived = default_timer()

        recPacket, addr = mySocket.recvfrom(ICMP_MAX_RECV)

        ipHeader = recPacket[:20]

        iphVersion, iphTypeOfSvc, iphLength, iphID, iphFlags, iphTTL, \
            iphProtocol, iphChecksum, iphSrcIP, iphDestIP = struct.unpack(
                "!BBHHHBBHII", ipHeader)

        if ipv6:
            icmpHeader = recPacket[0:8]
        else:
            icmpHeader = recPacket[20:28]

        icmpType, icmpCode, icmpChecksum, icmpPacketID, icmpSeqNumber \
            = struct.unpack("!BBHHH", icmpHeader)

        # Match only the packets we care about
        if (icmpType != 8) and (icmpPacketID == myID):
            dataSize = len(recPacket) - 28
            return timeReceived, (dataSize + 8), iphSrcIP, icmpSeqNumber, \
                iphTTL

        timeLeft = timeLeft - howLongInSelect
        if timeLeft <= 0:
            return None, 0, 0, 0, 0


def _dump_stats(myStats, logger=None):
    """
    Show stats when pings are done
    """
    try:
        if logger:
            logger.debug("\n----%s PYTHON PING Statistics----" % (myStats.thisIP))

            #logger.debug("%d packets transmitted, %d packets received, %0.1f%% packet loss"
            #      % (myStats.pktsSent, myStats.pktsRcvd, 100.0 * myStats.fracLoss))
            logger.debug("%d packets transmitted, %d packets received"
                  % (myStats.pktsSent, myStats.pktsRcvd))

            if myStats.pktsRcvd > 0:
                logger.debug("round-trip (ms)  min/avg/max = %0.1f/%0.1f/%0.1f" % (
                    myStats.minTime, myStats.avrgTime, myStats.maxTime
                ))
                logger.debug('                 median/pstddev = %0.2f/%0.2f' % (
                    myStats.median_time, myStats.pstdev_time
                ))
        else:
            print("\n----%s PYTHON PING Statistics----" % (myStats.thisIP))

            print("%d packets transmitted, %d packets received, %0.1f%% packet loss"
                  % (myStats.pktsSent, myStats.pktsRcvd, 100.0 * myStats.fracLoss))

            if myStats.pktsRcvd > 0:
                print("round-trip (ms)  min/avg/max = %0.1f/%0.1f/%0.1f" % (
                    myStats.minTime, myStats.avrgTime, myStats.maxTime
                ))
                print('                 median/pstddev = %0.2f/%0.2f' % (
                    myStats.median_time, myStats.pstdev_time
                ))

            print('')
    except:
        exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
        print('Exception in doJobEndpoints: {}'.format(exception))
    return


def _signal_handler(signum, frame):
    """ Handle exit via signals """
    global myStats
    _dump_stats(myStats)
    print("\n(Terminated with signal %d)\n" % (signum))
    sys.exit(0)


def _pathfind_ping(destIP, hostname, timeout, mySeqNumber, numDataBytes,
                   ipv6=None, sourceIP=None):
    single_ping(destIP, hostname, timeout,
                mySeqNumber, numDataBytes, ipv6=ipv6, verbose=False, sourceIP=sourceIP)
    time.sleep(0.5)


def verbose_ping(hostname, timeout=3000, count=3,
                 numDataBytes=64, path_finder=False, ipv6=False, sourceIP=None):
    """
    Send >count< ping to >destIP< with the given >timeout< and display
    the result.

    To continuously attempt ping requests, set >count< to None.

    To consume the generator, use the following syntax:
        >>> import ping
        >>> for return_val in ping.verbose_ping('google.ca'):
            pass  # COLLECT YIELDS AND PERFORM LOGIC.

    Alternatively, you can consume the generator by using list comprehension:
        >>> import ping
        >>> consume = list(ping.verbose_ping('google.ca'))

    Via the same syntax, you can successfully get the exit code via:
        >>> import ping
        >>> consume = list(ping.verbose_ping('google.ca'))
        >>> exit_code = consume[-1:]  # The last yield is the exit code.
        >>> sys.exit(exit_code)
    """

    global myStats

    # Handle Ctrl+C
    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, "SIGBREAK"):  # Handle Ctrl-Break /Windows/
        signal.signal(signal.SIGBREAK, _signal_handler)

    myStats = MStats2()  # Reset the stats
    mySeqNumber = 0  # Starting value

    try:
        if ipv6:
            info = socket.getaddrinfo(hostname, None)[0]
            destIP = info[4][0]
        else:
            destIP = socket.gethostbyname(hostname)
        print("\nPYTHON PING %s (%s): %d data bytes" % (hostname, destIP,
                                                        numDataBytes))
    except socket.gaierror as e:
        print("\nPYTHON PING: Unknown host: %s (%s)" % (hostname, str(e)))
        print('')
        return

    myStats.thisIP = destIP

    # This will send packet that we don't care about 0.5 seconds before it
    # starts actually pinging. This is needed in big MAN/LAN networks where
    # you sometimes loose the first packet. (while the switches find the way)
    if path_finder:
        print("PYTHON PING %s (%s): Sending pathfinder ping" % (hostname, destIP))
        _pathfind_ping(destIP, hostname, timeout,
                       mySeqNumber, numDataBytes, ipv6=ipv6, sourceIP=sourceIP)
        print()

    i = 0
    while 1:
        delay = single_ping(destIP, hostname, timeout, mySeqNumber,
                            numDataBytes, ipv6=ipv6, myStats=myStats, sourceIP=sourceIP)
        ## Chris Satterthwaite
        #delay = 0 if delay is None else delay[0]
        delay = 0 if delay is None or delay[0] is None else delay[0]

        mySeqNumber += 1

        # Pause for the remainder of the MAX_SLEEP period (if applicable)
        if (MAX_SLEEP > delay):
            time.sleep((MAX_SLEEP - delay)/1000)

        if count is not None and i < count:
            i += 1
            yield myStats.pktsRcvd
        elif count is None:
            yield myStats.pktsRcvd
        elif count is not None and i >= count:
            break

    _dump_stats(myStats)
    # 0 if we receive at least one packet
    # 1 if we don't receive any packets
    yield not myStats.pktsRcvd



def ping_ip(ipAddr, timeout=3000, maxTries=3, logger=None, numDataBytes=64, verbose=False, ipv6=False, sourceIP=None):
    """
    Ping an IP up to the number of maxTries; breaking on the first response.

    """

    myStats = MStats2()  # Reset the stats
    mySeqNumber = 0  # Starting value

    if verbose:
        if logger:
            logger.debug("PYTHON PING {}: {} data bytes".format(ipAddr, numDataBytes))
        else:
            print("\nPYTHON PING %s (%s): %d data bytes" % (ipAddr, ipAddr, numDataBytes))

    myStats.thisIP = ipAddr

    i = 1
    while 1:
        response = single_ping(ipAddr, ipAddr, timeout, mySeqNumber,
                            numDataBytes, ipv6=ipv6, myStats=myStats,
                            sourceIP=sourceIP, verbose=verbose, logger=logger)
        #delay = 0 if delay is None or delay[0] is None else delay[0]
        delay = 0
        if response is not None and response[0] is not None:
            delay = response[0]
        if myStats.pktsRcvd:
            break

        mySeqNumber += 1

        if maxTries is None or i >= maxTries:
            break
        elif i < maxTries:
            i += 1

        # Pause for the remainder of the MAX_SLEEP period (if applicable)
        if (MAX_SLEEP > delay):
            time.sleep((MAX_SLEEP - delay)/1000)

    if verbose:
        _dump_stats(myStats, logger=logger)
    # 0 if we receive at least one packet
    # 1 if we don't receive any packets
    return (not myStats.pktsRcvd)


def quiet_ping(hostname, timeout=3000, count=3, advanced_statistics=False,
               numDataBytes=64, path_finder=False, ipv6=False, sourceIP=None):
    """ Same as verbose_ping, but the results are yielded as a tuple """
    myStats = MStats2()  # Reset the stats
    mySeqNumber = 0  # Starting value

    try:
        if ipv6:
            info = socket.getaddrinfo(hostname, None)[0]
            destIP = info[4][0]
        else:
            destIP = socket.gethostbyname(hostname)
    except socket.gaierror:
        yield False
        return

    myStats.thisIP = destIP

    # This will send packet that we don't care about 0.5 seconds before it
    # starts actually pinging. This is needed in big MAN/LAN networks where
    # you sometimes loose the first packet. (while the switches find the way)
    if path_finder:
        _pathfind_ping(destIP, hostname, timeout,
                       mySeqNumber, numDataBytes, ipv6=ipv6, sourceIP=sourceIP)

    i = 1
    while 1:
        delay = single_ping(destIP, hostname, timeout, mySeqNumber,
                            numDataBytes, ipv6=ipv6, myStats=myStats,
                            verbose=False, sourceIP=sourceIP)
        delay = 0 if delay is None else delay[0]

        mySeqNumber += 1
        # Pause for the remainder of the MAX_SLEEP period (if applicable)
        if (MAX_SLEEP > delay):
            time.sleep((MAX_SLEEP - delay) / 1000)

        yield myStats.pktsSent
        if count is not None and i < count:
            i += 1
        elif count is not None and i >= count:
            break
        elif count is not None:
            yield myStats.pktsSent

    if advanced_statistics:
        # return tuple(max_rtt, min_rtt, avrg_rtt, percent_lost, median, pop.std.dev)
        yield myStats.maxTime, myStats.minTime, myStats.avrgTime, myStats.fracLoss,\
              myStats.median_time, myStats.pstdev_time
    else:
        # return tuple(max_rtt, min_rtt, avrg_rtt, percent_lost)
        yield myStats.maxTime, myStats.minTime, myStats.avrgTime, myStats.fracLoss


if __name__ == '__main__':
    # FIXME: Add a real CLI (mostly fixed)
    if sys.argv.count('-T') or sys.argv.count('--test_case'):
        print('Running PYTHON PING test case.')
        # These should work:
        for val in verbose_ping("127.0.0.1"):
            pass
        for val in verbose_ping("8.8.8.8"):
            pass
        for val in verbose_ping("heise.de"):
            pass
        for val in verbose_ping("google.com"):
            pass

        # Inconsistent on Windows w/ ActivePython (Python 3.2 resolves
        # correctly to the local host, but 2.7 tries to resolve to the local
        # *gateway*)
        for val in verbose_ping("localhost"):
            pass

        # Should fail with 'getaddrinfo failed':
        for val in verbose_ping("foobar_url.fooobar"):
            pass

        # Should fail (timeout), but it depends on the local network:
        for val in verbose_ping("192.168.255.254"):
            pass

        # Should fails with 'The requested address is not valid in its context'
        for val in verbose_ping("0.0.0.0"):
            pass

        exit()

    parser = argparse.ArgumentParser(prog='python-ping',
                                     description='A pure python implementation\
                                      of the ping protocol. *REQUIRES ROOT*')
    parser.add_argument('address', help='The address to attempt to ping.')

    parser.add_argument('-t', '--timeout', help='The maximum amount of time to\
                         wait until ping timeout.', type=int, default=3000)

    parser.add_argument('-c', '--request_count', help='The number of attempts \
                        to make. See --infinite to attempt requests until \
                        stopped.', type=int, default=3)

    parser.add_argument('-i', '--infinite', help='Flag to continuously ping \
                        a host until stopped.', action='store_true')

    parser.add_argument('-I', '--ipv6', action='store_true', help='Flag to \
                        use IPv6.')

    parser.add_argument('-s', '--packet_size', type=int, help='Designate the\
                        amount of data to send per packet.', default=64)

    parser.add_argument('-T', '--test_case', action='store_true', help='Flag \
                        to run the default test case suite.')

    parser.add_argument('-S', '--source_address', help='Source address from which \
                        ICMP Echo packets will be sent.')

    parsed = parser.parse_args()

    if parsed.infinite:
        sys.exit(list(verbose_ping(parsed.address, parsed.timeout,
                                   None, parsed.packet_size,
                                   ipv6=parsed.ipv6, sourceIP=parsed.source_address))[:-1])

    else:
        sys.exit(list(verbose_ping(parsed.address, parsed.timeout,
                                   parsed.request_count, parsed.packet_size,
                                   ipv6=parsed.ipv6, sourceIP=parsed.source_address))[:-1])
