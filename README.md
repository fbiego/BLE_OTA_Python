# BLE_OTA_Python
A script for performing OTA update over BLE on ESP32

## Requirements
- [`Bleak`](https://github.com/hbldh/bleak)
 `$ pip install bleak`


## Usage
`python ota.py "01:23:45:67:89:ab" "firmware.bin"`

you can create a batch file on windows

```
@echo off
python ota.py "40:F5:20:4A:45:B7" "firmware.bin"
pause
```
