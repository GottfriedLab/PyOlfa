// Created on 2015-04-20
// @author: Admir Resulaj
/*
 * This is an Arduino protocol implementing a behavioral Go/NoGo paradigm for
 * an olfactory task.
 */


// include the library code:
#include <SPI.h>
#include <C:\git\Voyeur\Arduino libraries\voyeur_timer_lib.pde>
#include <C:\git\Voyeur\Arduino libraries\ioFunctions_external_timers.pde>
#include <C:\git\Voyeur\Arduino libraries\voyeur_serial_stream_tools.pde>

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
#define CLEARVALVE SOLENOID1
#define WATERVALVE1 SOLENOID2
#define WATERVALVE2 SOLENOID8
#define FINALVALVE SOLENOID3
#define FV_T DIGITAL8

// Masking blue light LED control channel.
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
	unsigned int num_pulses;
	// this needs to be long to allow pulses longer than 33000 us
	unsigned long on_duration;
	unsigned int off_duration;
	unsigned int onset_delay;
	unsigned int offset_delay;
	unsigned int amplitude;
	// internal fields
	uint8_t train_timer;
	boolean timer_allocation;
	unsigned int trigger_iteration;
	bool trig_wait_exhale;
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

// Initializes pulse_train_array as an empty structure of structures.
// This simply pre-allocates the memory needed for two pulse trains. There are
// two pulse generator channels on the behaviour board so we statically make
// this two, but this behaviour can be modified dynamically.
void init_trains() {
	pulse_train_array.num_trains = 0;
	pulse_train_array.trains = (pulse_train*)malloc(2*sizeof(pulse_train));
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

//===================
// Internal variables
//===================
// Counter for received parameters at the start of a trial.
short received_parameters = 0;
// Variables that hold the index of a defined timer.
uint8_t laser_routine_timer = 255, led_timer = 255;
// index to keep track of a specific value in the buffer of lick signals.
uint16_t lick_buffer_index;
// Flags to use for internal states.
boolean trial_done_flag = false, send_last_packet = false;
boolean light_mask_ON = false;
volatile bool stop_light = false;


// state of the state machine and command code sent from the master.
int state = 0, code = 0;
// Time in milliseconds of quiet, no licking behavior, to be enforced
// before delivery of the stimulus. This can be made a trial input parameter.
unsigned long quiescent_duration = 1000;
unsigned long quiescent_since = 0;

unsigned long mask_dur = 500;
unsigned long maskontime = 0;
int last_sniffndx = -1, cur_sniffndx = 0, trig_laser_multi_sniff = 0;
unsigned long ledMask = 0;
unsigned long nextpulsedelay = 0;
unsigned long no_sniff=0;

// buffer to use for receiving special ASCII commands.
char buffer[128];
// Number of words in a command line.
char *argv[8];
uint8_t idx = 0;  // Index to use when filling the receive command buffer.

// temporary variables
unsigned long time_now = 0;
long time_difference = 0;

void trigTrain(uint8_t train_index) { //call this to start a pulse train.
	// this routine will run iteratively to trigger a pulse train based on the parameters residing in a pulse_train structure within the pulse_train_array structure of structures.
	// on the first iteration (0), it allocates a timer and starts that timer for the duration of the onset_delay parameter. After that latency, the timer recalls trigTrain.
	// on subsequent iterations (1+), the function calls the trigPulse function (ioFunctions) for the channel and sets a timer to run the function again after the on_duration plus off_duration.
	// pulse length and amplitude is set in the pulse generator when the trial parameters are recieved. The pulse generator controls the on_duration timer (length of the pulse), so we don't have to turn the laser off.
	// We don't have to turn the laser off, we just have to send another pulse to the pulsegen when the next laser should begin.
	// If the iteration counter is equal to the defined number of pulses requested, the function sends the last pulse to the pulsegen, frees the timer, and sets the iteration counter to 0.
	// FOR THIS TO RUN PROPERLY, THE PULSE PARAMETERS (AMP & DUR) MUST BE UPLOADED TO THE PULSEGEN PREVIOUSLY. THIS ONLY CONTROLS THE FREQUENCY OF THE INITIATION FOR THESE PULSES.

	pulse_train *train = &pulse_train_array.trains[train_index];  //makes a pointer of to the pulse train address of the memory size allocated for a pulse_train element based on the index input to the function.

	if(train->trigger_iteration == 0) {
		// wait for onset time first
		//digitalWrite(train->channel,LOW); // make  sure the pulse is low

		if(!train->timer_allocation) {
			train->train_timer = allocateTimer();
			train->timer_allocation = true;

			if(train->train_timer == 255) {
				Serial1.println("TIMER ERROR");
				return;
			}
			else{
				startTimer(train->train_timer, 1, trigTrain, train_index);



				return;
			}
		}

		if (train->trig_wait_exhale) { // if we're waiting for an exhale before we start an inhale:
			if (stop_light) { // if the state machine sets stop_light to true (ie the mouse has already answered and the trial is complete, set trig_wait_exhale to false, free the timer, and return.
				train->trig_wait_exhale = false;
				freeTimer(train->train_timer);
				train->timer_allocation = false;
				return;
			}
			else if (sniff_trigger) { // if there's an exhale,, we stop waiting and start looking for the start of inhale.
				train->trig_wait_exhale = false;
				startTimer(train->train_timer, 1, trigTrain, train_index);
				return;
			}
			else { // or we just keep waiting and looking for the start of exhale every 1 ms.
				startTimer(train->train_timer, 1, trigTrain, train_index);
				return;
			}
		}

		else if ((!sniff_trigger && light_trigger_phase == INHALATION) || max_no_sniff_time == 0 ||
				(sniff_trigger && light_trigger_phase == EXHALATION)) {
			startTimer(train->train_timer, train->onset_delay, trigTrain, train_index);
			train->trigger_iteration++;
			if (light_ON_time == 0 && train->amplitude != 0){
				light_ON_time = totalms+train->onset_delay;
			}
			return;
		}
		else { //wait for inhale or exhale to start, check every ms.
			startTimer(train->train_timer, 1, trigTrain, train_index);
			return;
		}
	}


	else if (train->trigger_iteration < train->num_pulses){
		trigPulse(train->channel);
		startTimer(train->train_timer,train->off_duration,trigTrain, train_index); // off_duration is already calculated to include the pulse time when the parameters are read.
		//Serial1.print(train->trigger_iteration);
		train->trigger_iteration++;
		return;
	}

	else if (train->trigger_iteration == train->num_pulses) { // pulse it for the final iteration and end the routine and free the timer and reset the timer iteration to 0.
		trigPulse(train->channel);
		train->trigger_iteration = 0;
		// if the protocol wants the trigger to initiate pulses for multiple sniffs, wait for the next exhale by calling trigtrain
		if (trig_laser_multi_sniff) {
			train->trig_wait_exhale = true;
			startTimer(train->train_timer, 1, trigTrain, train_index);
		}
		else {
			freeTimer(train->train_timer);
			train->timer_allocation = false;
		}
		return;
	}

	else { //just in case the above conditions aren't met, reset the timer and set the trigger iterator.
		train->trigger_iteration = 0;  // reset the iterations to indicate to the begin of train pulse triggers
		freeTimer(train->train_timer);
		train->timer_allocation = false;
		return;
	}


	return;
}


// Trigger masking LED
void trigMask(uint8_t mask) {
	light_mask_ON = true;
	maskontime = totalms;
	cueOnTimer(LEDMASK,mask_dur);
	digitalWrite(LEDMASK_T,HIGH);
	freeTimer(led_timer);
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
		// initialize trigTrain if it is triggered on inhalation onset. trigTrain will start checking for inhalation onset every 1 ms.
		if (haslicked(1,quiescent_since)){ //check for lick, if you've licked, you have to do the whole thing over or sniff threshold waiting gets messed up.
			state = 1;
			break;
		}
		if(sniff_trigger || max_no_sniff_time == 0) {
			//digitalWrite(STARTTRIAL,HIGH);
			valveOnTimer(FINALVALVE,final_valve_duration); ///opens valve but does NOT start timer. Timer is started in case 2.
			final_valve_onset = totalms;
			digitalWrite(FV_T,HIGH);

			if (mask_dur > 0) {
				digitalWrite(LEDMASK,LOW);
				digitalWrite(LEDMASK_T,LOW);
				light_mask_ON = true;
				maskontime = totalms;
			}

			if(light_trigger_phase == INHALATION && pulse_train_array.num_trains > 0) {
				stop_light = false;
				for(int i=0; i<pulse_train_array.num_trains; i++) {
					pulse_train_array.trains[i].trig_wait_exhale = false;
					trigTrain(i); // run trigTrain, which will now start monitoring the sniff for the next threshold cross to inhale.

				}
			}
			state = 4;
		}

		break;

	case 4:  // wait for inhalation onset
		// inhalation onset
		// trigTrain is already checking for inhalation onset to trigger lasers.
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

		if(((totalms-final_valve_onset) > mask_dur) && light_mask_ON) { // turn mask off if it is on.
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
			if(reward_on == 1){ //enables partial reinforcement: only reward if flag is 1
				valveOnTimer(WATERVALVE1,water_duration);
			}

			state = 8;
		}
		else if((totalms-trial_start) >= trial_duration) {
			response = 3; // A MISS
			state = 8;
		}
		if(((totalms-final_valve_onset) > mask_dur) && light_mask_ON) {
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
		if(((totalms-final_valve_onset) > mask_dur) && light_mask_ON) { // turn mask off if it is on.
			digitalWrite(LEDMASK,HIGH);
			digitalWrite(LEDMASK_T,HIGH);
			light_mask_ON = false;
		}
		break;

	case 8:  // shut everything down.
		
                trial_end = totalms;
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

