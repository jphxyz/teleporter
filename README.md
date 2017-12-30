# Cryptopia TELEPORTER
Auto-trader for Cryptopia Currency exchange

Inspired by code from Cryptopia forum user, 'CoinUser'. This script
automatically finds and executes the most profitable trade route
to consolidate many altcoins into one desired currency.

## Install

### \*NIX (Linux, OSX)
* download and extract https://github.com/jphxyz/teleporter/archive/master.zip
* Create and edit `config/teleporter.ini` (Use `config/teleporter.ini.sample` as starting point)

### Windows
* Get Python >= 2.7 (https://www.python.org/downloads/)
* Follow steps for UNIX

## Usage
Basic usage, executes based on parameters in config/teleporter.ini
```
cd <UNZIPPED DIRECTORY>
python ./teleporter.py
```

You can also override parameters with command line flags.
```
teleporter [-h|--help] [-n|--dry-run] [-c|--coin <COIN>] [-m|--max-trades <MAX_TRADES>]
```
