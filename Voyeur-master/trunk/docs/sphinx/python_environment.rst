===========================================
Setting up a Python development environment
===========================================


Learning Python
===============

The best (complete, well written, and relatively short) tutorial on Python is the 
`Python Tutorial <http://docs.python.org/tutorial/index.html>`_ at python.org.

The tutorial uses the standard Python interpreter (what you get if you type ``python`` at the command line), but virtually everyone uses 
`IPython <http://ipython.scipy.org>`_, an enhanced interpreter with nice things like tab completion, better integration with help etc. You can install IPython using EasyInstall, the python package manager. At the command line::

    sudo easy_install -U ipython

IPython is started via ``ipython``. On Windows, IPython is included with the `Enthought Python Distribution <http://www.enthought.com/products/getepd.php>`_, which we recommend for Voyeur on Windows.

A Python Development Environment
================================

Python does not require a dedicated development environment or compiler. You can write Python code in any text editor.

Python uses whitespace instead of delimiters (e.g. { and }) to define blocks of code. Thus whitespace is significant in Python. Community convention is to use spaces instead of tabs for indentation. Thus a text editor with the ability to select tabs vs. spaces for indentation is useful. If you are an Emacs or vi user, both have excellent Python support. If not, we recommend 
`Text Mate <http://macromates.com/>`_ on OS X. There are many 
`editors and IDEs <http://wiki.python.org/moin/PythonEditors>`_ with Python support, however, and you may want to explore a bit.

Voyeur's distribution includes a protocol plugin template which you can copy and customize. This template includes support for unit testing your protocol. To do so, add any test functions that you would like to the module. You can then run the tests at the command line::

    nosetests my_plugin.py

or by running the plugin module directly::
    
    python my_plugin.py

Many Python editors/IDEs, including ``IPython`` will also let you run unit tests directly in the editor or interpreter.

The development workflow then consists of writing code and tests, running the tests at the command-line, editing code to fix errors and re-running tests at the command line.
