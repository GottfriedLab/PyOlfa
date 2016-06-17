===========================
Running a trial from Python
===========================

You can now run individual trials from within the Python interpreter, making use of the entire Voyeur stack except
the UI. Making use of the ``ExampleProtocol`` described in :ref:`User protocols`, we can run a single trial::

    >>> from voyeur.db import Persistor, Int
    >>> from voyeur.protocol import Protocol
    >>> from voyeur.arduino import SerialPort
    >>>
    >>> # Set up Voyeur persistence and Adruino stack
    >>> persistor = Persistor()
    >>> persistor.create_database('monitor_demo','Demo database')
    >>> serial = SerialPort('osx.conf') #path to configuration file
    >>>
    >>> # Create the protocol instance
    >>> protocol = ExampleProtocol()
    >>> 
    >>> # Create a Monitor instance
    >>> from voyeur.monitor import Monitor
    >>> monitor = Monitor(persistor=persistor, serial=serial, protocol=protocol)
    >>>
    >>> # Set the protocol parameters
    >>> protocol.count = 3
    >>> protocol.value = 1.0
    >>>
    >>> # Acquire a trial
    >>> monitor.acquire_trial()

