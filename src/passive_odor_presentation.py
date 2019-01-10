'''
Created on 2015_08_04 @author: Admir Resulaj
Modified on 2016_06_24 @author: Pei-Ching Chang

This protocol implements a passive odor and two alternative choice paradigm for the Voyeur/arduino_controller
platform. This includes the protocol behaviour as well as visualization (GUI).
'''


#!/usr/bin/env python2.7
# passive_odor_presentation.py

#  Python library imports
import os, time
from numpy import append, arange, hstack, nan, isnan, negative
from random import choice, randint, shuffle, seed, random
from itertools import chain, groupby

# Voyeur imports
import voyeur.db as db
from voyeur import Monitor, Protocol, TrialParameters, time_stamp

# Olfactometer module
from src import Olfactometers, LaserTrainStimulus,\
    RangeSelectionsOverlay, parse_rig_config, find_odor_vial

# Enthought's traits imports (For GUI) - Place these imports under
# voyeur imports since voyeur will select the GUI toolkit to be QT
# By default traits will pick wx as the GUI toolkit. By importing voyeur
# first, QT is set and used subsequently for all gui related things
from chaco.api import ArrayPlotData, Plot, VPlotContainer, DataRange1D
from chaco.axis import PlotAxis
from chaco.scales.api import TimeScale
from chaco.scales_tick_generator import ScalesTickGenerator
from enable.component import Component
from enable.component_editor import ComponentEditor
from pyface.timer.api import Timer
from pyface.api import FileDialog, OK
from traits.api import Int, Str, Array, Float, Enum, Bool, Range,Instance, Trait
from traits.has_traits import on_trait_change
from traits.trait_types import Button
from traitsui.api import View, Group, HGroup, VGroup, Item, spring
from traitsui.editors import ButtonEditor

import warnings
warnings.filterwarnings("ignore")

class Passive_odor_presentation(Protocol):
    """Protocol and GUI for a 2AFC behavioral paradigm."""

    # Protocol name
    PROTOCOL_NAME = 'Two Alternative Choice'

    # Streaming plot window size in milliseconds.
    STREAM_SIZE = 5000
    
    # Number of trials in a block.
    BLOCK_SIZE = 20

    # Flag to indicate whether we have an arduino_controller, Olfactometer, Scanner connected. Set to 0 for
    # debugging.
    ARDUINO = 1
    OLFA = 1
    FMRI = 0

    # Flag "LICKING_TRAINING" to indicate whether we are training mouse to lick or not.
    # Set to 0 when not training, 0.5 when half time are given "free water"
    # During initial free water trials, free water is 100% given to mice
    # Afterwards, free water is given based on the licking training chance and during side preference
    # When mice have a few missed responses on certain side, it will given free water to the bad side for 100%
    INITIAL_FREE_WATER_TRIALS = 16
    LICKING_TRAINING = 0.05
    SIDE_PREFERENCE_TRIALS = 3
    MISSED_RESPONSE_BEFORE_SIDE_PREFERENCE_TRIALS = 5

    # Grace period after FV open where responses are recorded but not scored.
    LICKING_GRACE_PERIOD = 0
    RESPONSE_DURATION = 2000

    # Number of trials in one sliding window used for continuous
    # visualizing of session performance.
    SLIDING_WINDOW = 400
    
    # Amount of time in milliseconds for odorant vial to be ON prior to
    # trial start. This should be sufficiently large so that odorant makes it to
    # the final valve by the trial start.
    VIAL_ON_BEFORE_TRIAL = 3000

    # Maximum trial duration to wait for, in seconds, before we assume problems
    # in communication.
    MAX_TRIAL_DURATION = 100
    
    # Number of initial trials to help motivating the subject to start
    # responding to trials.Must be even number. If INITIAL_TRIALS_TYPE is 2 or 3,
    # half of initial trials will be right and the rest is left
    INITIAL_TRIALS_TYPE = 0 # 0: LEFT, 1: RIGHT, 2: RIGHT then LEFT,, 3: LEFT then RIGHT
    INITIAL_TRIALS = 0

    # [Upper, lower] bounds in milliseconds when choosing an
    # inter trial interval for trials when there was no false alarm.
    ITI_BOUNDS_CORRECT = [15000, 17000]
    # [Upper, lower] bounds for random inter trial interval assignment
    # when the animal DID false alarm. Value is in milliseconds.
    ITI_BOUNDS_FALSE_ALARM = [20000, 22000]

    # MRI sampleing rate
    TR = 1000
    
    # Mapping of stimuli categories to code sent to arduino_controller.
    STIMULI_CATEGORIES = {
                          "Right": 0,
                          "Left" : 1,
                          "None": 2,
                          }

    # Mapping of sniff phase name to code sent to arduino_controller.
    ODORANT_TRIGGER_PHASE = 2
    SNIFF_PHASES = {
                    0: "Inhalation",
                    1: "Exhalation",
                    2: "Independent"
                    }

    #--------------------------------------------------------------------------
    # Protocol parameters.
    # These are session parameters that are not sent to the controller
    # (arduino_controller). These may change from trial to trial. They are stored in
    # the database file for each trial.
    #--------------------------------------------------------------------------
    mouse = Str(0, label='Subject')   # mouse name
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
    odorvalve = Int(label="Valve")

    
    # Session parameters do not change from trial to trial. These
    # are currently not stored in the trials table of the database file.
    stamp = Str(label='Stamp')   # time stamp.
    protocol_name = Str(label='Protocol')
    enable_blocks = Bool(True, label="Arrange stimuli in blocks")

    # Rewards given from start of session.
    rewards = Int(0, label="Rewards")
    rewards_left = Int(0, label="LeftRewards")
    rewards_right = Int(0, label="RightRewards")
    max_rewards = Int(400, label="Reward until")   # maximum rewards allowed.
    
    #-------------------------------------------------------------------------- 
    # Controller parameters.
    # These are trial parameters sent to arduino_controller. By default trial_number is
    # not sent to arduino_controller(???), but it is still logged in the database file.
    #--------------------------------------------------------------------------
    trial_number = Int(0, label='Trial Number')
    # Mapped trait. trial type keyword: code sent to arduino_controller.
    trial_type = Trait(STIMULI_CATEGORIES.keys()[0],
                       STIMULI_CATEGORIES,
                       label="Trial type")
    water_duration1 = Int(0, label="Left water duration")
    water_duration2 = Int(0, label="Right water duration")
    final_valve_duration = Int(0, label="Final valve duration")
    training_times1 = Int(100, label="Left water licking training")
    training_times2 = Int(100, label="Right water licking training")
    response_window = Int(0, label="Response duration")
    inter_trial_interval = Int(0, label='ITI')
    tr = Int(0, label='Repetition time')
    # Amount of time in ms to not count a lick response as the trial choice.
    # If the mouse is impulsive, this prevents uninformed false alarms.
    lick_grace_period = Int(0, label="Lick grace period")
    # Sniff phase from the onset of which the latency of triggering the light
    # stimulation pulse/pulses is measured. Default value is "Inhalation".
    sniff_phase = Str(SNIFF_PHASES[ODORANT_TRIGGER_PHASE], label="Odorant onset after")
    
    # Other trial parameters. These are not recording in the database file.
    # but are displayed and/or computed trial to trial.
    # Next trial air flow.
    next_air_flow = Float(label="Air (sccm)")
    # Next trial nitrogen flow.
    next_nitrogen_flow = Float(label="N2 (sccm)")
    # Next trial odorant name.
    next_odorant = Str("Next odorant", label="Odor")
    next_trial_number = Int(0, label='Trial Number')
    next_odorvalve = Int(label="Valve")
    # Reusing of the trait definition for trial_type.
    # The values will be independent but valiadation is done the same way.
    next_trial_type = trial_type
    # Used to notify the backend of voyeur when to send
    # the next trial parameters to arduino_controller. Recomputed every trial depending on
    # the result and iti choice.
    next_trial_start = 0
    # [Upper, lower] bounds in milliseconds when choosing an 
    # inter trial interval for trials when there was no false alarm.
    iti_bounds = [0, 0]
    # [Upper, lower] bounds for random inter trial interval assignment 
    # when the animal DID false alarm. Value is in milliseconds.
    iti_bounds_false_alarm = [0, 0]
    # Current overall session performance.
    total_available_rewards = Int(0)
    total_available_rewards_left = Int(0)
    total_available_rewards_right = Int(0)
    corrects = Int(0)
    corrects_left = Int(0)
    corrects_right = Int(0)
    percent_correct = Float(0, label="Correct%")
    percent_left_correct = Float(0, label="LeftCorrect%")
    percent_right_correct = Float(0, label="RightCorrect%")
    left_side_odor_test = [0]*5
    right_side_odor_test = [0]*5
    left_side_preference_trials = Int(0)
    right_side_preference_trials = Int(0)
    free_water = Bool(False, label='FreeWater')
    next_free_water = Bool(False, label='NextFreeWater')
    next_left_free_water = Bool(False, label='LeftFreeWater')
    next_right_free_water = Bool(False, label='RightFreeWater')
    initial_free_water_trials = Int(0)
        
    #--------------------------------------------------------------------------
    # Variables for the event.
    # These are the trial results sent from arduino_controller.
    # They are stored in the database file.
    #--------------------------------------------------------------------------    
    trial_start = Int(0, label="Start of trial time stamp")
    trial_end = Int(0, label="End of trial time stamp")
    first_lick = Int(0, label="Time of first lick")
    # Time when arduino_controller received the parameters for the trial (in arduino_controller
    # elapsed time).
    parameters_received_time = Int(0,
                                   label="Time parameters were received \
                                   by arduino_controller")
    final_valve_onset = Int(0, label="Time of final valve open")
    
    
    # Current stimulus object.
    # current_stimulus = Instance(LaserTrainStimulus)
    # next_stimulus = Instance(LaserTrainStimulus)
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
    
    # Time stamp of when voyeur requested the parameters to send to arduino_controller.
    _parameters_sent_time = float()
    # Time stamp of when voyeur sent the results for processing.
    _results_time = float()
    
    # Packets dropped as detected from the continuous data stream. 
    _unsynced_packets = 0
    
    # This is the voyeur backend monitor. It handles data acquisition, storage,
    # and trial to trial communications with the controller (arduino_controller).
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
    licking_training_button = Button()
    licking_training_label = Str('Licking training')
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
                                       Item('water_duration1'),
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
                                       Item('water_duration2'),
                                        ),
                                  ),
                           label="arduino_controller Control",
                           show_border=True
                           )
    
    session_group = Group(
                          HGroup(
                                 Item('stamp', style='readonly',
                                      width=-195),
                                 Item('protocol_name', style='readonly'),
                                ),
                          HGroup(
                                 Item('rig', style='readonly', width=-217),
                                 Item('sniff_phase', style='readonly')
                                ),
                          HGroup(
                                 Item('mouse',
                                      enabled_when='not monitor.running',
                                      width=-196),
                                 Item('session',
                                      enabled_when='not monitor.running'),
                                 ),
                          label='Session',
                          show_border=True
                          )

    result_group = Group(HGroup(
                                 Item('rewards', style='readonly', width=-67),
                                 Item('rewards_left', style='readonly', width=-66),
                                 Item('rewards_right', style='readonly'),
                                 ),
                          HGroup(
                                 Item('percent_correct', style='readonly',width=-60),
                                 Item('percent_left_correct', style='readonly',width=-60),
                                 Item('percent_right_correct', style='readonly'),
                                 ),
                          label='Result',
                          show_border=True
                          )

    
    current_trial_group = Group(
                                HGroup(
                                       Item('trial_number', style='readonly', width=-100),
                                       Item('trial_type', style='readonly'),
                                       ),
                                HGroup(
                                       Item('odorant', style='readonly', width=-157),
                                       Item('odorvalve', style='readonly'),
                                       ),
                                HGroup(
                                        Item('inter_trial_interval', style='readonly',  width=-171),
                                        Item('free_water')
                                ),
                                label='Current Trial',
                                show_border=True
                                )

    next_trial_group = Group(
                             HGroup(
                                    Item('next_trial_number', style='readonly', width=-100),
                                    Item('next_trial_type', style='readonly'),
                                    ),
                             HGroup(
                                    Item('next_odorant', style="readonly", width=-157),
                                    Item('next_odorvalve', style='readonly'),
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
                              result_group,
                              current_trial_group,
                              next_trial_group),
                       stream,
                       event,
                       show_labels=True,
                       ),
                title= "Passive Odor Presentation",
                width=1300,
                height=768,
                x=30,
                y=70,
                resizable=True,
                )
    
    def _stream_plots_default(self):
        """ Build and return the container for the streaming plots."""


        # ---------------------------------------------------------------------
        # Streaming signals container plot.
        #----------------------------------------------------------------------
        # Data definiton.
        # Associate the plot data array members with the arrays that are used
        # for updating the data. iteration is the abscissa values of the plots.
        self.stream_plot_data = ArrayPlotData(iteration=self.iteration,
                                              sniff=self.sniff)

        # Create the Plot object for the streaming data.
        plot = Plot(self.stream_plot_data, padding=20, padding_left=80, padding_top=0, padding_bottom=25, border_visible=False)

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
            y_range = DataRange1D(low=-20, high=20)  # for training non-mri sniff sensor
        plot.value_range = y_range
        plot.fixed_preferred_size = (100, 20)
        plot.y_axis.visible = True
        plot.x_axis.visible = False
        plot.legend.visible = True
        plot.legend.bgcolor = "white"
        plot.legend.align = "ul"
        plot.legend.border_visible = False
        plot.legend.font = "Arial 14"


        # Make a custom abscissa axis object.
        AXIS_DEFAULTS = {
            'axis_line_weight': 1,
            'tick_weight': 1,
            'tick_label_font': 'Arial 14',
        }

        x_axis = PlotAxis(orientation='bottom',
                          mapper=plot.x_mapper,
                          component=plot,
                          tick_generator=ScalesTickGenerator(scale=TimeScale(seconds=1)),
                          **AXIS_DEFAULTS)
        y_axis = PlotAxis(orientation='left',
                          mapper=plot.y_mapper,
                          tick_interval=20,
                          component=plot,
                          **AXIS_DEFAULTS)


        plot.x_axis = x_axis
        plot.y_axis = y_axis

        # Add the lines to the Plot object using the data arrays that it
        # already knows about.
        plot.plot(('iteration', 'sniff'), type='line', color='black', name="Breathing", line_width=1)

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
        
        # Lick left
        self.stream_events_data = ArrayPlotData(iteration=self.iteration,
                                              lick1=self.lick1, lick2=self.lick2, mri=self.mri)

        # Plot object created with the data definition above.
        plot = Plot(self.stream_events_data, padding=20, padding_left=80, padding_top=0,
                    padding_bottom=0, border_visible=False)

        # # Data array for the signal.
        # # The last value is not nan so that the first incoming streaming value
        # # can be set to nan. Implementation detail on how we start streaming.
        self.lick1 = [nan] * len(self.iteration)
        self.lick1[-1] = 0
        self.lick2 = [nan] * len(self.iteration)
        self.lick2[-1] = 0
        self.mri = [-2] * len(self.iteration)
        self.mri[-1] = 0

        self.stream_events_data.set_data("iteration", self.iteration)
        self.stream_events_data.set_data("lick1", self.lick1)
        self.stream_events_data.set_data("lick2", self.lick2)
        self.stream_events_data.set_data("mri", self.mri)

        # Change plot properties.)
        plot.fixed_preferred_size = (100, 5)
        y_range = DataRange1D(low=0, high=2)
        plot.value_range = y_range
        plot.y_axis.visible = False
        plot.x_axis.visible = False
        plot.y_grid = None
        plot.x_grid = None
        plot.legend.visible = True
        plot.legend.bgcolor = "white"
        plot.legend.align = "ul"
        plot.legend.line_spacing = 6
        plot.legend.font = "Arial 14"
        plot.legend.border_visible = False


        # Add the lines to the plot and grab one of the plot references.
        event_plot = plot.plot(("iteration", "lick1"),
                               name="Choice (L)",
                               color="blue",
                               line_width=5)[0]

        event_plot = plot.plot(("iteration", "lick2"),
                               name="Choice (R)",
                               color="red",
                               line_width=5)[0]
        event_plot = plot.plot(("iteration", "mri"),
                               name="Trigger",
                               color="green",
                               line_width=5)[0]


        self.stream_events_plot = plot

        # Two plots will be overlaid with no separation.
        container = VPlotContainer(bgcolor="transparent")

        # Add the plots and their data to each container.
        container.add(self.stream_plot, self.stream_events_plot)

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
        self.rewards_left = 0
        self.rewards_right = 0
        self.corrects = 0
        self.corrects_left = 0
        self.corrects_right = 0
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

        # Dictionary of all stimuli defined (arranged by category), with each
        # category having a list of stimuli
        self.STIMULI = {
            stim_category: [] for stim_category in self.STIMULI_CATEGORIES.keys()
        }


        # find all of the vials with the odor. ASSUMES THAT ONLY ONE OLFACTOMETER IS PRESENT!
        odorvalves_left_stimulus = find_odor_vial(self.olfas, 'Acetophenone', 1)['key']
        odorvalves_right_stimulus = find_odor_vial(self.olfas, 'Benzaldehyde', 1)['key']
        odorvalves_no_stimulus = find_odor_vial(self.olfas, 'Blank1', 1)['key']

        # randomly select the vial from the list for stimulation block. it may be same or different vials
        for i in range(len(odorvalves_left_stimulus)):
            right_stimulus = LaserTrainStimulus(
                                    odorvalves = odorvalves_right_stimulus,
                                    flows=[(900, 100)],  # [(AIR, Nitrogen)]
                                    id = 0,
                                    description="Right stimulus",
                                    trial_type = "Right"
                                    )
            left_stimulus = LaserTrainStimulus(
                                    odorvalves = odorvalves_left_stimulus,
                                    flows=[(900, 100)],  # [(AIR, Nitrogen)]
                                    id = 1,
                                    description = "Left stimulus",
                                    trial_type = "Left"
                                    )
            no_stimulus = LaserTrainStimulus(
                                    odorvalves = [choice(odorvalves_no_stimulus)],
                                    flows=[(900, 100)],  # [(AIR, Nitrogen)]
                                    id = 2,
                                    description="No stimulus",
                                    trial_type = "None"
                                    )

            self.STIMULI['Left'].append(left_stimulus)
            self.STIMULI['Right'].append(right_stimulus)
            #self.STIMULI['None'].append(no_stimulus)


        print "---------- Stimuli changed ----------"
        for stimulus in self.STIMULI.values():
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
        
        self.event_plot_data.set_data("trial_number_tick", self.trial_number_tick)        
        self.event_plot_data.set_data("_left_trials_line", self._left_trials_line)
        self.event_plot_data.set_data("_right_trials_line", self._right_trials_line)
        self.event_plot.request_redraw()

    # TODO: fix the cycle
    def _callibrate(self):
        """ Fire the final valve on and off in cycles.
        
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
        else:
            self.start_label = 'Stop'
            self._restart()
            self._odorvalveon()
            VoyeurData = os.path.join('/VoyeurData/')
            self.monitor.database_file = VoyeurData + self.db
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
        """ Send a laser trigger command to the arduino_controller, for pulse channel 1.
        """
        
        if self.monitor.recording:
            self._pause_button_fired()
        
        command = "Laser 1 trigger " + str(self.pulse_amplitude1) + " " + str(self.pulse_duration1)
        self.monitor.send_command(command)

    def _pulse_generator2_button_fired(self):
        """ Send a laser trigger command to the arduino_controller, for pulse channel 2.
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
                        response_window,
                        odorant_trigger_phase,
                        lick_grace_period,
                        tr,
                        licking_training,
                        initial_free_water_trials,
                        left_free_water,
                        right_free_water,
                        water_duration1,
                        water_duration2,
                        **kwtraits):
        
        super(Passive_odor_presentation, self).__init__(**kwtraits)
        self.trial_number = trial_number
        self.stamp = stamp
                
        self.db = 'mouse' + str(mouse) + '_' + 'sess' + str(session) \
                    + '_' + self.stamp     
        self.mouse = str(mouse)
        self.session = session
        self.initial_free_water_trials = initial_free_water_trials
        
        self.protocol_name = self.PROTOCOL_NAME
        
        # Get a configuration object with the default settings.
        voyeur_rig_config = os.path.join('/Users/Gottfried_Lab/PycharmProjects/PyOlfa/src/', 'voyeur_rig_config.conf')
        self.config = parse_rig_config(voyeur_rig_config)
        self.rig = self.config['rigName']
        self.water_duration1 = self.config['waterValveDurations']['valve_1_left']['0.25ul']
        self.water_duration2 = self.config['waterValveDurations']['valve_2_right']['0.25ul']
        self.olfas = self.config['olfas']

        self._build_stimulus_set()
        self.calculate_next_trial_parameters()
        self.calculate_current_trial_parameters()
        
        self.inter_trial_interval = inter_trial_interval
        self.final_valve_duration = final_valve_duration
        self.response_window = self.LICKING_GRACE_PERIOD + self.RESPONSE_DURATION
        self.tr = self.TR
        self.licking_training = self.LICKING_TRAINING *10
        self.lick_grace_period = self.LICKING_GRACE_PERIOD
        self.initial_free_water_trials = self.INITIAL_FREE_WATER_TRIALS
        self.stimuli_categories = self.STIMULI_CATEGORIES
        self.iti_bounds = self.ITI_BOUNDS_CORRECT
        self.iti_bounds_false_alarm = self.ITI_BOUNDS_FALSE_ALARM
        self.odorant_trigger_phase = self.ODORANT_TRIGGER_PHASE

        self.block_size = self.BLOCK_SIZE
        self.rewards = 0
        self.rewards_left = 0
        self.rewards_right = 0
        self.corrects = 0
        self.corrects_left = 0
        self.corrects_right = 0
        self.max_rewards = max_rewards
        
        # Setup the performance plots
        self.event_plot_data = ArrayPlotData(trial_number_tick=self.trial_number_tick,
                                             _left_trials_line=self._left_trials_line,
                                             _right_trials_line=self._right_trials_line)
        plot = Plot(self.event_plot_data, padding=20, padding_left=80, padding_bottom=40, border_visible=False)
        self.event_plot = plot
        plot.plot(('trial_number_tick', '_left_trials_line'), type='scatter', marker='circle', marker_size=6,
                  color='blue', outline_color='transparent', name="Trial (L)")
        plot.plot(('trial_number_tick', '_right_trials_line'), type='scatter', marker='circle', marker_size=6,
                  color='red', outline_color='transparent', name="Trial (R)")
        plot.legend.visible = True
        plot.legend.bgcolor = "white"
        plot.legend.align = "ul"
        plot.legend.border_visible = False
        plot.legend.line_spacing = 6
        plot.legend.font = "Arial 14"
        plot.y_axis.title = "% Correct"
        y_range = DataRange1D(low=0, high=100)
        plot.value_range = y_range
        plot.x_grid = None

        AXIS_DEFAULTS = {
            'axis_line_weight': 1,
            'tick_weight': 1,
            'tick_label_font': 'Arial 14',
            'tick_interval': 1
        }

        x_axis = PlotAxis(orientation='bottom',
                          mapper=plot.x_mapper,
                          component=plot,
                          **AXIS_DEFAULTS)
        y_axis = PlotAxis(orientation='left',
                          mapper=plot.y_mapper,
                          tick_interval=20,
                          component=plot)

        plot.x_axis = x_axis
        plot.y_axis = y_axis

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
                   "mouse"                          : self.mouse,
                   "rig"                            : self.rig,
                   "session"                        : self.session,
                   "block_size"                     : self.block_size,
                   "air_flow"                       : self.air_flow,
                   "nitrogen_flow"                  : self.nitrogen_flow,
                   "odorant"                        : self.odorant,
                   "odorvalve"                      : self.odorvalve,
                   "trial_category"                 : self.trial_type,
                   "odorant_trigger_phase"          : self.odorant_trigger_phase,
                   "initial_free_water_trials"      : self.initial_free_water_trials,
                   "rewards"                        : self.rewards,
                   "rewards_left"                   : self.rewards_left,
                   "rewards_right"                  : self.rewards_right,
                   "percent_correct"                : self.percent_correct,
                   "percent_left_correct"           : self.percent_left_correct,
                   "percent_right_correct"          : self.percent_right_correct,
                   }
        
        # Parameters sent to the controller (arduino_controller)
        controller_dict = {
                    "trialNumber"                   : (1, db.Int, self.trial_number),
                    "final_valve_duration"          : (2, db.Int, self.final_valve_duration),
                    "response_window"               : (3, db.Int, self.response_window),
                    "inter_trial_interval"          : (4, db.Int, self.inter_trial_interval),
                    "odorant_trigger_phase"         : (5, db.Int, self.odorant_trigger_phase),
                    "trial_type_id"                 : (6, db.Int, self.current_stimulus.id),
                    "lick_grace_period"             : (7, db.Int, self.lick_grace_period),
                    "tr"                            : (8, db.Int, self.tr),
                    "licking_training"              : (9, db.Int, self.licking_training),
                    "left_free_water"               : (10, db.Int, self.left_free_water),
                    "right_free_water"              : (11, db.Int, self.right_free_water),
                    "water_duration1"               : (12, db.Int, self.water_duration1),
                    "water_duration2"               : (13, db.Int, self.water_duration2),
        }
   
        return TrialParameters(
                    protocolParams=protocol_params,
                    controllerParams=controller_dict
                )

    def protocol_parameters_definition(self):
        """Returns a dictionary of {name => db.type} defining protocol parameters"""

        params_def = {
            "mouse"                         : db.String32,
            "rig"                           : db.String32,
            "session"                       : db.Int,
            "block_size"                    : db.Int,
            "air_flow"                      : db.Float,
            "nitrogen_flow"                 : db.Float,
            "odorant"                       : db.String32,
            "odorvalve"                     : db.Int,
            "trial_category"                : db.String32,
            "odorant_trigger_phase"         : db.String32,
            "initial_free_water_trials"     : db.Int,
            "rewards"                       : db.Int,
            "rewards_left"                  : db.Int,
            "rewards_right"                 : db.Int,
            "percent_correct"               : db.Float,
            "percent_left_correct"          : db.Float,
            "percent_right_correct"         : db.Float,
        }

        return params_def

    def controller_parameters_definition(self):
        """Returns a dictionary of {name => db.type} defining controller (arduino_controller) parameters"""

        params_def = {
            "trialNumber"                   : db.Int,
            "final_valve_duration"          : db.Int,
            "response_window"               : db.Int,
            "inter_trial_interval"          : db.Int,
            "odorant_trigger_phase"         : db.Int,
            "trial_type_id"                 : db.Int,
            "lick_grace_period"             : db.Int,
            "tr"                            : db.Int,
            "licking_training"              : db.Int,
            "left_free_water"               : db.Int,
            "right_free_water"              : db.Int,
            "water_duration1"               : db.Int,
            "water_duration2"               : db.Int,
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
            "first_lick"              : (6, db.Int)
        }

    def stream_definition(self):
        """Returns a dictionary of {name => (index,db.Type} of streaming data parameters for this protocol"""
             
        return {
            "packet_sent_time"         : (1, 'unsigned long', db.Int),
            "sniff_samples"            : (2, 'unsigned int', db.Int),
            "sniff"                    : (3, 'int', db.FloatArray),
            "lick1"                    : (4, 'unsigned long', db.IntArray),
            "lick2"                    : (5, 'unsigned long', db.IntArray),
            "mri"                      : (6, 'unsigned long', db.IntArray)
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
            self.rewards_left += 1
            if self.left_free_water:
                self.rewards += 1
                self.rewards_left += 1
            self.corrects += 1
            self.corrects_left += 1
            self.total_available_rewards += 1
            self.total_available_rewards_left += 1
            if self.rewards >= self.max_rewards and self.start_label == 'Stop':
                self._start_button_fired()  # ends the session if the reward target has been reached.
            self.inter_trial_interval = randint(self.iti_bounds[0], self.iti_bounds[1])

        if (response == 2) : # a right hit.
            self.rewards += 1
            self.rewards_right += 1
            if self.right_free_water:
                self.rewards += 1
                self.rewards_right += 1
            self.corrects += 1
            self.corrects_right += 1
            self.total_available_rewards += 1
            self.total_available_rewards_right += 1
            if self.rewards >= self.max_rewards and self.start_label == 'Stop':
                self._start_button_fired()  # ends the session if the reward target has been reached.
            self.inter_trial_interval = randint(self.iti_bounds[0], self.iti_bounds[1])

        if (response == 3) : # a left false alarm
            if self.left_free_water:
                self.rewards += 1
                self.rewards_left += 1
            self.total_available_rewards += 1
            self.total_available_rewards_left += 1
            self.inter_trial_interval = randint(self.iti_bounds_false_alarm[0],self.iti_bounds_false_alarm[1])

        if (response == 4):  # a right false alarm
            if self.right_free_water:
                self.rewards += 1
                self.rewards_right += 1
            self.total_available_rewards += 1
            self.total_available_rewards_right += 1
            self.inter_trial_interval = randint(self.iti_bounds_false_alarm[0], self.iti_bounds_false_alarm[1])

        if (response == 5) : # no response
            if self.left_free_water:
                self.rewards += 1
                self.rewards_left += 1
            self.total_available_rewards += 1
            self.total_available_rewards_left += 1
            self.inter_trial_interval = randint(self.iti_bounds[0],self.iti_bounds[1])

        if (response == 6) : # no response
            if self.right_free_water:
                self.rewards += 1
                self.rewards_right += 1
            self.total_available_rewards += 1
            self.total_available_rewards_right += 1
            self.inter_trial_interval = randint(self.iti_bounds[0],self.iti_bounds[1])

        self.responses = append(self.responses, response)
        
        # Update a couple last parameters from the next_stimulus object, then make it the current_stimulus..
        self.calculate_current_trial_parameters()
        # Calculate a new next stim.
        self.calculate_next_trial_parameters() # generate a new nextstim for the next next trial. 
        # If actual next trial is determined by the trial that just finished, calculate next trial parameters can set current_stimulus.
        
        # Use the current_stimulus parameters to calculate values that we'll record when we start the trial.
        self._setflows()

        # Calculate the performance to the odor discrimination
        self.percent_correct = round((float(self.corrects) / float(self.total_available_rewards)) * 100, 2)
        if float(self.total_available_rewards_left) > 0:
            self.percent_left_correct = round((float(self.corrects_left) / float(self.total_available_rewards_left)) * 100, 2)
        if float(self.total_available_rewards_right) > 0:
            self.percent_right_correct = round((float(self.corrects_right) / float(self.total_available_rewards_right)) * 100, 2)

        # Set up a timer for opening the vial at the begining of the next trial using the parameters from current_stimulus.
        timefromtrial_end = (self._results_time - self._parameters_sent_time) * 1000 #convert from sec to ms for python generated values
        timefromtrial_end -= (self.trial_end - self.parameters_received_time) * 1.0 
        nextvalveontime = self.inter_trial_interval - timefromtrial_end - self.VIAL_ON_BEFORE_TRIAL
        self.next_trial_start = nextvalveontime + self.VIAL_ON_BEFORE_TRIAL / 2
        if nextvalveontime < 0:
            print "Warning! nextvalveontime < 0"
            nextvalveontime = 20
            self.next_trial_start = 1000
        Timer.singleShot(int(nextvalveontime), self._odorvalveon)
        
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
                # Pad sniff signal with last value for the lost samples first then append received sniff signal
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

            # If we haven't received results by MAX_TRIAL_DURATION, pause and unpause as there was probably some problem with comm.
            if (self.trial_number > 1) and ((time.clock() - self._results_time) > self.MAX_TRIAL_DURATION) and self.pause_label == "Pause":
                print "=============== Pausing to restart Trial =============="
                self._unsynced_packets += 1
                self._results_time = time.clock()
                # Pause and unpause only iff running
                if self.pause_label == "Pause":
                    self.pause_label = 'Unpause'
                    self._pause_button_fired()
                    # Unpause in 1 second
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
                    last_state = lick1array[-1]
                    last_lick1_tick = self._last_stream_index
                    for lick1 in stream[lick1signal]:
                        shift = int(lick1 - last_lick1_tick)
                        if shift <= 0:
                            if shift < self.STREAM_SIZE * -1:
                                shift = -self.STREAM_SIZE + 1
                            if isnan(last_state):
                                lick1array[shift - 1:] = [i + 1] * (-shift + 1)
                            else:
                                lick1array[shift - 1:] = [nan] * (-shift + 1)
                        # Lick1 timestamp exceeds packet sent time. Just change the signal state but don't shift
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
                        # Last timestamp of lick1 signal change
                        self._last_lick1_index = lick1
                    lastshift = int(packet_sent_time - last_lick1_tick)
                    if lastshift >= self.STREAM_SIZE:
                        lastshift = self.STREAM_SIZE
                        lick1array = [lick1array[-1]] * lastshift
                    elif lastshift > 0 and len(lick1array) > 0:
                        lick1array = hstack((lick1array[-self.STREAM_SIZE + lastshift:], [lick1array[-1]] * lastshift))
                if len(lick1array) > 0:
                    self.stream_events_data.set_data(lick1signal, lick1array)
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
                    last_state = lick2array[-1]
                    last_lick2_tick = self._last_stream_index
                    for lick2 in stream[lick2signal]:
                        shift = int(lick2 - last_lick2_tick)
                        if shift <= 0:
                            if shift < self.STREAM_SIZE * -1:
                                shift = -self.STREAM_SIZE + 1
                            if isnan(last_state):
                                lick2array[shift - 1:] = [i + 1] * (-shift + 1)
                            else:
                                lick2array[shift - 1:] = [nan] * (-shift + 1)
                        # Lick2 timestamp exceeds packet sent time. Just change the signal state but don't shift
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
                        # Last timestamp of lick2 signal change
                        self._last_lick2_index = lick2
                    lastshift = int(packet_sent_time - last_lick2_tick)
                    if lastshift >= self.STREAM_SIZE:
                        lastshift = self.STREAM_SIZE
                        lick2array = [lick2array[-1]] * lastshift
                    elif lastshift > 0 and len(lick2array) > 0:
                        lick2array = hstack((lick2array[-self.STREAM_SIZE + lastshift:], [lick2array[-1]] * lastshift))
                if len(lick2array) > 0:
                    self.stream_events_data.set_data(lick2signal, lick2array)
                    lick2arrays[i] = lick2array

        return lick2arrays

    def _process_mris(self, stream, mrisignals, mriarrays):


        packet_sent_time = stream['packet_sent_time']

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
                            return
                        else:
                            if shift > self.STREAM_SIZE:
                                shift = self.STREAM_SIZE - 1
                            mriarray = hstack((mriarray[-self.STREAM_SIZE + shift:], [mriarray[-1]] * shift))
                            if (last_state==-2):
                                mriarray = hstack((mriarray[-self.STREAM_SIZE + 1:], [i + 1]))
                            else:
                                mriarray = hstack((mriarray[-self.STREAM_SIZE + 1:], [-2]))
                            last_mri_tick = mri
                        # last timestamp of lick signal change
                        self._last_mri_index = mri
                    lastshift = int(packet_sent_time - last_mri_tick)
                    if lastshift >= self.STREAM_SIZE:
                        lastshift = self.STREAM_SIZE
                        mriarray = [mriarray[-1]] * lastshift
                    elif lastshift > 0 and len(mriarray) > 0:
                        mriarray = hstack((mriarray[-self.STREAM_SIZE + lastshift:], [mriarray[-1]] * lastshift))
                if len(mriarray) > 0:
                    self.stream_events_data.set_data(mrisignal, mriarray*10)
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
            self.stream_mri_data2.set_data('mri', self.mri)
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
            if self.odorvalve != 0:
                self.olfactometer.olfas[i].valves.set_odor_valve(self.odorvalve) # Set the vial
    
    
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
        # turn off odor valve
        if (self.olfactometer is not None):
            for i in range(self.olfactometer.deviceCount):
                if self.odorvalve != 0:
                    self.olfactometer.olfas[i].valves.set_odor_valve(self.odorvalve, 0)
    
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
                self.stimulus_block = [self.STIMULI["Left"][0]] * block_size
            elif self.INITIAL_TRIALS_TYPE == 1:
                self.stimulus_block = [self.STIMULI["Right"][0]] * block_size

            elif self.INITIAL_TRIALS_TYPE == 2: # right then left
                self.stimulus_block = [self.STIMULI["Left"][0]] * (block_size/2)
                if self.INITIAL_TRIALS and self.trial_number <= self.INITIAL_TRIALS/2:
                    self.stimulus_block = [self.STIMULI["Right"][0]] * (block_size / 2)
            elif self.INITIAL_TRIALS_TYPE == 3: # left then right
                self.stimulus_block = [self.STIMULI["Right"][0]] * (block_size/2)
                if self.INITIAL_TRIALS and self.trial_number <= self.INITIAL_TRIALS/2:
                    self.stimulus_block = [self.STIMULI["Left"][0]] * (block_size / 2)
            return


        # Randomize seed from system clock.
        seed()
        if not len(self.STIMULI):
            raise ValueError("Stimulus set is empty! Cannot generate a block.")
        # Grab all stimuli arrays from our stimuli sets.
        list_all_stimuli_arrays = self.STIMULI.values()
        # Flatten the list so that we have a 1 dimensional array of items
        self.stimulus_block = list(chain.from_iterable(list_all_stimuli_arrays))
                
        if self.block_size/len(self.stimulus_block) > 1:
            copies = self.block_size/len(self.stimulus_block)
            self.stimulus_block *= copies
            if len(self.stimulus_block) < self.block_size:
                print "WARNING! Block size is not a multiple of stimulus set:"\
                    "\nBlock size: %d\t Stimulus set size: %d \tConstructed " \
                    " Stimulus block size: %d" \
                    %(self.block_size, len(self.STIMULI.values()),
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
        self.odorvalve = self.next_odorvalve
        self.nitrogen_flow = self.next_nitrogen_flow
        self.air_flow = self.next_air_flow
        self.free_water = self.next_free_water
        self.left_free_water = self.next_left_free_water
        self.right_free_water = self.next_right_free_water
        
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

        # When mouse is showing strong side preference (ex.only licking on one side of water),
        # break current block of trials and generate a few trials for the underperformed side to motive mouse to lick
        if len(self.responses) > 1:
            lastelement = self.responses[-1]
            if lastelement == 1 or lastelement == 3 or lastelement == 5:
                self.left_side_odor_test.append(lastelement)
            elif lastelement == 2 or lastelement == 4 or lastelement == 6:
                self.right_side_odor_test.append(lastelement)

            # Count the performance of last trials when choice to the odor is wrong or lack of response
            self.left_side_preference_index = self.left_side_odor_test[-5:].count(3) + self.left_side_odor_test[-5:].count(5)
            self.right_side_preference_index = self.right_side_odor_test[-5:].count(4) + self.right_side_odor_test[-5:].count(6)
            # Check if side preference exists
            if (self.left_side_preference_index >= self.MISSED_RESPONSE_BEFORE_SIDE_PREFERENCE_TRIALS):
                self.left_side_preference_trials = self.SIDE_PREFERENCE_TRIALS
            if (self.right_side_preference_index >= self.MISSED_RESPONSE_BEFORE_SIDE_PREFERENCE_TRIALS):
                self.right_side_preference_trials = self.SIDE_PREFERENCE_TRIALS

        
        # Grab next stimulus.
        if self.enable_blocks:
            if self.LICKING_TRAINING > 0:
                self.random_free_water_index = randint(1, 10)
                if self.next_trial_number <= self.initial_free_water_trials:
                    self.next_free_water = True
                elif self.LICKING_TRAINING *10 >= self.random_free_water_index:
                    self.next_free_water = True
                else:
                    self.next_free_water = False

            if not len(self.stimulus_block):
                self.generate_next_stimulus_block()
            self.next_stimulus = self.stimulus_block.pop(0)

        else:
            # Pick a random stimulus from the stimulus set of the next
            # trial type.
            if self.next_trial_number > self.INITIAL_TRIALS:
                # Randomly choose a stimulus.
                self.next_stimulus = choice([stimulus] for stimulus in
                                                 self.STIMULI.values())

        self.next_trial_type = self.next_stimulus.trial_type
        self.next_odorvalve = self.next_stimulus.odorvalves[0]
        self.next_odorant = self.olfas[0][self.next_stimulus.odorvalves[0]][0]
        self.next_air_flow = self.next_stimulus.flows[0][0]
        self.next_nitrogen_flow = self.next_stimulus.flows[0][1]

        if self.next_trial_type == "Left":
            self.next_right_free_water = False
            if self.next_free_water:
                self.next_left_free_water = True
            elif self.left_side_preference_trials > 0:
                self.next_left_free_water = True
                self.left_side_preference_trials -= 1
                self.next_free_water = True
            else:
                self.next_left_free_water = False

        if self.next_trial_type == "Right":
            self.next_left_free_water = False
            if self.next_free_water:
                self.next_right_free_water = True
            elif self.right_side_preference_trials > 0:
                self.next_right_free_water = True
                self.right_side_preference_trials -= 1
                self.next_free_water = True
            else:
                self.next_right_free_water = False

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
    response_window = 3000
    lick_grace_period = 100
    max_rewards = 200
    odorant_trigger_phase = 2
    inter_trial_interval = 2000

    # protocol parameter defaults
    mouse = 434  # can I make this an illegal value so that it forces me to change it????

    session = 18
    stamp = time_stamp()
    tr = 1000
    licking_training = 0
    initial_free_water_trials = 0
    left_free_water = 0
    right_free_water = 0
    water_duration1 = 150
    water_duration2 = 150

    # protocol
    protocol = Passive_odor_presentation(trial_number,
                                         mouse,
                                         session,
                                         stamp,
                                         inter_trial_interval,
                                         trial_type_id,
                                         max_rewards,
                                         final_valve_duration,
                                         response_window,
                                         odorant_trigger_phase,
                                         lick_grace_period,
                                         tr,
                                         licking_training,
                                         initial_free_water_trials,
                                         left_free_water,
                                         right_free_water,
                                         water_duration1,
                                         water_duration2
                                         )

    # Testing code when no hardware attached.
    # GUI
    protocol.configure_traits()
