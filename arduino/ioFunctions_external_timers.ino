#ifndef IOFUNCTIONS
#define IOFUNCTIONS
// 2013_06_05 CW - made a CueLowOnTimer for LED mask

// Functions that handle comm. with I/O devices
#include <C:\Users\Jay Gottfried\Documents\GitHub\Mod_Voyeur\arduino\ADfunctions.pde>
// Analog input ring buffer parameters
#define BUFFERS 500 //buffer size
#define LICKBUFF 100 // lick buffer
#define TRIGBUFF 20  // trigger buffer for signal (e.g sniff) threshold crossings

#define MAXCUES 16
#define TRIGGER1   4
#define TRIGGER2   5
#define TRIGGER3   6
#define DIGITAL5  66
#define DIGITAL6  67
#define SNIFF_T DIGITAL6

#define DIGITAL3  64
#define DIGITAL4  65

#define LEFT 0
#define RIGHT 1

// event parameters
int *sniff, *treadmill;
// the lick signal is a collection of timestamps for when the beam break changes state
unsigned long *lick, *lick2, *trig;  //*lick is lick buffer (a ring buffer)

const int blocksize = 100; //block size to send
boolean recordsniff = false, recordspeed = false, clockflag = false, recordsniffttl = false, trig_move = false;//flags signaling analog acquisition
volatile bool sniff_trigger = false;
unsigned int moved_side = 10;  // records movement side when trig_move is ON
int sniff_t_inh = -16;// threshold crossing value for inhalation in ADC units. Roughly -40mV. (-5000:5000)
int sniff_t_exh = 10; // threshold crossing value for start of exhalation. Wanted this to be above the 0 value so that it is actually indicative of positive pressure.
unsigned int treadmill_t = 20/(5000.0/2047);
volatile unsigned long lastsnifftime = 0;  // last time the sniff signal crossed threshold 

// lick buffer is a ring buffer with head, tail and it stores timestamps of state changes in the beam
volatile bool beamstatus = false, beam2status = false;
bool lickflag = false, lick2flag = false;
volatile int lickhead = 0, licktail = 0, lick2head = 0, lick2tail = 0;
volatile unsigned int trighead = 0, trigtail = 0;

unsigned int blockstart;
volatile int currentvalue = -1;
unsigned int blockend = blockstart+blocksize-1;
int sniffvalue, speedvalue; // analog in values
unsigned long bufftimes = 0; // times the buffer was full since start
unsigned long last_movement = 0;
unsigned int sniffb, lickb, treadmillb, trigb;

/* Cue timer arrays */
// array holding timers initialized to 255 (unavailable timer)
uint8_t cueTimers[] = {255,255,255,255,255,255,255,255,255,255,255,255,255,255,255,255};
uint8_t cuePins[MAXCUES];
uint8_t cueFree[] = {1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1};
bool pinIsOff = true;

// analog interrupt timer
uint8_t analogtimer = 0, licktimer = 255;
// adc pins for the analog channels 
uint8_t sniffin, speedin;
// beam break pin
uint8_t beampin, beam2pin;
// analog/digital constants
int dac2_const = 16;
float adc_const = 5000.0/2047;

// setup analog acquisition channels
// arguments are the adc pins to be used and which channels to record from
void setupAnalog(uint8_t sniffpin, uint8_t speedpin, uint8_t channels) {
  // adc pins for each channel
  sniffin = sniffpin;
  speedin = speedpin;
  // enable analog recording flags
  // 1 for sniff, 2 for treadmill velocity, 3 for both
  switch (channels) {
    case 0: recordsniff = recordspeed = false; break;
    case 1: recordsniff = true; break;
    case 2: recordspeed = true; break;
    case 3: recordsniff = recordspeed = true; break;
  } 
}

void setupBuffers(unsigned int sniffbuff, unsigned int treadmillbuff, unsigned int lickbuff, unsigned int trigbuff) {
  
  // Since lickbuffer is an array of timestamp of two possible states (ON/OFF) force the length divisible by two
  // This way, if there is a buffer overflow, the signal is not desynced.
  if(lickbuff%2 > 0)
    lickbuff--;

  sniff = (int *)malloc(sniffbuff * sizeof(int));
  treadmill = (int *)malloc(treadmillbuff * sizeof(int));
  lick = (unsigned long *)malloc(lickbuff * sizeof(unsigned long));
  lick2 = (unsigned long *)malloc(lickbuff * sizeof(unsigned long));
  trig = (unsigned long *)malloc(trigbuff * sizeof(unsigned long));

  trig[trighead++] = totalms; // first state of the trigger signal is set to low
  
  sniffb = sniffbuff;
  treadmillb = treadmillbuff;
  lickb = lickbuff;
  trigb = trigbuff;
  
 // #define BUFFERS sniffb
 // #define TMBUFF treadmillb
//  #define LICKBUFF lickb
 // #define TRIGBUFF trigb
}


//interrup handling routine for analog acquisition
void ain(uint8_t arg) {
  // only read values if the flag is set
  if(clockflag) {
    // restart interrupt timer so we come back in the next ms
    startTimer(analogtimer, 0, ain, 0);
    int current_ind = currentvalue; //make this local so that we don't have to go back to memory every time we need it.
    current_ind = (current_ind+1)%BUFFERS; // nextvalue index in the buffers
    //to do: if(currentvalue == blockstart) warn about buffer overflow  
    currentvalue = current_ind; //write back changed value from register to volatile.
    unsigned long t_ms = totalms; //cache this from memory to register.
    unsigned int trig_head_local = trighead;

    if(recordsniff) { // record analog values
      sniffvalue = adcRead(sniffin, 0);
      // convert input to mV
      //if (sniffvalue>0)
      sniff[current_ind] = sniffvalue;
      //else
      //  sniff[currentvalue] = sniffvalue;
      
      // Record the sniff TTL  when sniff_trigger == FALSE, mouse is inhaling.
 
      if(recordsniffttl) {
        if(sniff_trigger && (sniffvalue < sniff_t_inh)) { //start inhale.
          // filter signals higher than 50Hz after first change
          if((t_ms-lastsnifftime) > 20) {
            //digitalWrite(SNIFF_T,LOW);
            sniff_trigger = false; 
            lastsnifftime = t_ms;
            trig[trig_head_local] = lastsnifftime;
            trighead = (trig_head_local+1)%TRIGBUFF;
          }
        }
        else if(!sniff_trigger && (sniffvalue > sniff_t_exh)) { //start exhale
          // filter signals higher than 50Hz after first change
          if((t_ms-lastsnifftime) > 20) {
            //digitalWrite(SNIFF_T,HIGH);
            sniff_trigger = true;
            lastsnifftime = t_ms;
            trig[trig_head_local] = lastsnifftime;
            trighead = (trig_head_local+1)%TRIGBUFF;
          }
        }
      }
    }
    if(recordspeed) {
      speedvalue = adcRead(speedin, 0);
      // convert input to mV
      if(speedvalue>0)
        treadmill[current_ind] = speedvalue;
      else
        treadmill[current_ind] = speedvalue;
      
      // check if treadmill threshold crossed
      if(abs(treadmill[current_ind]) > treadmill_t) {
        // filter high freq noise
        if((t_ms-last_movement) > 2) {
          last_movement = t_ms;
          // want to record next move side
          if(trig_move) {
            if(treadmill[current_ind] > 0)
              moved_side = LEFT;
            else
              moved_side = RIGHT;
            trig_move = false;
          }
        }
      }
    }
    
    //buffer full
    if(current_ind == 0)
      bufftimes++;
  }
}

// Check beam break. Return TRUE if a poke occurs.
// Arguments: pin of the beam break connection
boolean checkBeam(uint8_t beam) {
  return digitalRead(beam) == HIGH;
}

// we check for difference in the state of the beam break and timestamp when the state changes
void checkLick(uint8_t freq) {
  // only record when flag is set
  if(lickflag || lick2flag) {
    // restart timer
    uint32_t time = freq;
    startTimer(licktimer, time, checkLick, freq);
    
    if(lickflag) {
      boolean bbreak = checkBeam(beampin);
    
      // record only if state has changed
      if(bbreak != beamstatus) {
        lick[lickhead] = totalms;  // time from clock start
        beamstatus = bbreak;
        //digitalWrite(DIGITAL4,bbreak);
        lickhead = (lickhead+1)%LICKBUFF;
        //if(lickhead == licktail)
        // warn about buffer overflow
      }
    }
    if(lick2flag)  {
      boolean bbreak = checkBeam(beam2pin);
    
      // record only if state has changed
      if(bbreak != beam2status) {
        lick2[lick2head] = totalms;  // time from clock start
        beam2status = bbreak;
        //digitalWrite(DIGITAL3,bbreak);
        lick2head = (lick2head+1)%LICKBUFF;
        //if(lick2head == lick2tail)
        // warn about buffer overflow
      }
    }
  }
}

// stop recording the lick signal of the given beam (1 or 2 for now)
void lickOff(uint8_t beam) {
  
  if ((beam==1 && !lickflag) || (beam==2 && !lick2flag))
    return;
  
  if (beam == 1)  {
    lickflag = false;  // stop recording lick timestamps

    if(beamstatus == true) {
      lick[lickhead] = totalms;  // insert a fake timestamp to drive the signal low
      beamstatus = false;  // our initial status for next block or recordings
      
      lickhead = (lickhead+1)%LICKBUFF;
      // if (lickhead == licktail)
        // warn about buffer overflow
    }
  }
  else if(beam == 2)  {
    lick2flag = false;  // stop recording lick timestamps

    if(beam2status == true) {
      lick2[lick2head] = totalms;  // insert a fake timestamp to drive the signal low
      beam2status = false;  // our initial status for next block or recordings
      
      lick2head = (lick2head+1)%LICKBUFF;
      // if (lickhead == licktail)
        // warn about buffer overflow
    }
  }
}

// start recording the lick signal
void lickOn(uint8_t beams, uint8_t freq) {
  /* arguments: beams = which beam break pins to turn on (1,2 or both (3))
                freq = frequency of the timer in ms */
  if(beams == 1)
    lickflag = true;
  else if(beams == 2)
    lick2flag = true;
  else if(beams == 3)
    lickflag = lick2flag = true;

  if(licktimer == 255)
    return; // warning that timer is not started/no timer available
  startTimer(licktimer, 0, checkLick, freq);
}

// initialize the lick buffer and lick beam pins
void startLick(uint8_t beam1, uint8_t beam2) {
  // setup the lick beam pins to use
  beampin = beam1;
  beam2pin = beam2;
  
  // initialize the first value
  lick[lickhead++] = totalms;  // first value we assume the beam is not broken
  lick2[lick2head++] = totalms;
  // initialize last value to 0 as it may be accessed when getLastLick() is first called
  lick[LICKBUFF-1] = 0;
  lick2[LICKBUFF-1] = 0;
  licktimer = allocateTimer();  // allocate timer
}

// stop recording of the lick and the lick buffer
void stopLick() {
  lickflag = false;
  lick2flag = false;
  beamstatus = false;
  beam2status = false;
  lickhead = licktail = 0;  // restart the index values of the buffer
  lick2head = lick2tail = 0;
  freeTimer(licktimer);
}

// check to see if there are any values in the lick buffer
boolean hasLickdata() {
  return (lickhead != licktail);
}
// check to see if there are any values in the lick buffer
boolean hasLickdata(uint8_t pin) {
  if(pin == 1)
    return (lickhead != licktail);
  else if(pin == 2)
    return (lick2head != lick2tail);
}

// check to see if there were any licks
// use iff licks are not being streamed, i.e. buffered and transmitted at end of trial
boolean hasLicked(uint8_t pin) {
  if(pin == 1) {
    // there is only one value in the buffer
    if(lickhead-licktail == 1)
      return beamstatus;
    // one value in the buffer and head index is wrapped to zero
    else if((lickhead == 0) && (licktail == LICKBUFF-1))
      return beamstatus;
    else
      return lickhead != licktail;
  }
  else if(pin == 2) {
    if(lick2head-lick2tail == 1)
      return beam2status;
    // one value in the buffer and head index is wrapped to zero
    else if((lick2head == 0) && (lick2tail == LICKBUFF-1))
      return beam2status;
    else
      return lick2head != lick2tail;
  }
}

// check to see if there were any licks from given lickindex
// use when licking is continuously being transmitted
boolean hasLicked(uint8_t pin, uint16_t lickindex) {
  if(pin == 1) {  
    // there is only one value difference
    if(lickhead-lickindex == 1)
      return beamstatus;
    // one value difference and head index is wrapped to zero
    else if((lickhead == 0) && (lickindex == LICKBUFF-1))
      return beamstatus;  // if beam is broken, there is a lick
    else
      return lickhead != lickindex;
  }
  else if(pin == 2) {
    // there is only one value difference
    if(lick2head-lickindex == 1)
      return beam2status;
    // one value difference and head index is wrapped to zero
    else if((lick2head == 0) && (lickindex == LICKBUFF-1))
      return beam2status;  // if beam is broken, there is a lick
    else
      return lick2head != lickindex;    
  }
}


//This checks for initiation of a lick after the lickchecktime in ms; returns false if no lick has been STARTED after the checktime, even if a lick continues into the check time.
boolean haslicked(uint8_t pin, unsigned long lickchecktime) {
  if(pin == 1) {
    if(beamstatus)
      // beam is high, animal is licking now, check if the lickhead-1 is after lickchecktime, meaning that the animal started the lick after the checktime. If so, return true.
      return lick[(LICKBUFF+lickhead-1)%LICKBUFF] > lickchecktime; 
    else
      // beam is low. Compare with two transition timestamps ago in the lickbuffer (OFF->ON)
      return lick[(LICKBUFF+lickhead-2)%LICKBUFF] > lickchecktime;   
  }
  else if(pin == 2) {
    if(beam2status)
      // beam is high, animal is licking now, check if the lickhead-1 is after lickchecktime, meaning that the animal started the lick after the checktime. If so, return true.
      return lick2[(LICKBUFF+lick2head-1)%LICKBUFF] > lickchecktime;
    else
      // beam is low, check 2 records back (the last high edge), to see if the animal initiated a lick before the checktime. If so, return true.
      return lick2[(LICKBUFF+lick2head-2)%LICKBUFF] > lickchecktime;    
  }  
}

// get the current head index in the lick ring buffer
uint16_t getLickstart(uint8_t pin) {
  if(pin == 1)
    return lickhead;
  else if(pin == 2)
    return lick2head;
  else
    return 0;
}

unsigned long getLastLick(uint8_t pin) {
  if(pin == 1) {
    if(beamstatus)
      return lick[(LICKBUFF+lickhead-1)%LICKBUFF];
    else
      return lick[(LICKBUFF+lickhead-2)%LICKBUFF];
  }
  else if(pin == 2) {
    if(beam2status)
      // beam is high. Return last transition timestamp in the lickbuffer
      return lick2[(LICKBUFF+lick2head-1)%LICKBUFF];
    else
      // beam is low. Return (OFF->ON) timestamp in the lickbuffer
      return lick2[(LICKBUFF+lick2head-2)%LICKBUFF];    
  } 
}


// start analog acquisition
void start_analog_timer() {
  clockflag = true;
  analogtimer = allocateTimer();
  startTimer(analogtimer, 1, ain, 0);
}

// stop analog acquisition
void stopAnalog() {
  clockflag = false;
}


// delay for given number of ms. Interrupts still run
// uses the ms timer clock
void msdelay(unsigned long msec) {
  // arguments: msec is the number of ms to do busy waiting
  
  unsigned long target = totalms+msec;
  
  while(true) {
    Serial.print(""); //need some sort of small delay or stuck in the loop? Not sure why
    if(target <= totalms)
      break;
  }
}

// set amplitude and duration of pulse generation on given channel
// takes at least 50ms
void setPulse(uint8_t channel, unsigned long duration, uint16_t amplitude, bool pause = true) {
  /* arguments:
     channel: 1 or 2
     duration: time in microseconds. Range: 0-4294s
     amplitude: signal amplitude in mV range: 0-5000 */

  Serial2.flush();
  // command format: "p1/p2 <duration> <amplitude>"
  switch (channel) {
    case 1:  Serial2.print("p1 "); break;
    case 2:  Serial2.print("p2 "); break;
    case 3:  Serial2.print("p3 "); break;
  }

  duration = duration/20; //duration is multiples of 20us. pulse generator multiplies by 20
  Serial2.print(duration);
  Serial2.print(" ");
  // amplitude is a 16bit unsigned value from 0V (0x0000) to 5.0V (0xffff)
  amplitude = amplitude*(65535.0/5000);
  Serial2.print(amplitude);
  Serial2.print('\r');
  Serial2.flush(); // wait for the message to be sent before returning (this should be pretty quick, and it should be outside the trial).
  if (pause) { // required for backward compatibility. Instead of using this, set pause = false when calling the variable and use timers so that you don't lock your state machine up.
  msdelay(50);//need time for the Serial print to transmit
  }
}

// set pulse duration on given channel. Takes at least 30ms
void setPulsedur(uint8_t channel, unsigned long duration) {
  /* arguments:
     channel: 1 or 2
     duration: time in microseconds. Range: 0-1.3s
   */
  Serial2.flush();
  // command format: "l1/l2 <duration>"
  switch (channel) {
    case 1:  Serial2.print("l1 "); break;
    case 2:  Serial2.print("l2 "); break;
    case 3:  Serial2.print("l3 "); break;
  }
  
  duration = duration/20; //duration is multiples of 20us. pulse generator multiplies by 20
  Serial2.print(duration);
  Serial2.print('\r');
  //msdelay(30); //need time for the Serial print to transmit
}

// set pulse amplitude on given channel. Takes at least 30ms
void setPulseamp(uint8_t channel, unsigned int amplitude) {
  /* arguments:
     channel: 1 or 2
     amplitude: signal amplitude in mV range: 0-5000 */
  Serial.flush();
  // command format: "a1/a2 <duration>"
  switch (channel) {
    case 1:  Serial2.print("a1 "); break;
    case 2:  Serial2.print("a2 "); break;
    case 3:  Serial2.print("a3 "); break;
  }
  
   // amplitude is a 16bit unsigned value from 0V (0x0000) to 5.0V (0xffff)
  amplitude = amplitude*(65535.0/5000);
  Serial2.print(amplitude);
  Serial2.print('\r');
  //msdelay(30);  //need time for the Serial print to transmit
}

// trigger the pulse of the given channel
void trigPulse(uint8_t channel) {
  // arguments: pulse gen. channel (1 or 2)
  switch (channel) {
    case 1:  digitalWrite(TRIGGER1, HIGH);  // trigger the pulse in less than 1us from here
             digitalWrite(TRIGGER1, LOW); break;
    case 2:  digitalWrite(TRIGGER2, HIGH);
             digitalWrite(TRIGGER2, LOW); break;
    case 3:  digitalWrite(TRIGGER3, HIGH);
             digitalWrite(TRIGGER3, LOW); break;
    }
}

void trigPulseTimerOn(uint8_t index) {

  trigPulse(cuePins[index]);
  freeTimer(cueTimers[index]);
  cueFree[index] = 1;  
}

// trigger the pulse of the given channel
void trigPulseTime(uint8_t channel, unsigned long time) {
  
  if(time == 0) { // trigger laser immediately
    trigPulse(channel);
    return;
  }
  
  uint8_t i;  
  // find a free slot for the cue timer
  for (i = 0; i < MAXCUES ; i++) {
    if (cueFree[i] == 1) {
      cueFree[i] = 0;
      break;
    }
  }
  
  if (i == MAXCUES)
    return; // warn that there is no more cue timers available

  uint8_t laserTimer; //timer
  laserTimer = allocateTimer(); // allocate the timer object
  cueTimers[i] = laserTimer;
  cuePins[i] = channel;

  // start timer which runs once and returns to the cueTimerOff function
  startTimer(laserTimer, time, trigPulseTimerOn, i);
}

// read Serial 2 (used for pulsegenerator) into given buffer
void get_line2(char *buff, uint16_t len) {
  uint8_t c;
  uint8_t idx = 0;

  for (;;) {
    if (Serial2.available() > 0) {
      c = Serial2.read();
      if (c == '\r') { 
        Serial2.read(); //get rid of any trailing NL chars
        break;
      }
      if ((c >= ' ') && (idx < len - 1)) {
        buff[idx++] = c;
      }
    }
  }
  buff[idx] = 0;
}

// read the settings for the pulse generator on the given channel
void getPulse(uint8_t channel,char *dur,char *amp) {
  // arguments: pulse gen. channel (1 or 2)
  // returns two strings with values for duration and amplitude

  Serial2.flush();
  // serial command: r1/r2
  switch (channel) {
    case 1:  Serial2.print("r1 \r"); break;
    case 2:  Serial2.print("r2 \r"); break;
    case 3:  Serial2.print("r3 \r"); break;
  }

  char buff[100];
  get_line2((char *)buff, sizeof(buff));

  // parse into duration and amplitude
  for(int i=0; i<sizeof(buff); i++) {
    if(buff[i] == ' ') {
      dur[i] = '\0';
      for(int j=0; j<sizeof(buff)-i; j++) {
        amp[j] = buff[i+j+1];
        if(amp[j] == '\0') // end of line
          break;
      }
      break;
    }
    dur[i] = buff[i];
  }
}

// Turn cue on
void cueOn(uint8_t cue) {
  // Turn on given pin that indicates the cue output
  // caller needs to make sure the pin is setup as output
  digitalWrite(cue, HIGH);
}

// Turn cue off
void cueOff(uint8_t cue) {
  // Turn off given pin that indicates the cue output
  // caller needs to make sure the pin is setup as output
  digitalWrite(cue, LOW);
}

// Turn cue off and free up the cue timer associated to it
void cueTimerOff(uint8_t cueslot) {
  cueOff(cuePins[cueslot]); // turn off cue
  freeTimer(cueTimers[cueslot]); // free the timer
  cueFree[cueslot] = 1; // free up the slot
}


void pinTimerOff(uint8_t cueslot) {
  cueOff(cuePins[cueslot]); // turn off cue
  freeTimer(cueTimers[cueslot]); // free the timer
  cueFree[cueslot] = 1; // free up the slot
  pinIsOff = true;
}



void cueTimerOffHigh(uint8_t cueslot) {
  cueOn(cuePins[cueslot]); // turn cue high (LED MASK!!!)
  freeTimer(cueTimers[cueslot]); // free the timer
  cueFree[cueslot] = 1; // free up the slot
}

// Turn cue on for given time in ms (interrupt handled)
void cueOnTimer(uint8_t cue, unsigned long time) {
  // Function turns on given cue pin, and sets up a timer interrupt to turn it off
  
  uint8_t i;  
  // find a free slot for the cue timer
  for (i = 0; i < MAXCUES ; i++) {
    if (cueFree[i] == 1) {
      cueFree[i] = 0;
      break;
    }
  }
  
  if (i == MAXCUES)
    return; // warn that there is no more cue timers available

  uint8_t cueTimer; //timer
  cueTimer = allocateTimer(); // allocate the timer object
  cueTimers[i] = cueTimer;
  cuePins[i] = cue;

  cueOn(cue);   //Turn on cue
  // start timer which runs once and returns to the cueTimerOff function
  startTimer(cueTimer, time, cueTimerOffHigh, i);
}

void cueOnLowTimer(uint8_t cue, unsigned long time) {
  // Function turns low given cue pin, and sets up a timer interrupt to turn it high again. For LED mask.
  
  uint8_t i;  
  // find a free slot for the cue timer
  for (i = 0; i < MAXCUES ; i++) {
    if (cueFree[i] == 1) {
      cueFree[i] = 0;
      break;
    }
  }
  
  if (i == MAXCUES)
    return; // warn that there is no more cue timers available

  uint8_t cueTimer; //timer
  cueTimer = allocateTimer(); // allocate the timer object
  cueTimers[i] = cueTimer;
  cuePins[i] = cue;

  cueOff(cue);   //writes cue low
  // start timer which runs once and returns to the cueTimerOffHigh function
  startTimer(cueTimer, time, cueTimerOffHigh, i);
}


// Turn valve on
void valveOn(uint8_t valve) {
  // Turn on given pin attached to the solenoid
  // caller needs to make sure the pin is setup as output
  digitalWrite(valve, HIGH);
}

// Turn valve off
void valveOff(uint8_t valve) {
  // Turn off given pin attached to the solenoid
  // caller needs to make sure the pin is setup as output
  digitalWrite(valve, LOW);
}

// Turn valve on for given time in ms (interrupt handled)
void valveOnTimer(uint8_t valve, unsigned long time) {
  // Function turns on given solenoid pin, and sets up a timer interrupt to turn it off
    
  uint8_t i;  
  // find a free slot for the valve timer
  for (i = 0; i < MAXCUES ; i++) {
    if (cueFree[i] == 1) {
      cueFree[i] = 0;
      break;
    }
  }
  if (i == MAXCUES)
    return; // to do: warn that there is no more valve timers available

  uint8_t valveTimer; //timer
  valveTimer = allocateTimer(); // allocate the timer object
  cueTimers[i] = valveTimer;
  cuePins[i] = valve;

  valveOn(valve);   //Turn on valve
  // start timer which runs once and returns to the cueTimerOff function that frees up the timer
  startTimer(valveTimer, time, cueTimerOff, i);
}


void pinOnTimer(uint8_t valve, unsigned long time) {
  // exactly the same functionality as valveOnTimer, except:
	//it returns to a pinTimerOff function which additionally returns a flag (pinIsOff) upon pin offset
	//can check within state machine for this flag to activate additional functions following pin offset
  
  uint8_t i;  
  // find a free slot for the valve timer
  for (i = 0; i < MAXCUES ; i++) {
    if (cueFree[i] == 1) {
      cueFree[i] = 0;
      break;
    }
  }
  if (i == MAXCUES)
    return; // to do: warn that there is no more valve timers available

  uint8_t valveTimer; //timer
  valveTimer = allocateTimer(); // allocate the timer object
  cueTimers[i] = valveTimer;
  cuePins[i] = valve;
  pinIsOff = false;
  valveOn(valve);   //Turn on valve
  // start timer which runs once and returns to the cueTimerOff function that frees up the timer
  startTimer(valveTimer, time, pinTimerOff, i);
}

#endif

