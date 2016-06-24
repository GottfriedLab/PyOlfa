Installation
===

Prepare your python environment
---
We recommend the Anaconda Python distribution. For now, Python 2.7 is required, so make sure you install the correct version of 
the Anaconda. <b>If you're using Windows, please restart after installation to update your path!</b>

Verify that you're using anaconda ion the command line:

    which python

This should return the path to your newly install anaconda distribution.
 
Once you have your favorite python distribution installed, please make sure the following packages are installed:

* pytables
* chaco
* kiwisolver
* pyqt
* traits
* traitsui
* pyserial

If you're using anaconda, you can install all of these from the command line very easily using the conda program:

    conda install pytables chaco kiwisolver pyqt traits traitsui pyserial
    
If you're using another distribution, you'll also need numpy and scipy packages installed, but these will be installed
by default with the other requirements listed above!

Installation of Voyeur
---
1. Clone or download the zip of the repository from Github (https://github.com/olfa-lab/Voyeur/archive/master.zip) and 
unzip it if required. Don't worry where you put it, installation will copy it into the right place!
2. Navigate to this directory in the command line.
3. Go to the trunk directory and run
    
    python setup.py install
    
4. If there are no errors, open a python instance in the command line by typing "python". Run "import Voyeur" to see if
the package has been successfully installed.

Add a configuration file
---
Voyeur wants to know about your system. Things like the COM port that hosts your Arduino (behavior box) are very 
important to it.

In the Voyeur/trunk/config folder of this repository is an example configuration file called "rinberg.conf". Copy and 
rename this to another folder on your computer, the name does not matter. Rinberg lab: use C:\voyeur_rig_config\rinberg.conf

Currently most of the configuration data is not used. The important fields are:

    [serial]
    baudrate = 115200
    [[windows]]
        port1 = COM3

Change the "port1" variable to the com port that your behavior box is attached to.

Next, you must add an environment variable. It is possible to do this through your IDE, but we recommend adding it 
through windows:

1. From the control panel open System.
2. Go to the Advanced tab and click Environment Variables...
3. Under System variables, click New.
4. For the variable name, use Voyeur_config, for value, use the path to your config file (ie C:\voyeur_rig_config\rinberg.conf)

Testing your installation
---
Currently there are no test routines to ensure the Voyeur core is functioning properly. This functionality will be added
at some point.
