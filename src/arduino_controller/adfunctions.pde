#define ADC_PIN 49 //PLO
#define DAC1_PIN 53
#define DAC2_PIN 48


// AD7328 ADC read routine
#if defined(__AVR_ATmega2560__) // including this in an if statement so that it will only use direct port register mapping if using this board.
uint16_t adcRead(uint8_t adc, uint8_t coding) {
  // adc = adc input, 0 - 7
  // coding = 0 -> two's compliment
  // coding = 1 -> binary
  uint16_t adcValue;
  //digitalWrite(ADC_PIN, LOW);
  PORTL &= ~_BV(PL0); //write low. This operation is much (orders of magnitude) faster than digitaWrite. It is specifically mapped
  SPI.transfer(0x80 | ((adc & 0x07)<<2));
  SPI.transfer(0x10 | ((coding & 0x01)<<5));
  //digitalWrite(ADC_PIN, HIGH);
  PORTL |= _BV(PL0); //write high
  //digitalWrite(ADC_PIN, LOW);
  PORTL &= ~_BV(PL0); //write low
  ((uint8_t*)&adcValue)[1] = SPI.transfer(0);
  ((uint8_t*)&adcValue)[0] = SPI.transfer(0);
  //digitalWrite(ADC_PIN, HIGH);
  PORTL |= _BV(PL0); //write high
  // sign-extend if negative
  if ((coding == 0) && ((adcValue & 0x1000) == 0x1000)) {
    adcValue = (adcValue >> 1) | 0xf000;
  } else {
    adcValue = (adcValue >> 1) & 0x0fff;
  }
  // return the 12 bit value
  return adcValue;
}
#else // for all other arduinos, use digitalWrite: slow but steady.
uint16_t adcRead(uint8_t adc, uint8_t coding) {
  // adc = adc input, 0 - 7
  // coding = 0 -> two's compliment
  // coding = 1 -> binary
  uint16_t adcValue;
  digitalWrite(ADC_PIN, LOW);
  SPI.transfer(0x80 | ((adc & 0x07)<<2));
  SPI.transfer(0x10 | ((coding & 0x01)<<5));
  digitalWrite(ADC_PIN, HIGH);
  digitalWrite(ADC_PIN, LOW);
  ((uint8_t*)&adcValue)[1] = SPI.transfer(0);
  ((uint8_t*)&adcValue)[0] = SPI.transfer(0);
  digitalWrite(ADC_PIN, HIGH);
  // sign-extend if negative
  if ((coding == 0) && ((adcValue & 0x1000) == 0x1000)) {
    adcValue = (adcValue >> 1) | 0xf000;
  } else {
    adcValue = (adcValue >> 1) & 0x0fff;
  }

  // return the 12 bit value
  return adcValue;
}
#endif


// AD5666 DAC write routine
void dac1Write(uint8_t dac, uint16_t value) {
  // dac = dac output channel, 0 - 3
  // value = 16 bit output value
  digitalWrite(DAC1_PIN, LOW);
  SPI.transfer(0x03); // CMD = 0011, write & update dac channel
  SPI.transfer(((dac & 0x0f)<<4) | ((value & 0xf000)>>12));
  SPI.transfer((value & 0x0ff0)>>4);
  SPI.transfer((value & 0x000f)<<4);
  digitalWrite(DAC1_PIN, HIGH);
  digitalRead(DAC1_PIN);
}

// AD5754 DAC write routine
void dac2Write(uint8_t dac, int16_t value) {
  // dac = dac output channel, 0 - 3
  // value = 16 bit output value
  digitalWrite(DAC2_PIN, LOW);
  SPI.transfer(dac);
  SPI.transfer((value & 0xff00)>>8);
  SPI.transfer((value & 0x00ff));
  digitalWrite(DAC2_PIN, HIGH);
  digitalRead(DAC2_PIN);
}



void startSPI() {
  // initialize SPI:  
  SPI.begin(); 
  // use SPI clock mode 2
  SPI.setDataMode(SPI_MODE2);
  // set clock mode to FCLK/2
  SPI.setClockDivider(SPI_CLOCK_DIV2);

  // DAC1 (AD5666) setup
  // Setup DAC REF register
  digitalWrite(DAC1_PIN, LOW);
  SPI.transfer(0x08); // CMD = 1000
  SPI.transfer(0x00);
  SPI.transfer(0x00);
  SPI.transfer(0x01); // Standalone mode, REF on
  digitalWrite(DAC1_PIN, HIGH);
  digitalRead(DAC1_PIN); // add some time

  // Power up all four DACs
  digitalWrite(DAC1_PIN, LOW);
  SPI.transfer(0x04); // CMD = 0100
  SPI.transfer(0x00);
  SPI.transfer(0x00); // Normal operation (power-on)
  SPI.transfer(0x0f); // All four DACs
  digitalWrite(DAC1_PIN, HIGH);
  digitalRead(DAC1_PIN);

  // Set DAC outputs to 0V
  dac1Write(0, 0x0000); // 0V
  dac1Write(1, 0x0000); // 0V
  dac1Write(2, 0x0000); // 0V
  dac1Write(3, 0x0000); // 0V


  // ADC (AD7328) setup
  /* range register 1: +/- 5V range on ch0 0,1,2,3 */
  digitalWrite(ADC_PIN, LOW);
  SPI.transfer(0xaa);
  SPI.transfer(0xa0);
  digitalWrite(ADC_PIN, HIGH);
  
  /* range register 2: +/-5V range on ch 4,5,6,7 */
  digitalWrite(ADC_PIN, LOW);
  SPI.transfer(0xca);
  SPI.transfer(0xa0);
  digitalWrite(ADC_PIN, HIGH);

  /* sequence register: all sequence bits off */
  digitalWrite(ADC_PIN, LOW);
  SPI.transfer(0xe0);
  SPI.transfer(0x00);
  digitalWrite(ADC_PIN, HIGH);

  /* control register: ch 000, mode = 00, pm = 00, code = 0, ref = 1, seq = 00 */
  digitalWrite(ADC_PIN, LOW);
  SPI.transfer(0x80);
  SPI.transfer(0x10);
  digitalWrite(ADC_PIN, HIGH);

  
  // DAC2 (AD5754) setup
  /* DAC power control register (all ch + ref powered up)*/
  digitalWrite(DAC2_PIN, LOW);
  SPI.transfer(0x10);
  SPI.transfer(0x00);
  SPI.transfer(0x1f);
  digitalWrite(DAC2_PIN, HIGH);
  
  /* DAC control register (SDO turned off) */
  digitalWrite(DAC2_PIN, LOW);
  SPI.transfer(0x19);
  SPI.transfer(0x00);
  SPI.transfer(0x0d);
  digitalWrite(DAC2_PIN, HIGH);
  
  /* DAC output range register (all ch +/-5V range)*/
  digitalWrite(DAC2_PIN, LOW);
  SPI.transfer(0x0c); // all four DACs
  // 0x08 = DAC1, 0x09 = DAC2, 0x0a = DAC3, 0x0b = DAC4, 0x0c = all DACs
  SPI.transfer(0x00);
  SPI.transfer(0x03);
  // 0 = +5V range, 1 = +10V range, 2 = +10.8V range, 3 = +/-5V range
  // 4 = +/-10V range, 5 = +/- 10.8V range
  digitalWrite(DAC2_PIN, HIGH);
  // set outputs to 0V
  dac2Write(0, 0);
  dac2Write(1, 0);
  dac2Write(2, 0);
  dac2Write(3, 0);
  dac2Write(4, 0);
  dac2Write(5, 0);
  dac2Write(6, 0);
  dac2Write(7, 0);
}
