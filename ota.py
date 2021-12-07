"""
  
MIT License

Copyright (c) 2021 Felix Biego

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import print_function
import os.path
from os import path
import asyncio
import platform
import math
import sys
import re

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

header = """#####################################################################
    ------------------------BLE OTA update---------------------
    Arduino code @ https://github.com/fbiego/ESP32_BLE_OTA_Arduino
#####################################################################"""

UART_SERVICE_UUID = "fb1e4001-54ae-4a28-9f74-dfccb248601d"
UART_RX_CHAR_UUID = "fb1e4002-54ae-4a28-9f74-dfccb248601d"
UART_TX_CHAR_UUID = "fb1e4003-54ae-4a28-9f74-dfccb248601d"

PART = 16000
MTU = 500

end = True
clt = None
fileBytes = None
total = 0

def get_bytes_from_file(filename):
    print("Reading from: ", filename)
    return open(filename, "rb").read()

async def start_ota(ble_address: str, file_name: str):
    device = await BleakScanner.find_device_by_address(ble_address, timeout=20.0)
    disconnected_event = asyncio.Event()

    def handle_disconnect(_: BleakClient):
        global disconnect
        disconnect = False
        print(": Device disconnected")
        disconnected_event.set()
            
    async def handle_rx(_: int, data: bytearray):        
        if (data[0] == 0xAA):
            print("Transfer mode:", data[1])
            printProgressBar(0, total, prefix = 'Progress:', suffix = 'Complete', length = 50)
            if data[1] == 1:
                for x in range(0, fileParts):
                    await send_part(x, fileBytes, clt)
                    printProgressBar(x + 1, total, prefix = 'Progress:', suffix = 'Complete', length = 50)
            else:
                await send_part(0, fileBytes, clt)
                
        if (data[0] == 0xF1):
            nxt = int.from_bytes(bytearray([data[1], data[2]]), "big")  
            await send_part(nxt, fileBytes, clt)
            printProgressBar(nxt + 1, total, prefix = 'Progress:', suffix = 'Complete', length = 50)
        if (data[0] == 0xF2):
            ins = 'Installing firmware'
            #print("Installing firmware")
        if (data[0] == 0x0F):
            result = bytearray([])
            for s in range(1, len(data)):
                result.append(data[s])
            print("OTA result: ", str(result, 'utf-8'))
            global end
            end = False
        #print("received:", data)

    def printProgressBar (iteration, total, prefix = '', suffix = '', decimals = 1, length = 100, fill = '█', printEnd = "\r"):
        """
        Call in a loop to create terminal progress bar
        @params:
            iteration   - Required  : current iteration (Int)
            total       - Required  : total iterations (Int)
            prefix      - Optional  : prefix string (Str)
            suffix      - Optional  : suffix string (Str)
            decimals    - Optional  : positive number of decimals in percent complete (Int)
            length      - Optional  : character length of bar (Int)
            fill        - Optional  : bar fill character (Str)
            printEnd    - Optional  : end character (e.g. "\r", "\r\n") (Str)
        """
        percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
        filledLength = int(length * iteration // total)
        bar = fill * filledLength + '-' * (length - filledLength)
        print(f'\r{prefix} |{bar}| {percent}% {suffix}', end = printEnd)
        # Print New Line on Complete
        if iteration == total: 
            print()

    async def send_part(position: int, data: bytearray, client: BleakClient):
        start = (position * PART)
        end = (position + 1) * PART
        if len(data) < end:
            end = len(data)
        parts = (end - start) / MTU
        for i in range(0, int(parts)):
            toSend = bytearray([0xFB, i])
            for y in range(0, MTU):
                toSend.append(data[(position*PART)+(MTU * i) + y])
            await send_data(client, toSend, False)
        if (end - start)%MTU != 0:
            rem = (end - start)%MTU
            toSend = bytearray([0xFB, int(parts)])
            for y in range(0, rem):
                toSend.append(data[(position*PART)+(MTU * int(parts)) + y])
            await send_data(client, toSend, False)
        update = bytearray([0xFC, int((end - start)/256), int((end - start) % 256), int(position/256), int(position % 256) ])
        await send_data(client, update, True)

    async def send_data(client: BleakClient, data: bytearray, response: bool):
        await client.write_gatt_char(UART_RX_CHAR_UUID, data, response)
        
    if not device:
        print("-----------Failed--------------")
        print(f"Device with address {ble_address} could not be found.")
        return
        #raise BleakError(f"A device with address {ble_address} could not be found.")
    async with BleakClient(device, disconnected_callback=handle_disconnect) as client:
        await client.start_notify(UART_TX_CHAR_UUID, handle_rx)
        await asyncio.sleep(1.0)
        
        await send_data(client, bytearray([0xFD]), False)
        
        global fileBytes
        fileBytes = get_bytes_from_file(file_name)
        global clt
        clt = client
        fileParts = math.ceil(len(fileBytes) / PART)
        fileLen = len(fileBytes)
        fileSize = bytearray([0xFE, fileLen >>  24 & 0xFF, fileLen >>  16 & 0xFF, fileLen >>  8 & 0xFF, fileLen & 0xFF])
        await send_data(client, fileSize, False)
        global total
        total = fileParts
        otaInfo = bytearray([0xFF, int(fileParts/256), int(fileParts%256), int(MTU / 256), int(MTU%256) ])
        await send_data(client, otaInfo, False)
        
        while end:
            await asyncio.sleep(1.0)
        print("Waiting for disconnect... ", end="")
        await disconnected_event.wait()
        print("-----------Complete--------------")

"""
ble_address = (
    "24:6F:28:AE:F6:B6"
    if platform.system() != "Darwin"
    else "B9EA5233-37EF-4DD6-87A8-2A875E821C46"
)
"""

def isValidAddress(str):
 
    # Regex to check valid
    # MAC address
    regex = ("^([0-9A-Fa-f]{2}[:-])" +
             "{5}([0-9A-Fa-f]{2})|" +
             "([0-9a-fA-F]{4}\\." +
             "[0-9a-fA-F]{4}\\." +
             "[0-9a-fA-F]{4}){17}$")
    regex2 = "^[{]?[0-9a-fA-F]{8}" + "-([0-9a-fA-F]{4}-)" + "{3}[0-9a-fA-F]{12}[}]?$"
 
    # Compile the ReGex
    p = re.compile(regex)
    q = re.compile(regex2)
 
    # If the string is empty
    # return false
    if (str == None):
        return False
 
    # Return if the string
    # matched the ReGex
    if(re.search(p, str) and len(str) == 17):
        return True
    else:
        if (re.search(q, str) and len(str) == 36):
            return True
        else:
            return False


if __name__ == "__main__":
    print(header)
    if (len(sys.argv) > 2):
        print("Trying to start OTA update")
        if isValidAddress(sys.argv[1]) and path.exists(sys.argv[2]):
            asyncio.run(start_ota(sys.argv[1], sys.argv[2]))
        else:
            if not isValidAddress(sys.argv[1]):
                print("Invalid Address: ", sys.argv[1])
            if not path.exists(sys.argv[2]):
                print("File not found: ", sys.argv[2])
    else:
        print("Specify the device address and firmware file")
        print(">python ota.py \"01:23:45:67:89:ab\" \"firmware.bin\"")
