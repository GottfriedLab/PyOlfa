/*
General functions for the control of code based serial communication with the Arduino board.
This is configured for 2 licks to maintain compatability with the 2-lick python protocol transmission standards.
*/

void parse(char *line, char **argument_words, uint8_t maxArgs) {
  uint8_t argCount = 0;
  while (*line != '\0') {       /* if not the end of line ....... */
    while (*line == ',' || *line == ' ' || *line == '\t' || *line == '\n')
      *line++ = '\0';     /* replace commas and white spaces with 0    */
    *argument_words++ = line;          /* save the argument position     */
    argCount++;
    if (argCount == maxArgs-1)
      break;
    while (*line != '\0' && *line != ',' && *line != ' ' &&
           *line != '\t' && *line != '\n')
      line++;             /* skip the argument until ...    */
  }
  *argument_words = '\0';                 /* mark the end of argument list  */
}

//=======================
void RunSerialCom(int code) {

  switch (code) {

    case 86: // user defined command
      uint8_t c;
      msdelay(12);
      while (Serial.available() > 0) { // PC communication
        c = Serial.read();
        if (c == '\r') {
          user_command_buffer[user_command_buffer_index] = 0;
          parse((char*)user_command_buffer, argument_words, sizeof(argument_words));
          if (strcmp(argument_words[0], "fv") == 0) {
            if(strcmp(argument_words[1], "on") == 0) {
              valveOn(FINALVALVE);
              digitalWrite(FV_T,HIGH);
            }
            else if(strcmp(argument_words[1], "off") == 0) {
              valveOff(FINALVALVE);
              digitalWrite(FV_T,LOW);
            }
          }
          // water valve
          else if(strcmp(argument_words[0], "wv") == 0) {
            int water_valve = atoi(argument_words[1]);
            if(water_valve == 1) {
              if(strlen(argument_words[2]) > 0)
                water_duration = atoi(argument_words[2]);
              valveOnTimer(WATERVALVE1, water_duration);
            }
            else if(water_valve == 2) {
              if(strlen(argument_words[2]) > 0)
                water_duration2 = atoi(argument_words[2]);
              valveOnTimer(WATERVALVE2, water_duration2);
            }
          }

          // water callibration (100 water drops)
          else if(strcmp(argument_words[0], "calibrate") == 0) {
            int water_valve = atoi(argument_words[1]);
            if(strlen(argument_words[2]) > 0) {
              if(water_valve == 1)
                water_duration = atoi(argument_words[2]);
              else if(water_valve == 2)
                water_duration2 = atoi(argument_words[2]);
            }
            for(int x=0; x<=100; x=x+1){
              if(water_valve == 1)
                valveOnTimer(WATERVALVE1, water_duration);
              else if(water_valve == 2)
                valveOnTimer(WATERVALVE2, water_duration2);
              //Serial1.print(0x0c, BYTE);
              delay(1000);
						Serial1.write(0x94);
              Serial1.print("CAL: ");
              Serial1.print(x);
            }
          }
          else if(strcmp(argument_words[0], "water_duration") == 0) {
            int water_valve = atoi(argument_words[1]);
            if(water_valve == 1)
              water_duration = atoi(argument_words[2]);
            else if(water_valve == 2)
              water_duration2 = atoi(argument_words[2]);
          }
          else if(strcmp(argument_words[0], "Laser") == 0) {
            if(strcmp(argument_words[2], "trigger") == 0) {
              unsigned long laser_dur;
              uint16_t laser_amp;
              uint8_t laser_chan;
              char **endptr;
              laser_chan = (uint8_t)atoi(argument_words[1]);
              laser_amp = atoi(argument_words[3]);
              laser_dur = strtoul(argument_words[4],endptr,0)*1000;
              setPulse(laser_chan,laser_dur,laser_amp);
              trigPulse(laser_chan);
            }
          }
          user_command_buffer_index = 0;
        }
        else if (((c == '\b') || (c == 0x7f)) && (user_command_buffer_index > 0))
          user_command_buffer_index--;
        else if ((c >= ' ') && (user_command_buffer_index < sizeof(user_command_buffer) - 1))
          user_command_buffer[user_command_buffer_index++] = c;
      }
      Serial.print(2);
      Serial.print(",");
      Serial.println("*");
      // Serial.flush();
      break;


    case 87: // streaming data has been requested

      unsigned long currenttime;
      // transmit buffer
      if((trial_done_flag) && ((send_last_packet))) {
        // send end code
        Serial.print(5);
        Serial.print(",");
        Serial.println("*");
        trial_done_flag = false;
        send_last_packet = false;
        break;
      }

      else if(trial_done_flag) {
        // prepare to send last packet
        send_last_packet = true;
      }
      Serial.print(6);
      Serial.print(",");

      // transmit sniff signal.
      // TODO: Check for sniff buffer overflow
      currenttime = totalms;
      current_sniff_data_index = currentvalue;
      /* A timer tick might occur between the above two assignments, incrementing totalms and
         misaligning timestamp and values written to buffer. The following while
         loop makes sure both assignments occur with no time tick in between the statements */
      while(currenttime != totalms) {
        currenttime = totalms;
        current_sniff_data_index = currentvalue;
      }
      // calculate number of bytes to send for sniff and lick.
      int sniff_sample_number; // number of sniff samples
      int sniff_bytes;
      sniff_sample_number = (current_sniff_data_index+BUFFERS-last_sent_sniff_data_index)%BUFFERS;
      sniff_bytes = sniff_sample_number * 2;

      // ----- Calculate the number of lick values to send and the start and stop indices ------
      // ---LICK1---
      int tail1, head1, numlicks1,lickbytes1;
      bool lick_signal_state1;
      tail1 = licktail;
      head1 = lickhead;
      lick_signal_state1 = beamstatus;
      // make sure the above two variables were assigned at the same millisecond
      while(head1 != lickhead) {
        head1 = lickhead;
        lick_signal_state1 = beamstatus;
      }
      if (lick_signal_state1){
        //if licking currently, won't transmit the last value, which is lick on with no off
        head1 = head1 - 1;
        if (head1 < 0)
          head1 = LICKBUFF + head1;
      }
      if(head1 < tail1)
        numlicks1 = (LICKBUFF - tail1) + head1;
      else
        numlicks1 = head1-tail1;
      lickbytes1 = numlicks1*4;
      
      // SEND HEADER INFORMATION: NUMBER STREAMS, NUMBER OF PACKETS PER STREAM
      Serial.print(4); // number of streams to send
      Serial.print(",");
      Serial.print(4); //number of bytes for stream 1 (packet_sent_time)
      Serial.print(",");
      Serial.print(2); //number of bytes for sniff_samples (single integer)
      Serial.print(",");
      Serial.print(sniff_bytes); //number of bytes for actual sniff stream.
      Serial.print(",");
      Serial.println(lickbytes1);
      // end line here so that python will read and parse the handshake. Then...
      // ----- SEND ACTUAL DATA AS BINARY -----------------
      sendLongAsBytes(currenttime);
      sendShortAsBytes(sniff_sample_number);
      
      while(last_sent_sniff_data_index != current_sniff_data_index) {
        last_sent_sniff_data_index = (last_sent_sniff_data_index+1)%BUFFERS;
        sendShortAsBytes(sniff[last_sent_sniff_data_index]);
      }

      while(tail1!=head1)  {
        sendLongAsBytes(lick[tail1]);
        tail1 = (tail1+1)%(LICKBUFF);
      }
      // move the ring buffer tail index to current untransmitted tail index
      licktail = tail1;


      
//		// trigger signal
//		if(trighead != trigtail) {
//			int head, tail;
//			head = trighead;
//			tail = trigtail;
//
//			for (int i=tail; i!=head;) {
//				Serial.print(trig[i]);
//				i = (i+1)%TRIGBUFF;
//				if(i == head)
//					Serial.print(",");
//				else
//					Serial.print(";");
//			}
//			trigtail = head;
//		}
//		else
//			Serial.print(","); // empty signal
////////
      // end of packet signal
      break;
   case 88: // trail ended and the trial details were requested
      // tell the monitor about the trial details
      Serial.print(4);
      Serial.print(",");
      Serial.print(parameters_received_time);
      Serial.print(",");
      Serial.print(trial_start);
      Serial.print(",");
      Serial.print(trial_end);
      Serial.print(",");
      Serial.print(lost_sniff);
      Serial.print(",");
      Serial.print(final_valve_onset);
      Serial.print(",");
      Serial.println("*");
      break;

    case 90: // Start trial state (i.e. need to read from the serial port)
      received_parameters = 0;
      final_valve_duration = readULongFromBytes();
      trial_duration = readULongFromBytes();
      inter_trial_interval = readULongFromBytes();
      odorant_trigger_phase = readULongFromBytes();
      max_no_sniff_time = readULongFromBytes();

      Serial.print(2);
      Serial.print(",");
      Serial.println("*");
      Serial.flush();
      break;

    case 91:
      Serial.print(6);
      Serial.print(",");
      Serial.print(protocolName);
      Serial.print(",");
      Serial.println("*");
      break;

//    case 92: // directly control the arduino pin settings
//
//
//      break;
  }
}

int readIntFromBytes() {

  union u_tag {
    byte b[2];
    int ival;
  } u;

  u.b[0] = Serial.read();
  u.b[1] = Serial.read();

  return u.ival;
}

byte readbyte() {

  unsigned long temp1;
  byte value;
  temp1 = totalms;
  // attempt reading the serial for 200ms
  while(totalms-temp1 < 2000)  {
    if(Serial.available() > 0)
      return Serial.read();
    //value = Serial.read();
    //if(value != 255)
    //  return value;
  }
  Serial1.write(0x0c); // clear the display
  delay(10);
  Serial1.write(0x80); // col 0, row 0
  Serial1.print(" Timeout in Serial ");
  Serial1.print("Params read: ");
  Serial1.print(received_parameters);
  return 0;
}

unsigned long readULongFromBytes() {

  union u_tag {
    byte b[4];
    unsigned long ulval;
  } u;

  u.b[0] = readbyte();
  u.b[1] = readbyte();
  u.b[2] = readbyte();
  u.b[3] = readbyte();

  // debugging value indicating number of longs read
  received_parameters++;
  return u.ulval;
}
