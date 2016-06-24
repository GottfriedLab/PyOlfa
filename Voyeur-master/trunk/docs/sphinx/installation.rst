=================
Installing Voyeur
=================

You can check out the latest Voyeur code from SVN::
    svn checkout https://svn.physionconsulting.com/voyeur/trunk voyeur


OS X
====

Dependencies
------------

Voyeur requires
	1. OS X 10.6 (Snow Leopard) or greater
	3. Arduino `0021 <http://www.arduino.cc/en/Main/Software>`_ or greater.
	4. Nokia `Qt 4.7.1 <http://qt.nokia.com/downloads/sdk-mac-os-cpp>`_ or greater.



Install
-------

#. Install the dependencies above.
#. Run the Voyeur OS X `installer <https://code.physionconsulting.com/projects/dudman-acq/files>`_
#. From within the Voyeur source root directory, run the following command in the terminal::

    python setup.py install
#. There is a bug in the Enthought Traits UI for Qt module in version 3.6.0. You may need to change the 2 to a 1 at
line XXX of
/Library/Frameworks/Python.framework/Versions/2.7/lib/python2.7/site-packages/enthought/qt/__init__.py after installation.

Installation on OS X requires administrator privileges.


Windows
=======


Dependencies
------------
1. Windows XP or later (we have not tested on Vista or Windows 7)
2. Arduino `0021 <http://www.arduino.cc/en/Main/Software>`_
3. The `Enthought Python Distribution <http://www.enthought.com/products/getepd.php>`_ (32-bit)
4. Nokia `Qt 4.7.1 <http://qt.nokia.com/downloads/sdk-windows-cpp>`_ or greater.
5. `PyQt <http://www.riverbankcomputing.co.uk/software/pyqt/download>`_


Install
-------

#. Install the dependencies above.
#. From within the Voyeur source root directory, run the following command in the terminal::

    python setup.py install

