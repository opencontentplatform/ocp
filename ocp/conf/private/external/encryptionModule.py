"""External utility to work with encoding and encryption.

Externally referenced functions:
  |  transform : called by apiResourceConfig via API methods on /cred
  |  encode    : called by createProtocolEntry when creating credentials via CLI
  |            : called by protocolHandler for creating default API context
  |  decode    : called by protocolHandler on protocol connection credentials
  |  getToken : called by platformSetup during initial setup


The intention with an external wrapper, is to move responsibility of protecting
sensitive data away from the open-source platform. From a modular perspective,
this module would be best coded as a single Python class. However, doing that
provides easier access to internals and so we intentionally avoid encapsulation
with individual functions.

"""
import sys
import traceback
import os
import base64
from cryptography.fernet import Fernet, InvalidToken
## Get relative paths based on install location
import env


def validateTokenSize(thisToken):
	if len(thisToken) != 44:
		raise EnvironmentError('Invalid Token')
		#raise EnvironmentError('Invalid Token. token: {} has length is {}'.format(thisToken, len(thisToken)))


def modify(thisToken):
	## Shuffle positional values to enable external exposure
	if not isinstance(thisToken, str):
		thisToken = str(thisToken, 'utf-8')
	t = list(thisToken)
	squirrelyList = [(2,6), (5,13), (7,22), (8,20), (24,26), (25,27)]
	for i in squirrelyList:
		(x,y) = i
		t[x], t[y] = t[y], t[x]

	## end modify
	return ''.join(t)


def getTokenConfigured(tokenType):
	thisToken = None
	## Statically assign name of file based on type (platform/service); do not
	## allow passing in a file name, to avoid inspection from user defined data
	fileName = None
	if tokenType == 'platform':
		fileName = 'key.conf'
	elif tokenType == 'service':
		fileName = 'client.conf'
	else:
		raise IOError('Unknown token type requested')
	tokenFile = os.path.join(env.privateInternalKeyPath, fileName)
	with open(tokenFile, 'r') as f:
		thisToken = f.read()
	if thisToken is None:
		raise IOError('Token not found')
	thisToken = thisToken.strip()
	validateTokenSize(thisToken)

	## The only getToken call that isn't scrambled before returning, since
	## the value previously stored was scrambled when created.

	## end getTokenConfigured
	return thisToken


def getTokenPlain():
	## Generate a new plain token to use with the crypto library
	newToken = base64.urlsafe_b64encode(os.urandom(int(32)))
	return modify(str(newToken, 'utf-8'))


def getTokenFromValue(value):
	## Generate a new plain token to use with the crypto library
	if not isinstance(value, bytes):
		value = bytes(value, 'utf-8')
	value = value[:32]
	newToken = base64.urlsafe_b64encode(value)
	return modify(str(newToken, 'utf-8'))


def getToken(value=None):
	## When called without a value, this creates a new plain token. When called
	## with a value, it uses that value for the seed to generate the token.
	if value is None:
		return getTokenPlain()
	else:
		return getTokenFromValue(value)


def resolveToken(thisToken=None, generateToken=True, tokenType=None):
	if thisToken is None:
		if generateToken:
			thisToken = getTokenPlain()
		else:
			if tokenType == None:
				tokenType = 'platform'
			thisToken = getTokenConfigured(tokenType)

	## end resolveToken
	return thisToken


def tokenInBytes(thisToken):
	## If token is in string form, convert back to bytes
	if not isinstance(thisToken, bytes):
		thisToken = bytes(thisToken, 'utf-8')
	## Using Fernet
	return thisToken


def getEncodingUtility(thisToken):
	## Using Fernet
	return Fernet(tokenInBytes(thisToken))


def getDecodingUtility(thisToken):
	## Same utility call for both
	return getEncodingUtility(thisToken)


def encode(value, thisToken=None, generateToken=False, tokenType=None, returnRawFormat=False):
	## Create an encoding utility with the crypto lib, and encode the value
	thisToken = resolveToken(thisToken, generateToken, tokenType)
	## Assume the token was shuffled
	thisToken = modify(thisToken)
	encodingUtility = getEncodingUtility(thisToken)
	## The provided value is most likely a string, but may be bytes
	if not isinstance(value, bytes):
		value = bytes(value, 'utf-8')
	encodedValue = encodingUtility.encrypt(value)
	if not returnRawFormat:
		encodedValue = str(encodedValue, 'utf-8')

	## end encode
	return encodedValue


def decode(value, thisToken=None, generateToken=False, tokenType=None, returnRawFormat=False):
	## Create an decoding utility with the crypto lib, and decode the value
	thisToken = resolveToken(thisToken, generateToken, tokenType)
	## Assume the token was shuffled
	thisToken = modify(thisToken)
	decodingUtility = getDecodingUtility(thisToken)
	## The provided value is most likely a string, but may be bytes
	decodedValue = None
	if value is not None:
		## If this is of type dict, it's probably a non-wrapped protocol,
		## meaning it's already been decoded and is now already readable...
		## in which case it throws a TypeError: encoding without string argument
		if not isinstance(value, bytes):
			value = bytes(value, 'utf-8')
		decodedValue = decodingUtility.decrypt(value)
		if not returnRawFormat:
			decodedValue = str(decodedValue, 'utf-8')

	## end decode
	return decodedValue


def convert(valueAsText, thisToken=None, generateToken=True, tokenType=None):
	## Return an encrypted text value, along with shuffled token for restoring
	returnToken = True
	if thisToken is None:
		if generateToken:
			thisToken = getTokenPlain()
		else:
			if tokenType == None:
				tokenType = 'platform'
			thisToken = getTokenConfigured(tokenType)
			returnToken = False
	else:
		validateTokenSize(thisToken)
	encryptedPass = encode(valueAsText, thisToken)
	## Don't expose any configured tokens, shuffled or not
	shuffledToken = None
	if returnToken:
		shuffledToken = thisToken

	## end convert; return encrypted
	return (encryptedPass, shuffledToken)


def transform(valueAsEncrypted, oldToken=None, newToken=None, generateToken=False, tokenType=None):
	## Take either a plain text value, or one previously encrypted using
	## oldToken, unencrypt if necessary, then re-encrypt using a new key.
	valueAsText = valueAsEncrypted
	if oldToken is not None:
		validateTokenSize(oldToken)
		#valueAsText = str(decode(valueAsEncrypted, oldToken), 'utf-8')
		valueAsText = decode(valueAsEncrypted, oldToken)

	## end transform
	return convert(valueAsText, newToken, generateToken, tokenType)

def transformDefault(valueAsEncrypted, newToken=None):
	## So we don't have to expose the getTokenConfigured call
	return transform(valueAsEncrypted, getTokenConfigured('platform'), newToken)
