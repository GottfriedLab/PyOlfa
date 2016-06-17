// adcRead routine
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


// dacWrite routine
void dacWrite(uint8_t dac, int16_t value) {
  // dac = dac output, 0 - 3
  // value = 16 bit output value
  digitalWrite(DAC_PIN, LOW);
  SPI.transfer(dac);
  SPI.transfer((value & 0xff00)>>8);
  SPI.transfer((value & 0x00ff));
  digitalWrite(DAC_PIN, HIGH);
  digitalRead(DAC_PIN);
}


void startSPI() {
  // use SPI clock mode 2
  SPI.setDataMode(1<<CPOL); // SPI mode 2

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
  SPI.transfer(0xd0);
  SPI.transfer(0x00);
  digitalWrite(ADC_PIN, HIGH);

  /* control register: ch 000, mode = 00, pm = 00, code = 0, ref = 1, seq = 00 */
  digitalWrite(ADC_PIN, LOW);
  SPI.transfer(0x80);
  SPI.transfer(0x10);
  digitalWrite(ADC_PIN, HIGH);
  
  // DAC (AD5754) setup
  /* DAC power control register (all ch + ref powered up)*/
  digitalWrite(DAC_PIN, LOW);
  SPI.transfer(0x10);
  SPI.transfer(0x00);
  SPI.transfer(0x1f);
  digitalWrite(DAC_PIN, HIGH);
  
  /* DAC control register (SDO turned off) */
  digitalWrite(DAC_PIN, LOW);
  SPI.transfer(0x19);
  SPI.transfer(0x00);
  SPI.transfer(0x0d);
  digitalWrite(DAC_PIN, HIGH);
  
  /* DAC output range register (all ch +/-5V range)*/
  digitalWrite(DAC_PIN, LOW);
  SPI.transfer(0x0c); // all four DACs
  // 0x08 = DAC1, 0x09 = DAC2, 0x0a = DAC3, 0x0b = DAC4, 0x0c = all DACs
  SPI.transfer(0x00);
  SPI.transfer(0x03);
  // 0 = +5V range, 1 = +10V range, 2 = +10.8V range, 3 = +/-5V range
  // 4 = +/-10V range, 5 = +/- 10.8V range
  digitalWrite(DAC_PIN, HIGH);
}
