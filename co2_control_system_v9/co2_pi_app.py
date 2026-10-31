#!/usr/bin/env python3
import csv, glob, os, re, threading, time, queue
from logging_system.experiment_manager import ExperimentManager
from logging_system.logger import DataLogger
from sensors.weather import WeatherStation
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox
try:
    import serial
except ImportError:
    serial = None

BAUD=115200
COMM_TIMEOUT=5.0
HEARTBEAT_INTERVAL=1.0
WEATHER_INTERVAL = 30.0
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
        super().__init__()
        self.experiment_manager = ExperimentManager()
        self.experiment_active = False
        self.experiment_stopping = False
        self.weather_station = None
        self.weather_logger = None
        self.weather_thread = None
        self.last_weather_timestamp = None
        self.status_log_lock = threading.Lock()
        self.finalization_in_progress = False
        self.weather_stop_event = threading.Event()
        self.title('CO2 System Control'); self.minsize(900,600); self.state_data={}; self.devices={}; self.current_phase='IDLE'; self.logging=False; self.csvfile=None; self.writer=None; self.pi_g=0.0; self.prev_gps=None; self.prev_ms=None; self.note=tk.StringVar(); self.times=[tk.StringVar(value=x) for x in ('04:00:00','00:00:55','00:55:00')]; self.sync_send_time=None; self.sync_time=None; self.sync_arduino_start_ms=None; self.pending_desorb_start=False; self.last_heartbeat=0.0; self.reset_pending=False; self.reset_deadline=0.0; self.last_control_message=tk.StringVar(value='Controller response: --'); self.safety_vars=[tk.StringVar(value=x) for x in ('150.0','30.0','00:05:00','0.0','00:05:00','00:00:15')]
        self.build(); self.after(100,self.poll); threading.Thread(target=self.discover,daemon=True).start()

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
        self.retry_finalize_button = ttk.Button(
            self.over,
            text="RETRY FINALIZATION",
            command=self.retry_finalize_experiment,
            state="disabled"
        )
        self.retry_finalize_button.pack(pady=5)
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
        ttk.Label(self.settings,text='CSV folder: ' + str(self.experiment_manager.data_dir)).pack(pady=10)
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

        if role == 'CONTROL' and (
            line.startswith('ERROR,')
            or line.startswith('OK,')
            or line.startswith('EMERGENCY,')
            or line.startswith('SHUTDOWN,')
        ):
            self.last_control_message.set('Controller response: ' + line)

            if line == 'SHUTDOWN,EVACUATION_STARTED':
                self.experiment_stopping = True
                self.log_status('CONTROL', line)
                self.send('DATA', 'STOP_LOG')
                self.close_csv()
                print("Normal shutdown evacuation started.")

            elif line == 'SHUTDOWN,COMPLETE':
                self.log_status('CONTROL', line)
                self.finalize_experiment('completed')

            elif line == 'EMERGENCY,LOCKOUT':
                self.log_status('CONTROL', line)
                self.finalize_experiment('aborted')

            elif line == 'EMERGENCY,EVACUATION_STARTED':
                self.experiment_stopping = True
                self.log_status('CONTROL', line)
                self.send('DATA', 'STOP_LOG')
                self.close_csv()
                print("Emergency evacuation started. Weather collection continues.")

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
        self.pi_g = 0
        self.prev_gps = None
        self.prev_ms = None

        if not self.experiment_active:
            messagebox.showerror(
                "CO2 Logging Error",
                "Cannot start CO2 logging: no active experiment."
            )
            return

        path = self.experiment_manager.get_file_path("co2")
        file_is_empty = not os.path.exists(path) or os.path.getsize(path) == 0
        self.csvfile = open(path, 'a', newline='', encoding='utf-8')
        self.writer = csv.writer(self.csvfile)

        if file_is_empty:
            self.writer.writerow([
                'Calculated Timestamp',
                'Pi Receive Timestamp',
                'Arduino Elapsed (ms)',
                'Estimated Latency (ms)',
                'CO2 (%)',
                'Flow (SLPM)',
                'Arduino CO2 (g)',
                'Pi CO2 (g)',
                'Difference (g)',
                'Arduino CO2 (mol)',
                'Pi CO2 (mol)'
            ])
            self.csvfile.flush()

        self.logging = True
        self.filelabel.set('Recording: ' + str(path))

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

    def log_status(self, device, message):
        if not self.experiment_active:
            return

        try:
            status_path = self.experiment_manager.get_file_path("status")

            timestamp = datetime.now().astimezone().isoformat(
                timespec="milliseconds"
            )

            with self.status_log_lock:
                with open(status_path, "a", newline="", encoding="utf-8") as file:
                    writer = csv.writer(file)
                    writer.writerow([timestamp, device, message])
                    file.flush()

        except Exception as e:
            print("Status logging error:", e)

    def weather_loop(self):
        while not self.weather_stop_event.is_set():
            try:
                data = self.weather_station.read_data()

                if self.weather_station.validate_data(data):
                    timestamp = data["timestamp"]

                    if timestamp != self.last_weather_timestamp:
                        self.weather_logger.log_weather(data)
                        self.last_weather_timestamp = timestamp
                        print("New weather data recorded:", timestamp)
                    else:
                        print("Duplicate weather data skipped:", timestamp)
                else:
                    print("Invalid weather data skipped.")

            except Exception as e:
                print("Weather data collection error:", e)

            self.weather_stop_event.wait(WEATHER_INTERVAL)

    def start(self):
        if self.experiment_active:
            messagebox.showwarning("Warning", "An experiment is already running.")
            return

        try:
            self.experiment_manager.start_experiment(
                experiment_name=self.note.get().strip()
            )
            self.experiment_active = True

        except Exception as e:
            messagebox.showerror(
                "Experiment Start Error",
                f"Could not start experiment:\n{e}"
            )
            return

        # Initialize weather data collection
        try:
            self.weather_stop_event.clear()

            self.weather_station = WeatherStation()

            weather_path = self.experiment_manager.get_file_path("weather")
            self.weather_logger = DataLogger(str(weather_path))

            self.weather_thread = threading.Thread(
                target=self.weather_loop,
                daemon=True
            )
            self.weather_thread.start()

            print("Weather data collection started.")

        except Exception as e:
            self.weather_station = None
            self.weather_logger = None
            self.weather_thread = None

            print("Weather initialization failed:", e)
            messagebox.showwarning(
                "Weather Collection Warning",
                f"Weather collection could not start:\n{e}\n\n"
                "The CO2 experiment will continue without weather data."
            )
        self.send('CONTROL', 'MODE,AUTO')
        self.after(150, lambda: self.send('CONTROL', 'START'))

    def finalize_experiment(self, status):
        if self.finalization_in_progress:
            return

        if not self.experiment_active:
            return

        if status not in ("completed", "aborted"):
            raise ValueError("Invalid experiment finalization status.")

        self.finalization_in_progress = True

        print(f"Finalizing experiment: {status}")

        # Stop weather collection
        self.weather_stop_event.set()

        # Wait until the weather thread exits
        self.wait_for_weather_thread(status)

    def _cleanup_experiment_collection(self):
        """
        Stop CO2 logging and release local weather collection resources.
        This operation can be retried if cleanup fails.
        """
        # Request the DATA Arduino to stop logging.
        # Note: send() does not confirm that the Arduino received the command.
        self.send('DATA', 'STOP_LOG')

        # Close the local CO2 CSV file.
        self.close_csv()

        # Clear weather collection references only after cleanup succeeds.
        self.weather_station = None
        self.weather_logger = None
        self.weather_thread = None
        self.last_weather_timestamp = None


    def retry_finalize_experiment(self):
        if self.finalization_in_progress:
            return

        status = getattr(self, "pending_finalization_status", None)
        stage = getattr(self, "pending_finalization_stage", None)

        if status not in ("completed", "aborted"):
            return

        if stage not in ("cleanup", "metadata"):
            return

        self.finalization_in_progress = True

        try:
            # Retry cleanup only if the previous cleanup failed.
            if stage == "cleanup":
                self._cleanup_experiment_collection()
                self.pending_finalization_stage = "metadata"

            # Save final experiment metadata.
            self.experiment_manager.end_experiment(status=status)

            # All finalization steps succeeded.
            self.experiment_active = False
            self.experiment_stopping = False
            self.pending_finalization_status = None
            self.pending_finalization_stage = None

            self.retry_finalize_button.config(state="disabled")

            print(f"Experiment finalized after retry: {status}")

        except Exception as e:
            self.finalization_in_progress = False

            if getattr(self, "pending_finalization_stage", None) == "cleanup":
                messagebox.showerror(
                    "Cleanup Retry Failed",
                    f"Could not complete experiment cleanup:\n{e}\n\n"
                    "You can retry finalization again."
                )
            else:
                self.pending_finalization_stage = "metadata"

                messagebox.showerror(
                    "Metadata Save Retry Failed",
                    f"Could not save experiment metadata:\n{e}\n\n"
                    "You can retry finalization again."
                )

            return

        self.finalization_in_progress = False


    def wait_for_weather_thread(self, status):
        if self.weather_thread and self.weather_thread.is_alive():
            self.after(
                100,
                lambda: self.wait_for_weather_thread(status)
            )
            return

        try:
            # First complete local cleanup.
            self._cleanup_experiment_collection()

        except Exception as e:
            self.pending_finalization_status = status
            self.pending_finalization_stage = "cleanup"
            self.finalization_in_progress = False

            self.retry_finalize_button.config(state="normal")

            messagebox.showerror(
                "Experiment Cleanup Error",
                f"Experiment cleanup could not be completed:\n{e}\n\n"
                "Click RETRY FINALIZATION to try again."
            )
            return

        # Cleanup succeeded. Metadata saving is now a separate stage.
        self.pending_finalization_stage = "metadata"

        try:
            self.experiment_manager.end_experiment(status=status)

        except Exception as e:
            self.pending_finalization_status = status
            self.finalization_in_progress = False

            self.retry_finalize_button.config(state="normal")

            messagebox.showerror(
                "Experiment Metadata Save Error",
                f"Experiment cleanup succeeded, "
                f"but metadata could not be saved:\n{e}\n\n"
                "Click RETRY FINALIZATION to try again."
            )
            return

        # All finalization steps succeeded.
        self.experiment_active = False
        self.experiment_stopping = False
        self.pending_finalization_status = None
        self.pending_finalization_stage = None

        self.retry_finalize_button.config(state="disabled")

        self.finalization_in_progress = False

        print(f"Experiment finalized: {status}")

    def stop(self):
        if not self.experiment_active:
            return

        if self.experiment_stopping:
            print("Experiment is already stopping.")
            return

        control_device = self.devices.get('CONTROL')

        if not control_device or not control_device.alive:
            messagebox.showwarning(
                "Communication Error",
                "Cannot stop the experiment: CONTROL Arduino is disconnected."
            )
            self.log_status(
                "CONTROL",
                "STOP_REQUEST_FAILED: controller disconnected"
            )
            return

        self.experiment_stopping = True

        self.log_status("CONTROL", "STOP_REQUESTED")

        self.send('CONTROL', 'STOP')

        print("Stop requested. Waiting for Arduino evacuation to complete.")

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
