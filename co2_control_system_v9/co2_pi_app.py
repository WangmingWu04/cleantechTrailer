#!/usr/bin/env python3
import csv, glob, os, re, threading, time, queue
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox
try:
    import serial
except ImportError:
    serial = None

BAUD=115200
DATA_DIR=os.path.expanduser('~/CO2_Data')
COMM_TIMEOUT=5.0
HEARTBEAT_INTERVAL=1.0
CO2_MOLAR_MASS=44.01
MOLAR_VOLUME_STP=22.414
CO2_G_PER_SL=CO2_MOLAR_MASS/MOLAR_VOLUME_STP

class Device:
    def __init__(self,port,role,ser): self.port,self.role,self.ser=port,role,ser; self.last=time.monotonic(); self.q=queue.Queue(); self.alive=True
    def send(self,s):
        try:self.ser.write((s+'\n').encode())
        except Exception: self.alive=False

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('CO2 System Control'); self.minsize(900,600); self.state_data={}; self.devices={}; self.current_phase='IDLE'; self.logging=False; self.csvfile=None; self.writer=None; self.pi_g=0.0; self.prev_gps=None; self.prev_ms=None; self.note=tk.StringVar(); self.times=[tk.StringVar(value=x) for x in ('04:00:00','00:00:55','00:55:00')]; self.sync_send_time=None; self.sync_time=None; self.sync_arduino_start_ms=None; self.pending_desorb_start=False; self.last_heartbeat=0.0; self.reset_pending=False; self.reset_deadline=0.0; self.last_control_message=tk.StringVar(value='Controller response: --'); self.safety_vars=[tk.StringVar(value=x) for x in ('150.0','30.0','00:05:00','0.0','00:05:00','00:00:15')]
        os.makedirs(DATA_DIR,exist_ok=True); self.build(); self.after(100,self.poll); threading.Thread(target=self.discover,daemon=True).start()
    def build(self):
        style=ttk.Style(); style.configure('Big.TLabel',font=('TkDefaultFont',20,'bold')); style.configure('Value.TLabel',font=('TkDefaultFont',16))
        nb=ttk.Notebook(self); nb.pack(fill='both',expand=True,padx=8,pady=8)
        self.over=ttk.Frame(nb); self.manual=ttk.Frame(nb); self.data=ttk.Frame(nb); self.settings=ttk.Frame(nb)
        for f,n in [(self.over,'Overview'),(self.manual,'Manual Control'),(self.data,'Data'),(self.settings,'Settings')]: nb.add(f,text=n)
        self.status=tk.StringVar(value='Discovering Arduinos...'); ttk.Label(self.over,textvariable=self.status,style='Big.TLabel').pack(pady=20)
        self.phase=tk.StringVar(value='State: IDLE'); ttk.Label(self.over,textvariable=self.phase,style='Value.TLabel').pack(pady=8)
        self.safety=tk.StringVar(value='Safety: UNKNOWN'); ttk.Label(self.over,textvariable=self.safety,style='Value.TLabel').pack(pady=8)
        self.sensors=tk.StringVar(value='Temp -- C   RH -- %   Pressure -- psig'); ttk.Label(self.over,textvariable=self.sensors,style='Value.TLabel').pack(pady=8)
        ttk.Label(self.over,textvariable=self.last_control_message).pack(pady=4)
        b=ttk.Frame(self.over);b.pack(pady=25);ttk.Button(b,text='START',command=self.start).grid(row=0,column=0,padx=20,ipadx=30,ipady=15);ttk.Button(b,text='STOP / SHUTDOWN',command=self.stop).grid(row=0,column=1,padx=20,ipadx=20,ipady=15);ttk.Button(b,text='RESET SYSTEM',command=self.reset).grid(row=0,column=2,padx=20,ipadx=20,ipady=15)
        ttk.Label(self.manual,text='Manual controls require MODE,MANUAL and physical switch ON.',style='Value.TLabel').pack(pady=15)
        grid=ttk.Frame(self.manual);grid.pack(pady=10)
        for r,name in enumerate(['ADSORB','DESORB','BELLOWS_EVAC','BELLOWS_TANK','VACUUM','STATE_CHANGE']):
            ttk.Label(grid,text=name,width=18).grid(row=r,column=0,padx=5,pady=5);ttk.Button(grid,text='ON',command=lambda n=name:self.output(n,1)).grid(row=r,column=1,padx=5);ttk.Button(grid,text='OFF',command=lambda n=name:self.output(n,0)).grid(row=r,column=2,padx=5)
        ttk.Button(self.manual,text='Enter Manual Mode',command=lambda:self.send('CONTROL','MODE,MANUAL')).pack(pady=10);ttk.Button(self.manual,text='Return Auto Mode',command=lambda:self.send('CONTROL','MODE,AUTO')).pack()
        self.live=tk.StringVar(value='CO2 -- %    Flow -- SLPM'); ttk.Label(self.data,textvariable=self.live,style='Big.TLabel').pack(pady=20)
        self.totals=tk.StringVar(value='Pi CO2: -- g    Arduino CO2: -- g'); ttk.Label(self.data,textvariable=self.totals,style='Value.TLabel').pack(pady=10)
        self.filelabel=tk.StringVar(value='Logging: waiting for desorption'); ttk.Label(self.data,textvariable=self.filelabel).pack(pady=10)
        self.timing=tk.StringVar(value='Timing: waiting for synchronization'); ttk.Label(self.data,textvariable=self.timing).pack(pady=5)
        ttk.Label(self.data,text='Optional run name / notes for filename:').pack(); ttk.Entry(self.data,textvariable=self.note,width=60).pack(pady=5)
        form=ttk.Frame(self.settings);form.pack(pady=30)
        for i,(name,var) in enumerate(zip(['Adsorb','Evacuation','Desorption'],self.times)):
            ttk.Label(form,text=name+' (HH:MM:SS)').grid(row=i,column=0,padx=10,pady=10);ttk.Entry(form,textvariable=var,width=12).grid(row=i,column=1,padx=10)
        ttk.Button(form,text='Apply Cycle Settings',command=self.apply_times).grid(row=3,column=0,columnspan=2,pady=20)
        safety_box=ttk.LabelFrame(self.settings,text='Safety Settings'); safety_box.pack(fill='x',padx=30,pady=15)
        safety_labels=['MAX6675 temperature limit (C)','Incoming humidity limit (% RH)','Humidity trip delay (HH:MM:SS)','Desorption pressure limit (psig)','Pressure trip delay (HH:MM:SS)','Sensor reporting loss delay (HH:MM:SS)']
        for i,(label,var) in enumerate(zip(safety_labels,self.safety_vars)):
            ttk.Label(safety_box,text=label).grid(row=i,column=0,sticky='w',padx=10,pady=6); ttk.Entry(safety_box,textvariable=var,width=14).grid(row=i,column=1,padx=10,pady=6)
        ttk.Button(safety_box,text='Apply Safety Settings',command=self.apply_safety).grid(row=len(safety_labels),column=0,columnspan=2,pady=12)
        self.safety_config_status=tk.StringVar(value='Active safety configuration: waiting for SAFETY Arduino')
        ttk.Label(safety_box,textvariable=self.safety_config_status).grid(row=len(safety_labels)+1,column=0,columnspan=2,padx=10,pady=6)
        ttk.Label(self.settings,text='Safety settings are applied to the SAFETY Arduino for the current powered session.').pack(pady=4)
        ttk.Label(self.settings,text='CSV folder: '+DATA_DIR).pack(pady=10)
    def discover(self):
        if serial is None: self.status.set('pyserial is not installed'); return
        while True:
            for port in glob.glob('/dev/ttyACM*')+glob.glob('/dev/ttyUSB*'):
                if any(d.port==port and d.alive for d in self.devices.values()): continue
                try:
                    # Opening an Arduino USB serial port can reset the board. Open the
                    # candidate ONCE, keep it open through startup, and retry IDENTIFY
                    # on this same serial session. Closing/reopening here can create an
                    # endless reset loop, especially on the DATA Arduino.
                    s=serial.Serial(port,BAUD,timeout=.20)
                    role=None
                    startup_deadline=time.monotonic()+3.0
                    while time.monotonic()<startup_deadline:
                        # Preserve the same open connection while the Arduino reboots.
                        line=s.readline().decode(errors='ignore').strip()
                        if line.startswith('ID,'):
                            role=line.split(',',1)[1]
                            break

                    identify_deadline=time.monotonic()+6.0
                    next_identify=0.0
                    while role is None and time.monotonic()<identify_deadline:
                        now_id=time.monotonic()
                        if now_id>=next_identify:
                            s.write(b'IDENTIFY\n')
                            s.flush()
                            next_identify=now_id+0.75
                        line=s.readline().decode(errors='ignore').strip()
                        if line.startswith('ID,'):
                            role=line.split(',',1)[1]
                            break
                        # READY,<role> is useful startup evidence, but still request ID
                        # so all controllers use the same identification protocol.

                    if role in ('CONTROL','DATA','SAFETY'):
                        # Hand the SAME already-open serial object to normal operation.
                        d=Device(port,role,s)
                        self.devices[role]=d
                        threading.Thread(target=self.reader,args=(d,),daemon=True).start()
                        if role=='SAFETY':
                            self.after(100,lambda:self.send('SAFETY','GET_CONFIG'))
                    else:
                        # Only abandon a port after the full held-open identification
                        # window has expired. It will not be immediately hammered by
                        # rapid reopen cycles because discovery itself sleeps below.
                        s.close()
                except Exception:
                    try:
                        s.close()
                    except Exception:
                        pass
            time.sleep(2)
    def reader(self,d):
        while d.alive:
            try:
                line=d.ser.readline().decode(errors='ignore').strip()
                if line:d.last=time.monotonic();d.q.put(line)
            except Exception:d.alive=False
    def send(self,role,cmd):
        d=self.devices.get(role)
        if d and d.alive:d.send(cmd)
    def poll(self):
        now=time.monotonic(); connected=[]
        # Heartbeat: all three Arduinos answer GET_STATUS. This keeps last-seen
        # timestamps current even when the process state itself is not changing.
        if now-self.last_heartbeat >= HEARTBEAT_INTERVAL:
            self.last_heartbeat=now
            for role in ('CONTROL','DATA','SAFETY'):
                self.send(role,'GET_STATUS')
        for role,d in list(self.devices.items()):
            while not d.q.empty(): self.handle(role,d.q.get())
            if d.alive and now-d.last<COMM_TIMEOUT: connected.append(role)
        missing=[x for x in ('CONTROL','DATA','SAFETY') if x not in connected]
        # Remove dead serial objects so discovery can reopen the port.
        for role,d in list(self.devices.items()):
            if not d.alive:
                try:d.ser.close()
                except Exception:pass
                self.devices.pop(role,None)
        self.status.set('Connected: '+', '.join(connected)+(('   LOST: '+', '.join(missing)) if missing else ''))
        # Pi communication-loss detection: prominently flag it. Hardware safety remains independent.
        if 'CONTROL' in missing or 'SAFETY' in missing:self.safety.set('COMMUNICATION FAULT - check CONTROL/SAFETY connection')
        self.after(100,self.poll)
    def handle(self,role,line):
        p=line.split(',')
        if role=='CONTROL' and (line.startswith('ERROR,') or line.startswith('OK,') or line.startswith('EMERGENCY,') or line.startswith('SHUTDOWN,')):
            self.last_control_message.set('Controller response: '+line)
        if role=='CONTROL':
            if line.startswith('STATE,'):
                phase=p[1]; self.set_phase(phase)
            elif line.startswith('STATUS,CONTROL') and len(p)>4:
                phase=p[4];
                if phase in ('ADSORB','EVACUATION','DESORB') and phase!=self.current_phase:self.set_phase(phase)
                self.phase.set('State: '+p[3]+' / '+phase+'   Remaining: '+self.hms(int(p[5]) if len(p)>5 and p[5].isdigit() else 0))
        elif role=='SAFETY' and line.startswith('STATUS,SAFETY'):
            try:self.safety.set('Safety: '+p[2]);self.sensors.set(f'MAX6675 {p[3]} C   Pressure {p[4]} psig   Inlet {p[5]} C   RH {p[6]} %')
            except:pass
        elif role=='SAFETY' and line.startswith('OK,SAFETY_RESET'):
            self.safety.set('Safety: reset accepted; verifying interlock...')
            if self.reset_pending:
                self.after(250,self.verify_safety_reset)
        elif role=='SAFETY' and line.startswith('ERROR,'):
            self.safety.set('Safety reset/config response: '+line)
            if self.reset_pending:
                self.reset_pending=False
                messagebox.showerror('Reset blocked','Safety Arduino rejected reset:\n'+line)
        elif role=='SAFETY' and line.startswith('CONFIG,SAFETY,'):
            self.handle_safety_config(p)
        elif role=='DATA' and line.startswith('LOG_STARTED,'): self.finish_log_sync(p)
        elif role=='DATA' and line.startswith('LIVE,'): self.live_data(p)
        elif role=='DATA' and line.startswith('STATUS,DATA') and len(p)>5:
            try:
                if p[4] != 'NA': self.live.set(f'CO2 {float(p[4]):.4f} %    Flow {float(p[5]):.4f} SLPM')
            except (ValueError, IndexError): pass
        elif role=='DATA' and line.startswith('DATA,'): self.data_row(p)
    def set_phase(self,phase):
        old=self.current_phase; self.current_phase=phase
        safety_phase = phase if phase in ('ADSORB','EVACUATION','DESORB') else 'IDLE'
        self.send('SAFETY','PHASE,'+safety_phase)
        if phase=='DESORB' and old!='DESORB':
            self.begin_log_sync()
        elif old=='DESORB' and phase!='DESORB':
            self.send('DATA','STOP_LOG'); self.close_csv()
    def begin_log_sync(self):
        self.pending_desorb_start=True
        self.sync_time=None
        self.sync_arduino_start_ms=None
        self.sync_send_time=datetime.now().astimezone()
        self.timing.set('Timing: synchronizing with DATA Arduino...')
        self.send('DATA','START_LOG')
    def finish_log_sync(self,p):
        if not self.pending_desorb_start or len(p)<2: return
        try: arduino_start=int(p[1])
        except ValueError: return
        receive_time=datetime.now().astimezone()
        if self.sync_send_time is None: self.sync_send_time=receive_time
        self.sync_time=self.sync_send_time+(receive_time-self.sync_send_time)/2
        self.sync_arduino_start_ms=arduino_start
        self.pending_desorb_start=False
        rtt_ms=(receive_time-self.sync_send_time).total_seconds()*1000.0
        self.open_csv()
        self.timing.set(f'Timing: SYNCHRONIZED   START RTT {rtt_ms:.1f} ms')
    def open_csv(self):
        self.pi_g=0;self.prev_gps=None;self.prev_ms=None
        base_time=self.sync_time or datetime.now().astimezone()
        stamp=base_time.strftime('%Y-%m-%d_%H-%M-%S')
        note=re.sub(r'[^A-Za-z0-9_-]+','_',self.note.get().strip()).strip('_')
        name=stamp+('_'+note if note else '')+'_Desorb.csv'
        path=os.path.join(DATA_DIR,name)
        self.csvfile=open(path,'w',newline='')
        self.writer=csv.writer(self.csvfile)
        self.writer.writerow(['Calculated Timestamp','Pi Receive Timestamp','Arduino Elapsed (ms)','Estimated Latency (ms)','CO2 (%)','Flow (SLPM)','Arduino CO2 (g)','Pi CO2 (g)','Difference (g)','Arduino CO2 (mol)','Pi CO2 (mol)'])
        self.logging=True
        self.filelabel.set('Recording: '+path)
    def close_csv(self):
        self.logging=False
        if self.csvfile:self.csvfile.close();self.csvfile=None;self.writer=None
    def live_data(self,p):
        try:
            co2=float(p[1]); flow=float(p[2])
            self.live.set(f'CO2 {co2:.4f} %    Flow {flow:.4f} SLPM')
        except (ValueError, IndexError):
            pass

    def data_row(self,p):
        try:
            ms=int(p[1]);co2=float(p[2]);flow=float(p[3]);ag=float(p[4]);am=float(p[5])
            receive_time=datetime.now().astimezone()
            gps=(co2/100.0)*(flow/60.0)*CO2_G_PER_SL
            if self.prev_gps is not None and self.prev_ms is not None and ms>=self.prev_ms:
                self.pi_g+=(self.prev_gps+gps)/2.0*((ms-self.prev_ms)/1000.0)
            self.prev_gps,self.prev_ms=gps,ms
            pm=self.pi_g/CO2_MOLAR_MASS
            if self.sync_time is not None:
                calculated_time=self.sync_time+timedelta(milliseconds=ms)
                latency_ms=(receive_time-calculated_time).total_seconds()*1000.0
            else:
                calculated_time=receive_time
                latency_ms=0.0
            self.live.set(f'CO2 {co2:.4f} %    Flow {flow:.4f} SLPM')
            self.totals.set(f'Pi CO2: {self.pi_g:.6f} g    Arduino CO2: {ag:.6f} g    Difference: {ag-self.pi_g:+.6f} g')
            self.timing.set(f'Timing: SYNCHRONIZED   Arduino {ms/1000:.3f} s   Serial latency {latency_ms:.1f} ms')
            if self.logging and self.writer:
                self.writer.writerow([calculated_time.isoformat(timespec='milliseconds'),receive_time.isoformat(timespec='milliseconds'),ms,round(latency_ms,3),co2,flow,ag,self.pi_g,ag-self.pi_g,am,pm])
                self.csvfile.flush()
        except Exception: pass
    def handle_safety_config(self,p):
        try:
            temp,rh,rh_s,press,press_s,loss_s=p[2:8]
            vals=[temp,rh,self.hms(int(rh_s)),press,self.hms(int(press_s)),self.hms(int(loss_s))]
            for var,val in zip(self.safety_vars,vals): var.set(val)
            self.safety_config_status.set(f'Active: Temp > {float(temp):g} C | RH > {float(rh):g}% for {self.hms(int(rh_s))} | Desorb pressure >= {float(press):g} psig for {self.hms(int(press_s))} | Sensor loss {self.hms(int(loss_s))}')
        except Exception:
            self.safety_config_status.set('Active safety configuration: invalid response')
    def apply_safety(self):
        try:
            temp=float(self.safety_vars[0].get()); rh=float(self.safety_vars[1].get()); rh_s=self.to_s(self.safety_vars[2].get()); press=float(self.safety_vars[3].get()); press_s=self.to_s(self.safety_vars[4].get()); loss_s=self.to_s(self.safety_vars[5].get())
            if temp<=0 or rh<0 or rh>100 or rh_s<=0 or press_s<=0 or loss_s<=0: raise ValueError
            self.send('SAFETY',f'SET_SAFETY,{temp},{rh},{rh_s},{press},{press_s},{loss_s}')
            self.after(250,lambda:self.send('SAFETY','GET_CONFIG'))
        except ValueError:
            messagebox.showerror('Invalid safety setting','Check the safety limits and use HH:MM:SS for all safety delays.')
    def start(self): self.send('CONTROL','MODE,AUTO');self.after(150,lambda:self.send('CONTROL','START'))
    def stop(self): self.send('CONTROL','STOP')
    def reset(self):
        if self.reset_pending: return
        self.reset_pending=True
        self.reset_deadline=time.monotonic()+5.0
        self.safety.set('Safety: reset requested...')
        self.send('SAFETY','RESET_ERROR')
        self.after(1000,self.reset_timeout_check)
    def verify_safety_reset(self):
        if not self.reset_pending: return
        self.send('SAFETY','GET_STATUS')
        self.after(300,self.finish_reset_if_safe)
    def finish_reset_if_safe(self):
        if not self.reset_pending: return
        # SAFETY reset acknowledgement guarantees D5 was commanded LOW. Give the hardwired line time to settle.
        self.send('CONTROL','RESET_ERROR')
        self.reset_pending=False
        self.last_control_message.set('Controller response: reset sent after SAFETY confirmation')
    def reset_timeout_check(self):
        if self.reset_pending and time.monotonic()>=self.reset_deadline:
            self.reset_pending=False
            messagebox.showerror('Reset timeout','No SAFETY reset acknowledgement was received. Check the Safety Arduino and active fault conditions.')
    def output(self,n,v): self.send('CONTROL',f'SET_OUTPUT,{n},{v}')
    def apply_times(self):
        try: vals=[self.to_s(v.get()) for v in self.times];self.send('CONTROL','SET_TIMES,'+','.join(map(str,vals)))
        except ValueError: messagebox.showerror('Invalid time','Use HH:MM:SS for all three times.')
    @staticmethod
    def to_s(x):
        h,m,s=map(int,x.split(':'))
        if m>59 or s>59 or min(h,m,s)<0:raise ValueError
        return h*3600+m*60+s
    @staticmethod
    def hms(s):return f'{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}'

if __name__=='__main__': App().mainloop()
