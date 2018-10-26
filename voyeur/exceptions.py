import sys
import os

class VoyeurException(Exception):
    """Base class for exceptions in this module."""
    pass
                    
class SerialException(VoyeurException):
    """Exception raised for errors in the serial communication.

    Attributes:
        path -- serial path
        msg  -- explanation of the error
    """

    def __init__(self, path, msg):
        self.path = path
        self.msg = msg

class ProtocolException(VoyeurException):
    """Exception raised for errors in the protocol.

    Attributes:
        protocol -- name of protocol
        msg      -- explanation of the error
    """

    def __init__(self, protocol, msg):
        self.protocol = protocol
        self.msg = msg
        
class EndOfTrialException(VoyeurException):
    """Exception raised when end of trial occurs.

    Attributes:
        msg -- explanation of the error
    """

    def __init__(self, last_read, msg="End of Trial"):
        self.last_read = last_read
        self.msg = msg

class NonOperationException(VoyeurException):
    """Exception raised when contoller communication is working but no data was sent.

    Attributes:
        msg -- explanation of the error
    """

    def __init__(self, msg="Non-operation, serial communication working, no data sent"):
        self.msg = msg