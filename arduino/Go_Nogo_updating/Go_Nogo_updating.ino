// Created on 2015-04-20
// @author: Admir Resulaj
/*
 * This is an Arduino protocol implementing a behavioral Go/NoGo paradigm for
 * an olfactory task.
 */


// include the library code:
#include <SPI.h>
#include <C:\git\Olfalab_Voyeur_protocols_and_files\Arduino\libraries\voyeur_timer_lib.pde>
#include <C:\git\Olfalab_Voyeur_protocols_and_files\Arduino\libraries\ioFunctions_external_timers.pde>
#include <C:\git\Olfalab_Voyeur_protocols_and_files\Arduino\libraries\voyeur_serial_stream_tools.pde>

#define LED_PIN   13

#define TRIGGER1   4
#define TRIGGER2   5
#define TRIGGER3   6

#define SOLENOID1 29
#define SOLENOID2 28
#define SOLENOID3 27
#define SOLENOID4 26
#define SOLENOID5 25
#define SOLENOID6 24
#define SOLENOID7 23
#define SOLENOID8 22

#define BEAM1     37
#define BEAM2     36
#define BEAM3     35
#define BEAM4     34
#define BEAM5     33
#define BEAM6     32
#define BEAM7     31
#define BEAM8     30

#define CUE1      45
#define CUE2      44
#define CUE3      43
#define CUE4      42
#define CUE5      41
#define CUE6      40
#define CUE7      39
#define CUE8      38

#define ADC_PIN   49
#define DAC1_PIN  53
#define DAC2_PIN  48
#define TEENSY_PIN 47

#define DIGITAL1  62
#define DIGITAL2  63
#define DIGITAL3  64
#define DIGITAL4  65
#define DIGITAL5  66
#define DIGITAL6  67
#define DIGITAL7  68
#define DIGITAL8  69
#define DIGITAL9  54
#define DIGITAL10 55
#define DIGITAL11 56
#define DIGITAL12 57
#define DIGITAL13 58
#define DIGITAL14 59
#define DIGITAL15 60
#define DIGITAL16 61

// Valves attached to the behaviour box and their solenoid channels.
#define FINALVALVE SOLENOID1
#define WATERVALVE1 SOLENOID7
#define WATERVALVE2 SOLENOID8
#define CLEARVALVE SOLENOID6
#define FV_T DIGITAL5

// Masking blue LED control channel.
#define LEDMASK DIGITAL11
// Another channel for the masking blue light. This one is on one of the BNCs.
#define LEDMASK_T DIGITAL7

// Trial category labels and codes
#define NOGO 0
#define GO 1

// Phases of the sniff signal and the codes for each phases.
#define INHALATION 0
#define EXHALATION 1

// Trial result code mapping.
#define HIT 1
#define CORRECT_REJECTION 2
#define MISS 3
#define FALSE_ALARM 4

//=======================
// Set the protocol name.
char protocolName[] = "Go_Nogo"; // should be less than 20 characters
//=======================

// Data structure to use for storing the parameters of a train of light pulses.
// Each pulse has the same square waveform.
struct pulse_train {
    uint8_t channel;
    unsigned int number_of_pulses;
    // this needs to be long to allow pulses longer than 33000 us
    unsigned long on_duration;
    unsigned long off_duration;
    unsigned int onset_delay;
    unsigned int offset_delay;
    unsigned int amplitude;
    unsigned short trigger_phase;
    // internal fields
    uint8_t train_timer;
    boolean timer_allocated;
    unsigned int trigger_iteration;
    // Store state of the pulse_train function. This can be used for signaling
    // to stop the pulses.
    boolean running;
};

// Data structure to store all the pulse trains. It has the pointer to the first
// pulse train and the number of active trains in the array. Note that the
// array can be made arbitrarily large by allocating enough memory to it.
// See init_trains() and change it to the desired size. Or dynamically change it
// via appropriate calls to malloc() and free().
struct pulse_trains {
    pulse_train *trains;
    uint8_t num_trains;
};

//==============================================================================
// Trial input parameters.
//==============================================================================
unsigned long trial_type = GO;
unsigned long water_duration = 60;
unsigned long final_valve_duration = 0;
unsigned long trial_duration = 2000;
unsigned long max_no_sniff_time = 0;
unsigned long lick_grace_period = 0;
unsigned long inter_trial_interval = 5000;
// Sniff phase for starting the final valve onset time.
unsigned long odorant_trigger_phase = EXHALATION;
unsigned long light_trigger_phase = INHALATION;
// This data structure stores the fields of a pulse train array. Each train
// and its parameters is read from the input parameters one by one.
pulse_trains pulse_train_array;

// Parameter to indicate whether the trial can be rewarded. Use for partial
// reinforcement. Currently unused and always set to 1.
unsigned int reward_on = 1;
// Water reward duration for the second water spout.
// Unused in this protocol as there is only one water reward zone.
unsigned long water_duration2 = 0;
// Light mask duration parameter. Currently not being sent with the other
// trial input parameters.
unsigned long light_mask_duration = 0;

// Initialize pulse_train_array as an empty structure of structures.
// This simply pre-allocates the memory needed for two pulse trains. There are
// two pulse generator channels on the behaviour board so we statically make
// the array size equal to two, but this behaviour can be modified dynamically.
void init_trains() {
    pulse_train_array.num_trains = 0;
    pulse_train_array.trains = (pulse_train*)malloc(2 * sizeof(pulse_train));
    return;
}

//==============================================================================
// Event to be transmitted back. These are the trial result variables.
//==============================================================================
unsigned long response = 0;
unsigned long parameters_received_time = 0;
unsigned long trial_start = 0;
unsigned long trial_end = 0;
unsigned long first_lick = 0;
unsigned long light_ON_time = 0;
unsigned long lost_sniff = 0;
unsigned long final_valve_onset = 0;
// Currently not sent with the result events.
unsigned long light_mask_ON_time = 0;

//===================
// Internal variables
//===================
// Counter for received parameters at the start of a trial.
short received_parameters = 0;
// Variables that hold the id of a defined timer for the masking LED.
// Currently not used.
uint8_t led_timer = 255;
// Flags used for internal states.
boolean trial_done_flag = false, send_last_packet = false;
boolean light_mask_ON = false;
// TODO: look at train structure and set running to false.
volatile bool stop_light = false;
// Internal variable to constantly check if sniff is lost.
boolean no_sniff = 0;

// State of the state machine.
int state = 0;
// The command code sent from the master (python).
int code = 0;
// Time in milliseconds of quiet, no licking behavior, to be enforced
// before delivery of the stimulus. This can be made a trial input parameter.
unsigned long quiescent_duration = 1000;
unsigned long quiescent_since = 0;

// Ideces to keep track when transmitting the sniffing data in the sniff buffer.
int last_sent_sniff_data_index = -1, current_sniff_data_index = 0;
// index to keep track of a specific value in the lick signals buffer.
uint16_t lick_buffer_index;

// Buffer to use for receiving special user-defined ASCII commands.
char user_command_buffer[128];
// Number of words (argument variables) in a user command line.
char *argument_words[8];
// Index to use when filling the user command buffer.
uint8_t user_command_buffer_index = 0;

// temporary variables used to keep track of time and time windows.
unsigned long time_now = 0;
long time_difference = 0;

void trig_train(uint8_t train_index) {
/*
 * Triggers a train of pulses given its index in the global pulse_train_array.
 *
 * This function will run iteratively and trigger a train of pulses based on
 * the parameters residing as fields in a pulse_train structure.
 * The parameter passed to the function is the index of this structure
 * in the array of trains stored inside "pulse_train_array".
 *
 * The function uses timers to set off each ON phase of the pulse.
 * It will store the iteration number in the trigger_iteration field of the
 * pulse_train that it is servicing, as it iterates through all the pulses.
 *
 * On the first iteration (train->trigger_iteration == 0) it allocates a timer
 * and starts it so that it calls back the same trig_train function after the
 * time value stored in the onset_delay field of the pulse_train has elapsed.
 *
 * Resolution is limited by the timer frequency (1ms).
 *
 * On subsequent iterations (1+), it calls the trigPulse function in the
 * ioFunctions library with the appropriate pulse channel, which is also stored
 * as a field in the pulse_train variable, and sets a timer to rerun itself
 * after the on_duration plus off_duration of the pulse. When the timer expires,
 * trig_train is called again and the subsequent iteration is processed.
 *
 * The pulse ON duration and amplitude should have already been notified to the
 * pulse generator as this functions only does the triggering. This can be
 * done when the trial parameters are received and before the trial starts.
 * The pulse generator hardware controls the actual pulse duration and
 * amplitude. This function controls the time of each pulse onset.
 *
 * When the last pulse is serviced, as found out by looking at the number
 * of pulses in the pulse_train, the function triggers a last pulse, and calls
 * itself one last time after train->on_duration of the pulse in order to free
 * the timer and set the train_iteration variable to 0.
 *
 */
    return;

    // Pointer to the pulse train variable in memory.
    pulse_train *train = &pulse_train_array.trains[train_index];

    // The internal state of the pulse train is set to stopped. Or the amplitude
    // of the pulse train is 0. Return without setting off any more pulses.
    if (!train->running || train->amplitude == 0) {
        // Free the timer if it is allocated.
        if (train->timer_allocated) {
            train->timer_allocated = false;
            freeTimer(train->train_timer);
        }
        // Make sure the iteration counter is reset to 0.
        train->trigger_iteration = 0;
        return;
    }

    // First iteration. No pulse is triggered in this iteration as we wait for
    // the onset_delay to elapse.
    if (train->trigger_iteration == 0) {
        // Allocate timer if it does not exist yet.
        if (!train->timer_allocated) {
            train->train_timer = allocateTimer();
            // Timer allocation failed as the timer list is already full.
            if (train->train_timer == 255) {
                Serial1.println("TIMER ERROR");
                return;
            }
            train->timer_allocated = true;
        }
        // Return to the same function to service the next iteration.
        startTimer(train->train_timer, train->onset_delay,
                   trig_train, train_index);
        train->trigger_iteration++;
    }
    // Iterations 2+ but before the last pulse iteration.
    else if (train->trigger_iteration < train->number_of_pulses) {
        // Trigger the pulse.
        trigPulse(train->channel);
        // Record the timestamp of the first pulse triggered.
        if (train->trigger_iteration == 1)
            light_ON_time = totalms;
        startTimer(train->train_timer, train->on_duration + train->off_duration,
                   trig_train, train_index);
        train->trigger_iteration++;
    }
    // Send last pulse if iteration is equal to the number of pulses.
    else if (train->trigger_iteration == train->number_of_pulses) {
        // Last pulse triggered.
        trigPulse(train->channel);
        // Set a timer for one more iteration after the pulse has finished
        // in order to reset the train fields.
        startTimer(train->train_timer, train->on_duration,
                   trig_train, train_index);
        train->trigger_iteration++;
    }
    // Last iteration. Timer is not reset but freed instead.
    else {
        // Reset the train fields and free the timer.
        train->trigger_iteration = 0;
        freeTimer(train->train_timer);
        train->timer_allocated = false;
        train->running = false;
    }
	return;
}

void find_light_stimulus_start(uint8_t train_index, unsigned short phase,
                               uint8_t phase_timer, boolean previous_phase) {
/*
 * Find the sniff phase edge required for triggering a light stimulus.
 *
 * Arguments:
 *     train_index: This is the index of the pulse train, which is wished to be
 *         triggered, in the global pulse_trains "pulse_train_array". This
 *         index will be passed on to the trig_train function as its argument.
 *     phase: The sniff signal phase, the onset of which will be detected.
 *     phase_timer: The timer index being used to call this function on a timer
 *         basis.
 *     previous_phase: The sniff signal phase prior to calling of this run of
 *         the function.
 *
 * This function checks every milliseconds for the sniff phase edge onset which
 * is passed as a parameter. Once this edge is detected in the sniff signal,
 * it calls the trig_train function, which services the pulse train defined
 * at the index given by train_index. It detects the edge by looking at the
 * sniff_trigger flag that is internal to the ioFunctions library. This flag
 * follows the phase of the analog sniff signal as it is acquired and
 * thresholded.
 *
 * If the phase parameter does not match a known phase, or if the trial
 * parameter "max_no_sniff_time" is set to 0, it is assumed that the phase does
 * not matter and the light stimulus is triggered immediately.
 *
 */

    boolean current_phase = sniff_trigger;

    // If the phase to trigger the light stimulus is neither inhalation, nor
    // exhalation, or if we are not paying attention to the sniff signal (the
    // special value of 0 in "max_no_sniff_time") then call the light
    // triggering function immediately.
    if ((max_no_sniff_time == 0) ||
            ((phase != INHALATION) && (phase != EXHALATION))) {
        freeTimer(phase_timer);
        trig_train(train_index);
    }
    // If the current sniff signal phase is different from the phase prior to
    // calling this function, then a phase change must have occurred.
    // Start the pulse train servicing timer if this corresponds to the edge
    // that is asked for in the "phase" parameter.
    else if (current_phase != previous_phase) {
        if ((!sniff_trigger && phase == INHALATION) ||
                (sniff_trigger && phase == EXHALATION)) {
            freeTimer(phase_timer);
            trig_train(train_index);
        }
    }
    // (re)start the timer and come check again for a phase change in 1 ms.
    //else
        //startTimer(phase_timer, 1, find_light_stimulus_start, 0);
    return;
}

void find_light_stimulus_start(uint8_t train_index, unsigned short phase) {
/*
 * Find the sniff phase edge required for triggering a light stimulus.
 *
 * Arguments:
 *     train_index: This is the index of the pulse train, which is wished to be
 *         triggered, in the global pulse_trains "pulse_train_array". This
 *         index will be passed on to the trig_train function as its argument.
 *     phase: The sniff signal phase, the onset of which will be detected.
 *
 * This function sets up a timer, and calls an overloaded function of the same
 * name that includes that timer as a parameter. It is that function that will
 * call trig_train after the sniff signal edge is detected.
 *
 */

    uint8_t phase_timer;
    phase_timer = allocateTimer();
    // Timer allocation failed as the timer list is already full.
    if (phase_timer == 255) {
        Serial1.println("TIMER ERROR");
        return;
    }

    // Pointer to the pulse train variable in memory.
    pulse_train *train = &pulse_train_array.trains[train_index];
    train->trigger_phase = phase;

//    train->train_timer

    // Call an overloaded function with the extra parameters of the phase timer
    // and the current phase of the sniff signal.
    // sniff_trigger is an internal flag, found in the ioFunctions library,
    // and used to store the currently sampled sniff signal state.
    //find_light_stimulus_start(train_index, phase_timer, sniff_trigger);
}

// Trigger masking LED
void trigMask(uint8_t mask) {
	light_mask_ON = true;
	light_mask_ON_time = totalms;
	cueOnTimer(LEDMASK,light_mask_duration);
	digitalWrite(LEDMASK_T,HIGH);
	// Free the timer if this function was a timer callback.
	//freeTimer(led_timer);
}


void setup() {
	pinMode(LED_PIN, OUTPUT); // Green LED on the front
	pinMode(TRIGGER1, OUTPUT); // Pulse generator ch. 1 trigger
	pinMode(TRIGGER2, OUTPUT); // Pulse generator ch. 2 trigger
	pinMode(SOLENOID1, OUTPUT);
	pinMode(SOLENOID2, OUTPUT);
	pinMode(SOLENOID3, OUTPUT);
	pinMode(SOLENOID4, OUTPUT);
	pinMode(SOLENOID5, OUTPUT);
	pinMode(SOLENOID6, OUTPUT);
	pinMode(SOLENOID7, OUTPUT);
	pinMode(SOLENOID8, OUTPUT);
	pinMode(DIGITAL1,OUTPUT);
	pinMode(DIGITAL2,OUTPUT);
	pinMode(DIGITAL3,OUTPUT);
	pinMode(DIGITAL4,OUTPUT);
	pinMode(DIGITAL5,OUTPUT);
	pinMode(DIGITAL6,OUTPUT);
	pinMode(DIGITAL7,OUTPUT);
	pinMode(DIGITAL8,OUTPUT);
	pinMode(DIGITAL9,OUTPUT);
	pinMode(DIGITAL10,OUTPUT);
	pinMode(DIGITAL11,OUTPUT);
	pinMode(DIGITAL12,OUTPUT);
	pinMode(CUE1, OUTPUT);
	pinMode(CUE2, OUTPUT);
	pinMode(CUE3, OUTPUT);
	pinMode(CUE4, OUTPUT);
	pinMode(CUE5, OUTPUT);
	pinMode(CUE6, OUTPUT);
	pinMode(CUE7, OUTPUT);
	pinMode(CUE8, OUTPUT);
	pinMode(ADC_PIN, OUTPUT);
	pinMode(DAC1_PIN, OUTPUT);
	pinMode(DAC2_PIN, OUTPUT);
	pinMode(TEENSY_PIN, OUTPUT);

	digitalWrite(LED_PIN, LOW);
	digitalWrite(TRIGGER1, LOW);
	digitalWrite(TRIGGER2, LOW);
	digitalWrite(SOLENOID1, LOW);
	digitalWrite(SOLENOID2, LOW);
	digitalWrite(SOLENOID3, LOW);
	digitalWrite(SOLENOID4, LOW);
	digitalWrite(SOLENOID5, LOW);
	digitalWrite(SOLENOID6, LOW);
	digitalWrite(SOLENOID7, LOW);
	digitalWrite(SOLENOID8, LOW);
	//digitalWrite(DIGITAL1,LOW);
	digitalWrite(DIGITAL2,LOW);
	digitalWrite(DIGITAL3,LOW);
	digitalWrite(DIGITAL4,LOW);
	digitalWrite(DIGITAL5,LOW);
	digitalWrite(DIGITAL6,LOW);
	digitalWrite(DIGITAL7,LOW);
	digitalWrite(DIGITAL8,LOW);
	digitalWrite(DIGITAL9,LOW);
	digitalWrite(DIGITAL10,LOW);

	digitalWrite(DIGITAL12,LOW);
	digitalWrite(CUE1, LOW);
	digitalWrite(CUE2, LOW);
	digitalWrite(CUE3, LOW);
	digitalWrite(CUE4, LOW);
	digitalWrite(CUE5, LOW);
	digitalWrite(CUE6, LOW);
	digitalWrite(CUE7, LOW);
	digitalWrite(CUE8, LOW);
	digitalWrite(LED_PIN, LOW);
	digitalWrite(ADC_PIN, HIGH);
	digitalWrite(DAC1_PIN, HIGH);
	digitalWrite(DAC2_PIN, HIGH);
	digitalWrite(TEENSY_PIN, HIGH);
	digitalWrite(LEDMASK, HIGH);


	//=======================
	// prep ANALOG inputs
	analogReference(DEFAULT);
	//=======================

	//=======================
	// prep SPI for AD control
	startSPI();
	//=======================

	//=======================
	// initialize the SERIAL communication
	Serial.begin(115200);
	//  Serial.println("* Monitor System ready *");
	//=======================

	//=======================
	// initialize SERIAL for LCD
	Serial1.begin(19200);
	Serial1.write(0x0c); // clear the display
	delay(10);
	Serial1.write(0x11); // Back-light on
	Serial1.write(0x80); // col 0, row 0
	Serial1.print("GoNogo_ec");
	//    Serial1.print(0x94, BYTE); // col 0, row 0
	//    Serial1.print("MODE 0");
	//=======================

	// Pulse generator communication
	Serial2.begin(115200);
	setupVoyeurTimer(); //setup and start ms timer (From: voyeur_timer_lib.pde) (THIS DEFINES TOTALMS).

	// setup buffer sizes
	setupBuffers(400,1,20,50);  //(unsigned int sniffbuff, unsigned int treadmillbuff, unsigned int lickbuff, unsigned int trigbuff)

	// recording of both sniff and velocity
	// first two args are analog channels' pins, 3rd arg indicates which channels are on (3=both)
	setupAnalog(0,1,1);

	// start analog acquisition
	start_analog_timer(); //(ioFunctions).
	// start lick recording timer.
	// first arg. is the beam break pin, second is the 	start_analog_timer(); //(ioFunctions).ait. 0 = every ms
	startLick(BEAM1,BEAM2);
	lickOn(1, 0);
	recordsniffttl = true;

	// Init done
	init_trains();
	digitalWrite(LED_PIN, HIGH);
}

//===================================================================================================
void loop() {  //BREAKS TO HERE

	//===================================================================================================
	//================ State machine goes here===========================================================
	// check sniffing for lost sniff
	time_now = totalms; //copy this to register from volatile.

	time_difference = time_now-lastsnifftime;
	if((time_difference > 0) && (max_no_sniff_time > 0) && time_difference<10000) {
		if(time_difference > max_no_sniff_time) {
			no_sniff = 1;
			//digitalWrite(DIGITAL2,HIGH);
		}
		else {
			no_sniff = 0;
		}

		//digitalWrite(DIGITAL2,LOW);
	}

	// sniff lost forced trial stop
	if(max_no_sniff_time > 0 && state > 0 && no_sniff > 0 ){
		state = 8;
		if (trial_start = 0) {
			trial_start = time_now;
		}
		lost_sniff = no_sniff;
	}


	switch (state) {

	case 0: //waiting for initialization of trial
		break;

	case 1:
		// Python has uploaded the trial parameters to start a trial.
		// Wait for ITI to be over and wait for 1 second of lick free time before starting the trial.
		quiescent_since = totalms-quiescent_duration;

		if (((totalms-trial_end) > inter_trial_interval) && !(haslicked(1,quiescent_since))){
			state = 2;
			trial_start = totalms;
		}
		break;

	case 2: // wait for inhalation state so that you know that the next threshold crossing is the start of exhalation.
		if (haslicked(1,quiescent_since)){ //check for lick, if you've licked, you have to do the whole thing over or sniff threshold waiting gets messed up.
			state = 1;
			break;
		}

		if(!sniff_trigger || max_no_sniff_time == 0){
			state = 3;
		}


	case 3:
		//Wait for exhalation state.
		// turn valve on if final_valve_duration is greater than zero. Do not start timer - timer start with inhalation onset.
		// initialize trig_train if it is triggered on inhalation onset. trig_train will start checking for inhalation onset every 1 ms.
		if (haslicked(1,quiescent_since)){ //check for lick, if you've licked, you have to do the whole thing over or sniff threshold waiting gets messed up.
			state = 1;
			break;
		}
		if(sniff_trigger || max_no_sniff_time == 0) {
			//digitalWrite(STARTTRIAL,HIGH);
			valveOnTimer(FINALVALVE,final_valve_duration); ///opens valve but does NOT start timer. Timer is started in case 2.
			final_valve_onset = totalms;
			digitalWrite(FV_T,HIGH);

			if (light_mask_duration > 0) {
				digitalWrite(LEDMASK,LOW);
				digitalWrite(LEDMASK_T,LOW);
				light_mask_ON = true;
				light_mask_ON_time = totalms;
			}

			if(light_trigger_phase == INHALATION && pulse_train_array.num_trains > 0) {
			    // TODO: look at train structure and set running to false.
				stop_light = false;
				for(int i=0; i<pulse_train_array.num_trains; i++) {
					trig_train(i); // run trig_train, which will now start monitoring the sniff for the next threshold cross to inhale.

				}
			}
			state = 4;
		}

		break;

	case 4:  // wait for inhalation onset
		// inhalation onset
		// trig_train is already checking for inhalation onset to trigger lasers.
		if(!sniff_trigger || max_no_sniff_time == 0) {
			if(final_valve_duration > 0)
//				valveOnTimer(FINALVALVE,final_valve_duration); //valve is already high from state 1, start timer on inhale
//			}
			state = 5;
		}
		break;

	case 5: // grace period.
		//changed by cw - grace period is relative to inh_onset not firststim - this makes S+ and S- trials' grace periods symmetrical.
		if(totalms >= final_valve_onset + lick_grace_period) {
			lick_buffer_index = getLickstart(1);
			if(trial_type == GO)
				state = 6;
			else if(trial_type == NOGO)
				state = 7;
		}

		if(((totalms-final_valve_onset) > light_mask_duration) && light_mask_ON) { // turn mask off if it is on.
			digitalWrite(LEDMASK,HIGH);
			digitalWrite(LEDMASK_T,HIGH);
			light_mask_ON = false;
		}

		break;

	case 6:  // GO Trial

		if(hasLicked(1, lick_buffer_index)) { // lick has occured
			if(first_lick == 0)
				first_lick = totalms;
			response = 1; // A HIT
			if(reward_on){ //enables partial reinforcement: only reward if flag is 1
				valveOnTimer(WATERVALVE1,water_duration);
			}

			state = 8;
		}
		else if((totalms-trial_start) >= trial_duration) {
			response = 3; // A MISS
			state = 8;
		}
		if(((totalms-final_valve_onset) > light_mask_duration) && light_mask_ON) {
			digitalWrite(LEDMASK,HIGH);
			digitalWrite(LEDMASK_T,HIGH);
			light_mask_ON = false;
		}
		break;

	case 7:  //No-Go Trial

		if(hasLicked(1, lick_buffer_index)) {
			if(first_lick == 0)
				first_lick = totalms;
			response = 4; // A FALSE ALARM
			state = 8;
			break;
		}
		else if((totalms-trial_start) >= trial_duration) {
			response = 2; // A CORRECT REJECTION
			state = 8;
			break;
		}
		if(((totalms-final_valve_onset) > light_mask_duration) && light_mask_ON) { // turn mask off if it is on.
			digitalWrite(LEDMASK,HIGH);
			digitalWrite(LEDMASK_T,HIGH);
			light_mask_ON = false;
		}
		break;

	case 8:  // shut everything down.
		
                trial_end = totalms;
                // TODO: look at train structure and set running to false.
                stop_light = true;
		//digitalWrite(STARTTRIAL,LOW);
		if(light_mask_ON) {
			digitalWrite(LEDMASK,HIGH);
			digitalWrite(LEDMASK_T,HIGH);
			light_mask_ON = false;
		}

		if(final_valve_duration == 0) {
			valveOff(FINALVALVE);
			digitalWrite(FV_T,LOW);
		}
		digitalWrite(FV_T,LOW);
		trial_done_flag = true;
		inter_trial_interval = 0;
		state = 0;
		break;
	}
	//===================================================================================================
	// CHECK SERIAL PORT
	//===================================================================================================


	if (Serial.available() > 0) {

		code = Serial.read();

		switch (code) {
		case 89: // stop execution
			state = 0;
			Serial.print(3);
			Serial.print(",");
			Serial.print("*");
			break;

			// all other codes are handshaking codes either requesting data or sending data
		case 87:
			RunSerialCom(code);
			break;

		case 88:
			RunSerialCom(code);
			break;

		case 86:
			RunSerialCom(code);
			break;

		case 90:
			RunSerialCom(code);
			if(odorant_trigger_phase == EXHALATION)
				state = 1;
			else
				state = 1;
			parameters_received_time = totalms;
			first_lick = 0;
			trial_start = lost_sniff = 0;
			light_ON_time = 0;
			final_valve_onset = 0;
			quiescent_since = 0;
			if (pulse_train_array.num_trains > 0) {
				int i;
				i = 0;
				setPulse((uint8_t)pulse_train_array.trains[i].channel, pulse_train_array.trains[i].on_duration, (uint16_t)pulse_train_array.trains[i].amplitude);
				if (pulse_train_array.num_trains > 1) {
					i = 1;
					setPulse((uint8_t)pulse_train_array.trains[i].channel, pulse_train_array.trains[i].on_duration, (uint16_t)pulse_train_array.trains[i].amplitude, false);
				}
			}
                        //Serial1.print(trial_duration);
			break;

		case 91:
			RunSerialCom(code);
			break;

		case 92:
			digitalWrite(SOLENOID1, HIGH);
			delay(5000);
			digitalWrite(SOLENOID1, LOW);
			break;
		}
	}
}

