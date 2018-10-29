/*
General functions for the control of code based serial communication with the Arduino board.
This is configured for licks to maintain compatability with the python protocol transmission standards.
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
                  water_duration1 = atoi(argument_words[2]);
                valveOnTimer(WATERVALVE1, water_duration1);
            }
            else if(water_valve == 2) {
                if(strlen(argument_words[2]) > 0)
                  water_duration2 = atoi(argument_words[2]);
                valveOnTimer(WATERVALVE2, water_duration2);
            }
          }

          // water callibration (100 water drops, 0.5ml)
          else if(strcmp(argument_words[0], "calibrate") == 0) {
            int water_valve = atoi(argument_words[1]);
            if(strlen(argument_words[2]) > 0) {
                if(water_valve == 1)  {
                  water_duration1 = atoi(argument_words[2]);
                }
                else if(water_valve == 2) {
                  water_duration2 = atoi(argument_words[2]);
                }
            }
            for(int x=0; x<=100; x=x+1) {
                if(water_valve == 1)  {
                  valveOnTimer(WATERVALVE1, water_duration1);
                }
                else if(water_valve == 2) {
                  valveOnTimer(WATERVALVE2, water_duration2);
                }
              delay(2000);
  				    Serial1.write(0x94);
              Serial1.print(F("CAL: "));
              Serial1.print(x);
            }
          }
          else if(strcmp(argument_words[0], "water_duration") == 0) {
            int water_valve = atoi(argument_words[1]);
            if(water_valve == 1)
              water_duration1 = atoi(argument_words[2]);
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
      Serial.print(F(","));
      Serial.println(F("*"));
      break;


    case 87: // streaming data has been requested

      unsigned long currenttime;
      // transmit buffer
      if( trial_done_flag && send_last_packet ){
        // send end code
        Serial.print(5);
        Serial.print(F(","));
        Serial.println(F("*"));
        trial_done_flag = false;
        send_last_packet = false;
        break;
      }
      else if(trial_done_flag) {
        // prepare to send last packet
        send_last_packet = true;
      }
      Serial.print(6);
      Serial.print(F(","));

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
      // calculate number of bytes to send for sniff, lick1 and mri_trigger.
      int sniff_sample_number; // number of sniff samples
      int sniff_bytes;
      sniff_sample_number = (current_sniff_data_index+BUFFERS-last_sent_sniff_data_index)%BUFFERS;
      sniff_bytes = sniff_sample_number * 2;

      // ----- Calculate the number of lick1 values to send and the start and stop indices ------
      // ---LICK1---
      int tail1, head1, numlick1s,lick1bytes;
      bool lick1_signal_state;
      tail1 = lick1tail;
      head1 = lick1head;
      lick1_signal_state = beam1status;
      // make sure the above two variables were assigned at the same millisecond
      while(head1 != lick1head) {
        head1 = lick1head;
        lick1_signal_state = beam1status;
      }

      if (lick1_signal_state){
        //if licking currently, won't transmit the last value, which is lick1 on with no off
        head1 = head1 - 1;
        if (head1 < 0)
          head1 = LICKBUFF + head1;
      }
      
      if(head1 < tail1)
        numlick1s = (LICKBUFF - tail1) + head1;
      else
        numlick1s = head1-tail1;
        
      lick1bytes = numlick1s*4;


       // ---LICK2---
      int tail2, head2, numlick2s,lick2bytes;
      bool lick2_signal_state;
      tail2 = lick2tail;
      head2 = lick2head;
      lick2_signal_state = beam2status;
      // make sure the above two variables were assigned at the same millisecond
      while(head2 != lick2head) {
        head2 = lick2head;
        lick2_signal_state = beam2status;
      }

      if (lick2_signal_state){
        //if licking currently, won't transmit the last value, which is lick on with no off
        head2 = head2 - 1;
        if (head2 < 0)
          head2 = LICKBUFF + head2;
      }
      
      if(head2 < tail2)
        numlick2s = (LICKBUFF - tail2) + head2;
      else
        numlick2s = head2-tail2;
        
      lick2bytes = numlick2s*4;
           

      // ---MRI TRIGGER---
      int tail3, head3, nummris,mribytes;
      bool mri_signal_state;
      tail3 = mritail;
      head3 = mrihead;
      mri_signal_state = beam3status;
      // make sure the above two variables were assigned at the same millisecond
      while(head3 != mrihead) {
        head3 = mrihead;
        mri_signal_state = beam3status;
      }
            
      if(head3 < tail3)
        nummris = (MRIBUFF - tail3) + head3;
      else
        nummris = head3-tail3;
        
      mribytes = nummris*4;
      
      // SEND HEADER INFORMATION: NUMBER STREAMS, NUMBER OF PACKETS PER STREAM
      Serial.print(6); // number of streams to send
      Serial.print(F(","));
      Serial.print(4); //number of bytes for mstream 1 (packet_sent_time)
      Serial.print(F(","));
      Serial.print(2); //number of bytes for sniff_samples (single integer)
      Serial.print(F(","));
      Serial.print(sniff_bytes); //number of bytes for actual sniff stream.
      Serial.print(F(","));
      Serial.print(lick1bytes);
      Serial.print(F(","));
      Serial.print(lick2bytes);
      Serial.print(F(","));
      Serial.println(mribytes); //number of bytes for actual mri stream.

      // end line here so that python will read and parse the handshake. Then...
      // ----- SEND ACTUAL DATA AS BINARY -----------------
      sendLongAsBytes(currenttime);
      sendShortAsBytes(sniff_sample_number);
      
      while(last_sent_sniff_data_index != current_sniff_data_index) {
        last_sent_sniff_data_index = (last_sent_sniff_data_index+1)%BUFFERS;
        sendShortAsBytes(sniff[last_sent_sniff_data_index]);
      }

      while(tail1!= head1)  {
        sendLongAsBytes(lick1[tail1]);
        tail1 = (tail1+1)%(LICKBUFF);
      }
      // move the ring buffer tail index to current untransmitted tail index
      lick1tail = tail1;


      while(tail2!= head2)  {
        sendLongAsBytes(lick2[tail2]);
        tail2 = (tail2+1)%(LICKBUFF);
      }
      // move the ring buffer tail index to current untransmitted tail index
      lick2tail = tail2;

      
      while(tail3!=head3)  {
        sendLongAsBytes(mri[tail3]);
        tail3 = (tail3+1)%(MRIBUFF);
      }
      mritail = tail3;

      
      break;
   case 88: // trail ended and the trial details were requested
      // tell the monitor about the trial details
      Serial.print(4);
      Serial.print(F(","));
      Serial.print(parameters_received_time);
      Serial.print(F(","));
      Serial.print(trial_start);
      Serial.print(F(","));
      Serial.print(trial_end);
      Serial.print(F(","));
      Serial.print(final_valve_onset);
      Serial.print(F(","));
      Serial.print(response);
      Serial.print(F(","));
      Serial.print(first_lick);
      Serial.print(F(","));
      Serial.print(mri_onset);
      Serial.print(F(","));
      Serial.println(F("*"));
      break;

    case 90: // Start trial state (i.e. need to read from the serial port)

      received_parameters = 0;
      final_valve_duration = readULongFromBytes();
      response_window = readULongFromBytes();
      inter_trial_interval = readULongFromBytes();
      odorant_trigger_phase = readULongFromBytes();
      trial_type = readULongFromBytes();     
      lick_grace_period = readULongFromBytes();
      hrf_phase = readULongFromBytes();
      tr = readULongFromBytes();
      licking_training = readULongFromBytes();

      Serial.print(2);
      Serial.print(F(","));
      Serial.println(F("*"));
      break;

    case 91:
      Serial.print(6);
      Serial.print(F(","));
      Serial.print(protocolName);
      Serial.print(F(","));
      Serial.println(F("*"));
      break;

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
  // attempt reading the serial for 50ms
  while(totalms-temp1 < 50)  {
    if(Serial.available() > 0)
      return Serial.read();
  }
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
