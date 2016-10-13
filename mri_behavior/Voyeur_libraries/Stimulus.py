
'''
Created on Jun 2, 2011

@author: Admir Resulaj
'''

#from enthought.traits.api import Int, Str, Array, Instance, HasTraits, Float
from numpy import append,insert


class Stimulus:
    ''' Objects representing a stimulus set '''
    
    #An id number for the stimulus
    id = int()
    
    #Stimulus description
    description = str()
    
    #Number of intervals
    num_intervals = int()
    #odor valves
    odorvalves = []
    #MFC flow rates
    flows = []
    #Intervals, each having a set of (valve_on,duration,duration_type) tuples
    intervals = []
    
    #Extra dillution
    dillution = int()
    
    def __init__(self, odorvalves, flows, intervals, id=0, num_intervals=2, dillution=1):
        ''' Constructor '''
        
        self.id = id
        self.num_intervals = num_intervals
        
        self.intervals = []
        self.flows = []
        self.odorvalves = []
        self.dillution = dillution
        
        for interval in intervals:
            self.intervals.append(interval)
            
        for ov in odorvalves:
            self.odorvalves.append(ov)
        for flow in flows:
            self.flows.append(flow)
        
        return None
    
    def __str__(self):
        return "odor valves: " + str(self.odorvalves) + "\tmfc flows: " + str(self.flows) + \
                "\tintervals: " + str(self.intervals) + "\tid: " + str(self.id) + "\tnumber of intervals: " + \
                str(self.num_intervals) + "\tdillution: " + str(self.dillution)


class LaserStimulus(object):
    ''' Objects representing a stimulus set '''
    
    #An id number for the stimulus
    id = int()
    
    #Stimulus description
    description = str()
    
    #Number of lasers
    num_lasers = int()
    #odor valves
    odorvalves = []
    #MFC flow rates as tuples for each MFC (e.g [(air1,nitrogen1),..,(airN,nitrogenN)])
    flows = []
    
    #extra dillution of odor
    dillution=int()
    #Stimuli, each having a set of (amplitude (mv),duration(us),latency(ms),channel) tuples
    laserstims = []
    within_block_repeats = int() # number of times to repeat this stimulus in a single block for use with block objects.
    trial_type = str() # left,right, go, nogo, etc...
    
    
    def __init__(self, odorvalves, flows, laserstims, id=0, num_lasers=1, dillution=1, fvDur=[], description="", within_block_repeats = 1, trial_type = '', **kwds):
        ''' Constructor '''
        
        self.id = id
        self.num_lasers = num_lasers
        self.description = description
        self.dillution = dillution
        self.fvDur = fvDur # vector of durations of fvalve openings (ordered by valves, default is empty)
        self.laserstims = []
        self.flows = []
        self.odorvalves = []
        self.within_block_repeats = within_block_repeats # number of times to repeat this stimulus in a single block for use with block objects.
        self.trial_type = trial_type # left,right, go, nogo, etc...
        
        for laserstim in laserstims:
            self.laserstims.append(laserstim)
            
        for ov in odorvalves:
            self.odorvalves.append(ov)
        for flow in flows:
            self.flows.append(flow)
        super(LaserStimulus,self).__init__(**kwds)
        
        return None
    
    def __str__(self,indent = ''):
        return indent+"Stimulus: " + self.description + "\todor valves: " + str(self.odorvalves) + \
                "\tmfc flows: " + str(self.flows) + \
                "\tdillution: " + str(self.dillution)+ \
                "\tfvDur: " + str(self.fvDur) + \
                '\tTrial_type: ' +str(self.trial_type)
        
class LaserTrainStimulus(LaserStimulus):
    
    # Number of pulses in the pulse train
    numPulses = int()
    
    # Period of OFF time between ON pulse times (in ms). Together the ON time and OFF time define the duty cycle.
    # The ON time is defined in the inherited Laserstimulus class
    pulseOffDuration = int()
    updownmask = False
    updown_start = int() # initial mask start latency.
    updown_initialstepsize = int() # the stepsize in ms for the first step down.
    responsehistory = [] # empty array for tracking the previous response pattern for this stimulus. Use 'stim'.responsehistory.append() to append responses to this list.
    
    
    def __init__(self, numPulses=1, pulseOffDuration=100,updownmask = False, updown_start = 200, updown_initialstepsize = 10,updown_groupid=0, **kwds):
        self.numPulses = numPulses
        self.pulseOffDuration = pulseOffDuration
        self.updownmask = updownmask
        self.updown_start = updown_start
        self.updown_initialstepsize = updown_initialstepsize
        self.updown_laststepsize = 0
        self.updown_stepsexecuted = 0
        self.updown_lastsequence = []
        self.responsehistory = []
        self.updown_groupid = updown_groupid # identifies which group of stimuili this falls into if any. if 0, will be treated as independently tracked by updown algorithm.
        # call the constructer of the inherited class to populate the rest of the args
        super(LaserTrainStimulus,self).__init__(**kwds)

    
    
    