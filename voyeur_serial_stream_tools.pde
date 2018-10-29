#ifndef VOYEURSTREAM
#define VOYEURSTREAM


void sendShortAsBytes(int intValue)
{
	byte temp;
	temp = (intValue & 0xFF);
	Serial.write(temp);
	temp = (intValue >> 8) & 0xFF;
	Serial.write(temp);
	return;
}

void sendLongAsBytes(long longValue)
{
	// first send the low 16 bit integer value
	byte temp;
	temp = (longValue & 0xFF);  // get the value of the lower 16 bits
	Serial.write(temp);
	temp = (longValue >> 8) & 0xFF;
	Serial.write(temp);
	temp = (longValue >> 16) & 0xFF;
	Serial.write(temp);
	temp = (longValue >> 24) & 0xFF;
	Serial.write(temp);
	return;
}


#endif
