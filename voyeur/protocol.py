import abc
import traits.api as ui
from datetime import datetime
from voyeur.plugins import IPlugin



class TrialParameters(object):
    """
    Describes the protocol and controller parameter values for a single trial. Both dictionaries are
    of  of {name => (index,db.Type,value)}
    """

    def __init__(self, protocolParams={}, controllerParams={}):
        self.protocolParameters = protocolParams
        self.controllerParameters = controllerParams

    protocolParameters = {}
    controllerParameters = {}


class IProtocol(IPlugin):
    """
    Interface for plugins defining an experimental protocol

    Usage
    =====

    User-provided protocol plugins should subclass IProtocol, provide traits-based UI
    for configuration and override next_trial_parameters(), protocol_definition(), event_definition(),
    data_values(), and process_completed_trial().


    Example
    =======


    """

    # This is a placeholder for a metadata dictionary. Items in the metadata dictionary are written as attributes to the
    # session attributes of the HDF5 file at file creation time.
    # FUTURE: changes to this dictionary after session start will result in attribute addition or change.
    metadata = {}


    @abc.abstractmethod
    def protocol_parameters_definition(self):
        """
        Returns a python dictionary defining the parameters of this protocol.
        
        The protocol parameters definition dictionary describes the type of each
        protocol parameter. Types must be one of the types defined in :mod:`voyeur.db`.

        Example::
            {
                "trialNumber" : db.Int, # an integer value
                "param1" : db.Float, # a floating-point value
                "param2" : db.Time # a time stamp value
            }
        """
        return {}

    @abc.abstractmethod
    def controller_parameters_definition(self):
        """
        Returns a python dictionary defining the controller sent by this protocol.

        The controller parameters definition dictionary describes the type and index of each
        parameter sent to the Arduino controller at the start of each trial. The index defines
         the order in the serial stream of the parameter. The index defined here, *not the order of
         definition within the dictionary* define the order parameters are sent to the Arduino controller.
        Types must be one of the types defined in :mod:`voyeur.db`.

        Example::
            {
                "param1" : (1,db.Int16), # an integer value (sent 1st)
                "param2" : (2,db.Int16) # an integer value (sent 2nd)
            }
        """

        return {}

    @abc.abstractmethod
    def event_definition(self):
       """Returns a dictionary of {name => (index,db.Type)} of event fields for this protocol"""

       return {}

    @abc.abstractmethod
    def stream_definition(self):
       """Returns a dictionary of {name => (index,db.Type)} of streaming data fields for this protocol"""

       return {}

    @abc.abstractmethod
    def trial_parameters(self):
        """
        Returns a :class:`TrialParameters` instance describing the values of
        the protocol parameters and controller parameters for the next trial.

        The protocol parameters dictionary is a key=>value dictionary, using the keys defined in protocol_parameters_definition.
        The controller parameters dictionary is a key=>(index, format, value) dictionary, using the keys defined
        in controller_parameters_definition. The index here must also match the index defined in controller_parameters_definition
        for the given key.

        May return None to indicate no next trial.

         Example::
            def trial_parameters(self):
                return TrialParameters(
                    protocolParams = {
                        "trialNumber" : 1,
                        "param1" : 2.1,
                        ...
                    },
                    controllerParams = {
                        "param1" : (1, db.Int, 1),
                        "param2" : (2, db.Int, 200)
                    }


         """

        return TrialParameters({},{})

    @abc.abstractmethod
    def start_of_trial(self):
        """
        Called by Monitor before trial starts.
        """
        pass
    
    @abc.abstractmethod
    def process_event_request(self, event):
        """
        Process event data requested from controller.

        Parameters:
            event : dictionary of single event that matches event_definition()
        """
        pass

    @abc.abstractmethod
    def process_stream_request(self, stream):
        """
        Process stream data requested from controller.

        Parameters:
            stream : list of streamed data that matches stream_definition()
        """
        pass

    @abc.abstractmethod
    def end_of_trial(self):
        pass

    @abc.abstractmethod
    def trial_iti_milliseconds(self):
        """Returns the number of millisecods of inter-trial interval following the trial whose parameters
        were most recently supplied"""

        pass

    def protocol_description(self):
        """A string description of the protocol"""

        return self.__class__.__name__ + ' protocol'



class Protocol(ui.HasTraits, IProtocol):
    pass

def time_stamp():
    dt = datetime.now().timetuple()
    return    'D' + str(dt.tm_year) \
            + '_' + str(dt.tm_mon)  \
            + '_' + str(dt.tm_mday) \
            + 'T' + str(dt.tm_hour) \
            + '_' + str(dt.tm_min)  \
            + '_' + str(dt.tm_sec)  \
    
    
