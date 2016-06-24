Voyeur architecture
===================

The Voyeur system is a multi-component system, comprised of the Arduino hardware, a communication
module (:mod:`arduino`) for talking to the hardware, a data storage system (:mod:`db`),
a user interface (:mod:`ui`) and a software :mod:`monitor`.
The :class:`monitor.Monitor` class is responsible for coordinating the action of the rest of the components.

Specific experimental protocol details, including the parameters of the protocol are provided by user-written plugins called Protocols.
