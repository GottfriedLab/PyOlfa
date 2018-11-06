import os
import time
import struct
import binascii
import glob
import db
import platform
import socket
from Queue import Queue
from PyQt4.QtCore import QThread
from numpy import array, int32, float32, append, ndarray, int16
from serial import Serial, SerialException
from configobj import ConfigObj
import voyeur.exceptions as ex


class SerialCallThread(QThread):
        '''
        This thread serializes communication across a single serial port.

        Calls are serialized and performed on a separate thread.
        '''

        def __init__(self, monitor=None, max_queue_size = 1, QObject_parent=None):
            QThread.__init__(self, QObject_parent)
            self.monitor = monitor
            self.output_queue = Queue(maxsize=max_queue_size)

        def enqueue(self, fn, *args, **kwargs):
            #print "Enqueuing: ", fn
            self.output_queue.put((fn, args, kwargs), block=True)

        def run(self):
            try:
                from Foundation import NSAutoreleasePool
                pool = NSAutoreleasePool.alloc().init()
            except ImportError:
                pass # Windows

            while self.monitor.running or not self.output_queue.empty():
                """print "Serializer running: ", time.clock()
                print "max size: ", self.output_queue.maxsize
                print "items: ", self.output_queue.qsize()
                print "Getting item from queue: ", time.clock()"""

                (output_fn, args, kwargs) = self.output_queue.get(block=True, timeout=0.5) # block 0.5 seconds
                #print "Got item in queue: ", time.clock()
                #print "queue function starting: ", time.clock()
                output_fn(*args, **kwargs)
                #print "queue function return: ", time.clock()


class SerialPort(object):

    # Make it equal to the buffer size of Arduino. Used to detect buffer overflows and packets missing
    NOLOSSTRANSMISSIONRATE = 0.7
    # Absolute time in seconds (from start of python program) of the last received streaming data
    lastStreamTime = 0
    # Keep the maximum time in seconds between streaming data transmissions from Arduino
    maxRate = 0
    # Keep a counter of packets that arrive later than NOLOSSTRANSMISSIONRATE, indicating buffer overflown in Arduino
    overflownpackets = 0

    def __init__(self, configFile, board = 'board1', port='port1', send_trial_number = False):
        """Takes the string name of the serial port
        (e.g. "/dev/tty.usbserial","COM1") and a baud rate (bps) and
        connects to that port at that speed.
        """
        # Flag for denoting wether to send trial number to Arduino. This depends on protocol and if the trial number is used
        # or further forwarded from Arduino to an acquisition device
        self.send_trial_number = send_trial_number
        self.config = ConfigObj(configFile)
        serial = self.config['serial']
        baudrate = serial['baudrate']
        self.board = self.config['platform'][board]
        serialport  = serial[socket.gethostname()][port]
        if os.path.exists(serialport) or platform.win32_ver()[0] != '':
            self.serial = Serial(serialport, baudrate, timeout=1)
        else:
            raise ex.SerialException(serialport, "Serial Port Incorrect. Check config file.")

    def read_line(self):
        """Reads the serial buffer"""
        line = None
        try:
            line = self.serial.readline()
        except SerialException as e:
            print('pySerial exception: Exception that is raised on write timeouts')
            print(e)
        return line

    def read_byte_streams(self, num_bytes,tries=8):
        count = 0
        #print num_bytes
        while self.serial.inWaiting() != num_bytes and count < tries: #wait until number of bytes in recieve buffer is equal to expected number of bytes.
            # Reading the serial stream is part of the separate serial acquisition thread and will not break or make the UI lag
            if tries <= 8:
                time.sleep(0.01+.01*count**2)# blocks for 1 second, with exponentially increasing checks.(10ms,20ms,50ms,100ms...)
            else:    # If tries was higher than 8, wait the minimum set time of 10ms
                time.sleep(0.01)
            count += 1
            
        if self.serial.inWaiting() == num_bytes: # when buffer is ready, read and return.
            bytestream = self.serial.read(num_bytes)
            if len(bytestream) == num_bytes:
                return bytestream
        # TODO: Take partially transmitted data but warn of data loss?? Implement a retry protocol?
        else: # if buffer never fills to expected value, do not read the packet, instead flush the incoming serial of partial packet and return.
            #print "serial buffer has ", self.serial.inWaiting(), "bytes"
            self.serial.flushInput()
            print 'ERROR in serial stream acquisition: not enough bytes transmitted by arduino'
            return None


    def write(self, data):
        """Writes *data* string to serial"""
        self.serial.write(data)

    def request_stream(self, stream_def, tries=10):
        """Reads stream"""
        #print "Stream request to serial: ", time.clock()
        for i in range(tries):
            #print "try: ", i
            self.write(chr(87))
            packets = self.read_line()
            
            # Collect statistics about the transmission rate and lost packets
            streamtime = time.clock()
            rate = streamtime - self.lastStreamTime
            #print "Stream received: ", rate
            # Skip the first measurement as that depends on when the user starts the streaming and
            #  the first transmission will for sure overflow the buffer
            if self.lastStreamTime > 0:
                if rate > self.maxRate:
                    self.maxRate = rate
                if rate > self.NOLOSSTRANSMISSIONRATE:
                    self.overflownpackets += 1
            self.lastStreamTime = streamtime
            #print "Stream returned: ", packets, " time: ", time.clock()
            #print packets
            return parse_serial(packets, stream_def, self)

    def request_event(self, event_def, tries=10):
        """Reads event data"""
        for i in range(tries):
            self.write(chr(88))
            packets = self.read_line()
            #print packets
            return parse_serial(packets, event_def, self)

    def start_trial(self, parameters, tries=10):
        """Sends start command"""
        params = convert_format(parameters)
         # trial number is needed for some protocols which send the trial parameter to Arduino
         # Arduino can make use of this or send it via serial to an acquisition device.
        if not self.send_trial_number:
            params.pop("trialNumber")
        values = params.values()
        values.sort()
        #print "Starting trial..."
        for i in range(tries):
            self.write(chr(90))
            for index, format, value in values:
                #print value
                self.write(pack_integer(format, value))
            line = self.read_line()
            #print line
            if line and int(line[:1]) == 2:
                #print "Time 2 = ", time.clock()
                return True

    def user_def_command(self, command, tries=10):
        """Sends a user defined command
           Args: command is a string representing a command issued to arduino"""
        for i in range(tries):
            self.write(chr(86))
            self.write(command)
            self.write("\r")
            line = self.read_line()
            #print line
            if line and int(line[:1]) == 2:
                return True

    def end_trial(self, tries=10):
        """Sends end command"""
        for i in range(tries):
            self.write(chr(89))
            line = self.read_line()
            #print line
            print "Maximum intertransmission rate(ms): ", self.maxRate
            print "Number of transmissions slower than max rate: ", self.overflownpackets
            if line and int(line[:1]) == 3:
                return True

    def request_protocol_name(self, tries=10):
        """Get protocal name from arduino (gives the name of the code that is running)"""
        for i in range(tries):
            self.write(chr(91))
            line = self.read_line()
            if line and int(line[:1]) == 6:
                values = line.split(',')
                return values[1]

    def upload_code(self, hex_path):
        """Upload code to the arduino"""
        self.serial.close()
        avr = self.config['avr']
        verbosity = avr['verbosity']
        command = avr[self.os]['command']
        conf = avr[self.os]['conf']
        flags = avr[self.board]['flags']
        arduino_upload_cmd = command \
                            + " -C" + conf \
                            + " " + verbosity \
                            + " " + flags \
                            + " -P" + self.serial.name \
                            + " -Uflash:w:" + hex_path + ":i"
        os.system(arduino_upload_cmd)
        self.serial.open()

    def open(self):
        """Open the serial connection"""
        self.serial.open()

    def close(self):
        """Close the serial connection"""
        self.serial.close()

def parse_serial(packets, protocol_def, serial_obj):
    """Parse serial read"""
    #print "packet: ", packets
    #print "protocol_def: ", protocol_def
    data = {}
    eot = False
    #print protocol_def
    #print packets
    if packets:
        for packet in packets.split('*'):
            if packet and packet != '\r\n':
                payload = packet.split(',')
                handshake = int(payload[0])
                #print "handshake:", handshake
                if handshake == 1:
                    if protocol_def:
                        for key, (index, kind) in protocol_def.items():
                            if payload[index] == '':
                                data[key] = None
                            else:
                                data[key] = convert_type(kind, payload[index])
                elif handshake == 4:
                    #print "protocol def:", protocol_def
                    if protocol_def:
                        for key, (index, kind) in protocol_def.items():
                            data[key] =  convert_type(kind, payload[index])
                            #print data[key]
                    #print data
                elif handshake == 5:
                    eot = True
                elif handshake == 6:
                    bytes_per_stream = [];
                    num_streams = int(payload.pop(1)) #read and discard this value to maintain consistency with the stream_definition numbering.
                    if len(payload) < num_streams + 1:
                        print "oh shit, you don't have enough stream length specifiers"
                    for stream_number in range(num_streams):
                        bytes_per_stream.append(int(payload[1+stream_number]))
                    bytes_to_read = sum(bytes_per_stream)
                    #print "Reading ", bytes_to_read, " bytes"
                    bytestream = serial_obj.read_byte_streams(bytes_to_read)
                    
                    if bytestream == None: # failure, no streams recieved,
                        for key, (index, arduinoType, kind) in protocol_def.items():
                            data[key] = None
                        print 'Lost packet: no data received'
                    
                    byte_index_start = 0
                    
                    for key, (index, arduinoType, kind) in protocol_def.items():
                        #data[key] =  convert_type(kind, payload[index])
                        if bytes_per_stream[index-1] == 0: # expecting empty stream, so set output to None.
                            data[key] = None
                            continue
                        
                        byte_index_start = sum(bytes_per_stream[:(index-1)])
                        byte_index_end = sum(bytes_per_stream[:(index)])
                        stream_bytes = bytestream[byte_index_start:byte_index_end]
                        unpacked_stream =[]
                        
                        ## unpack the bytes into integers based on the type specified in the stream_definition.
                        if arduinoType == 'int': # h for short integers
                            num_vals = len(stream_bytes)/2
                            t = "<%ih" % (num_vals) # little-endian,number of integers,signed int
                            vals = struct.unpack(t,stream_bytes)
                            unpacked_stream = array(vals,dtype = int16)
                                
                        elif arduinoType == 'unsigned int': #H 
                            num_vals = len(stream_bytes)/2
                            t = "<%iH" % (num_vals) # little-endian(<),number of integers,unsigned int (H)
                            vals = struct.unpack(t,stream_bytes)
                            unpacked_stream = list(vals)
                            
                        elif arduinoType == 'long': # i
                            num_vals = len(stream_bytes)/4
                            t = "<%ii" % (num_vals) # little-endian(<),number of integers,unsigned int (i)
                            vals = struct.unpack(t,stream_bytes)
                            unpacked_stream = list(vals)
                                
                        elif arduinoType == 'unsigned long': #I
                            num_vals = len(stream_bytes)/4
                            t = "<%iI" % (num_vals) # little-endian(<),number of integers,unsigned int (H)
                            vals = struct.unpack(t,stream_bytes)   
                            unpacked_stream = list(vals)                            
                        
                        if type(kind) != type(db.Int): 
                            if type(kind) == ndarray:
                                if kind.dtype == int16:
                                    unpacked_stream = append(db.Int16Array, unpacked_stream)
                                elif kind.dtype == float32:
                                    unpacked_stream = [float(i) for i in unpacked_stream]
                                    unpacked_stream = append(db.FloatArray, unpacked_stream)
                                elif kind.dtype == int32:
                                    unpacked_stream = append(db.IntArray, unpacked_stream)
                                
                        
                        elif len(unpacked_stream) == 1:
                            unpacked_stream = int(unpacked_stream[0])
                                
                        data[key] = unpacked_stream;         
        if eot:
            exp = ex.EndOfTrialException('End of trial')
            exp.last_read = data
            raise exp
    return data


def convert_format(parameters):
    """Converts dictionary database type format to serial transmission format"""
    values = parameters.copy()
    for key, (index, format, value) in values.items():
        if type(format) == type(db.Int):
            values[key] = (index, 'i', value)  # signed 32 bit int (arduino long)
        elif type(format) == type(db.Int16):
            values[key] = (index, 'h', value)
        elif type(format) == type(db.Float):
            values[key] = (index, 'f', value)
        elif type(format) == type(db.String32):
            values[key] = (index, 's', value)
        elif type(format) == type(db.StringN):
            values[key] = (index, 's', value)
        elif type(format) == type(db.Time):
            values[key] = (index, 'd', value)
    return values


def convert_type(kind, value):
    """Converts string to python type"""
    if type(kind) == type(db.Int):
        return int(value)
    elif type(kind) == type(db.Int16):
        return int(value)
    elif type(kind) == type(db.Float):
        return float(value)
    elif type(kind) == type(db.String32):
        return str(value)
    elif type(kind) == type(db.StringN):
        return str(value)
    elif type(kind) == type(db.Time):
        return float(value)
    elif type(kind) == ndarray:
        array = []
        elements = value.split(';')
        if(elements[:-1] is None): # NB: Admir's spec says there shouldn't be a trailing semi-colon, but check anyways
            elements.pop() # null value
        if kind.dtype == int32:
            for element in elements:
                array.append(int(element))
            return append(db.IntArray, array)
        elif kind.dtype == float32:
            for element in elements:
                array.append(float(element))
            return append(db.FloatArray, array)
    return value


def pack_integer(format, value):
    """Packs integer as a binary string
       I = python 4 byte unsigned integer to an arduino unsigned long
       h = python 2 byte short to an arduino integer
    """

    return struct.pack(format, value)


def strip_tuple(dict):
    """Ensures the tuple in the dictionary does not have third value"""
    values = dict.values()
    if len(values[0]) == 2:
        return dict
    elif len(values[0]) == 3:
        return strip_3tuple(dict)
    return None


def strip_2tuple(dict):
    """
    Strips the second value of the tuple out of a dictionary
    {key: (first, second)} => {key: first}
    """
    new_dict = {}
    for key, (first, second) in dict.items():
        new_dict[key] =  first
    return new_dict


def strip_3tuple(dict):
    """
    Strips the third value of the tuple out of a dictionary
    {key: (first, second, third)} => {key: first, second}
    """
    new_dict = {}
    for key, (first, second, third) in dict.items():
        new_dict[key] =  (first, second)
    return new_dict
