"""Wrapper for accessing Windows Management Infrastructure (WMI).

Classes:
  |  Wmi : wrapper class for WMI

"""
## Using pythoncom since WMI is COM-based, and when using
## in a thread, it needs it's own COM threading model
import pythoncom

## Using an externally provided library defined in globalSettings and located
## in '<install_path>/external'.
import utils
externalProtocolLibrary = utils.loadExternalLibrary('externalProtocolWmi')

## PyMI is used in the external library:
##   import wmi
## To call this function for a remote connection:
##   wmi.WMI(moniker, computer, user, password)

class Wmi:
	"""Wrapper class for WMI."""
	def __init__(self, runtime, logger, endpoint, reference, protocol, **kwargs):
		self.runtime = runtime
		self.logger = logger
		self.endpoint = endpoint
		self.connection = None
		self.reference = reference
		self.protocol = protocol
		self.kwargs = kwargs
		self.namespace="root/cimv2"
		## Set things from the kwargs; right now just namespace
		if 'namespace' in kwargs:
			self.namespace=kwargs['namespace']
		pythoncom.CoInitialize()


	def open(self):
		## Extract user/password from protocol and return the following:
		##   wmi.WMI(moniker=self.namespace, computer=self.endpoint, user, password)
		self.connection = externalProtocolLibrary.connection(self.runtime, self.protocol, self.endpoint, self.namespace)

	def close(self):
		pythoncom.CoUninitialize()

	def getId(self):
		return self.reference

	def __del__(self):
		self.close()
