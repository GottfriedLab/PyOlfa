==============
User protocols
==============

Voyeur is a general data acquisition system. To describe the experimental protocol, users write protocol plugins for the system. A protocol plugin provides three necessary pieces of information to Voyeur. The :class:`voyeur.monitor.Monitor` class uses this information to coordinate the actions of the Arduino controller, the user interface, and the data persistence modules. This description is used to parse the controller's output and to describe the data written to disk:

    1. The user-configurable *protocol parameters*
        The user interface module (:mod:`voyeur.ui`) uses the described parameters to present a user interface for manipulating those parameters. Protocol parameters are declared in the protocol class as types from the :mod:`voyeur.ui` module.
    2. The *controller parameters*—the values sent to the hardware controller—for each trial
        The protocol must provide a dictionary describing the type and order of these parameters and a method that returns the parameters for the next trial. For example, a protocol that sends two values, a 16-bit integer and a floating-point value, to the controller with each trial would describe the format of these parameters in a type dictionary::
        
            { 
                'integer-value' : (1,db.Int16),
                'float-value'   : (2,db.Float)
            }
        
        When the :class:`voyeur.monitor.Monitor` request the parameters for the next trial, this same protocol would provide them as, for example::
        
            {
                'integer-value' : (1, db.Int16, 10)
                'float-value'   : (2, db.Float, 1.141)
            }
            
        
    3. The *event parameters* describing results returned from the controller at the end of the trial. 
        Similarly, the protocol must provide a type dictionary describing format of results returned from the controller and the particular values for a given trial. 
    

Monitor's interaction with user protocols
=========================================

The :class:`voyeur.monitor.Monitor` calls the current user protocol using a specific API, defined in :class:`voyeur.protocol.IProtocol`.
User protocols must implement the methods defined in this abstract base class. The interaction between the Monitor
and the current user protocol for a single trial are summarized in the image below:

.. image:: ../Monitor-Protocol.pdf



Writing a protocol
==================

The tasks for writing an experimental protocol for use with the Voyeur system are:

1. Subclass :mod:`voyeur.protocol.Protocol`
2. Define *protocol parameters* as class instance variables of types defined in the :mod:`voyeur.ui` module
3. Describe the *protocol parameters* that you want to persist in the database by name and type in :mod:`voyeur.db`
4. Describe the *controller parameters* by index (the order sent to the Arduino controller) and type in :mod:`voyeur.db`
5. Provide a TrialParameters instance with protocol and controller parameter valuesfor the next trial, when requested
4. Describe and provide the *event parameters* for the most recently completed trial, when requested
    
A simple ``Protocol`` implementation that performs these tasks is shown below::

	class ExampleProtocol(Protocol):
	    """
	    Example protocol demonstrating a minimal user protocol implementation

	    This protocol describes a fictional protocol with two parameters, count and value.
	    For illustration, we may consider an experimental protocol where a stimulus is presented
	    count times, at intensity value.

	    """


	    # The protocol parameters are described as class members of types defined in the
	    # voyeur.ui module. These parameters will be automatically presented by the UI module

	    count = Int(0, label='count')
	    value = Float(1.0, label='value')
	    lastEvent1 = Int(0, label='Event Param 1 from last trial')

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

	        In this example, this protocol defines three parameters of types db.Int and db.Float.
	        """

	        return {
	            'trialNumber' : (1, db.Int),
	            'count' : (2, db.Int),
	            'value' : (3, db.Float),
	        }

	    def controller_parameters_definition(self):
	        """
	        Returns a python dictionary defining the controller sent by this protocol.

	        The controller parameters definition dictionary describes the type and index of each
	        parameter sent to the Arduino controller at the start of each trial. The index defines
	         the order in the serial stream of the parameter. The index defined here, *not the order of
	         definition within the dictionary* define the order parameters are sent to the Arduino controller.
	        Types must be one of the types defined in :mod:`voyeur.db`.

	        """

	        return {
	            'value' : (1,db.Int),
	            'count' : (2,db.Int)
	        }

	    def trial_parameters(self):
	        """
	        Returns a :class:`TrialParameters` instance describing the values of
	        the protocol parameters and controller parameters for the next trial.

	        The protocol parameters dictionary is a key=>value dictionary, using the keys defined in protocol_parameters_definition.
	        The controller parameters dictionary is a key=>(index,value) dictionary, using the keys defined
	        in controller_parameters_definition. The index here must also match the index defined in controller_parameters_definition
	         for the given key.
	        """

	        protocolParams = {
	            "trialNumber" : self.trialNumber,
	            "count" : self.count,
	            "value" : self.value
	        }

	        controllerParams = {
	            'value' : (1, db.Int, int(self.value)),
	            'count' : (2, db.Int, self.count)
	        }
	        return TrialParameters(protocolParams=protocolParams,
	                               controllerParams=controllerParams)


	    def event_definition(self):
	        """
	        At the end of each trial, the controller returns a set of "event parameters"
	        describing events that occured during that trial. This method returns a dictionary
	        defining the event defintiion for this protocol. This dictionary is, in essence, a
	        template for the event parameters for each trial. The description format is a python
	        dictionary. The keys are the names of each event parameter. They will be used
	        elsewhere in the protocol to refer to the event parameters. The values of the
	        dictionary are tuples of the form (index,type) where index gives ordered the
	        position of this parameter in the stream received from the Arduino controller. Thus,
	        the index, **not** the order of the parameters in the type dictionary dictates the
	        order in which parameters are expected to be sent by the controller.

	         The type of the parameter must be one of the types defined in the :mod:`voyeur.db`
	         module.

	         In this example, the event parameters are three integers, eventParam1-3.

	         Returns a dictionary of {name => (index,db.Type)} of event parameters for this
	         protocol.
	        """

	        return {
	            "eventParam1" : (1, db.Int),
	            "eventParam2" : (2, db.Int),
	            "eventParam3" : (3, db.Int),
	        }

	    def stream_definition(self):
	        """
	        Upon request the controller returns a set of "stream parameters" describing 
	        readins that occured during that trial. This method returns a dictionary
	        defining the stream defintiion for this protocol. This dictionary is, in essence, a
	        template for the stream parameters for each trial. The description format is a python
	        dictionary. The keys are the names of each event parameter. They will be used
	        elsewhere in the protocol to refer to the event parameters. The values of the
	        dictionary are tuples of the form (index,type) where index gives ordered the
	        position of this parameter in the stream received from the Arduino controller. Thus,
	        the index, **not** the order of the parameters in the type dictionary dictates the
	        order in which parameters are expected to be sent by the controller.

	         The type of the parameter must be one of the types defined in the :mod:`voyeur.db`
	         module.

	         In this example, the event parameters are three integers, streamParam1-3.

	         Returns a dictionary of {name => (index,db.Type)} of stream parameters for this
	         protocol.
	        """

	        return {
	            "streamParam1" : (1, db.Int),
	            "streamParam2" : (2, db.Int),
	            "streamParam3" : (3, db.Int),
	        }

	    def process_event_request(self, event):
	        """
	        Process completed stream data.

	        At the completion of each trial, the Monitor passes an event dictionary
	        to the protocol for processing. Each event dictionary is described by the
	        result of this protocol's event_definition() method: each event dictionary
	        has the same keys and values of the same type as the type dictionary.

	        In this method, the protocol may update class members, automatically udpating
	        UI elements or may perform any needed calculations at the conclusion of each trial.

	        Parameters:
	            events : list
	                List of (single) event dictionary, matching event_parameters_type()
	        """

	        self.lastEvent = event['eventParam1']

	    def process_stream_request(self, stream):
	        """
	        Process completed stream data.

	        At the completion of each trial, the Monitor passes a stream dictionary
	        to the protocol for processing. Each stream dictionary is described by the
	        result of this protocol's stream_definition() method: each event dictionary
	        has the same keys and values of the same type as the type dictionary.

	        In this method, the protocol may update class members, automatically udpating
	        UI elements or may perform any needed calculations at the conclusion of each trial.

	        Parameters:
	            events : list
	                List of (single) event dictionary, matching stream_parameters_type()
	        """

	        self.lastEvent1 = int(stream['streamParam1'])

	    def start_of_trial(self):
	        """
	        Called by Monitor before trial starts to perform intialization.
	        """

	        pass

	    def end_of_trial(self):
	        """
	        Called by Monitor before trial starts to perform post trial operations.
	        """

	        self.trialNumber = self.trialNumber + 1
	        self.count = self.count + 1
	        self.value = self.value * 2

	    def trial_iti_milliseconds(self):
	        """Returns the number of millisecods of inter-trial interval following the trial whose parameters
	        were most recently supplied"""

	        return 1000
