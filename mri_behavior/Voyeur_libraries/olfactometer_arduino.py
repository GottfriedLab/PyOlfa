'''
Created on 2011-03-11, 
Uportdated on 2015-08-07
version: 1.2

@author: Admir Resulaj

License: GPLv3 or earlier version of GPL if user chooses so.
'''

import itertools
import time, serial, os
from serial import Serial, SerialException

# Change the gui toolkit from the default to qt version 4
from traits.etsconfig import etsconfig
etsconfig.ETSConfig.toolkit = 'qt4'

# Pyside import modules for gui elements.
from PySide import QtCore, QtGui
from PySide.QtCore import QObject, QTimer, SIGNAL
from PySide.QtGui import QPalette, QHBoxLayout, QIcon
from PySide.QtGui import QPushButton, QWidget, QGridLayout, QGroupBox
from PySide.QtGui import QSlider, QLineEdit, QLCDNumber, QButtonGroup, QFont
# Imports from the traits and traitsui packages.
from pyface.action.api import Action, MenuManager, MenuBarManager, Separator
from pyface.api import ApplicationWindow, GUI, information, error
from pyface.timer.api import Timer
from traits.api import Instance, Int, Str, Float, List

# Utilities written for the voyeur package.
from Voyeur_utilities import parse_rig_config
from voyeur.monitor import Monitor

# Flag for operating in debug mode.
TEST_OLFA = False

# Imports for listing the communication ports available by the OS.
if os.name == 'nt':
    import _winreg as winreg
else:
    from serial.tools import list_ports 

class Valvegroup(QWidget, QObject):
    """ Widget that has a button group object for a set of vials(pair of valves)
    
    The buttons are exclusive. There is one normally ON valve channel, which
    is used as a no odorant channel. When a valve/vial different from
    the normally ON is toggled, this will also toggle the normally ON channel,
    hence shutting it down and diverting flow to the odor channel that was
    switched ON. 
    """

    # Button group with the buttons representing vials.
    valves = Instance(QButtonGroup)
    # The currently checked(pressed) button, representing the currently ON vial.
    ON_valve = 0
    # Reference to the Voyeur Monitor or serial connection to Arduino.
    # This object should have a send_command method for sending a string to
    # the Arduino controller.
    olfa_communication = Instance(Monitor)
    # Address of the olfactometer module in the system. This is the I2C address.
    olfactometer_address = Int(1)
    # Minimum time needed between different valves/vials being opened to prevent
    # contamination. Value is in milliseconds.
    MINIMUM_VALVE_OFF_TIME = 1000
    def __init__(self,
                 monitor, 
                 parent=None, 
                 name="Odor Valves", 
                 olfactometer_address=1, 
                 background_vial=4,
                 valve_numbers=(1, 13),
                 ):
        """ Creates the Valvegroup object with the given number of valve 
        buttons.
        
        monitor :   is the parent process that has the communication link with
                    the physical device. Currently it is the Monitor class of 
                    the Voyeur package, which has a link to the serial port.
        parent  :   is the parent of the Widget.
        name    :   is the name for the Widget group, displayed in the UI.
        olfactometer_address  : is the address of the Olfactometer device.
                                Currently, this holds the I2C address of
                                olfactometer controller board.
        background_vial       : is the number of the vial for the background
                                channel, which is normally opened.
                                This represents a dummy vial that should
                                normally output no odorant.
        valve_numbers         : is the [lower, upper) limit for the sequential
                                numbering of the valves/vial channels. I.e the
                                valves/vials will be numbered from lower to 
                                upper-1.
        
        """
         
        print "Initializing olfactometer_arduino..."
        super(Valvegroup, self).__init__(parent)
        # Reference to the object that has the communication link to the 
        # olfactometer's Arduino controller.
        self.olfa_communication = monitor
        # The widget that is the parent, i.e the Olfactometer widget.
        self.parent_olfa = parent
        self.olfactometer_address = olfactometer_address
        self.background_vial = background_vial  # the normally open vial/valve
        # The currently checked (pressed) button representing the normally ON
        # valve.
        self.valves = QButtonGroup()
        self.valve_group_box = QGroupBox(name)
        # Horizontal layout for the buttons.
        buttonlayout = QHBoxLayout()
        buttonlayout.addStretch(1)
        
        # Flag that indicates if a valve/vial can be safely opened without
        # risking contamination. The lock out time is MINIMUM_VALVE_OFF_TIME .
        self.safe_to_open = True
        
        # Add the buttons for each valve/vial.
        for valve_number in range(valve_numbers[0], valve_numbers[1]):
            button = QPushButton(str(valve_number))
            # Make buttons checkable.
            button.setCheckable(True)
            self._paint_button(button, False)
            button.setMinimumSize(35, 35)
            button.setFont(QFont("Verdana", 10, QFont.DemiBold))
            # Add button to the groupbox layout and button group object.
            self.valves.addButton(button, valve_number)
            buttonlayout.addWidget(button)
        # Normally open vial button text.
        self.valves.button(background_vial).setText("Background")
        self.valves.button(background_vial).setMinimumSize(100,35)
        buttonlayout.addStretch(1)
        self.ON_valve = 0
        # Turn off any vials that may be open.
        if monitor is not None:
            self.all_OFF()
            self.valves.button(self.background_vial).setChecked(True)
        # Button clicked signal.
        self.connect(self.valves, SIGNAL('buttonClicked (int)'),
                     self._button_clicked)
        # Handle to the group box layout.
        self.valve_group_box.setLayout(buttonlayout)
        print "Initialization done!"

    def _button_clicked(self, button_number):
        """ Handler for a button clicked event."""
        
        if not self._check_olfactometer_comm():
            return
        
        # Background, normally ON (N/O) vial button was pressed.
        if (button_number == self.background_vial):
            # Toggle background valve --> turn normally open valve ON which
            # stops background flow.
            if (self.ON_valve == self.background_vial):
                self.set_background_valve()
            # Turn OFF N/O vial. This restores background flow and shuts off
            # any other valves/vials currently ON.
            else:
                self.set_background_valve(valve_state=0)
            return
        
        # If we pressed the currently toggled button, turn this valve/vial OFF
        # and switch to the background channel. This turns OFF the currently
        # ON channel.
        if (self.valves.checkedButton() == self.valves.button(self.ON_valve)):
            self.set_odor_valve(button_number, valve_state=0)
        # A different button was pressed. Turn ON the new vial if possible.
        else:
            self.set_odor_valve(button_number)
        # If the valve was not set, don't change the button that is checked.
        if (self.valves.checkedId() != self.ON_valve and self.ON_valve > 0):
            self.valves.button(self.ON_valve).setChecked(True)
            self._paint_button(self.valves.button(self.ON_valve), True)
        
    def _clear_valve_lockout(self):
        """ Clear the lockout and allow new odor channels to open. """ 
        self.safe_to_open = True
        
    
    def _check_olfactometer_comm(self):
        """ Check parent olfactometer for connectivity and report result. """
        
        if self.olfa_communication is None:
            print "Not connected to the olfactometer!"
            return False
        return True
    
    def _check_olfactometer_MFCs(self):
        """ Check parent olfactometer for MFC operational status.
        
        This method checks that flows are not out of operational range.
        """

        if not self.parent_olfa.check_MFCs() and not TEST_OLFA:
            print "MFC check failed! Aborting odor vial command!"
            return False
        return True
    
    def _send_command(self, command):
        """ Send a command to the olfactometer hardware. """

        line = self.olfa_communication.send_command(command)
        if line.split()[0] != 'Error':
            return True
        else:
            print "Error reported from Arduino: ", line
            return False
    
    def set_odor_valve(self, valve_number, valve_state=1):
        """ Sets a given odor vial ON/OFF . 
        
        This method sends the vialOff or vialOn command to the Arduino. """
        
        if not self._check_olfactometer_comm() or \
                not self._check_olfactometer_MFCs():
            return False
        
        # Normally ON valve/vial. Jump to the method that handles the background
        # channel.
        if valve_number == self.background_vial:
            return self.set_background_valve(valve_state)
     
        # If another odor channel is already ON or it has not been closed for a
        # sufficient time, return without doing anything to prevent
        # cross-contamination.
        if not self.safe_to_open and valve_state == 1 and not TEST_OLFA:
            print "Operation not permitted: previous odor valve/vial must be "\
                    "closed for %s milliseconds before another odor channel "\
                    "is opened! This prevents cross-contamination." \
                     %(self.MINIMUM_VALVE_OFF_TIME)
            return False
        
        # Different valve/vial from the currently ON odor channel.
        if (valve_number != self.ON_valve):
            # Request to turn that valve ON.
            if valve_state == 1:
                # This is an extra check. It should not get to this point.
                if self.ON_valve != self.background_vial and self.ON_valve != 0\
                    and not TEST_OLFA:
                    print "Operation not permitted! Cannot open an odor "\
                            " channel while another one is ON. THis prevents "\
                            " cross-contamination."
                    return False
                command = "vialOn "
                command += str(self.olfactometer_address) + " " + \
                            str(valve_number)
                if self._send_command(command):
                    self.safe_to_open = False
                    if self.ON_valve != 0:
                        self._paint_button(self.valves.button(self.ON_valve),
                                           False)
                    self.ON_valve = valve_number
                    button = self.valves.button(valve_number)
                    button.setChecked(True)
                    self._paint_button(button, True)
                else:
                    return False
            # Turn OFF a vial that is not ON? Notify of this happenence. 
            else:
                print "Odor channel %i is already closed!" %(valve_number)
        # Requested vial is already ON.        
        elif valve_state == 1:
            print "Odor channel %i is already opened!" %(valve_number)
        # Turn OFF currently ON valve/vial. This turns on the background
        #  channel, i.e. the normally ON vial/valve.
        else:
            command = "vialOff "
            command += str(self.olfactometer_address) + " " + str(valve_number)
            if self._send_command(command):
                # Clears the vial lockout after MINIMUM_VALVE_OFF_TIME 
                # milliseconds of air has passed through the olfactometer.
                Timer.singleShot(self.MINIMUM_VALVE_OFF_TIME,
                                 self._clear_valve_lockout)
                self.ON_valve = self.background_vial
                button = self.valves.button(self.background_vial)
                button.setChecked(True)
                self._paint_button(button, True)
                self._paint_button(self.valves.button(valve_number), False)
            else:
                return False
        return True
    
    def set_valve(self, valve_number, valve_state=1):
        """ Sets a given valve ON/OFF """

        if self.olfa_communication is None:
            print "Not connected to the olfactometer!"
            return False
        
        # Don't mess with odor valves; Those are only turned ON/OFF with vial
        # commands.
        if valve_number > 6 and not TEST_OLFA:
            print "Operation not permitted: Valve number %i is an odor valve. "\
                    "This prevents cross-contamination. Go to Test mode to" \
                    " allow this operation." %(valve_number)
            return False
        
        # Turn valve ON/OFF.
        command = "valve " + str(self.olfactometer_address) + " " + \
                        str(valve_number)
        if valve_state:
            command += " on"
        else:
            command = " off"
        if not self._send_command(command):
            return False
        return True
    
    def _paint_button(self, button, is_toggled):
        """ Change the stylesheet of the button according to toggled state. """
        
        if is_toggled:
            button.setStyleSheet("background-color: rgb(10,100,200);\
                                  border-radius: 5px; border-style: outset;\
                                  border-width: 2px; border-color: cyan")
        else:
            button.setStyleSheet("background-color: rgb(10,200,250);\
                                  border-radius: 5px; border-style: outset;\
                                  border-width: 2px; border-color: cyan")
        
    
    def set_background_valve(self, valve_state=1):
        """ Sets the normally open valve/vial ON/OFF. """
        
        if not self._check_olfactometer_comm():
            return
        
        #TODO: Add error checks in comm.
        if(self.ON_valve == self.background_vial) and valve_state == 1:
            # Turn only normally ON solenoids ON (i.e. shutting the air flow).
            command = "vial " + str(self.olfactometer_address) + " " + \
                         str(self.background_vial) + " on"
            if self._send_command(command):
                # Temporarily disable exclusive status to update the GUI.
                self.valves.setExclusive(False)
                # Untoggle valve button.
                self.valves.button(self.background_vial).setChecked(False)
                self._paint_button(self.valves.button(self.background_vial),
                                   False)
                self.ON_valve = 0  # No button pressed
                # Reset exlusive state for the button group.
                self.valves.setExclusive(True)
            else:
                return            
        # No button is currently pressed in the GUI. Normally open valve may
        # be ON, i.e. the channel is closed. Set it OFF to make sure there is 
        # background air flowing through the olfactometer.
        elif(self.valves.button(self.ON_valve) is None):
            command = "vial " + str(self.olfactometer_address) + " " \
                        + str(self.background_vial) + " off"
            if self._send_command(command):
                self.ON_valve = self.background_vial
                self.valves.button(self.background_vial).setChecked(True)
                self._paint_button(self.valves.button(self.background_vial),
                                   True)
            else:
                return
        else:
            # Turn OFF current valve first.
            command = "vialOff "
            command += str(self.olfactometer_address) + " " + str(self.ON_valve)
            if self._send_command(command): 
                # Clears the vial lockout after MINIMUM_VALVE_OFF_TIME
                # milliseconds of air have passed through the olfactometer.
                Timer.singleShot(self.MINIMUM_VALVE_OFF_TIME,
                                 self._clear_valve_lockout)
                self._paint_button(self.valves.button(self.ON_valve), False)
                # Indicate that background channel is now active.
                self.valves.button(self.background_vial).setChecked(True)
                self._paint_button(self.valves.button(self.background_vial),
                                    True)
                self.ON_valve = self.background_vial

    def all_OFF(self):
        """ Turns all vials OFF. """
        
        if not self._check_olfactometer_comm():
            return
        
        for button in self.valves.buttons():
            # We assume that each button was labelled by the correct vial
            # channel number in the olfactometer.
            vial = self.valves.id(button)
            command = "vialOff " + str(self.olfactometer_address) + " " + \
                        str(vial)
            if not self._send_command(command):
                # Comm. problem? Abort!
                return
        # Clears the vial lockout after the required amount of time in 
        # milliseconds of air has flushed through the olfactometer.
        Timer.singleShot(self.MINIMUM_VALVE_OFF_TIME, self._clear_valve_lockout)
        self.valves.button(self.background_vial).setChecked(True)
        self.ON_valve = self.background_vial
    
class MFC(QWidget):
    """A single MFC widget that has a slider and line text edit box. 
    
    The physical MFC connected can be interfaced with via the set_MFC_rate and
    get_MFC_rate methods, which are functions that depend on the protocol of
    the interface (for example analag or digital.
    
    """
    
    mfcgroup = Instance(QGroupBox)
    mfcslider = Instance(QSlider)
    mfctextbox = Instance(QLineEdit)
    mfcvalue = float()  # value of mfc rate we want
    olfa_communication = Instance(Monitor)  # reference to the Voyeur Monitor or serial connection to Arduino
    mfcindex = Int()  # index of MFC in the module
    olfactometer_address = Int()  # index of the module in the system connected
    # MFC capacity determined by the MFC hardware
    mfccapacity = float()
    # MFC units
    mfcunits = str()
    timer = Instance(QTimer)
    auxilary_analog_read_pin = 6
    auxilary_analog_write_pin = 1

    def __init__(self, parent, monitor, mfcindex, name, value=-1, pollingtime=4000, olfactometer_address=1, MFCtype='alicat_digital'):
        """ creates an MFC widget """

        self.setMFCrate = MFCprotocols[MFCtype]['setMFCrate']
        self.getMFCrate = MFCprotocols[MFCtype]['getMFCrate']

        # Base class constructor
        super(MFC, self).__init__(parent)
        # parent_olfactometer dll library connection
        self.olfa_communication = monitor
        self.parent_olfactometer = parent
        self.mfcindex = mfcindex  # index of MFC in the module
        self.olfactometer_address = olfactometer_address  # index of the slave in the system
        self.flow = 0.
        # TODO: Get MFC info if operating in digital mode
        # self._getMFCtype()
        if name == "Air":
            self.mfccapacity = 1000
        elif name == "Nitrogen":
            self.mfccapacity = 100
        elif name == "Background":
            self.mfccapacity = 1000
        self.name = name
        self.mfcunits = "sccm"
        # inter polling time interval
        self.pollingtime = pollingtime
        # MFC group box
        name = name + " " + str(self.mfccapacity) + str(self.mfcunits)
        self.mfcgroup = QGroupBox(name, parent)
        # MFC group layout
        mfclayout = QGridLayout()
        # MFC slider
        self.mfcslider = QSlider(QtCore.Qt.Vertical)
        self.mfcslider.setMaximum(int(self.mfccapacity))
        # MFC line edit
        self.mfctextbox = QLineEdit()
        self.mfctextbox.setPlaceholderText("Set value")
        """ Signals """
        # MFC lcd display, connected to the slider change
        lcd = QLCDNumber()
        lcd.setMinimumSize(50, 25)
        self.connect(self.mfcslider, SIGNAL('valueChanged(int)'), lcd,
            QtCore.SLOT('display(int)'))
        self.connect(self.mfcslider, SIGNAL('sliderReleased()'), self._sliderchanged)
        self.connect(self.mfcslider, SIGNAL('sliderPressed ()'), self._sliderpressed)
        # Line edit box changes connected to the slider and lcd visualization
        self.connect(self.mfctextbox, SIGNAL('textChanged (const QString&)'),
                     self._textchange)
        # Line edit box finished editing
        self.connect(self.mfctextbox, SIGNAL('editingFinished ()'),
                     self._textchanged)
        # initialize value of MFC
        if(value == -1) or (value > self.mfccapacity):
            flow = self.getMFCrate(self)
            if flow != None:
                self.mfcslider.setValue(flow * self.mfccapacity)
                self.last_poll_time = time.time()
        else:
            self.setMFCrate(self, value)
            self.last_poll_time = 0.
        # add the slider and textbox to the layout
        mfclayout.addWidget(self.mfcslider, 0, 0, 2, 1)
        mfclayout.addWidget(self.mfctextbox, 0, 1, 1, 2)
        mfclayout.addWidget(lcd, 1, 1, 1, 2)
        # add the layout to the group box
        self.mfcgroup.setLayout(mfclayout)
        if(self.mfcunits == None):
            self.mfcgroup.setEnabled(False)
        return
    
    
    def _textchange(self, value):
        """ slot for when text in the line edit is changing
        Causes the change in the visualization (slider + lcd) """
        self.parent_olfactometer.stop_mfc_polling()  # stop the timer while we're updating the MFC value
        try:
            value = int(value)
        except ValueError:
            value = 0
        self.mfcslider.setValue(int(value))
        return
    def _textchanged(self):
        """ Text of the line edit has changed. Sets the new MFC value """
        value = float(self.mfctextbox.text())
        # if value is different from current rate, set the new rate
        if abs(value - self.mfcvalue) > 0.0005:
            self.setMFCrate(self, value)
        self.parent_olfactometer.restart_mfc_polling()  # restart timer
        return
    def _sliderchanged(self):
        """ Slot when the slider has been changed and released """
        value = float(self.mfcslider.value())
        # if value is different from current rate, set the new rate
        if abs(value - self.mfcvalue) > 0.0005:
            self.setMFCrate(self, value)
        self.parent_olfactometer.restart_mfc_polling()  # restart the timer
        return
    def _sliderpressed(self):
        """ Slot for when the slider is pressed """
        # stop the timer as the user is updating the MFC value
        self.parent_olfactometer.stop_mfc_polling()
        return
    # def _startpolling(self):
    #     """ Start polling of the MFC measured output """
    #     self.timer.start(self.pollingtime)
    #     return
    def poll(self):
        """ Timer overflow SLOT. Updates the MFC flow representation"""
        # print QtCore.QTime.currentTime() # debuging printout to see frequency of polling
        flow = self.getMFCrate(self)
        #print "Polling...", flow
        if flow is not None:
            self.mfcslider.setValue(flow * self.mfccapacity)
            self.last_poll_time = time.time()
            return True
        else:
            return False


class Olfactometer(QWidget):
    """ Olfactometer widget that contains the widgets for a single parent_olfactometer """
    mfc1 = Instance(MFC)  # Mass flow controller object
    mfc2 = Instance(MFC)
    valves = Instance(Valvegroup)  # Valve group object
    def __init__(self, parent):
        """ creates an Olfactometer widget """
        # Base class constructor
        super(Olfactometer, self).__init__(parent)
        self.timer = QTimer()
        self.mfcs=[]
        self.polling_interval=0
        return

    def start_mfc_polling(self, polling_interval_ms=2000):
        self.polling_interval = polling_interval_ms
        self.mfcs = [self.mfc1, self.mfc2]
        self.last_mfc_checks = []
        for mfc in self.mfcs:
            self.last_mfc_checks.append(0.)
        self.connect(self.timer, SIGNAL('timeout()'), self.poll_mfcs)
        self.timer.start(polling_interval_ms)
        return

    def poll_mfcs(self):
        for i in xrange(len(self.mfcs)):
            mfc = self.mfcs[i]
            mfc.poll()
        return

    def stop_mfc_polling(self):
        self.timer.stop()
        return

    def restart_mfc_polling(self):
        self.timer.start(self.polling_interval)
        return

    def check_MFCs(self):
        flows_on = True
        for mfc in self.mfcs:
            time_elapsed = time.time() - mfc.last_poll_time
            if time_elapsed > 2.1 * self.polling_interval:  #TODO: don't hardcode this, although this is ~2 timer ticks.
                raise Exception('MFC polling is not ok.')
            if mfc.flow <= 0.:
                print '{0} MCF reporting no flow.'.format(mfc.name)
                flows_on = False
        return flows_on
    
    def read_mfc_flows(self):
        """ Check MFC flows and return the integer values in sccm """
        flows_sccm = []
        for i in xrange(len(self.mfcs)):
            mfc=self.mfcs[i]
            flows_sccm.append(mfc.flow*mfc.mfccapacity)
        return flows_sccm

class ViewAction(Action):
    """ The view window action """
    accelerator = Str('Ctrl-V')
    def perform(self):
        """ Performs the action. """
        print 'Performing', self.name
        return
def enumerate_serial_ports():
    """ Uses the Win32 registry to return an
    iterator of serial (COM) ports
    existing on this computer."""
    # TODO: make it platform independent, new traitsui has a tool that can be used
    
    if os.name == 'nt':
        path = 'HARDWARE\\DEVICEMAP\\SERIALCOMM'
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
        except WindowsError:
            raise IterationError
        for i in itertools.count():
            try:
                val = winreg.EnumValue(key, i)
                yield str(val[1])
            except EnvironmentError:
                break
    else:
        for port in list_ports.comports():
            yield port[0]


class SerialSelectionAction(Action):
    """ The Serial selection action, tied to the main window Menu bar """
    accelerator = Str('Ctrl-V')
    # controller window for this action
    controller = Instance(ApplicationWindow)
    # called when user performs the action (i.e clicks on the menu item choice in this case
    def perform(self):
        """ Performs the action. """
        # Get system known serials and make a list
        serials = enumerate_serial_ports()
        currentSerials = []
        for serial in serials:
            currentSerials.append(serial)
        # does this action correspond to an active serial?
        if self.name in currentSerials:
            # new serial selection?
            if self.name != self.controller.currentSerial:
                self.controller.currentSerial = self.name
                # establish the serial connection
                self.controller.create_serial(self.name)
                # new serial ports added?
                if(not currentSerials == self.controller.serialList):
                    self.controller._refresh_serial_ports(currentSerials)
        # update the serial list actions (i.e. Menu bar)
        else:
            self.controller._refresh_serial_ports(currentSerials)
        return


class SerialMonitor(Serial):
    """ Serial Connection Class that handles communication with Arduino """
    TIMEOUT = 1
    BAUDRATE = 115200
    def send_command(self, command, tries=10):
        for i in range(tries):
            self.write(command)
            self.write("\r")
            line = self.read_line()
#            if line == (command+'\r\n'):
#                print "Echoed command: ", line
            line = self.read_line()
            morebytes = self.inWaiting()
            if morebytes:
                # print "additional bytes sent: "
                extrabytes = self.read(morebytes)
                # print extrabytes
            if line:
                return line
    def read_line(self):
        """Reads the serial buffer"""
        line = None
        try:
            line = self.readline()
        except SerialException as e:
            print('pySerial exception: Exception that is raised on write timeouts')
            print(e)
        return line


class Olfactometers(ApplicationWindow):
    """ The main application window. """
    #### 'IWindow' interface ##################################################
    # The size and position of the window.
    size = (100, 100)
    position = (200, 200)
    # The window title.
    title = 'Olfactometers'
    olfas = []
    # The ratio of the size of the left/top pane to the right/bottom pane.
    ratio = Float(0.3)
    direction = Str('vertical')
    serialList = List
    currentSerial = Str
    # olfa =
    monitor = Instance(object)
    deviceCount = 1
    """mfc1 = Instance(MFC) # Mass flow controller object
    mfc2 = Instance(MFC)
    valves = Instance(Valvegroup) # Valve group object"""
    ###########################################################################
    # 'object' interface.
    ###########################################################################
    def __init__(self, monitor = None, config_obj = None, **traits):
        """ Creates a new application window. """
        # Base class constructor.
        super(Olfactometers, self).__init__(**traits)
        # Create an action that exits the application.
        exit_action = Action(name='E&xit', on_perform=self.close)
        # Serial Ports Menu
        self.serialPorts = MenuManager(name='Serial Port:')
        # Get the names from the OS
        # TODO: Try to talk to the serials to see which one is Arduino
        portnames = enumerate_serial_ports()
        for portname in portnames:
            portchoice = SerialSelectionAction(name=portname, controller=self, style='radio')
            self.serialPorts.append(portchoice)
            self.serialList.append(portname)
        # TODO: extend the Behaviour Box option to the connection list
        if monitor is not None:
            portchoice = SerialSelectionAction(name="Behaviour Box", controller=self, style='radio')
            self.serialPorts.append(portchoice)
            self.serialList.append("Behaviour Box")
        self.testing_mode = Action(style='toggle', name="Test Mode",
                                   on_perform=self._testing)
        # Add a menu bar.
        self.menu_bar_manager = MenuBarManager(
            MenuManager(
                        exit_action,
                        name='&File'),
            MenuManager(ViewAction(name='Compact', style='radio'),
                        ViewAction(name='Full', style='radio'),
                        Separator(),
                        name='&View'
                        ),
            MenuManager(self.serialPorts,
                        self.testing_mode,
                        name='&Tools')
        )
#        self.status_bar_manager = StatusBarManager(message='hi')
#        self._create_status_bar(self.control)
        # status_bar = self.status_bar_manager.create_status_bar(self.control)
        # monitor is the Voyeur Monitor that handles the COM port
        self.monitor = monitor
        self.config_obj = config_obj
        # check monitor serial connection
        if (self.monitor is None):# or not self.monitor.serial1.serial._isOpen):  # error dialog box here later
            print "Arduino Serial comm failed: Port not open"
            # return None
        # else:
            # TODO: find device number
            # self.devicecount =
        for i in range(self.deviceCount):
            panel = Olfactometer(self.control)
            panel.valves = Valvegroup(self.monitor, panel, olfactometer_address=i + 1)
            try:
                mfc1type =self.config_obj['olfas'][i]['MFC1_type']
            except:
                mfc1type = 'analog'
            try:
                mfc2type =self.config_obj['olfas'][i]['MFC2_type']
            except:
                mfc2type = 'analog'
            try:
                mfc3type = self.config_obj['olfas'][i]['MFC3_type']
            except:
                mfc3type = 'auxilary_analog'
            panel.mfc1 = MFC(panel, self.monitor, 1, "Air", olfactometer_address=i + 1, MFCtype=mfc1type)
            panel.mfc2 = MFC(panel, self.monitor, 2, "Nitrogen", olfactometer_address=i + 1, MFCtype=mfc2type)
            panel.mfc3 = MFC(panel, self.monitor, 3, "Background", olfactometer_address=i+1, MFCtype=mfc3type)
            panel.start_mfc_polling()
            # define the layout
            grid = QGridLayout(panel)
            grid.setSpacing(15)
            grid.addWidget(panel.mfc1.mfcgroup, 0, 0, 2, 1)
            grid.addWidget(panel.mfc2.mfcgroup, 0, 1, 2, 1)
            grid.addWidget(panel.mfc3.mfcgroup, 0, 2, 2, 1)
            grid.addWidget(panel.valves.valve_group_box, 1, 3, 1, 1)
            # add the layout container to the main window widget
            panel.setLayout(grid)
            palette = QtGui.QPalette(panel.palette())
            palette.setColor(QtGui.QPalette.Window, QtGui.QColor('red'))
            # set palette brushes here
            panel.setPalette(palette)
            panel.setAutoFillBackground(True)
            self.olfas.append(panel)
            # TODO: Turn everything off as we startup
            # if ret != 0:
            #    print "couldn't turn valves off"
        return
    # this draws the center widget
    def _create_contents(self, parent):
        splitter = QtGui.QSplitter(parent)
        splitter.setOrientation(QtCore.Qt.Vertical)
        for i in range(self.deviceCount):
            splitter.addWidget(self.olfas[i])
        return splitter
    def _updateMonitor(self):
        """ update the monitor instance for the elements of the Olfactometer """
        for olfa in self.olfas:
            olfa.valves.olfa_communication = self.monitor
            olfa.valves.all_OFF()
            olfa.mfc1.olfa_communication = self.monitor
            olfa.mfc2.olfa_communication = self.monitor
            olfa.mfc3.olfa_communication = self.monitor
    def create_serial(self, serial,verbose = True):
        """ Create a Serial connection to the Olfactometer """
        self.monitor = SerialMonitor(port=serial, baudrate=SerialMonitor.BAUDRATE, timeout=1)
        if self.monitor.isOpen():
            if verbose:
                information(self.control, "Port Opened!", serial)
            self._updateMonitor()
        else:
            error(self.control, "Failed openeing Port!!", serial)
    def _refresh_serial_ports(self, serialList):
        """ Refresh list of serial ports available """
        # Menu item Group
        self.serialPorts = MenuManager(name='Serial Port:')
        # Add choices for each Serial list item
        for portname in serialList:
            portchoice = SerialSelectionAction(name=portname, controller=self, style='radio')
            self.serialPorts.append(portchoice)
        # refresh the Serial Ports menu by first removing the current MenuManager list
        for group in self.menu_bar_manager.groups:  # top menu level
            for item in group.items:  # individual menus
                if item.name == '&Tools':  # Looking for the Tools menu
                    for tools in item.groups:  # Sub-menus of Tools menu
                        for toolmenu in tools.items:  # Looking for Serial-Port submenu
                            if toolmenu.name == 'Serial Port:':
                                tools.remove(toolmenu)  # Remove old menu
                                tools.append(self.serialPorts)  # add new menu
        # update menu_bar of the window and refresh
        menu_bar = self.menu_bar_manager.create_menu_bar(self.control)
        self.control.setMenuBar(menu_bar)
        self._create_contents(self.control)
    
    def _testing(self):
        """ Toggle test mode."""
        global TEST_OLFA

        TEST_OLFA = self.testing_mode.checked
        

# ---------- MFC PROTOCOLS -------------


def getMFCrate_analog(self, *args, **kwargs):
    """ get MFC flow rate measure as a percentage of total capacity (0.0 to 100.0)"""
    if self.olfa_communication is None:
        return
    command = "MFC " + str(self.olfactometer_address) + " " + str(self.mfcindex)
    rate = self.olfa_communication.send_command(command)
    self.flow = float(rate)
    if (rate < 0):
        print "Couldn't get MFC flow rate measure"
        print "mfc index: " + str(self.mfcindex), "error code: ", rate
        return None
    else:
        return float(rate)
    return

def setMFCrate_analog(self, flowrate, *args, **kwargs):
    """ sets the value of the MFC flow rate setting as a % from 0.0 to 100.0
        argument is the absolute flow rate """
    if self.olfa_communication is None:
        return
    if flowrate > self.mfccapacity or flowrate < 0:
        return  # warn about setting the wrong value here
    # if the rate is already what it should be don't do anything
    if abs(flowrate - self.mfcvalue) < 0.0005:
        return  # floating points have inherent imprecision when using comparisons
    command = "MFC " + str(self.olfactometer_address) + " " + str(self.mfcindex) + " " + str(flowrate * 1.0 / self.mfccapacity)
    set = self.olfa_communication.send_command(command)
    if(set != "MFC set\r\n"):
        print "Error setting MFC: ", set
    self.mfcvalue = float(flowrate)
    self.mfcslider.setValue(self.mfcvalue)

def setMFCrate_alicat(self, flowrate, *args, **kwargs):
    """

    :param flowrate: flowrate in units of self.mfccapacity (usually ml/min)
    :param args:
    :param kwargs:
    :return:
    """
    
    if self.olfa_communication is None:
        return
    if flowrate > self.mfccapacity or flowrate < 0:
        return
    if abs(flowrate-self.mfcvalue) < 0.0005:
        return
    flownum = (flowrate * 1. / self.mfccapacity) * 64000.
    flownum = int(flownum)
    command = "DMFC {0:d} {1:d} A{2:d}".format(self.olfactometer_address, self.mfcindex, flownum)
    confirmation = self.olfa_communication.send_command(command)
    if(confirmation != "MFC set\r\n"):
        print "Error setting MFC: ", confirmation
    else:
        # Attempt to read back
        command = "DMFC {0:d} {1:d}".format(self.olfactometer_address, self.mfcindex)
        returnstring = self.olfa_communication.send_command(command)
        
    self.mfcvalue = float(flowrate)
    self.mfcslider.setValue(self.mfcvalue)

def getMFCrate_alicat(self, *args, **kwargs):
    """

    :param args:
    :param kwargs:
    :return: float flowrate normalized to max flowrate.
    """
    #print "trying to get rate from MFC: ", self.mfcindex
    start_time = time.clock()
    if self.olfa_communication is None:
        return
    command = "DMFC {0:d} {1:d} A".format(self.olfactometer_address, self.mfcindex)

    # Try for 200 ms. If we fail, return None
    while (time.clock() - start_time < .2):
        confirmation = self.olfa_communication.send_command(command)
    
        if confirmation.startswith("MFC set"):
            command = "DMFC {0:d} {1:d}".format(self.olfactometer_address, self.mfcindex)
            returnstring = self.olfa_communication.send_command(command)
        else:
            warning_str = "MFC {0:d} not read.".format(self.mfcindex)
            raise Warning(warning_str)

        try:
            li = returnstring.split(' ')
            r_str = li[4]  # 5th column is mass flow, so index 4.
            flow = float(r_str)
            flow = flow / self.mfccapacity  # normalize as per analog api.
            #print "Rate extracted: ", flow
            if (flow < 0):
                print "Couldn't get MFC flow rate measure"
                print "mfc index: " + str(self.mfcindex), "error code: ", flow
                return None
            #print "It took: ", time.clock()-start_time, "seconds"
            #print "MFC returned message: ", returnstring
            self.flow = flow
            return flow
        except:  # if any errors, print the return string.
           print "Couldn't get MFC flow rate measure.\nMFC index: {0:d}, return string: '{1:s}'".format(self.mfcindex,
                                                                                                        returnstring)
        return None
    
def get_MFC_rate_auxilary_analog(self, *args, **kwargs):
    """ Poll the MFC for the current flow rate. 
    
    :param args:
    :param kwargs:
    :return: float flowrate normalized to max flowrate.
    
    The MFC is assumed to be connected to the auxiliary analog output and analog
    input on the 10x2 header connected to the Atmel controller of the
    olfactometer controller board.
    """
    start_time = time.clock()
    if self.olfa_communication is None:
        return
    command = "analogRead {0:d} {1:d}".format(self.olfactometer_address,
                                              self.auxilary_analog_read_pin)
    
    # Try for 200 ms. If we fail, return None
    while (time.clock() - start_time < .2):
        confirmation = self.olfa_communication.send_command(command)
        
        try:
            rate = float(confirmation)
        except:
            warning_str = "Got a non-float value as a response when reading MFC {0:d}"\
                     " flow rate.".format(self.mfcindex)
            raise Warning(warning_str)
        
        self.flow = rate
        if (rate < 0):
            print "Couldn't get MFC flow rate measure"
            print "mfc index: " + str(self.mfcindex), "error code: ", flow
            return None
        return rate
    return None

def set_MFC_rate_auxilary_analog(self, flow_rate, *args, **kwargs):
    """ Set the MFC rate via the auxilary analog output.
    
    This function assumes that the analog input channel of the MFC is
    connected to the auxiliary 10x2 header of the Atmel processor of the
    olfactometer controller board.
    
    :param flow_rate: Flow rate to set in units of self.mfccapacity 
                        (usually ml/min)
    :param args:
    :param kwargs:
    :return:
    
    """
    
    if self.olfa_communication is None:
        return
    if flow_rate > self.mfccapacity or flow_rate < 0:
        return
    if abs(flow_rate-self.mfcvalue) < 0.0005:
        return
    command = "analogSet {0:d} {1:d} {2:f}".format(self.olfactometer_address,
                                               self.auxilary_analog_write_pin,
                                               flow_rate/self.mfccapacity)
    confirmation = self.olfa_communication.send_command(command)
    if(confirmation != "analog-out set\r\n"):
        print "Error setting MFC: ", confirmation
        return
        
    self.mfcvalue = float(flow_rate)
    self.mfcslider.setValue(self.mfcvalue)

analog_protocol = {'getMFCrate': getMFCrate_analog,
                   'setMFCrate': setMFCrate_analog}
alicat_digital = {'getMFCrate': getMFCrate_alicat,
                  'setMFCrate': setMFCrate_alicat}
auxilary_analog = {'getMFCrate': get_MFC_rate_auxilary_analog,
                   'setMFCrate': set_MFC_rate_auxilary_analog}

MFCprotocols = {'analog': analog_protocol,
                'alicat_digital': alicat_digital,
                'auxilary_analog': auxilary_analog}



# Application entry point.
if __name__ == '__main__':
    # Create the GUI (this does NOT start the GUI event loop).
    gui = GUI()
    # Create and open the main window.
    config_obj = parse_rig_config("C:\Users\Gottfried_Lab\PycharmProjects\Mod_Voyeur\mri_behavior\Voyeur_libraries\\voyeur_rig_config.conf")
    window = Olfactometers(None, config_obj=config_obj)
    window.open()
    # Start the GUI event loop!
    gui.start_event_loop()
##### EOF #####################################################################
