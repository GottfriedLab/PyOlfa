// Created on 2015-08-04
// @author: Admir Resulaj
/*
 * This is an Arduino protocol implementing a passive odorant exposure
 * paradigm for an olfactory experiment.
 */


// include the library code:
#include <SPI.h>
#include <C:\Users\SAM-PC\Documents\Arduino\voyeur_timer_lib.pde>
#include <C:\Users\SAM-PC\Documents\Arduino\ioFunctions_external_timers.pde>
#include <C:\Users\SAM-PC\Documents\Arduino\voyeur_serial_stream_tools.pde>

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
#define WATERVALVE1 SOLENOID8
#define WATERVALVE2 SOLENOID5
#define FV_T DIGITAL5
#define LICK_SENSOR DIGITAL8


// Phases of the sniff signal and the codes for each phases.
#define INHALATION 0
#define EXHALATION 1
#define PHASE_INDEPENDENT 2

//=======================
// Set the protocol name.
char protocolName[] = "Passive_exposure"; // should be less than 20 characters
//=======================

//==============================================================================
// Trial input parameters.
//==============================================================================
unsigned long final_valve_duration = 0;
unsigned long trial_duration = 2000;
unsigned long inter_trial_interval = 5000;
// Sniff phase for starting the final valve onset time.
unsigned long odorant_trigger_phase = EXHALATION;
unsigned long max_no_sniff_time = 0;

// Parameter to indicate whether the trial can be rewarded. Use for partial
// reinforcement. Currently unused and always set to 1.
unsigned int reward_on = 1;

// Water reward durations in milliseconds. Not used in this particular paradigm.
unsigned long water_duration = 65;
unsigned long water_duration2 = 65;


//==============================================================================
// Event to be transmitted back. These are the trial result variables.
//==============================================================================
unsigned long parameters_received_time = 0;
unsigned long trial_start = 0;
unsigned long trial_end = 0;
unsigned long lost_sniff = 0;
unsigned long final_valve_onset = 0;

//===================
// Internal variables
//===================
// Counter for received parameters at the start of a trial.
short received_parameters = 0;
// Flags used for internal states.
boolean trial_done_flag = false, send_last_packet = false;
// Internal variable to constantly check if sniff is lost.
boolean no_sniff = 0;

// State of the state machine.
int state = 0;
// The command code sent from the master (python).
int code = 0;

// Indices to keep track when transmitting the sniffing data in the sniff buffer
int last_sent_sniff_data_index = -1, current_sniff_data_index = 0;

// Buffer to use for receiving special user-defined ASCII commands.
char user_command_buffer[128];
// Number of words (argument variables) in a user command line.
char *argument_words[8];
// Index to use when filling the user command buffer.
uint8_t user_command_buffer_index = 0;

// temporary variables used to keep track of time and time windows.
unsigned long time_now = 0;
long time_difference = 0;

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
	//pinMode(DIGITAL9,OUTPUT);
	pinMode(LICK_SENSOR,INPUT);
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
	digitalWrite(DIGITAL1,LOW);
	digitalWrite(DIGITAL2,LOW);
	digitalWrite(DIGITAL3,LOW);
	digitalWrite(DIGITAL4,LOW);
	digitalWrite(DIGITAL5,LOW);
	digitalWrite(DIGITAL6,LOW);
	digitalWrite(DIGITAL7,LOW);
	digitalWrite(DIGITAL8,LOW);
	//digitalWrite(DIGITAL9,LOW);
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
	Serial1.print("Passive exposure");
	//    Serial1.print(0x94, BYTE); // col 0, row 0
	//    Serial1.print("MODE 0");
	//=======================

	// Pulse generator communication
	Serial2.begin(115200);
	// Setup and start ms timer from: voyeur_timer_lib.pde .
	// This defines totalms.
	setupVoyeurTimer();

	// setup buffer sizes
	//(unsigned int sniffbuff, unsigned int treadmillbuff, unsigned int lickbuff, unsigned int trigbuff)
	setupBuffers(400,1,20,50);

	// Recording of sniff
  // The first two arguments define the two analog pins that we are recording from: 0 = AIN1, 1=AIN2
  // The third argument indicates which channel to actually record data from: 1 = first channel, 2 = second channel, 3 = both
	setupAnalog(0,1,1);

	// start analog acquisition. Every millisecond go and fetch a value from the sniff sensor into the sniff buffer.
	start_analog_timer(); //(ioFunctions).
	// start lick recording timer. Creates a buffer to store the lick event timestamps and defines which pin to sample from.
  // Argument 1 is channel 1 (first lick port), argument 2 is channel 2 (if you are using 2 licking sensors).
	startLick(LICK_SENSOR_MRI,BEAM2);
	// first argument is how many channels to look for licking. 1 = only first channel. 2 = both.
  // function is found at ioFunctions.pde . Second argument is the inter sample interval 0 = every ms
	lickOn(3, 0);
	recordsniffttl = true;

	// Init done
	digitalWrite(LED_PIN, HIGH);
}

//==============================================================================
void loop() {

    //==========================================================================
    //                       State machine goes here
    //==========================================================================
    // check sniffing for lost sniff
    //copy this to register from volatile.
    time_now = totalms;

	time_difference = time_now-lastsnifftime;
	if((time_difference > 0) && (max_no_sniff_time > 0) && time_difference<10000) {
		if(time_difference > max_no_sniff_time) {
			no_sniff = 1;
		}
		else {
			no_sniff = 0;
		}
	}

	// sniff lost forced trial stop
	if(max_no_sniff_time > 0 && state > 0 && no_sniff > 0 ){
		state = 7;
		if (trial_start = 0) {
			trial_start = time_now;
		}
		lost_sniff = no_sniff;
	}

	// Trial period is over.
	if ((state > 0) && (totalms-trial_start >= trial_duration)) {
	            state = 7;
	}

	switch (state) {

	case 0: //waiting for initialization of trial
		break;

	case 1:
		// Python has uploaded the trial parameters to start a trial.
		// Wait for ITI to be over and wait for 1 second of lick free time before starting the trial.

		if ((totalms-trial_end) > inter_trial_interval) {
		    trial_start = totalms;
			if (odorant_trigger_phase == PHASE_INDEPENDENT)
			    // Final valve trigger state
			    state = 6;
			else if (odorant_trigger_phase == EXHALATION)
			    state = 2;
			else if (odorant_trigger_phase == INHALATION)
			    state = 4;
		}
		break;

	case 2: // Wait for inhalation state.

	    if(!sniff_trigger || max_no_sniff_time == 0){
            state = 3;
        }
	    break;

	case 3: // Find exhalation state so that the stimulus can be triggered.

	    if(sniff_trigger || max_no_sniff_time == 0){
            state = 6;
        }
	    break;

	case 4: // Wait for exhalation state

	    if(sniff_trigger || max_no_sniff_time == 0){
	                state = 5;
	    }
	    break;

	case 5: // Find inhalation state so that the stimulus can be triggered.

	    if(!sniff_trigger || max_no_sniff_time == 0){
	        state = 6;
	    }
	    break;

	case 6: // Trigger stimulus state.

	    // open final valve
	    valveOnTimer(FINALVALVE, final_valve_duration);
	    valveOnTimer(FV_T, final_valve_duration);
        final_valve_onset = totalms;
        digitalWrite(FV_T,HIGH);
	    break;

	case 7:  // shut everything down.
        trial_end = totalms;
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


	//==========================================================================
	// CHECK SERIAL PORT
	//==========================================================================


	if (Serial.available() > 0) {

		code = Serial.read();

		switch (code) {
		case 89: // stop execution. 89 = 'Y'
			state = 0;
			Serial.print(3);
			Serial.print(",");
			Serial.print("*");
			break;

			// all other codes are handshaking codes either requesting data or sending data
		case 87:  // Streaming packet was requested. Send all the streaming data.
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
			parameters_received_time = totalms;
			trial_start = lost_sniff = 0;
			final_valve_onset = 0;
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

