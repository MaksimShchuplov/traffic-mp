#!/usr/bin/python2

import socket
import pickle
import json

HOST = '127.0.0.1'  # The remote host
PORT = 50007  # The same port as used by the server
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((HOST, PORT))
s.sendall('give me data')
datai = s.recv(1024)
data_arr = pickle.loads(datai)
s.close()
#print 'Received', data_arr
datamass = {}
datahmass = []
for i in data_arr:
    #print i, data_arr
    datah = {}
    datah["{#NAME}"] = i
    datah["{#ADDRESS}"] = data_arr[i][1]
    datahmass.append(datah)

datamass["data"] = datahmass

print datamass

print json.dumps(datamass, sort_keys=True,   indent=4, separators=(',', ': '))




