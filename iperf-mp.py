#!/usr/bin/python2

import ConfigParser as configparser
import Queue as queue
import smtplib
import threading
import time
import syslog

import socket
import pickle
import subprocess


# thread class to run a command
class CmdCommands(threading.Thread):
    def __init__(self, icmd, iqueue, iparameters):
        threading.Thread.__init__(self)
        self.cmd = icmd
        self.queue = iqueue
        self.parameters = iparameters

    def run(self):
        if self.parameters["wait_extra"] > self.parameters["wait_time"]:
            # print("waiting " + str(self.parameters["wait_extra"]))
            time.sleep(self.parameters["wait_extra"])

            # return  wait_extra parameter to default wait_time
            self.parameters["wait_extra"] = self.parameters["wait_time"]
        else:
            if self.parameters["wait_time"] > 0:
                # print("waiting " + str(self.parameters["wait_time"]))
                time.sleep(self.parameters["wait_time"])


        try:
            ioutput = subprocess.check_output(self.cmd, stderr=subprocess.STDOUT, shell=True)
        except subprocess.CalledProcessError as e:
            ioutput = e.output
        istatus = 0
        self.queue.put((self.cmd, ioutput, istatus, self.parameters))


class LowLevelLoop(threading.Thread):
    def __init__(self, iqueue, queue2, mainthread):
        threading.Thread.__init__(self)
        self.queue = iqueue
        self.zbxqueue = queue2
        self.mthread = mainthread

    def run(self):

        errortimer = 0
        # execute the command, queue the result
        # one thread is this thread, otherhread is main thread so 2 will alive with  no job
        while self.mthread.is_alive():

            while not operational_queue.empty():
                operational_item = operational_queue.get()

                try:

                    if "Interval           Transfer     Bandwidth" in str(operational_item[0]) and "error" not in \
                            str(operational_item[0]):
                        par = operational_item[1]

                        lines = str(operational_item[0]).split("\n")

                        a = lines[-5].split()

                        speed_limit = int(par["min_bandwidth"]) * 1024
                        email = par["mail"]
                        # prepairing data for zabbix queue: name address minbandwidth

                        zabbix_data = [par["section"], par["ip"], a[6], speed_limit]
                        # checking that zabbix queue is not bigger than threads count*3 and putting new data on it
                        if self.zbxqueue.qsize() < (threading.active_count() * 3):
                            self.zbxqueue.put(zabbix_data)
                        else:
                            self.zbxqueue.get()
                            self.zbxqueue.put(zabbix_data)

                        msg = "[" + par["section"] + "] - current speed : " + a[6] + " " + a[
                            7] + ", speed lim: " + str(speed_limit) + " " + a[7] + " destIP: " + par["ip"]

                        if int(a[6]) < speed_limit:
                            status_msg = "  Status ALERT"
                            if global_mail_timer_hash[par["section"]] == 0:
                                syslog.syslog("im going to send mail just debug")
                                send_email(email, "ALERT :" + msg + str(" " + par["prefix"]), msg)
                                # send mail, then block sending mail from this name to spam protect,
                                # look "if timer" below
                                global_mail_timer_hash[par["section"]] = 1
                            else:
                                syslog.syslog("too fast to send alert mail for [" + par["section"] + "]")
                        else:
                            status_msg = "  Status OK"

                        syslog.syslog(msg + status_msg)

                except:
                    syslog.syslog("not succesfull loop")
                    continue

                if "error" in str(operational_item[0]):

                    par = operational_item[1]
                    erroremail = par["errormail"]
                    error_message = str(operational_item[0]) + " INFO: " + str(par["section"]) + " " + str(par["ip"])

                    errorkey = str(par["section"] + "error")
                    if errorkey not in global_error_mail_timer_hash:
                        global_error_mail_timer_hash[errorkey] = 0
                        print "adding to hach"

                    if global_error_mail_timer_hash[errorkey] == 0:
                        send_email(erroremail, "Error in :" + str(par["section"]) + str(" " + par["prefix"]),
                                   error_message)
                        global_error_mail_timer_hash[errorkey] = 1
                    else:
                        syslog.syslog("too fast to send error mail for [" + par["section"] + "]")

                    syslog.syslog(error_message)

                if "timer 60" in str(operational_item[1]):

                    for llist in global_mail_timer_hash:
                        # allow to send mail again 
                        global_mail_timer_hash[llist] = 0
                    print errortimer
                    if errortimer < 9:
                        errortimer += 1

                    else:

                        for errorllist in global_error_mail_timer_hash:
                            # allow to send mail
                            global_error_mail_timer_hash[errorllist] = 0
                            print "zeroing hash"
                        errortimer = 0

            time.sleep(0.1)

        syslog.syslog("stop process... main loop is stopped")
        # needt to connect once to close zabbix loop
        host = '127.0.0.1'
        port = 50007
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, port))
        s.close()

        syslog.syslog("LowLevelLoop is stopped ")


class ZabbixLoop(threading.Thread):
    def __init__(self, iqueue, mainthread):
        threading.Thread.__init__(self)
        self.socket = None
        self.queue = iqueue
        self.mthread = mainthread
        self.host = '127.0.0.1'
        self.port = 50007
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.bind((self.host, self.port))

    def stop(self):
        socket.socket(socket.AF_INET,
                      socket.SOCK_STREAM).connect((self.host, self.port))
        self.socket.close()

    def run(self):
        # execute the command, queue the result

        statushash = {}
        while self.mthread.is_alive():

            self.s.listen(1)
            conn, addr = self.s.accept()

            while not self.queue.empty():
                operational_item = self.queue.get()
                statushash[operational_item[0]] = operational_item

            while 1:
                data = conn.recv(1024)
                if not data:
                    break
                if "give me data" in str(data):
                    pichash = pickle.dumps(statushash)
                    conn.sendall(pichash)
            conn.close()
        syslog.syslog("ZabbixLoop is stopped")


def send_email(recipient, subject, body):
    gmail_user = "gmail account name"
    gmail_pwd = " gmail pass"
    FROM = "from address"
    TO = recipient if type(recipient) is list else [recipient]
    SUBJECT = subject
    TEXT = body

    # Prepare actual message
    message = """\From: %s\nTo: %s\nSubject: %s\n\n%s
    """ % (FROM, ", ".join(TO), SUBJECT, TEXT)
    try:
        # SMTP_SSL Example
        server_ssl = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=5)
        server_ssl.ehlo()  # optional, called by login()
        server_ssl.login(gmail_user, gmail_pwd)
        # ssl server doesn't support or need tls, so don't call server_ssl.starttls()
        server_ssl.sendmail(FROM, TO, message)
        # server_ssl.quit()
        server_ssl.close()
        #        print 'successfully sent the mail'
        syslog.syslog("successfully sent the mail")
    except:
        #        print "failed to send mail"
        syslog.syslog("failed to send mail")


def main_programm():
    syslog.syslog("starting")

    # initiallization command list, add some needed timers
    cmds = [["sleep 2", {"section": "timer 60", "wait_time": 0, "wait_extra": 0}],

            ]

    # reading config and sections
    syslog.syslog("Reading config /etc/iperf-mp/main.cfg")
    config = configparser.ConfigParser(
        {'reverse': 'no', 'mail': 'none', 'wait_between_reconnect': float(0.1), 'port': "default", 'prefix': " "})
    config.read('/etc/iperf-mp/main.cfg')
    section_list = config.sections()
    # getting parameters of each sections
    for section in section_list:
        try:
            reverse = config.get(section, "reverse")
            ip = config.get(section, "address")
            mail = config.get(section, "mail").split(",")
            errormail = config.get(section, "errormail").split(",")
            bandwidth = config.get(section, "bandwidth")
            min_bandwidth = config.get(section, "min_bandwidth")
            port = config.get(section, "port")
            prefix = config.get(section, "prefix")
            wait_time = float(config.get(section, "wait_between_reconnect"))

        except:
            syslog.syslog("cannot read,skip in [" + section + "]")
            continue
        # checking direction
        reverse_option = ""
        remote_port = ""
        #        wait_time = 0.1
        wait_extra = 0
        if reverse == "yes":
            reverse_option = "-R "

        if "default" in str(port):
            pass

        else:
            try:
                remote_port = " -p " + str(int(port))
            except:
                print("wrong port number. I will try default")

        # prepairing command, add command and check options to  cmd list
        command = "iperf3 -c " + ip + " -t 20 -f k -b " + bandwidth + "m -i 1 -C reno" + reverse_option + remote_port
        parameters = {"min_bandwidth": min_bandwidth, "mail": mail, "section": section, "ip": ip, "port": port,
                      "wait_time": wait_time, "wait_extra": wait_extra, "prefix": prefix, "errormail": errormail}

        cmds.append([command, parameters])
    # first initial start of all commands
    for cmd in cmds:
        command = cmd[0]
        print(command)
        syslog.syslog(command)
        parametersforrun = cmd[1]
        print (parametersforrun)
        syslog.syslog(str(parametersforrun))
        # allowing to sent first mail for this name
        global_mail_timer_hash[parametersforrun["section"]] = 0

        thread = CmdCommands(command, result_queue, parametersforrun)
        thread.start()
        time.sleep(0.5)

    # starting low level loop thread(syslog alerts mails etc)
    # get the name of main thread
    mainthread = threading.currentThread()
    thread = LowLevelLoop(operational_queue, zabbix_queue, mainthread)
    thread.start()
    thread = ZabbixLoop(zabbix_queue, mainthread)
    thread.start()
    sleeptimer1m = 0

    # starting main operation loop
    while True:
        # if some threads are finished lets check them:
        while not result_queue.empty():
            #  get thread operation results:
            (cmd, output, status, parameters) = result_queue.get()
            # print(cmd, output, status, parameters)
            if "iperf3" in cmd:

                # slow down  infinite starting of iperf if previous was  error
                if "unable to connect to server" or "server is busy running a test" in str(output):
                    # if error wait more time (increase to 1s wait_extra parameter)
                    parameters["wait_extra"] = 4

                thread = CmdCommands(cmd, result_queue, parameters)
                thread.start()
                operational_queue.put([output, parameters])
                # start  just finished iperf thread again
            elif "sleep" in cmd:
                thread = CmdCommands(cmd, result_queue, parameters)
                thread.start()
                if sleeptimer1m < 30:
                    sleeptimer1m += 1
                else:
                    operational_queue.put([output, parameters])
                    sleeptimer1m = 0
                    syslog.syslog(" 1 minute")

        time.sleep(0.001)



if __name__ == "__main__":

    result_queue = queue.Queue()
    operational_queue = queue.Queue()
    zabbix_queue = queue.Queue()
    global_mail_timer_hash = {}
    global_error_mail_timer_hash = {}

    main_programm()
