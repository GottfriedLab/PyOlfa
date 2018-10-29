#ifndef sbi
#define sbi(sfr, bit) (_SFR_BYTE(sfr) |= _BV(bit))

#endif

#define MAX_FUNC 32
void (*p_func[MAX_FUNC])(uint8_t);
uint32_t funcTime[MAX_FUNC];
uint8_t funcFree[MAX_FUNC];
uint8_t funcEnable[MAX_FUNC];
uint8_t funcArg[MAX_FUNC];
volatile unsigned long totalms = 0; // volatile so that the interrupt actually changes it. COPY THIS LOCALLY WITHIN FUNCTIONS.


void startTimer(uint8_t timer, uint32_t time, void (*userFunc)(uint8_t), uint8_t arg) {
	if (funcFree[timer] == 0) {
		funcEnable[timer] = 0;
		funcTime[timer] = totalms + time;
		funcArg[timer] = arg;
		p_func[timer] = userFunc;
		funcEnable[timer] = 1;
	}
}

void stopTimer(uint8_t timer) {
	if (funcFree[timer] == 0) {
		funcEnable[timer] = 0;
	}
}

uint8_t allocateTimer(void) {
	uint8_t i;
	for (i = 0; i < MAX_FUNC; i++) {
		if (funcFree[i] == 1) {
			funcFree[i] = 0;
			break;
		}
	}
	if (i == MAX_FUNC)
		return 255;

	return i;
}

void freeTimer(uint8_t timer) {
	if (timer < MAX_FUNC) {
		funcEnable[timer] = 0;
		funcFree[timer] = 1;
	}
}

void setupVoyeurTimer(void) { // this must be executed in the setup function of your sketch.
	cli(); //disable interrupts
	totalms = 0;

	// SETUP TIMER 5 to generate interrupt TIMER5_COMPA_vect every 1 ms. ------------------------------
	TCCR5B = 0;
	TIMSK5 = 0;
	TCCR5C = 0;
	TCCR5A = 0;
	sbi(TCCR5B, CS50); // write bit 1 of CS5 to set prescaler to 1 (1 tick per clock tick).
	sbi(TIMSK5, OCIE5A); // enable TIMER5_COMPA_vect interrupt flag. This sets activates the comparison mode for the 'A' register.
	sbi(TCCR5B, WGM52); //put timer 5 in CTC (Clear Timer on Compare) mode. Timer count resets on hitting value set in OCR5A.
	OCR5A = 15999; // sets the top value that the timer will reach before resetting the count.
	//----------------------------
	int i;
	//Free all your timers.
	for (i = 0; i < MAX_FUNC; i++) {
		funcEnable[i] = 0;
		funcFree[i] = 1;
	}

	sei(); //re-enable interrupts

}


ISR(TIMER5_COMPA_vect) { // this is the actual interrupt routine that occurs every 1 ms.
	int i;
	// copy these to local variables so they can be stored in registers
	// (volatile variables must be read from memory on every access)
	unsigned long m = totalms;

	m++; // this timer vector ticks once per ms.
	totalms = m; //rewrite to the volatile variable.

	// run user timer routines as required.
	for (i = 0; i < MAX_FUNC; i++) {
		if ((funcFree[i] ==0) && (funcEnable[i] != 0) && (funcTime[i] <= m)) {
			funcEnable[i] = 0;
			(*p_func[i])(funcArg[i]);
		}
	}
}
