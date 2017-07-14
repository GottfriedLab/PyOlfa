'''
Created on 2015_08_04

@author: Admir Resulaj

This protocol implements a passive odor paradigm for the Voyeur/Arduino 
platform. This includes the protocol behaviour as well as visualization (GUI).
'''

# Python library imports
from numpy import append, arange, hstack, nan, isnan, copy, negative
from copy import deepcopy
import time, os
from numpy.random import permutation  #numpy >= 1.7 for choice function
from random import choice, randint, shuffle, seed, random
from datetime import datetime
from configobj import ConfigObj
from itertools import chain, groupby
from PyQt4.QtCore import QThread

# Voyeur imports
import voyeur.db as db
from voyeur.monitor import Monitor
from voyeur.protocol import Protocol, TrialParameters, time_stamp
from voyeur.exceptions import SerialException, ProtocolException

# Olfactometer module
from olfactometer_arduino import Olfactometers
from olfactometer_arduino import SerialMonitor as olfa_monitor

# Utilities
from Stimulus import LaserStimulus, LaserTrainStimulus  # OdorStimulus
from range_selections_overlay import RangeSelectionsOverlay
from Voyeur_utilities import save_data_file, parse_rig_config, find_odor_vial

# Enthought's traits imports (For GUI) - Place these imports under
#   voyeur imports since voyeur will select the GUI toolkit to be QT
#   By default traits will pick wx as the GUI toolkit. By importing voyeur
#   first, QT is set and used subsequently for all gui related things
from traits.trait_types import Button
from traits.api import Int, Str, Array, Float, Enum, Bool, Range,\
                                Instance, HasTraits, Trait, Dict, DelegatesTo
from traitsui.api import View, Group, HGroup, VGroup, Item, spring, Label
from chaco.api import ArrayPlotData, Plot, VPlotContainer,\
                                DataRange1D
from enable.component_editor import ComponentEditor
from enable.component import Component
from traitsui.editors import ButtonEditor, DefaultOverride
from pyface.timer.api import Timer, do_after
from pyface.api import FileDialog, OK, warning, error
from chaco.tools.api import PanTool
from chaco.axis import PlotAxis
from chaco.scales.api import TimeScale
from chaco.scales_tick_generator import ScalesTickGenerator
from chaco.scales.api import CalendarScaleSystem
from traits.has_traits import on_trait_change

import warnings
# warnings.simplefilter(action = "ignore", category = FutureWarning)
warnings.filterwarnings("ignore")

class Passive_odor_presentation(Protocol):
    """Protocol and GUI for a 2AFC behavioral paradigm."""

    # Streaming plot window size in milliseconds.
    STREAM_SIZE = 5000
    
    # Number of trials in a block.
    BLOCK_SIZE = 20

    # Flag to indicate whether we have an Arduino, Olfactometer, Scanner connected. Set to 0 for
    # debugging.
    ARDUINO = 1
    OLFA = 1
    FMRI = 1

    # Flag to indicate whether we are training mouse to lick or not. Set to 0 when not training
    LICKING_TRAINING_PROBABILITY = 1

    # Number of trials in one sliding window used for continuous
    # visualizing of session performance.  .0+---
    SLIDING_WINDOW = 100
    
    # Amount of time in milliseconds for odorant vial to be ON prior to
    # trial start. This should be sufficiently large so that odorant makes it to
    # the final valve by the trial start.
    VIAL_ON_BEFORE_TRIAL = 1500

    # Maximum trial duration to wait for, in seconds, before we assume problems
    # in communication.
    MAX_TRIAL_DURATION = 100
    
    # Number of initial trials to help motivating the subject to start
    # responding to trials.
    INITIAL_TRIALS_TYPE = 1 #0: LEFT, 1: RIGHT, 2: RIGHT then LEFT,, 3: LEFT then RIGHT
    INITIAL_TRIALS = 0 # Must be even number. If INITIAL_TRIALS_TYPE is 2 or 3, there will half of initial trials right and half of initial trials left

    # Number of samples for HRF
    TR = 1000
    HRF_SAMPLES = 1
    
    # Mapping of stimuli categories to code sent to Arduino.
    stimuli_categories = {
                          "Right": 0,
                          "Left" : 1,
                          "None" : 2,
                          }
    # Dictionary of all stimuli defined (arranged by category), with each
    # category having a list of stimuli.
    stimuli = {
               stim_category: [] for stim_category in stimuli_categories.keys()
               }
    
    # Mapping of sniff phase name to code sent to Arduino.
    odorant_trigger_phase_code = 0
    sniff_phases = {
                    0: "Inhalation",
                    1: "Exhalation",
                    2: "PhaseIndependent"
                    }

    #--------------------------------------------------------------------------
    # Protocol parameters.
    # These are session parameters that are not sent to the controller
    # (Arduino). These may change from trial to trial. They are stored in
    # the database file for each trial.
    #--------------------------------------------------------------------------
    mouse = Str(0, label='Mouse')   # mouse name
    rig = Str("", label='Rig')   # rig ID.
    session = Int(0, label='Session')   # session number.
    block_size = Int(BLOCK_SIZE, label="Block size")
    # Air flow in sccm set by the Air MFC.
    air_flow = Float(label="Air (sccm)")
    # Nitrogen flow in sccm set by the Nitrogen MFC.
    nitrogen_flow = Float(label="N2 (sccm)")
    # Current trial odorant name.
    odorant = Str("Current odorant", label="Odor")
    # Current vial number
    odor_valve = Int(label="Valve")

    
    # Other session parameters that do not change from trial to trial. These
    # are currently not stored in the trials table of the database file.
    stamp = Str(label='Stamp')   # time stamp.
    protocol_name = Str(label='Protocol')
    enable_blocks = Bool(True, label="Arrange stimuli in blocks")
    # Rewards given from start of session.
    rewards = Int(0, label="Total rewards")
    left_rewards = Int(0, label="Left rewards")
    right_rewards = Int(0, label="Right rewards")
    max_rewards = Int(400, label="Reward until")   # maximum rewards allowed.
    
    #-------------------------------------------------------------------------- 
    # Controller parameters.
    # These are trial parameters sent to Arduino. By default trial_number is
    # not sent to Arduino(???), but it is still logged in the database file.
    #--------------------------------------------------------------------------
    trial_number = Int(0, label='Trial Number')
    # Mapped trait. trial type keyword: code sent to Arduino.
    trial_type = Trait(stimuli_categories.keys()[0],
                       stimuli_categories,
                       label="Trial type")
    water_duration1 = Int(0, label="Left water duration")
    water_duration2 = Int(0, label="Right water duration")
    final_valve_duration = Int(0, label="Final valve duration")
    response_duration = Int(0, label="Response duration")
    inter_trial_interval = Int(0, label='ITI')
    hemodynamic_delay = Int(0, label='HRF phase-lock delay')
    tr = Int(0, label='Repetition time')
    # Amount of time in ms to not count a lick response as the trial choice.
    # If the mouse is impulsive, this prevents uninformed false alarms.
    lick_grace_period = Int(0, label="Lick grace period")
    # Sniff phase from the onset of which the latency of triggering the light
    # stimulation pulse/pulses is measured. Default value is "Inhalation".
    odorant_trigger_phase = Str(sniff_phases[odorant_trigger_phase_code], label="Odorant onset after")
    
    # Other trial parameters. These are not recording in the database file.
    # but are displayed and/or computed trial to trial.
    # Next trial air flow.
    next_air_flow = Float(label="Air (sccm)")
    # Next trial nitrogen flow.
    next_nitrogen_flow = Float(label="N2 (sccm)")
    # Next trial odorant name.
    next_odorant = Str("Next odorant", label="Odor")
    next_trial_number = Int(0, label='Trial Number')
    next_odor_valve= Int(label="Valve")
    # Reusing of the trait definition for trial_type.
    # The values will be independent but valiadation is done the same way.
    next_trial_type = trial_type
    # Used to notify the backend of voyeur when to send
    # the next trial parameters to Arduino. Recomputed every trial depending on
    # the result and iti choice.
    next_trial_start = 0
    # [Upper, lower] bounds in milliseconds when choosing an 
    # inter trial interval for trials when there was no false alarm.
    iti_bounds  = [20000, 22000]
    # [Upper, lower] bounds for random inter trial interval assignment 
    # when the animal DID false alarm. Value is in milliseconds.
    iti_bounds_false_alarm = [25000,27000]
    # Current overall session performance.
    total_available_rewards = 0
    total_available_left_rewards = 0
    total_available_right_rewards = 0
    percent_correct = Float(0, label="Total percent correct")
    percent_left_correct = Float(0, label="Left percent correct")
    percent_right_correct = Float(0, label="Right percent correct")
        
    #--------------------------------------------------------------------------
    # Variables for the event.
    # These are the trial results sent from Arduino.
    # They are stored in the database file.
    #--------------------------------------------------------------------------    
    trial_start = Int(0, label="Start of trial time stamp")
    trial_end = Int(0, label="End of trial time stamp")
    first_lick = Int(0, label="Time of first lick")
    mri_onset = Int(0, label="Time of mri scan start")
    # Time when Arduino received the parameters for the trial (in Arduino
    # elapsed time).
    parameters_received_time = Int(0,
                                   label="Time parameters were received \
                                   by Arduino")
    final_valve_onset = Int(0, label="Time of final valve open")
    
    
    # Current stimulus object.
    current_stimulus = Instance(LaserTrainStimulus)
    next_stimulus = Instance(LaserTrainStimulus)
    # Holds available stimulus ids that have been recycled when generating
    # unique stimulus ids to assign to each stimulus. The first element holds
    # the smallest id available for assignment.
    _available_stimulus_ids = [1]
    # Current block of stimuli. Used when stimuli is arranged in blocks.
    stimulus_block = []
    
    # Olfactometer object that has the interface and representation of the
    # odor delivery hardware.
    olfactometer = Instance(Olfactometers)
    
    # Arrays for the responses plot.
    trial_number_tick = Array
    # All response codes (results of each trial) for the session.
    responses = Array
    # Internal arrays for the plotting of results for each trial type.
    _left_trials_line = Array
    _right_trials_line = Array

    # Arrays for the streaming data plots.
    iteration = Array
    sniff = Array
    lick1 = Array
    lick2 = Array
    odor = Array
    mri = Array

    # Internal indices uses for the streaming plots.
    _last_stream_index = Float(0)
    _last_lick_index = 0
    _last_mri_index = 0
    _previous_last_stream_index = 0
    
    # Running total of each trial result type.
    # Displayed on the console after each trial.
    _total_left_hits = 0
    _total_left_misses = 0
    _total_right_hits = 0
    _total_right_misses = 0
    
    # Used for sliding window performance calculations.
    _sliding_window_left_hits = 0
    _sliding_window_right_hits = 0
    # values of Left trials for the current sliding window period.
    _sliding_window_left_array = []
    # Values of Right trials for the current sliding window period.
    _sliding_window_right_array = []
    
    # Time stamp of when voyeur requested the parameters to send to Arduino.
    _parameters_sent_time = float()
    # Time stamp of when voyeur sent the results for processing.
    _results_time = float()
    
    # Packets dropped as detected from the continuous data stream. 
    _unsynced_packets = 0
    
    # This is the voyeur backend monitor. It handles data acquisition, storage,
    # and trial to trial communications with the controller (Arduino).
    monitor = Instance(Monitor)
    # used as an alias for trial_number. Included because the monitor wants to
    # access the trialNumber member not trial_number. monitor will be updated
    # in the future to be more pythonesque.
    trialNumber = Int()
    
    # GUI elements.
    event_plot = Instance(Plot, label="Success Rate")
    stream_plots = Instance(Component)   # Container for the streaming plots.
    # This plot contains the continuous signals (sniff, and laser currently).
    stream_plot = Instance(Plot, label="Sniff")
    # This is the plot that has the event signals (licks, mri etc.)
    stream_lick_plot = Instance(Plot, label="Licks")
    stream_mri_plot = Instance(Plot, label="MRI")


    start_button = Button()
    start_label = Str('Start')

    # Used to cycle final valve ON/OFF automatically.
    auto_final_valve = Button()
    auto_final_valve_label = Str('Final valve cycling (OFF)')
    auto_final_valve_on_duration = Int(2500, label="ON time(ms)")
    auto_final_valve_off_duration = Int(2500, label="OFF time")
    auto_final_valve_mode = Enum('Single', 'Continuous', 'Repeated',
                                  label="Mode")
    auto_final_valve_state = Bool(True)
    auto_final_valve_repetitions = Int(5, label="Times")
    auto_final_valve_repetitions_label = Str("Times")
    auto_final_valve_repetitions_off_time = Int(5, label="ITI")
    pause_button = Button()
    pause_label = Str('Pause')
    save_as_button = Button("Save as")
    olfactometer_button = Button()
    olfactometer_label = Str('Olfactometer')
    final_valve_button = Button()
    final_valve_label = Str("Final Valve (OFF)")
    left_water_calibrate_button = Button()
    left_water_calibrate_label = Str("Calibrate Left Water Valve")
    right_water_calibrate_button = Button()
    right_water_calibrate_label = Str("Calibrate Right Water Valve")
    left_water_button = Button()
    left_water_label = Str('Left Water Valve')
    right_water_button = Button()
    right_water_label = Str('Right Water Valve')
    pulse_generator1_button = Button(label="Trigger")
    pulse_generator2_button = pulse_generator1_button
    pulse_amplitude1 = Range(low=0,
                             high=5000,
                             value=2000,
                             mode='slider',
                             enter_set=True)
    pulse_amplitude2 = pulse_amplitude1
    pulse_duration1 = Int(0, label='Pulse duration')
    pulse_duration2 = pulse_duration1
    
    
    #--------------------------------------------------------------------------
    # GUI layout
    #--------------------------------------------------------------------------
    control = VGroup(
                     HGroup(
                            Item('start_button',
                                 editor=ButtonEditor(label_value='start_label'),
                                 show_label=False),
                            Item('pause_button',
                                 editor=ButtonEditor(label_value='pause_label'),
                                 show_label=False,
                                 enabled_when='monitor.running'),
                            Item('save_as_button',
                                 show_label=False,
                                 enabled_when='not monitor.running'),
                            Item('olfactometer_button',
                                 editor=ButtonEditor(
                                            label_value='olfactometer_label'),
                                 show_label=False),
                            label='Application Control',
                            show_border=True
                            ),
                     VGroup(
                             HGroup(
                                    Item('auto_final_valve',
                                         editor=ButtonEditor(
                                                             style="button",
                                                             label_value='auto_final'
                                                                        '_valve_label'),
                                         show_label=False,
                                         enabled_when='not monitor.running'),
                                    Item('auto_final_valve_on_duration'),
                                    Item('auto_final_valve_off_duration',
                                         visible_when='auto_final_valve_mode != \
                                                       "Single"'),
                                    show_border=False
                                    ),
                             HGroup(
                                    Item('auto_final_valve_mode'),
                                    spring,
                                    Item('auto_final_valve_repetitions',
                                         visible_when='auto_final_valve_mode == \
                                                         "Repeated"',
                                         show_label=False,
                                         width=-70),
                                    Item("auto_final_valve_repetitions_label",
                                         visible_when='auto_final_valve_mode == \
                                                 "Repeated"',
                                         show_label=False,
                                         style='readonly'),
                                    spring,
                                    Item('auto_final_valve_repetitions_off_time',
                                         visible_when='auto_final_valve_mode == \
                                                                "Repeated"',
                                         width=-70),
                                    label='',
                                    show_border=False,
                                    ),
                             label = '',
                             show_border = True,
                             )
                     )
    
    arduino_group = VGroup(
                           HGroup(
                                  Item('final_valve_button',
                                       editor=ButtonEditor(
                                            style="button",
                                            label_value='final_valve_label'),
                                       show_label=False),
                                  VGroup(
                                       Item('left_water_button',
                                            editor=ButtonEditor(
                                                style="button"),
                                            show_label=False),
                                       Item('left_water_calibrate_button',
                                            editor=ButtonEditor(
                                                style="button"),
                                            show_label=False),
                                       Item('water_duration1')
                                        ),
                                  VGroup(
                                       Item('right_water_button',
                                            editor=ButtonEditor(
                                                style="button"),
                                            show_label=False),
                                       Item('right_water_calibrate_button',
                                            editor=ButtonEditor(
                                                style="button"),
                                            show_label=False),
                                       Item('water_duration2')
                                        ),
                                  ),
                           label="Arduino Control",
                           show_border=True
                           )
    
    session_group = Group(
                          HGroup(
                                 Item('stamp', style='readonly',
                                      width=-140),
                                 Item('protocol_name', style='readonly'),
                                ),
                          HGroup(
                                 Item('mouse',
                                      enabled_when='not monitor.running',
                                      width=-70),
                                 Item('session',
                                      enabled_when='not monitor.running',
                                      width=-70),
                                 Item('rig',
                                      enabled_when='not monitor.running',
                                      full_size=False,
                                      springy=True,
                                      resizable=False),
                                 ),
                          HGroup(
                                 Item('enable_blocks', width=-70),
                                 Item('odorant_trigger_phase', style='readonly')
                                 ),
                          HGroup(
                                 Item('rewards', style='readonly', width=-70),
                                 Item('left_rewards', style='readonly', width=-70),
                                 Item('right_rewards', style='readonly', width=-70),
                                 ),
                          HGroup(
                                 Item('percent_correct', style='readonly',width=-70),
                                 Item('percent_left_correct', style='readonly',width=-70),
                                 Item('percent_right_correct', style='readonly',width=-70),
                                 ),
                          label='Session',
                          show_border=True
                          )
    
    current_trial_group = Group(
                                HGroup(
                                       Item('trial_number', style='readonly', width=-135),
                                       Item('trial_type', style='readonly'),
                                       ),
                                HGroup(
                                       Item('odorant', style='readonly', width=-170),
                                       # Item('odor_valve', style='readonly'),
                                       ),
                                HGroup(
                                       Item('nitrogen_flow', style='readonly', width=-147),
                                       Item('air_flow', style='readonly')
                                       ),
                                HGroup(
                                        Item('response_duration', style='readonly', width=-52),
                                        Item('inter_trial_interval', style='readonly', width=-50),
                                        Item('hemodynamic_delay', style='readonly')
                                ),
                                label='Current Trial',
                                show_border=True
                                )

    next_trial_group = Group(
                             HGroup(
                                    Item('next_trial_number', style='readonly', width=-65),
                                    Item('next_trial_type', style='readonly'),
                                    ),
                             HGroup(
                                    Item('next_odorant', style="readonly", width=-100),
                                    # Item('odor_valve', style='readonly'),
                                    ),
                             HGroup(
                                    Item('nitrogen_flow', style='readonly', width=-77),
                                    Item('air_flow', style='readonly')
                             ),
                             label='Next Trial',
                             show_border=True
                             )

    event = Group(
                  Item('event_plot',
                       editor=ComponentEditor(),
                       show_label=False,
                       height=125),
                  label='Performance',
                  show_border=False,
                  )

    stream = Group(
                   Item('stream_plots',
                        editor=ComponentEditor(),
                        show_label=False,
                        height=250),
                   label='Streaming',
                   show_border=False,
                   )

    # Arrangement of all the component groups.
    main = View(
                VGroup(
                       HGroup(control, arduino_group),
                       HGroup(session_group,
                              current_trial_group,
                              next_trial_group),
                       stream,
                       event,
                       show_labels=True,
                       ),
                title='Voyeur - Left/Right protocol',
                width=1300,
                height=768,
                x=30,
                y=70,
                resizable=True,
                )
    
    def _stream_plots_default(self):
        """ Build and return the container for the streaming plots."""
        
        # Two plots will be overlaid with no separation.
        container = VPlotContainer(bgcolor="transparent",
                                   fill_padding=False,
                                   padding=0)


        # TODO: Make the plot interactive (zoom, pan, re-scale)

        # Add the plots and their data to each container.
        
        # ---------------------------------------------------------------------
        # Streaming signals container plot.
        #----------------------------------------------------------------------
        # Data definiton.
        # Associate the plot data array members with the arrays that are used
        # for updating the data. iteration is the abscissa values of the plots.
        self.stream_plot_data = ArrayPlotData(iteration=self.iteration,
                                              sniff=self.sniff)

        # Create the Plot object for the streaming data.
        plot = Plot(self.stream_plot_data, padding=20,
                    padding_top=5, padding_bottom=18, padding_left=80, border_visible=False)

        # Initialize the data arrays and re-assign the values to the
        # ArrayPlotData collection.
        # X-axis values/ticks. Initialize them. They are static.
        range_in_sec = self.STREAM_SIZE / 1000.0
        self.iteration = arange(0.001, range_in_sec + 0.001, 0.001)
        # Sniff data array initialization to nans.
        # This is so that no data is plotted until we receive it and append it
        # to the right of the screen.
        self.sniff = [nan] * len(self.iteration)
        self.stream_plot_data.set_data("iteration", self.iteration)
        self.stream_plot_data.set_data("sniff", self.sniff)

        # Change plot properties.

        # y-axis range. Change this if you want to re-scale or offset it.
        if self.FMRI:
            y_range = DataRange1D(low=-300, high=300)  # for mri pressure sensor
        else:
            y_range = DataRange1D(low=-80, high=80)  # for training non-mri sniff sensor
        plot.fixed_preferred_size = (100, 50)
        plot.value_range = y_range
        plot.y_axis.visible = True
        plot.x_axis.visible = False
        plot.title = "Sniff"
        plot.title_position = "left"

        # Make a custom abscissa axis object.
        bottom_axis = PlotAxis(plot,
                               orientation="bottom",
                               tick_generator=ScalesTickGenerator(scale=TimeScale(seconds=1)))
        plot.x_axis = bottom_axis

        # Add the lines to the Plot object using the data arrays that it
        # already knows about.
        plot.plot(('iteration', 'sniff'), type='line', color='blue', name="Sniff", line_width=0.5)

        # Keep a reference to the streaming plot so that we can update it in
        # other methods.
        self.stream_plot = plot

        # If the Plot container has a plot, assign a selection mask for the
        # trial duration to it. This overlay is for a light blue trial mask
        # that will denote the time window when a trial was running.
        if self.stream_plot.plots.keys():
            first_plot_name = self.stream_plot.plots.keys()[0]
            first_plot = self.stream_plot.plots[first_plot_name][0]
            rangeselector = RangeSelectionsOverlay(component=first_plot,
                                                   metadata_name='trials_mask')
            first_plot.overlays.append(rangeselector)
            datasource = getattr(first_plot, "index", None)
            # Add the trial timestamps as metadata to the x values datasource.
            datasource.metadata.setdefault("trials_mask", [])

        
        # ---------------------------------------------------------------------
        # Event signals container plot.
        #----------------------------------------------------------------------
        
        # This second plot is for the event signals (e.g. the lick signal).
        # It shares the same timescale as the streaming plot.
        # Data definiton.
        
        # Lick left
        self.stream_lick1_data = ArrayPlotData(iteration=self.iteration,
                                              lick1=self.lick1)

        # Plot object created with the data definition above.
        plot = Plot(self.stream_lick1_data,
                    padding=20,
                    padding_top=0,
                    padding_bottom=4,
                    padding_left=80,
                    border_visible=False,
                    index_mapper=self.stream_plot.index_mapper)

        # Data array for the signal.
        # The last value is not nan so that the first incoming streaming value
        # can be set to nan. Implementation detail on how we start streaming.
        self.lick1 = [nan] * len(self.iteration)
        self.lick1[-1] = 0
        self.stream_lick1_data.set_data("iteration", self.iteration)
        self.stream_lick1_data.set_data("lick1", self.lick1)

        # Change plot properties.
        plot.fixed_preferred_size = (100, 5)
        y_range = DataRange1D(low=0.99, high=1.01)
        plot.value_range = y_range
        plot.y_axis.visible = False
        plot.x_axis.visible = False
        plot.title = "Lick_L"
        plot.title_position = "left"
        plot.y_grid = None

        # Add the lines to the plot and grab one of the plot references.
        event_plot = plot.plot(("iteration", "lick1"),
                               name="Lick",
                               color="red",
                               line_width=20,
                               render_style="hold")[0]

        # Add the trials overlay to the streaming events plot too.
        event_plot.overlays.append(rangeselector)

        self.stream_lick1_plot = plot

        #### Lick right
        self.stream_lick2_data = ArrayPlotData(iteration=self.iteration,
                                              lick2=self.lick2)
        # Plot object created with the data definition above.
        plot = Plot(self.stream_lick2_data,
                    padding=20,
                    padding_top=0,
                    padding_bottom=4,
                    padding_left=80,
                    border_visible=False,
                    index_mapper=self.stream_plot.index_mapper)

        # Data array for the signal.
        # The last value is not nan so that the first incoming streaming value
        # can be set to nan. Implementation detail on how we start streaming.
        self.lick2 = [nan] * len(self.iteration)
        self.lick2[-1] = 0
        self.stream_lick2_data.set_data("iteration", self.iteration)
        self.stream_lick2_data.set_data("lick2", self.lick2)

        # Change plot properties.
        plot.fixed_preferred_size = (100, 5)
        y_range = DataRange1D(low=0.99, high=1.01)
        plot.value_range = y_range
        plot.y_axis.visible = False
        plot.x_axis.visible = False
        plot.title = "Lick_R"
        plot.title_position = "left"
        plot.y_grid = None

        # Add the lines to the plot and grab one of the plot references.
        event_plot = plot.plot(("iteration", "lick2"),
                               name="Lick",
                               color="red",
                               line_width=20,
                               render_style="hold")[0]

        # Add the trials overlay to the streaming events plot too.
        event_plot.overlays.append(rangeselector)

        self.stream_lick2_plot = plot
        
        
        #### MRI trigger signal plot
        self.stream_mri_data = ArrayPlotData(iteration=self.iteration,
                                                mri=self.mri)

        # Plot object created with the data definition above.
        plot = Plot(self.stream_mri_data,
                    padding=20,
                    padding_top=0,
                    padding_bottom=4,
                    padding_left=80,
                    border_visible=False,
                    index_mapper=self.stream_plot.index_mapper,)

        # Data array for the signal.
        # The last value is not nan so that the first incoming streaming value
        # can be set to nan. Implementation detail on how we start streaming.
        self.mri = [nan] * len(self.iteration)
        self.mri[-1] = 0
        self.stream_mri_data.set_data("iteration", self.iteration)
        self.stream_mri_data.set_data("mri", self.mri)

        # Change plot properties.
        plot.fixed_preferred_size = (100, 5)
        y_range = DataRange1D(low=0.99, high=1.01)
        plot.value_range = y_range
        plot.y_axis.visible = False
        plot.x_axis.visible = False
        plot.title = "MRI"
        plot.title_position = "left"
        plot.y_grid = None

        # Add the lines to the plot and grab one of the plot references.
        event_plot = plot.plot(("iteration", "mri"),
                               name="MRI",
                               color="green",
                               line_width=20)[0]

        # Add the trials overlay to the streaming events plot too.
        event_plot.overlays.append(rangeselector)

        self.stream_mri_plot = plot


        
        # Finally add both plot containers to the vertical plot container.
        container.add(self.stream_plot, self.stream_lick1_plot, self.stream_lick2_plot, self.stream_mri_plot)


        return container


    def _addtrialmask(self):
        """ Add a masking overlay to mark the time windows when a trial was \
        occuring """
        
        # TODO: eventually rewrite this using signal objects that handle the
        # overlays.
        # Get the sniff plot and add a selection overlay ability to it
        if 'Sniff' in self.stream_plot.plots.keys():
            sniff = self.stream_plot.plots['Sniff'][0]
            datasource = getattr(sniff, "index", None)
            data = self.iteration
            # The trial time window has already passed through our window size.
            if self._last_stream_index - self.trial_end >= self.STREAM_SIZE:
                return
            # Part of the trial window is already beyond our window size.
            elif self._last_stream_index - self.trial_start >= self.STREAM_SIZE:
                start = data[0]
            else:
                start = data[-self._last_stream_index + self.trial_start - 1]
            end = data[-self._last_stream_index + self.trial_end - 1]
            # Add the new trial bounds to the masking overlay.
            # datasource.metadata['trials_mask'] += (start, end)

    def __last_stream_index_changed(self):
        """ The end time tick in our plots has changed. Recompute signals. """

        shift = self._last_stream_index - self._previous_last_stream_index
        self._previous_last_stream_index = self._last_stream_index

        streams = self.stream_definition()
        # Nothing to display if no streaming data
        if streams == None:
            return
        # Currently this code is dependent on the sniff signal. Needs to change.
        # TODO: Uncouple the dependence on a particular signal.
        if 'Sniff' in streams.keys():
            # Get the sniff plot and update the selection overlay mask.
            if 'Sniff' in self.stream_plot.plots.keys():
                sniff = self.stream_plot.plots['Sniff'][0]
                datasource = getattr(sniff, "index", None)
                mask = datasource.metadata['trials_mask']
                new_mask = []
                for index in range(len(mask)):
                    mask_point = mask[index] - shift / 1000.0
                    if mask_point < 0.001:
                        if index % 2 == 0:
                            new_mask.append(0.001)
                        else:
                            del new_mask[-1]
                    else:
                        new_mask.append(mask_point)
                datasource.metadata['trials_mask'] = new_mask


    def _restart(self):

        self.trial_number = 1
        self.rewards = 0
        self.left_rewards = 0
        self.right_rewards = 0
        self._left_trials_line = [1]
        self._right_trials_line = [1]
        self.trial_number_tick = [0]
        self.responses = [0]
        self._sliding_window_left_array = []
        self._sliding_window_right_array = []
        self._total_left_hits = 0
        self._total_left_misses = 0
        self._total_right_hits = 0
        self._total_right_misses = 0
        self._sliding_window_left_hits = 0
        self._sliding_window_right_hits = 0
        self.calculate_next_trial_parameters()
        
        time.clock()


        return

    def _mouse_changed(self):
        new_stamp = time_stamp()
        db = 'mouse_' + str(self.mouse) + '_' + 'sess' + str(self.session) \
                    + '_' + new_stamp
        if self.db != db:
            self.db = db
        return

    def _build_stimulus_set(self):

        self.stimuli["Right"] = []
        self.stimuli["Left"] = []
        self.no_stimuli = []
        
        self.lick_grace_period = 0 # grace period aft
        # er FV open where responses are recorded but not scored.

        # find all of the vials with the odor. ASSUMES THAT ONLY ONE OLFACTOMETER IS PRESENT!
        odorvalves_left_stimulus = find_odor_vial(self.olfas, 'Octanal', 1)['key']
        odorvalves_right_stimulus = find_odor_vial(self.olfas, 'Benzaldehyde', 1)['key']
        # odorvalves_left_stimulus = find_odor_vial(self.olfas, 'Blank1', 1)['key']
        # odorvalves_right_stimulus = find_odor_vial(self.olfas, 'Blank2', 1)['key']
        odorvalves_no_stimulus = find_odor_vial(self.olfas, 'Blank1', 1)['key']


        # randomly select the vial from the list for stimulation block. it may be same or different vials
        for i in range(len(odorvalves_left_stimulus)):
            right_stimulus = LaserTrainStimulus(
                                    odorvalves = [choice(odorvalves_right_stimulus)],
                                    # flows = [(888, 98.7)],  # [(AIR, Nitrogen)]
                                    flows=[(900, 100)],  # [(AIR, Nitrogen)]
                                    id = 0,
                                    description="Right stimulus",
                                    trial_type = "Right"
                                    )
            left_stimulus = LaserTrainStimulus(
                                    odorvalves = [choice(odorvalves_left_stimulus)],
                                    # flows = [(888, 98.7)],  # [(AIR, Nitrogen)]
                                    flows=[(900, 100)],  # [(AIR, Nitrogen)]
                                    id = 1,
                                    description = "Left stimulus",
                                    trial_type = "Left"
                                    )
            no_stimulus = LaserTrainStimulus(
                                    odorvalves = [choice(odorvalves_no_stimulus)],
                                    # flows = [(888, 98.7)],  # [(AIR, Nitrogen)]
                                    flows=[(900, 100)],  # [(AIR, Nitrogen)]
                                    id = 2,
                                    description="No stimulus",
                                    trial_type = "None"
                                    )

            self.stimuli['Left'].append(left_stimulus)
            self.stimuli['Right'].append(right_stimulus)
        self.no_stimuli.append(no_stimulus)


        print "---------- Stimuli changed ----------"
        for stimulus in self.stimuli.values():
            for stim in stimulus:
                print stim
        print "Blocksize:", self.block_size
        print "-------------------------------------"
        return

    def _rig_changed(self):
        new_stamp = time_stamp()
        db = 'mouse' + str(self.mouse) + '_' + 'sess' + str(self.session) \
            + '_' + new_stamp
        if self.db != db:
            self.db = db
        return

    def _session_changed(self):
        new_stamp = time_stamp()
        self.db = 'mouse' + str(self.mouse) + '_' + 'sess' + str(self.session) \
            + '_' + new_stamp
    
    @on_trait_change('trial_number')        
    def update_trialNumber(self):
        """ Copy the value of trial_number when it changes into its alias \
        trialNumber.
        
        The Monitor object is currently looking for a trialNumber attribute.
        This maintains compatibility. The Monitor will be updated to a more
        pythonesque version in the near future and this method becomes then
        obsolete and will have no effect.
        """
        self.trialNumber = self.trial_number

    def _responses_changed(self):

        if len(self.responses) == 1:
            return

        leftcorrect = int
        rightcorrect = int
        lastelement = self.responses[-1]

        if(lastelement == 1):  # LEFT HIT
            self._total_left_hits += 1
            if len(self._sliding_window_left_array) == self.SLIDING_WINDOW:
                del self._sliding_window_left_array[:]
                if self._sliding_window_left_hits != 0:
                    del self._sliding_window_left_hits
                del self._left_trials_line
                self._sliding_window_left_hits += 1
            else:
                self._sliding_window_left_hits += 1
            self._sliding_window_left_array.append(lastelement)

        elif (lastelement == 2):  # RIGHT HIT
            self._total_right_hits += 1
            if len(self._sliding_window_right_array) == self.SLIDING_WINDOW:
                del self._sliding_window_right_array[:]
                if self._sliding_window_right_hits != 0:
                    del self._sliding_window_right_hits
                del self._right_trials_line
                self._sliding_window_right_hits += 1
            else:
                self._sliding_window_right_hits += 1
            self._sliding_window_right_array.append(lastelement)

        elif (lastelement == 3):  # LEFT MISS
            self._total_left_misses += 1
            if len(self._sliding_window_left_array) == self.SLIDING_WINDOW:
                del self._sliding_window_left_array[:]
                if self._sliding_window_left_hits != 0:
                    del self._sliding_window_left_hits
                self._left_trials_line = [1]
            self._sliding_window_left_array.append(lastelement)

        elif (lastelement == 4):  # RIGHT MISS
            self._total_right_misses += 1
            if len(self._sliding_window_right_array) == self.SLIDING_WINDOW:
                del self._sliding_window_right_array[:]
                if self._sliding_window_right_hits != 0:
                    del self._sliding_window_right_hits
                self._right_trials_line = [1]
            self._sliding_window_right_array.append(lastelement)

        elif (lastelement == 5):  # LEFT NO RESPONSE
            self._total_left_misses += 1
            if len(self._sliding_window_left_array) == self.SLIDING_WINDOW:
                del self._sliding_window_left_array[:]
                if self._sliding_window_left_hits != 0:
                    del self._sliding_window_left_hits
                self._left_trials_line = [1]
            self._sliding_window_left_array.append(lastelement)

        elif (lastelement == 6):  # RIGHT NO RESPONSE
            self._total_right_misses += 1
            if len(self._sliding_window_right_array) == self.SLIDING_WINDOW:
                del self._sliding_window_right_array[:]
                if self._sliding_window_right_hits != 0:
                    del self._sliding_window_right_hits
                self._right_trials_line = [1]
            self._sliding_window_right_array.append(lastelement)
        
        # sliding window data arrays
        slwlefttrials = len(self._sliding_window_left_array)
        if slwlefttrials == 0:
            leftcorrect = 0
        else:
            leftcorrect = self._sliding_window_left_hits*1.0/slwlefttrials
        
        slwrighttrials = len(self._sliding_window_right_array)
        if slwrighttrials == 0:
            rightcorrect = 0
        else:
            rightcorrect = self._sliding_window_right_hits*1.0/slwrighttrials
                
        self._left_trials_line = append(self._left_trials_line, leftcorrect*100)
        self._right_trials_line = append(self._right_trials_line, rightcorrect*100)
        self.trial_number_tick = arange(0, len(self._right_trials_line))
        # print "LeftHits: " + str(self._total_left_hits) + "\tRightHits: " + str(self._total_right_hits)
        
        self.event_plot_data.set_data("trial_number_tick", self.trial_number_tick)        
        self.event_plot_data.set_data("_left_trials_line", self._left_trials_line)
        self.event_plot_data.set_data("_right_trials_line", self._right_trials_line)
        self.event_plot.request_redraw()

    #TODO: fix the cycle
    def _callibrate(self):
        """ Fire the final valve on and off every 2.5s.
        
        This is is a convenience method used when PIDing for automatic
        triggering of the final valve.
        """
        if self.start_label == "Start" and  self.auto_final_valve_label == "Final valve cycling (ON)":
            Timer.singleShot(self.auto_final_valve_on_duration, self._callibrate)

        self._final_valve_button_fired()

        return


#-------------------------------------------------------------------------------
#--------------------------Button events----------------------------------------
    def _start_button_fired(self):
        if self.monitor.running:
            self.start_label = 'Start'
            if self.olfactometer is not None:
                for i in range(self.olfactometer.deviceCount):
                    self.olfactometer.olfas[i].mfc1.setMFCrate(self.olfactometer.olfas[i].mfc1, 0)
                    self.olfactometer.olfas[i].mfc2.setMFCrate(self.olfactometer.olfas[i].mfc2, 0)
                    self.olfactometer.olfas[i].mfc3.setMFCrate(self.olfactometer.olfas[i].mfc3, 0)
            if self.final_valve_label == "Final Valve (ON)":
                self._final_valve_button_fired()
            self.monitor.stop_acquisition()
            print "Unsynced trials: ", self._unsynced_packets
            #save_data_file(self.monitor.database_file,self.config['serverPaths']['mountPoint']+self.config['serverPaths']['chrisw'])
        else:
            self.start_label = 'Stop'
            self._restart()
            self._odorvalveon()
            self.monitor.database_file = 'C:/VoyeurData/' + self.db
            self.monitor.start_acquisition()
            # TODO: make the monitor start acquisition start an ITI, not a trial.
        return

    def _auto_final_valve_fired(self, button_not_clicked=True):
        """ Automatically cycle the final valve ON and OFF.
        
        This helps in testing or calibrating the rig impedances as the
        PID response is monitored.
        """
        
        # The status of the auto final valve. If the state is False, the user
        # requested stopping the operation via the gui/
        if not self.auto_final_valve_state:
            self.auto_final_valve_state = True
            return
        
        if not button_not_clicked and self.auto_final_valve_label == "Final "\
                                        "valve cycling (ON)":
            self.auto_final_valve_label = "Final valve cycling (OFF)"
            if self.final_valve_label == "Final Valve (ON)":
                self._final_valve_button_fired()
                self.final_valve_label = "Final Valve (OFF)"
            self.auto_final_valve_state = False
            return
        
        if self.auto_final_valve_mode == 'Repeated' and \
                self.final_valve_label == "Final Valve (ON)":
            self.auto_final_valve_repetitions -= 1
            if self.auto_final_valve_repetitions < 1:
                self.auto_final_valve_label = 'Final valve cycling (OFF)' 
                return

        if self.auto_final_valve_mode == 'Single':
            if self.final_valve_label == "Final Valve (OFF)":
                self._final_valve_button_fired()
                self.auto_final_valve_label = 'Final valve cycling (ON)'
                Timer.singleShot(self.auto_final_valve_on_duration,
                                 self._auto_final_valve_fired)
            else:
                self._final_valve_button_fired()
                self.auto_final_valve_label = 'Final valve cycling (OFF)'
        elif self.auto_final_valve_mode == 'Continuous' or \
                self.auto_final_valve_mode == 'Repeated':
            if self.final_valve_label == "Final Valve (OFF)":
                self._final_valve_button_fired()
                Timer.singleShot(self.auto_final_valve_on_duration,
                                 self._auto_final_valve_fired)
            elif self.final_valve_label == "Final Valve (ON)":
                self._final_valve_button_fired()
                Timer.singleShot(self.auto_final_valve_off_duration,
                                 self._auto_final_valve_fired)
            # At this point we are still cycling through the final valve
            self.auto_final_valve_label = 'Final valve cycling (ON)'
            
        return
    
    def _pause_button_fired(self):
        if self.monitor.recording:
            self.monitor.pause_acquisition()
            if self.olfactometer is not None:
                for i in range(self.olfactometer.deviceCount):
                    self.olfactometer.olfas[i].valves.set_background_valve(valve_state=0)
            self.pause_label = 'Unpause'
        else:
            self.pause_label = 'Pause'
            self.trial_number = self.next_trial_number
            self.next_trial_number += 1
            self.monitor.unpause_acquisition()
        return

    def _save_as_button_fired(self):
        dialog = FileDialog(action="save as")
        dialog.open()
        if dialog.return_code == OK:
            self.db = os.path.join(dialog.directory, dialog.filename)
        return

    # Open olfactometer object here
    def _olfactometer_button_fired(self):
        if(self.olfactometer != None):
            self.olfactometer.open()
            self.olfactometer._create_contents(self)

    def _final_valve_button_fired(self):
        if self.monitor.recording:
            self._pause_button_fired()
        if self.final_valve_label == "Final Valve (OFF)":
            self.monitor.send_command("fv on")
            self.final_valve_label = "Final Valve (ON)"
        elif self.final_valve_label == "Final Valve (ON)":
            self.monitor.send_command("fv off")
            self.final_valve_label = "Final Valve (OFF)"

    def _left_water_button_fired(self):
        if self.monitor.recording:
            self._pause_button_fired()
        command = "wv 1 " + str(self.water_duration1)
        self.monitor.send_command(command)

    def _right_water_button_fired(self):
        if self.monitor.recording:
            self._pause_button_fired()
        command = "wv 2 " + str(self.water_duration2)
        self.monitor.send_command(command)

    def _left_water_calibrate_button_fired(self):
        if self.monitor.recording:
            self._pause_button_fired()
        command = "calibrate 1" + " " + str(self.water_duration1)
        self.monitor.send_command(command)

    def _right_water_calibrate_button_fired(self):
        if self.monitor.recording:
            self._pause_button_fired()
        command = "calibrate 2" + " " + str(self.water_duration2)
        self.monitor.send_command(command)


    def _pulse_generator1_button_fired(self):
        """ Send a laser trigger command to the Arduino, for pulse channel 1.
        """
        
        if self.monitor.recording:
            self._pause_button_fired()
        
        command = "Laser 1 trigger " + str(self.pulse_amplitude1) + " " + str(self.pulse_duration1)
        self.monitor.send_command(command)

    def _pulse_generator2_button_fired(self):
        """ Send a laser trigger command to the Arduino, for pulse channel 2.
        """
        
        if self.monitor.recording:
            self._pause_button_fired()
        
        command = "Laser 2 trigger " + str(self.pulse_amplitude2) + " " + str(self.pulse_duration2)
        self.monitor.send_command(command)


#-------------------------------------------------------------------------------
#--------------------------Initialization---------------------------------------
    def __init__(self, trial_number,
                        mouse,
                        session,
                        stamp,
                        inter_trial_interval,
                        trial_type_id,
                        max_rewards,
                        final_valve_duration,
                        response_duration,
                        odorant_trigger_phase_code,
                        lick_grace_period,
                        hemodynamic_delay,
                        tr,
                        licking_training_probability,
                        **kwtraits):
        
        super(Passive_odor_presentation, self).__init__(**kwtraits)
        self.trial_number = trial_number
        self.stamp = stamp
                
        self.db = 'mouse' + str(mouse) + '_' + 'sess' + str(session) \
                    + '_' + self.stamp     
        self.mouse = str(mouse)
        self.session = session
        
        self.protocol_name = self.__class__.__name__
        
        #get a configuration object with the default settings.
        self.config = parse_rig_config("C:\Users\Gottfried_Lab\PycharmProjects\Mod_Voyeur\mri_behavior\Voyeur_libraries\\voyeur_rig_config.conf")
        self.rig = self.config['rigName']
        self.water_duration1 = self.config['waterValveDurations']['valve_1_left']['0.25ul']
        self.water_duration2 = self.config['waterValveDurations']['valve_2_right']['0.25ul']
        self.olfas = self.config['olfas']
        self.olfaComPort1 = 'COM' + str(self.olfas[0]['comPort'])
        self.laser_power_table = self.config['lightSource']['powerTable']

        self._build_stimulus_set()
        self.calculate_next_trial_parameters()
        self.calculate_current_trial_parameters()
        
        self.inter_trial_interval = inter_trial_interval
        self.final_valve_duration = final_valve_duration
        self.response_duration = response_duration
        self.hemodynamic_delay = hemodynamic_delay
        self.tr = self.TR
        self.licking_training_probability = self.LICKING_TRAINING_PROBABILITY*10
        
        self.block_size = self.BLOCK_SIZE
        self.rewards = 0
        self.left_rewards = 0
        self.right_rewards = 0
        self.max_rewards = max_rewards
        
        # Setup the performance plots
        self.event_plot_data = ArrayPlotData(trial_number_tick = self.trial_number_tick,
                                             _left_trials_line = self._left_trials_line,
                                             _right_trials_line = self._right_trials_line)
        plot = Plot(self.event_plot_data, padding=20, padding_top=10, padding_bottom=30, padding_left=80, border_visible=False)
        self.event_plot = plot
        plot.plot(('trial_number_tick', '_left_trials_line'), type = 'scatter', color = 'blue',
                   name = "Left Trials")
        plot.plot(('trial_number_tick', '_right_trials_line'), type = 'scatter', color = 'red',
                   name = "Right Trials")
        plot.legend.visible = True
        plot.legend.bgcolor = "transparent"
        plot.legend.align = "ul"
        plot.legend.border_visible = False
        plot.y_axis.title = "% Correct"
        y_range = DataRange1D(low=0, high=100)
        plot.value_range = y_range
        self.trial_number_tick = [0]
        self.responses = [0]
        
        time.clock()

        if self.OLFA:
            self.olfactometer = Olfactometers(config_obj=self.config)
        else:
            self.olfactometer = Olfactometers(config_obj=None)

        if len(self.olfactometer.olfas) == 0:
            print "self.olfactometer = None"
            self.olfactometer = None
        else:
            self.olfactometer.olfas[0].valves.set_background_valve(valve_state=0)
        self._setflows()

        if self.ARDUINO:
            self.monitor = Monitor()
            self.monitor.protocol = self


    def trial_parameters(self):
        """Return a class of TrialParameters for the upcoming trial.
        
        Modify this method, assigning the actual trial parameter values for the
        trial so that they can be passed onto the controller and saved on the
        database file.
        """

        protocol_params = {
                   "mouse"                  : self.mouse,
                   "rig"                    : self.rig,
                   "session"                : self.session,
                   "block_size"             : self.block_size,
                   "air_flow"               : self.air_flow,
                   "nitrogen_flow"          : self.nitrogen_flow,
                   "odorant"                : self.odorant,
                   "stimulus_id"            : self.current_stimulus.id,
                   "description"            : self.current_stimulus.description,
                   "trial_category"         : self.trial_type,
                   "odorant_trigger_phase"  : self.odorant_trigger_phase,
                   }
        
        # Parameters sent to the controller (Arduino)
        controller_dict = {
                    "trialNumber"                   : (1, db.Int, self.trial_number),
                    "final_valve_duration"          : (2, db.Int, self.final_valve_duration),
                    "response_duration"             : (3, db.Int, self.response_duration),
                    "inter_trial_interval"          : (4, db.Int, self.inter_trial_interval),
                    "odorant_trigger_phase_code"    : (5, db.Int, self.odorant_trigger_phase_code),
                    "trial_type_id"                 : (6, db.Int, self.current_stimulus.id),
                    "lick_grace_period"             : (7, db.Int, self.lick_grace_period),
                    "hemodynamic_delay"             : (8, db.Int, self.hemodynamic_delay),
                    "tr"                            : (9, db.Int, self.tr),
                    "licking_training_probability"  : (10, db.Int, self.licking_training_probability)
        }
   
        return TrialParameters(
                    protocolParams=protocol_params,
                    controllerParams=controller_dict
                )

    def protocol_parameters_definition(self):
        """Returns a dictionary of {name => db.type} defining protocol parameters"""

        params_def = {
            "mouse"                 : db.String32,
            "rig"                   : db.String32,
            "session"               : db.Int,
            "block_size"            : db.Int,
            "air_flow"              : db.Float,
            "nitrogen_flow"         : db.Float,
            "odorant"               : db.String32,
            "stimulus_id"           : db.Int,
            "description"           : db.String32,
            "trial_category"        : db.String32,
            "odorant_trigger_phase" : db.String32
        }

        return params_def

    def controller_parameters_definition(self):
        """Returns a dictionary of {name => db.type} defining controller (Arduino) parameters"""

        params_def = {
            "trialNumber"                   : db.Int,
            "final_valve_duration"          : db.Int,
            "response_duration"             : db.Int,
            "inter_trial_interval"          : db.Int,
            "odorant_trigger_phase_code"    : db.Int,
            "trial_type_id"                 : db.Int,
            "lick_grace_period"             : db.Int,
            "hemodynamic_delay"             : db.Int,
            "tr"                            : db.Int,
            "licking_training_probability"  : db.Int
        }
           
        return params_def

    def event_definition(self):
        """Returns a dictionary of {name => (index,db.Type} of event parameters for this protocol"""

        return {
            "parameters_received_time": (1, db.Int),
            "trial_start"             : (2, db.Int),
            "trial_end"               : (3, db.Int),
            "final_valve_onset"       : (4, db.Int),
            "response"                : (5, db.Int),
            "first_lick"              : (6, db.Int),
            "mri_onset"               : (7, db.Int)
        }

    def stream_definition(self):
        """Returns a dictionary of {name => (index,db.Type} of streaming data parameters for this protocol"""
             
        return {
            "packet_sent_time"         : (1, 'unsigned long', db.Int),
            "sniff_samples"            : (2, 'unsigned int', db.Int),
            "sniff"                    : (3, 'int', db.FloatArray),
            "lick1"                    : (4, 'unsigned long', db.FloatArray),
            "lick2"                    : (5, 'unsigned long', db.FloatArray),
            "mri"                      : (6, 'unsigned long', db.FloatArray)
        }

    def process_event_request(self, event):
        """
        Process event requested from controller, run sniff clean if needed, set the parameters for the following trial and set MFCs, calculate parameters
        for the trial that occurs after that, set timer to set vial open for next trial.
        """
        self.timestamp("end")
        self.parameters_received_time = int(event['parameters_received_time'])
        self.trial_start = int(event['trial_start'])
        self.trial_end = int(event['trial_end'])

        response = int(event['response'])
        if (response == 1) : # a left hit.
            self.rewards += 1
            self.left_rewards += 1
            self.total_available_rewards += 1
            self.total_available_left_rewards += 1
            if self.rewards >= self.max_rewards and self.start_label == 'Stop':
                self._start_button_fired()  # ends the session if the reward target has been reached.
            self.inter_trial_interval = randint(self.iti_bounds[0], self.iti_bounds[1])

        if (response == 2) : # a right hit.
            self.rewards += 1
            self.right_rewards += 1
            self.total_available_rewards += 1
            self.total_available_right_rewards += 1
            if self.rewards >= self.max_rewards and self.start_label == 'Stop':
                self._start_button_fired()  # ends the session if the reward target has been reached.
            self.inter_trial_interval = randint(self.iti_bounds[0], self.iti_bounds[1])

        if (response == 3) : # a left false alarm
            if (self.LICKING_TRAINING_PROBABILITY == 1):
                self.rewards += 1
                self.left_rewards += 1
            self.total_available_rewards += 1
            self.total_available_left_rewards += 1
            self.inter_trial_interval = randint(self.iti_bounds_false_alarm[0],self.iti_bounds_false_alarm[1])

        if (response == 4):  # a right false alarm
            if (self.LICKING_TRAINING_PROBABILITY == 1):
                self.rewards += 1
                self.right_rewards += 1
            self.total_available_rewards += 1
            self.total_available_right_rewards += 1
            self.inter_trial_interval = randint(self.iti_bounds_false_alarm[0], self.iti_bounds_false_alarm[1])

        if (response == 5) or (response == 6): # no response
            self.total_available_rewards += 1
            self.inter_trial_interval = randint(self.iti_bounds[0],self.iti_bounds[1])

        if (response == 7) or (response == 8): # a false alarm to no stimulus
            self.inter_trial_interval = randint(self.iti_bounds[0],self.iti_bounds[1])

        if (response == 9): # no response to no stimulus
            self.inter_trial_interval = randint(self.iti_bounds[0],self.iti_bounds[1])

        self.responses = append(self.responses, response)

        self.hemodynamic_delay = randint(0,self.HRF_SAMPLES-1) * self.tr / self.HRF_SAMPLES
        
        #update a couple last parameters from the next_stimulus object, then make it the current_stimulus..
        self.calculate_current_trial_parameters()
        self.current_stimulus = deepcopy(self.next_stimulus) # set the parameters for the following trial from nextstim.
        #calculate a new next stim.
        self.calculate_next_trial_parameters() # generate a new nextstim for the next next trial. 
        # If actual next trial is determined by the trial that just finished, calculate next trial parameters can set current_stimulus.
        
        # use the current_stimulus parameters to calculate values that we'll record when we start the trial.
        self._setflows()
        odorvalve = self.current_stimulus.odorvalves[0]
        valveConc = self.olfas[0][odorvalve][1]
        self.nitrogen_flow = self.current_stimulus.flows[0][1]
        self.air_flow = self.current_stimulus.flows[0][0]
        self.odorant = self.olfas[0][odorvalve][0]
        self.percent_correct = round((float(self.rewards) / float(self.total_available_rewards)) * 100, 2)
        if float(self.total_available_left_rewards) > 0:
            self.percent_left_correct = round((float(self.left_rewards) / float(self.total_available_left_rewards)) * 100, 2)
        if float(self.total_available_right_rewards) > 0:
            self.percent_right_correct = round((float(self.right_rewards) / float(self.total_available_right_rewards)) * 100, 2)

        # set up a timer for opening the vial at the begining of the next trial using the parameters from current_stimulus.
        timefromtrial_end = (self._results_time - self._parameters_sent_time) * 1000 #convert from sec to ms for python generated values
        timefromtrial_end -= (self.trial_end - self.parameters_received_time) * 1.0 
        nextvalveontime = self.inter_trial_interval - timefromtrial_end - self.VIAL_ON_BEFORE_TRIAL
        self.next_trial_start = nextvalveontime + self.VIAL_ON_BEFORE_TRIAL / 2
        if nextvalveontime < 0:
            print "Warning! nextvalveontime < 0"
            nextvalveontime = 20
            self.next_trial_start = 1000
        Timer.singleShot(int(nextvalveontime), self._odorvalveon)
        # print "ITI: ", self._next_inter_trial_interval, " timer set duration: ", int(nextvalveontime)
        
        return

    def process_stream_request(self, stream):
        """
        Process stream requested from controller.
        """
        if stream:
            num_sniffs = stream['sniff_samples']
            packet_sent_time = stream['packet_sent_time']

            if packet_sent_time > self._last_stream_index + num_sniffs:
                lostsniffsamples = packet_sent_time - self._last_stream_index - num_sniffs
                if lostsniffsamples > self.STREAM_SIZE:
                    lostsniffsamples = self.STREAM_SIZE
                lostsniffsamples = int(lostsniffsamples)
                # pad sniff signal with last value for the lost samples first then append received sniff signal
                new_sniff = hstack((self.sniff[-self.STREAM_SIZE + lostsniffsamples:], [self.sniff[-1]] * lostsniffsamples))
                if stream['sniff'] is not None:
                    self.sniff = hstack((new_sniff[-self.STREAM_SIZE + num_sniffs:], negative(stream['sniff'])))
            else:
                if stream['sniff'] is not None:
                    new_sniff = hstack((self.sniff[-self.STREAM_SIZE + num_sniffs:], negative(stream['sniff'])))
            self.sniff = new_sniff
            self.stream_plot_data.set_data("sniff", self.sniff)
            

            if stream['lick1'] is not None or (self._last_stream_index - self._last_lick1_index < self.STREAM_SIZE):
                [self.lick1] = self._process_lick1s(stream, ('lick1',), [self.lick1])
                
            if stream['lick2'] is not None or (self._last_stream_index - self._last_lick2_index < self.STREAM_SIZE):
                [self.lick2] = self._process_lick2s(stream, ('lick2',), [self.lick2])

            if stream['mri'] is not None or (self._last_stream_index - self._last_mri_index < self.STREAM_SIZE):
                [self.mri] = self._process_mris(stream, ('mri',), [self.mri])

            self._last_stream_index = packet_sent_time

            # if we haven't received results by MAX_TRIAL_DURATION, pause and unpause as there was probably some problem with comm.
            if (self.trial_number > 1) and ((time.clock() - self._results_time) > self.MAX_TRIAL_DURATION) and self.pause_label == "Pause":
                print "=============== Pausing to restart Trial =============="
                # print "param_sent time: ",self._parameters_sent_time, "_results_time:", self._results_time
                self._unsynced_packets += 1
                self._results_time = time.clock()
                # Pause and unpause only iff running
                if self.pause_label == "Pause":
                    self.pause_label = 'Unpause'
                    self._pause_button_fired()
                    # unpause in 1 second
                    Timer.singleShot(1000, self._pause_button_fired)
        return



    def _process_lick1s(self, stream, lick1signals, lick1arrays):

        packet_sent_time = stream['packet_sent_time']

        # TODO: find max shift first, apply it to all lick1s
        maxtimestamp = int(packet_sent_time)
        for i in range(len(lick1arrays)):
            lick1signal = lick1signals[i]

            if lick1signal in stream.keys():
                streamsignal = stream[lick1signal]
                if streamsignal is not None and streamsignal[-1] > maxtimestamp:
                        maxtimestamp = streamsignal[-1]
                        print "**************************************************************"
                        print "WARNING! lick1 timestamp exceeds timestamp of received packet: "
                        print "Packet sent timestamp: ", packet_sent_time, "lick1 timestamp: ", streamsignal[-1]
                        print "**************************************************************"
        maxshift = int(packet_sent_time - self._last_stream_index)
        if maxshift > self.STREAM_SIZE:
            maxshift = self.STREAM_SIZE - 1

        for i in range(len(lick1arrays)):

            lick1signal = lick1signals[i]
            lick1array = lick1arrays[i]

            if lick1signal in stream.keys():
                if stream[lick1signal] is None:
                    lick1array = hstack((lick1array[-self.STREAM_SIZE + maxshift:], [lick1array[-1]] * maxshift))
                else:
                    # print "lick1s: ", stream['lick1'], "\tnum sniffs: ", currentshift
                    last_state = lick1array[-1]
                    last_lick1_tick = self._last_stream_index
                    for lick1 in stream[lick1signal]:
                        # print "last lick1 tick: ", last_lick1_tick, "\tlast state: ", last_state
                        shift = int(lick1 - last_lick1_tick)
                        if shift <= 0:
                            if shift < self.STREAM_SIZE * -1:
                                shift = -self.STREAM_SIZE + 1
                            if isnan(last_state):
                                lick1array[shift - 1:] = [i + 1] * (-shift + 1)
                            else:
                                lick1array[shift - 1:] = [nan] * (-shift + 1)
                        # lick1 timestamp exceeds packet sent time. Just change the signal state but don't shift
                        elif lick1 > packet_sent_time:
                            if isnan(last_state):
                                lick1array[-1] = i + 1
                            else:
                                lick1array[-1] = nan
                        else:
                            if shift > self.STREAM_SIZE:
                                shift = self.STREAM_SIZE - 1
                            lick1array = hstack((lick1array[-self.STREAM_SIZE + shift:], [lick1array[-1]] * shift))
                            if isnan(last_state):
                                lick1array = hstack((lick1array[-self.STREAM_SIZE + 1:], [i + 1]))
                            else:
                                lick1array = hstack((lick1array[-self.STREAM_SIZE + 1:], [nan]))
                            last_lick1_tick = lick1
                        last_state = lick1array[-1]
                        # last timestamp of lick1 signal change
                        self._last_lick1_index = lick1
                    lastshift = int(packet_sent_time - last_lick1_tick)
                    if lastshift >= self.STREAM_SIZE:
                        lastshift = self.STREAM_SIZE
                        lick1array = [lick1array[-1]] * lastshift
                    elif lastshift > 0 and len(lick1array) > 0:
                        lick1array = hstack((lick1array[-self.STREAM_SIZE + lastshift:], [lick1array[-1]] * lastshift))
                if len(lick1array) > 0:
                    self.stream_lick1_data.set_data(lick1signal, lick1array)
                    # self.stream_lick1_plot.request_redraw()
                    lick1arrays[i] = lick1array

        return lick1arrays

    def _process_lick2s(self, stream, lick2signals, lick2arrays):

        packet_sent_time = stream['packet_sent_time']

        # TODO: find max shift first, apply it to all lick2s
        maxtimestamp = int(packet_sent_time)
        for i in range(len(lick2arrays)):
            lick2signal = lick2signals[i]

            if lick2signal in stream.keys():
                streamsignal = stream[lick2signal]
                if streamsignal is not None and streamsignal[-1] > maxtimestamp:
                    maxtimestamp = streamsignal[-1]
                    print "**************************************************************"
                    print "WARNING! lick2 timestamp exceeds timestamp of received packet: "
                    print "Packet sent timestamp: ", packet_sent_time, "lick2 timestamp: ", streamsignal[-1]
                    print "**************************************************************"
        maxshift = int(packet_sent_time - self._last_stream_index)
        if maxshift > self.STREAM_SIZE:
            maxshift = self.STREAM_SIZE - 1

        for i in range(len(lick2arrays)):

            lick2signal = lick2signals[i]
            lick2array = lick2arrays[i]

            if lick2signal in stream.keys():
                if stream[lick2signal] is None:
                    lick2array = hstack((lick2array[-self.STREAM_SIZE + maxshift:], [lick2array[-1]] * maxshift))
                else:
                    # print "lick2s: ", stream['lick2'], "\tnum sniffs: ", currentshift
                    last_state = lick2array[-1]
                    last_lick2_tick = self._last_stream_index
                    for lick2 in stream[lick2signal]:
                        # print "last lick2 tick: ", last_lick2_tick, "\tlast state: ", last_state
                        shift = int(lick2 - last_lick2_tick)
                        if shift <= 0:
                            if shift < self.STREAM_SIZE * -1:
                                shift = -self.STREAM_SIZE + 1
                            if isnan(last_state):
                                lick2array[shift - 1:] = [i + 1] * (-shift + 1)
                            else:
                                lick2array[shift - 1:] = [nan] * (-shift + 1)
                        # lick2 timestamp exceeds packet sent time. Just change the signal state but don't shift
                        elif lick2 > packet_sent_time:
                            if isnan(last_state):
                                lick2array[-1] = i + 1
                            else:
                                lick2array[-1] = nan
                        else:
                            if shift > self.STREAM_SIZE:
                                shift = self.STREAM_SIZE - 1
                            lick2array = hstack((lick2array[-self.STREAM_SIZE + shift:], [lick2array[-1]] * shift))
                            if isnan(last_state):
                                lick2array = hstack((lick2array[-self.STREAM_SIZE + 1:], [i + 1]))
                            else:
                                lick2array = hstack((lick2array[-self.STREAM_SIZE + 1:], [nan]))
                            last_lick2_tick = lick2
                        last_state = lick2array[-1]
                        # last timestamp of lick2 signal change
                        self._last_lick2_index = lick2
                    lastshift = int(packet_sent_time - last_lick2_tick)
                    if lastshift >= self.STREAM_SIZE:
                        lastshift = self.STREAM_SIZE
                        lick2array = [lick2array[-1]] * lastshift
                    elif lastshift > 0 and len(lick2array) > 0:
                        lick2array = hstack((lick2array[-self.STREAM_SIZE + lastshift:], [lick2array[-1]] * lastshift))
                if len(lick2array) > 0:
                    self.stream_lick2_data.set_data(lick2signal, lick2array)
                    # self.stream_lick2_plot.request_redraw()
                    lick2arrays[i] = lick2array

        return lick2arrays

    def _process_mris(self, stream, mrisignals, mriarrays):

        packet_sent_time = stream['packet_sent_time']

        # TODO: find max shift first, apply it to all
        maxtimestamp = int(packet_sent_time)
        for i in range(len(mriarrays)):
            mrisignal = mrisignals[i]

            if mrisignal in stream.keys():
                streamsignal = stream[mrisignal]
                if streamsignal is not None and streamsignal[-1] > maxtimestamp:
                        maxtimestamp = streamsignal[-1]
                        print "**************************************************************"
                        print "WARNING! MRI timestamp exceeds timestamp of received packet: "
                        print "Packet sent timestamp: ", packet_sent_time, "MRI timestamp: ", streamsignal[-1]
                        print "**************************************************************"
        maxshift = int(packet_sent_time - self._last_stream_index)
        if maxshift > self.STREAM_SIZE:
            maxshift = self.STREAM_SIZE - 1

        for i in range(len(mriarrays)):

            mrisignal = mrisignals[i]
            mriarray = mriarrays[i]

            if mrisignal in stream.keys():
                if stream[mrisignal] is None:
                    mriarray = hstack((mriarray[-self.STREAM_SIZE + maxshift:], [mriarray[-1]] * maxshift))
                else:
                    last_state = mriarray[-1]
                    last_mri_tick = self._last_stream_index
                    for mri in stream[mrisignal]:
                        shift = int(mri - last_mri_tick)
                        if shift <= 0:
                            if shift < self.STREAM_SIZE * -1:
                                shift = -self.STREAM_SIZE + 1
                            if isnan(last_state):
                                mriarray[shift - 1:] = [i + 1] * (-shift + 1)
                            else:
                                mriarray[shift - 1:] = [nan] * (-shift + 1)
                        elif mri > packet_sent_time:
                            if isnan(last_state):
                                mriarray[-1] = i + 1
                            else:
                                mriarray[-1] = nan
                        else:
                            if shift > self.STREAM_SIZE:
                                shift = self.STREAM_SIZE - 1
                            mriarray = hstack((mriarray[-self.STREAM_SIZE + shift:], [mriarray[-1]] * shift))
                            if isnan(last_state):
                                mriarray = hstack((mriarray[-self.STREAM_SIZE + 1:], [i + 1]))
                            else:
                                mriarray = hstack((mriarray[-self.STREAM_SIZE + 1:], [nan]))
                            last_mri_tick = mri
                        last_state = mriarray[-1]
                        # last timestamp of lick signal change
                        self._last_mri_index = mri
                    lastshift = int(packet_sent_time - last_mri_tick)
                    if lastshift >= self.STREAM_SIZE:
                        lastshift = self.STREAM_SIZE
                        mriarray = [mriarray[-1]] * lastshift
                    elif lastshift > 0 and len(mriarray) > 0:
                        mriarray = hstack((mriarray[-self.STREAM_SIZE + lastshift:], [mriarray[-1]] * lastshift))
                if len(mriarray) > 0:
                    self.stream_mri_data.set_data(mrisignal, mriarray)
                    # self.stream_mri_plot.request_redraw()
                    mriarrays[i] = mriarray

        return mriarrays

    def _shiftlicks(self, shift):

        if shift > self.STREAM_SIZE:
            shift = self.STREAM_SIZE - 1

        streamdef = self.stream_definition()
        if 'lick1' in streamdef.keys():
            self.lick1 = hstack((self.lick1[-self.STREAM_SIZE + shift:], self.lick1[-1] * shift))
            self.stream_lick_data.set_data('lick1', self.lick1)
        return

    def _shiftmris(self, shift):

        if shift > self.STREAM_SIZE:
            shift = self.STREAM_SIZE - 1

        streamdef = self.stream_definition()
        if 'mri' in streamdef.keys():
            self.mri = hstack((self.mri[-self.STREAM_SIZE + shift:], self.mri[-1] * shift))
            self.stream_mri_data.set_data('mri', self.mri)
        return

    def start_of_trial(self):

        self.timestamp("start")
        print "\n***** Trial:", self.trial_number, self.current_stimulus, "*****"

    def _odorvalveon(self):
        """ Turn on odorant valve """

        if(self.olfactometer is None) or self.start_label == 'Start' or self.pause_label == "Unpause":
            return
        for i in range(self.olfactometer.deviceCount):
            olfa = self.olfas[i]
            olfavalve = olfa[self.current_stimulus.odorvalves[i]][2]

            if olfavalve != 0:
                self.olfactometer.olfas[i].valves.set_odor_valve(olfavalve) #set the vial,
    
    
    def _setflows(self):
        """ Set MFC Flows """

        if(self.olfactometer is None):
            return

        for i in range(1, self.olfactometer.deviceCount + 1):
            self.olfactometer.olfas[i - 1].mfc1.setMFCrate(self.olfactometer.olfas[i - 1].mfc1, self.current_stimulus.flows[i - 1][1])
            self.olfactometer.olfas[i - 1].mfc2.setMFCrate(self.olfactometer.olfas[i - 1].mfc2, self.current_stimulus.flows[i - 1][0])
            self.olfactometer.olfas[i - 1].mfc3.setMFCrate(self.olfactometer.olfas[i - 1].mfc3, 1000)

    def end_of_trial(self):
        # set new trial parameters
        # turn off odorant valve
        if(self.olfactometer is not None):
            for i in range(self.olfactometer.deviceCount):
                olfa = self.olfas[i]
                olfavalve = olfa[self.current_stimulus.odorvalves[i]][2]
                if olfavalve != 0:
                    self.olfactometer.olfas[i].valves.set_odor_valve(olfavalve, 0)

    
    def generate_next_stimulus_block(self):
        """ Generate a block of randomly shuffled stimuli from the stimulus \
        set stored in self.stimuli.
        
        Modify this method to implement the behaviour you want for how a block
        of stimuli is chosen.
        
        """
        
        if not self.enable_blocks:
            return
        
        if len(self.stimulus_block):
            print "Warning! Current stimulus block was not empty! Generating \
                    new block..."
        
        # Generate an initial block of trials if needed.
        if self.trial_number < self.INITIAL_TRIALS :
            block_size = self.INITIAL_TRIALS + 1 - self.trial_number
            if self.INITIAL_TRIALS_TYPE == 0:
                self.stimulus_block = [self.stimuli["Left"][0]] * block_size
            elif self.INITIAL_TRIALS_TYPE == 1:
                self.stimulus_block = [self.stimuli["Right"][0]] * block_size

            elif self.INITIAL_TRIALS_TYPE == 2: # right then left
                self.stimulus_block = [self.stimuli["Left"][0]] * (block_size/2)
                if self.INITIAL_TRIALS and self.trial_number <= self.INITIAL_TRIALS/2:
                    self.stimulus_block = [self.stimuli["Right"][0]] * (block_size / 2)
            elif self.INITIAL_TRIALS_TYPE == 3: # left then right
                self.stimulus_block = [self.stimuli["Right"][0]] * (block_size/2)
                if self.INITIAL_TRIALS and self.trial_number <= self.INITIAL_TRIALS/2:
                    self.stimulus_block = [self.stimuli["Left"][0]] * (block_size / 2)
            return

        
        # Randomize seed from system clock.
        seed()
        if not len(self.stimuli):
            raise ValueError("Stimulus set is empty! Cannot generate a block.")
        # Grab all stimuli arrays from our stimuli sets.
        list_all_stimuli_arrays = self.stimuli.values()
        # Flatten the list so that we have a 1 dimensional array of items
        self.stimulus_block = list(chain.from_iterable(list_all_stimuli_arrays))
                
        if self.block_size/len(self.stimulus_block) > 1:
            copies = self.block_size/len(self.stimulus_block)
            self.stimulus_block *= copies
            if len(self.stimulus_block) < self.block_size:
                print "WARNING! Block size is not a multiple of stimulus set:"\
                    "\nBlock size: %d\t Stimulus set size: %d \tConstructed " \
                    " Stimulus block size: %d" \
                    %(self.block_size, len(self.stimuli.values()),
                      len(self.stimulus_block))
            
        # Shuffle the set.
        attempts = 0
        while attempts < 20:
            try:
                shuffle(self.stimulus_block, random)
                if all(len(list(group)) < 4 for _, group in groupby(self.stimulus_block)):
                    break
            except:
                attempts += 1
                if attempts == 19:
                    print "Failed to generate new stimulus block"
                    break
        # for i in range(len(self.stimulus_block)-1):
        #     self.stimulus_block[-(i*2-1):-(i*2-1)] = self.no_stimuli
        # self.stimulus_block[len(self.stimulus_block):len(self.stimulus_block)] = self.no_stimuli

        print "\nGenerated new stimulus block:"
        for i in range(len(self.stimulus_block)):
            trial = i + 1
            print "\t", trial, "\t", self.stimulus_block[i]
        print "\n"
    
    def calculate_current_trial_parameters(self):
        """ Calculate the parameters for the currently scheduled trial.
        
        This method can be used to calculate the parameters for the trial that
        will follow next. This method is called from process_event_request,
        which is automatically called after results of the previous trial are
        received.
        
        """
        
        self.trial_number = self.next_trial_number
        self.current_stimulus = self.next_stimulus
        self.trial_type = self.next_trial_type
        self.odorant = self.next_odorant
        self.nitrogen_flow = self.next_nitrogen_flow
        self.air_flow = self.next_air_flow
        
        # For the first trial recalculate the next trial parameters again
        # so that the second trial is also prepared and ready.
        # if self.trial_number == 1:
        #     self.calculate_next_trial_parameters()

    def calculate_next_trial_parameters(self):
        """ Calculate parameters for the trial that will follow the currently \
        scheduled trial.
        
        The current algorithm is such that at the end of the trial:
        current parameters are assigned values of the previous trial's next
            parameters AND
        next parameters are computed for the trial following. This is where the
        next parameters are assigned.
        
        At this point the current stimulus becomes the previous trial's next 
        stimulus. This makes it possible to know in advance the currently
        scheduled trial as well as the one after that and display this
        information in advance in the GUI. If any current trial parameters
        depend on the result of the previous trial, this is not the
        place to assign these parameters. They should be assigned in 
        calculate_current_trial_parameters method, before the call to this
        method.
        
        """
        
        self.next_trial_number = self.trial_number + 1
        
        # Grab next stimulus.
        if self.enable_blocks:
            if not len(self.stimulus_block):
                self.generate_next_stimulus_block()
            self.next_stimulus = self.stimulus_block.pop(0)

        else:
            # Pick a random stimulus from the stimulus set of the next
            # trial type.
            if self.next_trial_number > self.INITIAL_TRIALS:
                # Randomly choose a stimulus.
                self.next_stimulus = choice([stimulus] for stimulus in
                                                 self.stimuli.values())
        
        self.next_trial_type = self.next_stimulus.trial_type
        nextodorvalve = self.next_stimulus.odorvalves[0]
        self.next_odorant = self.olfas[0][nextodorvalve][0]
        self.next_air_flow = self.next_stimulus.flows[0][0]
        self.next_nitrogen_flow = self.next_stimulus.flows[0][1]

    def trial_iti_milliseconds(self):
        if self.next_trial_start:
            return self.next_trial_start
        return 0

    def timestamp(self, when):
        """ Used to timestamp events """
        if(when == "start"):
            self._parameters_sent_time = time.clock()
            # print "start timestamp ", self._parameters_sent_time
        elif(when == "end"):
            self._results_time = time.clock()
            

        
#
# Main - creates a database, sends parameters to controller, stores resulting data, and generates display
#

if __name__ == '__main__':

    # arduino parameter defaults

    trial_number = 0
    trial_type_id = 0
    final_valve_duration = 1000
    response_duration = 5000
    lick_grace_period = 50
    max_rewards = 200
    odorant_trigger_phase_code = 2
    trial_type_id = 0
    inter_trial_interval = 15000
    hemodynamic_delay = 0

    # protocol parameter defaults
    mouse = 434  # can I make this an illegal value so that it forces me to change it????

    session = 18
    stamp = time_stamp()
    tr = 1000
    licking_training_probability = 0
    
    # protocol
    protocol = Passive_odor_presentation(trial_number,
                                         mouse,
                                         session,
                                         stamp,
                                         inter_trial_interval,
                                         trial_type_id,
                                         max_rewards,
                                         final_valve_duration,
                                         response_duration,
                                         odorant_trigger_phase_code,
                                         lick_grace_period,
                                         hemodynamic_delay,
                                         tr,
                                         licking_training_probability
                                         )

    # Testing code when no hardware attached.
    # GUI
    protocol.configure_traits()