=========================
Persistence Format
=========================

Voyeur stores the data for a recording session in a single `HDF5 <http://www.hdfgroup.org/HDF5/>`_ file.
Voyeur uses HDF5's hierarchical format to organize the Protocols and Trials in a recording session.


=====  =====  ====== 
   Inputs     Output 
------------  ------ 
  A      B    A or B 
=====  =====  ====== 
False  False  False 
True   False  True 
False  True   True 
True   True   True 
=====  =====  ======

Session[1...j]/
===============
:creationDate: [UTC timestamp]
:timeZone: (needed?)

|indent| Trials/
*************************


    ========  ======== =========
     Parameters Table
    ----------------------------
    param1    param2   param3 
    ========  ======== =========
    trial1    trial1    trial1
    trial2    trial2    trial2

    trial[m]  trial[m]  trial[m]
    ========  ======== =========

|vertical|

.. |vertical| unicode:: U+2003 .. vertical space

|indent| |indent| Trial[1...k]/
-------------------------------
            :trialIndex: row in containing Protocol's parameters tables
    
                ========  ======== =========
                 Event Table
                ----------------------------
                param1    param2   param3 
                ========  ======== =========
                event1    event1    event1
                event2    event2    event2

                event[m]  event[m]  event[m]
                ========  ======== =========

                |vertical|

                ========= ========= =========
                    Stream Table 
                -----------------------------
                param1    param2    param3 
                ========= ========= =========
                sample1   sample1   sample1
                sample2   sample2   sample2

                sample[m] sample[m] sample[m]
                ========= ========= =========

.. |indent| unicode:: U+2003 .. title indent

Variable-length arrays
======================

Columns in parameter tables must be fixed in size. To accommodate variable-length parameters, Voyeur stores a
Universally Unique Identifier (UUID) in the corresponding parameter column and adds an HDF5 array with the same
UUID for its name to the same group containing the parameter table.
