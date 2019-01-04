import os, time
import getpass
from traits.etsconfig.etsconfig import ETSConfig
ETSConfig.toolkit = 'qt4'

from voyeur.db import Persistor
from voyeur.arduino import SerialPort, SerialCallThread
from voyeur.exceptions import (
    EndOfTrialException,
    SerialException,
    ProtocolException,
    NonOperationException
    )
    
from PyQt4.QtCore import QThread, QTimer
from PyQt4.Qt import  QApplication
from traits.api import (
    HasTraits,
    Instance,
    Bool,
    Str,
    Int,
    Float,
    File,
    Event,
    on_trait_change
    )


class AcquisitionThread(QThread):

    def acquire_stream(self):
        try:
            #print "Acquiring stream: "
            self.monitor.acquire_stream()
            #print "Acquired stream"
        except EndOfTrialException:
            self.monitor.eot = True
            #print "end of trial"
        except ProtocolException as e:
            #print('Protocol exception. Message:', e.msg, ' Protocol: ', e.protocol)
            pass
        except:
            print "Exception in acquisition thread"
            self.monitor.stop_acquisition()

    def run(self):
        # start streaming acquisition
        try:
            from Foundation import NSAutoreleasePool
            pool = NSAutoreleasePool.alloc().init()
        except ImportError:
            pass # Windows

        # acquisition loop
        while self.monitor.running:
            #print "Stream thread tryin to enqueue", time.clock()
            self.serial_queue.enqueue(self.acquire_stream)


class Monitor(HasTraits):
    """Central manager for CPU-side of Voyeur system"""

    # Client
    persistor = Instance(object, factory=Persistor)
    serial1 = Instance(object)
    serial_queue1 = Instance(object)
    protocol = Instance(object)
    database_file = File(None)
    user = Str(getpass.getuser())
    session_number = Int(1)
    protocol_number = Int(1)
    animal_id = Int(1)
    rig = Int(1)
    experiment_notes = Str("")
    voyeur_version = Float(1.0)
    usercode_version = Float(1.0)
    arduino_protocol_name = Str("")
    user_protocol_name = Str("")
    start_date = Float("")
    timezone = Str("")
    user_metadata = Str("")

    # Internal
    running = Bool(False)
    recording = Bool(False)
    paused = Bool(False)
    eot = Event() # queue for dispatch on ui thread
    push_event = Event() # dispatch immediately on ui thread
    push_streaming = Event() # dispatch immediately on ui thread
    current_session_group = Instance(object)
    current_trial_group = Instance(object)
    current_trial_parameters = Instance(object)
    acquisition_thread = Instance(AcquisitionThread)
    _iti_timer = Instance(QTimer)
    processed = 0
    acquired = 0
    _acquiringlock = False
    _eventlock = False

    def __init__(self, send_trial_number = False, *args, **kwargs):
        HasTraits.__init__(self, *args, **kwargs)
        
        # events -- dispatched on UI thread
        self.on_trait_event(self._handle_push_event, 'push_event', dispatch='fast_ui')
        self.on_trait_event(self._handle_push_streaming, 'push_streaming', dispatch='fast_ui')
        self.on_trait_change(self._handle_eot, 'eot', dispatch='ui')

        # database
        self.persistor = Persistor()

        # config
        # self.configFile = os.environ.get("voyeur_config")
        self.configFile = os.path.join('/Users/Gottfried_Lab/PycharmProjects/PyOlfa/src/voyeur_rig_config.conf')

        # serial
        self.serial_queue1 = SerialCallThread(monitor=self, max_queue_size=1)        
        try:
            if self.serial1 is None:
                self.serial1 = SerialPort(self.configFile, board='board1', port='port1', send_trial_number = send_trial_number)
        except SerialException as e:
            print('Serial Port 1 Error')
            print('Serial exception. Message: ', e.msg, ' Path: ', e.path)

        self.protocol_name = self.serial1.request_protocol_name()
        ### Define monitor metadata. This metadata is consistent between all protocols.
        self.metadata = {'arduino_protocol_name': self.protocol_name,
                         'start_date': time.mktime(time.localtime()),
                         #todo: add VOYEUR core version hash or version number lookup.
                         }


        
        
    def _database_file_changed(self):
        initial_metadata = dict(self.metadata.items() + self.protocol.metadata.items())  # combine protocol and monitor metadata
        if self.serial1 != None:
            #self.serial_queue1.enqueue(self.persistor.close_database)
            self.current_session_group = self.persistor.create_database(self.database_file, initial_metadata)

            self.persistor.create_trials(self.protocol.protocol_parameters_definition(),
                                            self.protocol.controller_parameters_definition(),
                                            self.protocol.event_definition(),
                                            self.current_session_group,
                                            '')
        
    def _protocol_changed(self, name, old, new):
        """
        Update protocol number.

        If self.protocol.__class__ == new.__class__ don't update
        """
        """if new != None and old.__class__ != new.__class__:
            self.protocol_number += 1
            self.user_protocol_name = self.protocol.protocol_name 
            self.persistor.create_trials(new.protocol_parameters_definition(),
                                            new.controller_parameters_definition(),
                                            new.event_definition(),
                                            self.current_session_group,
                                            '')"""
        # For Debugging
        """self.persistor.create_trials(new.protocol_parameters_definition(),
                                        new.controller_parameters_definition(),
                                        new.event_definition(),
                                        self.current_session_group,
                                        '')"""
        pass
                                    

    def start_acquisition(self):
        self.running = True
        self.recording = True
        self.paused = False
        self.start_new_trial()

    def stop_acquisition(self):
        """Stops acquisition"""
        if self._iti_timer:
            self._iti_timer.stop()
            self._iti_timer.deleteLater()
            self._iti_timer = None
        self.recording = False
        self.running = False
        self.paused = False
        self.setup_complete = False
        if self.serial1 != None:
            self._eventlock = True
            self.serial_queue1.enqueue(self.serial1.end_trial)
            self._eventlock = False
            #self.serial_queue1.enqueue(self.persistor.close_database)
            #self.serial_queue1.enqueue(self.serial1.close)
        self.persistor.close_database()

    def pause_acquisition(self, graceful = False):
        """Pauses acquisition"""
        self.paused = True
        if self._iti_timer:
            self._iti_timer.stop()
            self._iti_timer.deleteLater()
            self._iti_timer = None
        
        if graceful:
            if self.serial1 != None:
                self._eventlock = True
                self.serial_queue1.enqueue(self.serial1.end_trial)
                self._eventlock = False
        if self.running:
            self.recording = False
                
    def unpause_acquisition(self):
        """Unpauses acquisition"""
        self.paused = False
        if self.running:
            self.recording = True
            self.start_new_trial()
               
            
    def send_command(self, command):
        """ Sends a user command to arduino """
        
        if not self.serial_queue1.isRunning():
            self.serial_queue1.start()
        if self.serial1 != None:
            self._eventlock = True
            self.serial_queue1.enqueue(self.serial1.user_def_command, command)
            self._eventlock = False
            """if not sent:
                raise ProtocolException(self.protocol.protocol_description(),
                                         "Sending user defined command failed")"""
                
    def start_new_trial(self, ):
        """Start New Trial"""
        # Get parameters for next trial
        if self.running and self.recording:
            trial_parameters = self.protocol.trial_parameters()
            # Create the trial group
            self.current_trial_group = self.persistor.add_trial(self.protocol.trialNumber,
                                                                trial_parameters.protocolParameters,
                                                                trial_parameters.controllerParameters,
                                                                self.protocol.stream_definition(),
                                                                self.current_session_group,
                                                                self.protocol.protocol_description())

            self.protocol.start_of_trial()
            self._start_acquisition(trial_parameters.controllerParameters)
            
            if not self.serial_queue1.isRunning():
                self.serial_queue1.start()
                self._start_acquisition_thread()

    def acquire_events(self):
        """Run event acquisition"""
        event = self.serial1.request_event(self.protocol.event_definition())
        if event:
            self.push_event = (event, self.recording)
        else:
            raise ProtocolException(self.protocol.protocol_description(), "Event is null")


    def acquire_stream(self):
        """Run stream acquisition"""      
        try:
            stream = self.serial1.request_stream(self.protocol.stream_definition())
            #print "Stream acquired from serial: ", stream
            if stream:
                self._acquiringlock = True
                self.push_streaming = (stream, self.recording)
                self.acquired += 1
                #print "Total streams acquired: ", self.acquired
            else:
                raise ProtocolException(self.protocol.protocol_description(), "Stream data is null.")
                #print "Stream empty exception raised: ", time.clock()
        except NonOperationException:
            raise ProtocolException(self.protocol.protocol_description(), "NonOperationException.")
        except EndOfTrialException as ex:
            stream = ex.last_read
            if stream:
                self._acquiringlock = True
                self.push_streaming = (stream, self.recording)
                #self.acquired += 1
                #print "Total streams acquired: ", self.acquired
            raise ex
        while(self._acquiringlock):
            if self.running == False or self._eventlock:
                break
            continue
        return
                        
    def _handle_eot(self):
        self.protocol.end_of_trial()
        self._eventlock = True
        self.serial_queue1.enqueue(self.acquire_events)
        self._eventlock = False

    def _run_iti(self, continuation):
        """Starts a timer with Protocol-supplied inter-trial interval. Timer
        calls continuation when fired
        
        ITI timer is an object that can be modified and queried. To check if timer is active,
        use _iti_timer.is_active() method. To cancel timer, call _iti_timer.cancel() 
        """
        iti_ms = self.protocol.trial_iti_milliseconds()
        #print "next start iti = ", iti_ms
        if self._iti_timer:
            self._iti_timer.stop()
            self._iti_timer.deleteLater()
        self._iti_timer = QTimer()
        self._iti_timer.timeout.connect(continuation)
        self._iti_timer.setSingleShot(True)
        self._iti_timer.start(iti_ms)
        return

    def _start_acquisition_thread(self):
        """Spawns the acquisition thread"""
        self.acquisition_thread = AcquisitionThread()
        self.acquisition_thread.serial_queue = self.serial_queue1
        self.acquisition_thread.monitor = self
        self.acquisition_thread.start()
            
    def _start_acquisition(self, trial_parameters):
        """Starts acquisition. Called by AcquisitionThread.run"""
        if self.protocol != None:
            self._eventlock = True
            self.serial_queue1.enqueue(self.serial1.start_trial, trial_parameters)
            self._eventlock = False

    def _handle_push_event(self, event_tuple):
        event, persist = event_tuple
        self.persistor.insert_event(event, self.current_session_group)
        self.protocol.process_event_request(event)
        if not self.paused:
            self._run_iti(self.start_new_trial)

    def _handle_push_streaming(self, streaming_tuple):
        #print "processing stream....", time.clock()
        if not self.running:
            return
        stream, persist = streaming_tuple
        if persist:
            self.persistor.insert_stream(stream, self.current_trial_group)
        self.protocol.process_stream_request(stream)
        self.processed += 1
        #print "stream processed: ", time.clock(), ". Total processed: ", self.processed
        self._acquiringlock = False        
        return
