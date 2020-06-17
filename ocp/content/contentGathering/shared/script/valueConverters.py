"""Convert values between types when needed.

Functions:
  stripValue
  valueToInteger
  valueToFloat
  valueToLong
  valueToBoolean
  valueToDate

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Mar 2, 2017

"""
import json
import datetime
from contextlib import suppress

## TODO: enforce encoding to avoid stripping non-visible characters?
def stripValue(value):
	with suppress(Exception):
		value = value.strip()
		if len(value) <= 0:
			value = None
	return value

def valueToInteger(value):
	if value is not None:
		value = int(stripValue(value))
	return value

def valueToFloat(value):
	if value is not None:
		value = float(stripValue(value))
	return value

def valueToLong(value):
	if value is not None:
		value = long(stripValue(value))
	return value

def valueToBoolean(value):
	if value is not None:
		if value is True or str(value) == '1' or re.search('true', str(value), re.I):
			value = True
		else:
			value = False
	return value

def valueToDate(value, formatString='%Y-%m-%d'):
	if value is not None:
		#formatString = '%Y-%m-%d %H:%M:%S.%f'
		value = str(stripValue(value))
		value = datetime.datetime.strptime(value, formatString)
	return value
