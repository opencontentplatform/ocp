"""Gather software packages on OS types.

Entry function:
  getSoftwarePackages : standard module entry point

OS agnostic functions:
  queryForSoftware : gather software data - wrapper for OS types
  buildSoftwareDictionary : reate requested CIs and relationships
  getFilterParameters : get filters from the parameters
  setAttribute : set attribute only when value exists
  createSoftware : create a single software object
  inFilteredSoftwareList : determine if software is deemed valid

OS specific functions:
  windowsGetSoftware : get Windows software - wrapper for MSI/Registry
  windowsGetMsiProduct : parse Windows MSI packages - wrapper for WMI/VBScript
  executeProductQueryViaWMI : get Windows MSI packages via WMI
  executeProductQueryViaVBScript : get Windows MSI packages via VBScript
  windowsGetRegistryProduct : parse Windows Registry software package results
  executeRegistryQuery : get Windows Registry results

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created Mar 12, 2018

"""
import sys
import traceback
import os
import re

## From openContentPlatform content/contentGathering/shared/script
from utilities import updateCommand, cleanInstallLocation, compareFilter
from utilities import concatenate, resolve8dot3Name, sectionedStringToIterableObject
from utilities import delimitedStringToIterableObject, splitAndCleanList


def getSoftwarePackages(runtime, client, nodeId, trackResults=False):
	"""Standard entry function for osSoftwarePackages.

	Filter the software and create result objects. Any software not matching
	softwareFilterIncludeList or matching softwareFilterExcludeList (parameters)
	for the OS, is ignored. This function returns an updated dictionary with
	all software objects. And when the caller function requests to trackResults
	(meaning add objects onto the results object), this function adds all the
	created software onto runtime's results so the caller function doesn't need
	to code that logic.
	"""
	filteredSoftware = []
	try:
		osType = runtime.endpoint.get('data').get('node_type')
		shellParameters = runtime.endpoint.get('data').get('parameters')

		## Gather software
		softwareListing = queryForSoftware(runtime, client, osType, shellParameters)
		if len(softwareListing) > 0:
			## Build requested CIs and relationships
			buildSoftwareDictionary(runtime, osType, softwareListing, filteredSoftware, nodeId, trackResults)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error(' Failure in getSoftwarePackages: {stacktrace!r}', stacktrace=stacktrace)

	## end getSoftwarePackages
	return filteredSoftware


###############################################################################
###########################  BEGIN GENERAL SECTION  ###########################
###############################################################################

def queryForSoftware(runtime, client, osType, shellParameters):
	"""Gather software data; wrapper for OS types."""
	softwareListing = {}
	try:
		## Note: softwareListing will be a Dictionary-type for Windows
		## endpoints, but will be List-type for all Unix endpoints.
		runtime.logger.report('Gathering {osType!r} Software', osType=osType)
		if (osType == 'Windows'):
			windowsGetSoftware(runtime, client, softwareListing)
		elif (osType == 'Linux'):
			linuxGetSoftware(runtime, client, softwareListing)
		elif (osType == 'HPUX'):
			#hpuxGetSoftware(runtime, client, osType, softwareListing)
			raise NotImplementedError('Software solution on HP-UX is not yet implemented')
		elif (osType == 'Solaris'):
			#solarisGetSoftware(runtime, client, osType, softwareListing)
			raise NotImplementedError('Software solution on Solaris is not yet implemented')
		elif (osType == 'AIX'):
			#aixGetSoftware(runtime, client, osType, softwareListing)
			raise NotImplementedError('Software solution on AIX is not yet implemented')

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error(' Failure in queryForSoftware: {stacktrace!r}', stacktrace=stacktrace)

	## end queryForSoftware
	return softwareListing


def getFilterParameters(runtime, osType, filters):
	"""Get filters from the shell parameters."""
	shellParameters = runtime.endpoint.get('data').get('parameters')

	filters['softwareFilterFlag'] = shellParameters.get('softwareFilterFlag', False)
	if (not filters['softwareFilterFlag']):
		runtime.logger.report(' Returning all software since \'softwareFilterFlag\' for {osType!r} is not set to true in the shell parameters.', osType=osType)
	else:
		filters['softwareFilterByPackageName'] = shellParameters.get('softwareFilterByPackageName', False)
		filters['softwareFilterByCompany'] = shellParameters.get('softwareFilterByCompany', False)
		filters['softwareFilterByOwner'] = shellParameters.get('softwareFilterByOwner', False)
		filters['softwareFilterByVendor'] = shellParameters.get('softwareFilterByVendor', False)
		filters['softwareFilterIncludeCompare'] = runtime.endpoint.get('data').get('parameters').get('softwareFilterIncludeCompare', '==')
		filters['softwareFilterIncludeList'] = runtime.endpoint.get('data').get('parameters').get('softwareFilterIncludeList', [])
		filters['softwareFilterExcludeCompare'] = runtime.endpoint.get('data').get('parameters').get('softwareFilterExcludeCompare', '==')
		filters['softwareFilterExcludeList'] = runtime.endpoint.get('data').get('parameters').get('softwareFilterExcludeList', [])
		if (len(filters['softwareFilterIncludeList']) <= 0 and len(filters['softwareFilterExcludeList']) <= 0):
			runtime.logger.report(' No entries listed in either \'softwareFilterIncludeList\' or \'softwareFilterExcludeList\' for {osType!r} in the shell parameters.', osType=osType)

	## end getFilterParameters
	return


def buildSoftwareDictionary(runtime, osType, softwareListing, filteredSoftware, nodeId, trackResults):
	"""Create requested CIs and relationships."""
	runtime.logger.report('Building software dictionary on {osType!r}', osType=osType)
	filters = {}
	getFilterParameters(runtime, osType, filters)

	for entry in softwareListing:
		try:
			(name, thisID, version, title, thisType, path, description, company, owner, vendor, datestamp) = softwareListing[entry]
			if (not filters['softwareFilterFlag'] or (inFilteredSoftwareList(runtime, name, company, owner, vendor, filters))):
				createSoftware(runtime, nodeId, trackResults, filteredSoftware, name, thisID, version, title, thisType, path, description, company, owner, vendor, datestamp)
			else:
				runtime.logger.report(' Filtering out software {name!r} with {attributes!r}: ', name=entry, attributes=softwareListing[entry])
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error(' Exception with creating {osType!r} software in buildSoftwareDictionary: {stacktrace!r}', osType=osType, stacktrace=stacktrace)

	## end buildSoftwareDictionary
	return


def inFilteredSoftwareList(runtime, name, company, owner, vendor, filters):
	"""Determine whether software is in the list to return ."""
	## First check the exclude list
	if (len(filters['softwareFilterExcludeList']) >= 0):
		for matchContext in filters['softwareFilterExcludeList']:
			if (matchContext is None or len(matchContext) <= 0):
				continue
			searchString = matchContext.strip().lower()
			try:
				if (filters['softwareFilterByPackageName'] and name and
					compareFilter(filters['softwareFilterExcludeCompare'], searchString, name.lower())):
					return False
				if (filters['softwareFilterByCompany'] and company and
					compareFilter(filters['softwareFilterExcludeCompare'], searchString, company.lower())):
					return False
				if (filters['softwareFilterByOwner'] and owner and
					compareFilter(filters['softwareFilterExcludeCompare'], searchString, owner.lower())):
					return False
				if (filters['softwareFilterByVendor'] and vendor and
					compareFilter(filters['softwareFilterExcludeCompare'], searchString, vendor.lower())):
					return False
			except:
				stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				runtime.logger.error('Exception in inFilteredSoftwareList: on searchString {searchString!r}:  {stacktrace!r}', searchString=searchString, stacktrace=stacktrace)
		## Exclusion rules have precidence over inclusion rules. If the exclude
		## list had content but nothing matched, go ahead and include in results
		return True

	## Now check the include list
	for matchContext in filters['softwareFilterIncludeList']:
		if (matchContext is None or len(matchContext) <= 0):
			continue
		searchString = matchContext.strip().lower()
		try:
			if (filters['softwareFilterByPackageName'] and name and
				compareFilter(filters['softwareFilterIncludeCompare'], searchString, name.lower())):
				return True
			if (filters['softwareFilterByCompany'] and company and
				compareFilter(filters['softwareFilterIncludeCompare'], searchString, company.lower())):
				return True
			if (filters['softwareFilterByOwner'] and owner and
				compareFilter(filters['softwareFilterIncludeCompare'], searchString, owner.lower())):
				return True
			if (filters['softwareFilterByVendor'] and vendor and
				compareFilter(filters['softwareFilterIncludeCompare'], searchString, vendor.lower())):
				return True
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in inFilteredSoftwareList: on searchString {searchString!r}:  {stacktrace!r}', searchString=searchString, stacktrace=stacktrace)

	## end inFilteredSoftwareList
	return False


def createSoftware(runtime, nodeId, trackResults, filteredSoftware, name, thisID, version, title, thisType, path, description, company, owner, vendor, datestamp, attributes=None):
	"""Create Software object."""
	if attributes is None:
		attributes = {}
	setAttribute(attributes, 'name', name)
	setAttribute(attributes, 'identifier', thisID, 256)
	setAttribute(attributes, 'version', version, 256)
	setAttribute(attributes, 'title', title, 512)
	setAttribute(attributes, 'associated_date', datestamp, 256)
	setAttribute(attributes, 'recorded_by', thisType, 256)
	## These are mostly for Windows install packages, some for Solaris
	setAttribute(attributes, 'path', path, 256)
	setAttribute(attributes, 'description', description, 1024)
	setAttribute(attributes, 'company', company, 256)
	setAttribute(attributes, 'owner', owner, 256)
	setAttribute(attributes, 'vendor', vendor, 256)

	filteredSoftware.append(attributes)
	if trackResults:
		## Create the software and link it to the node
		softwareId, exists = runtime.results.addObject('SoftwarePackage', **attributes)
		runtime.results.addLink('Enclosed', nodeId, softwareId)

	## end createSoftware
	return


def setAttribute(attributes, name, value, maxLength=None):
	"""Helper to set attributes only when they are valid values."""
	if (value is not None and value != 'null' and len(value) > 0):
		attributes[name] = value
		if maxLength:
			attributes[name] = value[:maxLength]

	## end setAttribute
	return

###############################################################################
############################  END GENERAL SECTION  ############################
###############################################################################


###############################################################################
###########################  BEGIN WINDOWS SECTION  ###########################
###############################################################################

def windowsGetSoftware(runtime, client, softwareListing):
	"""Get Windows MSI Software packages."""
	try:
		useLibraryToGetWin32Products = runtime.endpoint.get('data').get('parameters').get('useLibraryToGetWin32Products', True)
		createVbscriptToGetWin32Products = runtime.endpoint.get('data').get('parameters').get('createVbscriptToGetWin32Products', False)
		## Use global parameters to direct whether to run the slower/native
		## WMI method to get Win32_Products, or to use the fast VBScript method
		output = None
		if useLibraryToGetWin32Products:
			## Newer method enabled once PowerShell came out
			runtime.logger.report('Gathering Software via WindowsInstaller library in PowerShell')
			(output, stdError, hitProblem) = executeProductQueryViaLibrary(runtime, client, 10)
		elif createVbscriptToGetWin32Products:
			runtime.logger.report('Gathering Software via WindowsInstaller library in vbscript')
			## Older method required streaming a vbscript file over to target,
			## before running. It was much faster the the native WMI method
			(output, stdError, hitProblem) = executeProductQueryViaVBScript(runtime, client, 10)
		else:
			runtime.logger.report('Gathering Software via WMI\'s Win32_Product class... this may take a while.')
			## Use the slower/native Win32_Product query
			(output, stdError, hitProblem) = executeProductQueryViaWMI(runtime, client, 300)
		windowsGetMsiProduct(runtime, client, output, softwareListing)
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in windowsGetSoftware: {stacktrace!r}', stacktrace=stacktrace)
		## Don't return yet; we can still leverage Registry and Services

	## Use Registy output to get non-MSI installed Products
	try:
		runtime.logger.report('Gathering additional Software via Windows Registry')
		## Process the 32-bit location first
		(output1, stdError, hitProblem) = executeRegistryQuery(runtime, client, r'software\microsoft\windows\currentversion\uninstall\*', 30000)
		windowsGetRegistryProduct(runtime, client, output1, softwareListing)
		## Now process the 64-bit location
		(output2, stdError, hitProblem) = executeRegistryQuery(runtime, client, r'software\wow6432Node\microsoft\windows\currentversion\uninstall\*', 30000)
		windowsGetRegistryProduct(runtime, client, output2, softwareListing)
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in windowsGetSoftware querying Registry: {stacktrace!r}', stacktrace=stacktrace)

	## end windowsGetSoftware
	return


def windowsGetMsiProduct(runtime, client, output, softwareListing):
	"""Parse Windows MSI package results.

	Note: There are several Windows-based provisioning tools. This WMI class
	will only return content for MSI packages (i.e. Windows native installer)
	but as such, it works great for custom provisioned .NET packages

	Sample output from WMI for attributes Name,InstallLocation,Version,InstallDate,PackageName,Vendor,RegCompany,RegOwner,IdentifyingNumber,Description
	===================================================================
	Name                            InstallLocation                                               Version     InstallDate  PackageName              RegCompany  RegOwner
	Visual C++ .NET Standard 2003   C:\Program Files (x86)\Microsoft Visual Studio .NET 2003\     7.1.6030    20100221     vs_setup.msi             Microsoft   CSatterthwaite
	WinZip 12.1                     C:\Program Files (x86)\WinZip\                                12.1.8519   20091216     WINZIP121.MSI                        Windows User
	SQL Server Compact 3.5 SP2 ENU  C:\Program Files (x86)\Microsoft SQL Server Compact Edition\  3.5.8080.0  20100810     SSCERuntime_x86-enu.msi
	ActivePerl 5.10.1 Build 1006    C:\Perl\                                                      5.10.1006   20091026     ActivePerl-x86-291086.msi            Windows User
	===================================================================
	"""
	if (output == None):
		runtime.logger.report('Error: No output from WMI for installed products')
		return

	while output.next():
		try:
			productName     = output.getString(1)
			installLocation = output.getString(2)
			productVersion  = output.getString(3)
			installDate     = output.getString(4)
			packageName     = output.getString(5)
			productVendor   = output.getString(6)
			regCompany      = output.getString(7)
			regOwner        = output.getString(8)
			identifyingNum  = output.getString(9)
			description     = output.getString(10)

			## Debug print
			runtime.logger.report('  Win32_Product Name: {productName!r}, Package: {packageName!r}, installLocation: {installLocation!r}, Version: {productVersion!r} installDate: {installDate!r}, Company: {regCompany!r}, Owner: {regOwner!r}, Vendor: {productVendor!r}, ID: {identifyingNum!r}, Description: {description!r}', productName=productName, packageName=packageName, installLocation=installLocation, productVersion=productVersion, installDate=installDate, regCompany=regCompany, regOwner=regOwner, productVendor=productVendor, identifyingNum=identifyingNum, description=description)

			if (productName is None or productName == 'null' or len(productName.strip()) <= 0):
				runtime.logger.report('   cannot proceed with NULL entry in Windows Products via MSI.  Product Name: {productName!r}, Package: {packageName!r}, installLocation: {installLocation!r}, Version: {productVersion!r} installDate: {installDate!r}, Company: {regCompany!r}, Owner: {regOwner!r}, Vendor: {productVendor!r}, ID: {identifyingNum!r}, Description: {description!r}', productName=productName, packageName=packageName, installLocation=installLocation, productVersion=productVersion, installDate=installDate, regCompany=regCompany, regOwner=regOwner, productVendor=productVendor, identifyingNum=identifyingNum, description=description)
				continue

			## Need to resolve 8dot3 names (short names) for path matching
			if (installLocation is not None and installLocation != "null" and re.search('\~', installLocation)):
				(updatedPath, stdError, hitProblem) = resolve8dot3Name(runtime, client, installLocation)
				if updatedPath is not None:
					runtime.logger.report('   Conversion returned path: {resolvedPath!r}', resolvedPath=updatedPath.encode('unicode-escape'))
					if updatedPath != installLocation and not hitProblem:
						runtime.logger.report('     ---> new install: {productName!r}, Package: {packageName!r}.  Old value: {installLocation!r}.  New value: {updatedInstallLocation!r}', productName=productName, packageName=packageName, installLocation=installLocation, updatedInstallLocation=updatedPath)
						installLocation = updatedPath

			## Add to the software list
			softwareListing[productName] = (productName, identifyingNum, productVersion, None, 'Windows Product from WMI', installLocation, description, regCompany, regOwner, productVendor, installDate)
		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in discovering Windows Software via WMI: {stacktrace!r}', stacktrace=stacktrace)

	## end windowsGetMsiProduct
	return


#######################################################
##  Discover Windows Software Products via Registry  ##
#######################################################
def windowsGetRegistryProduct(runtime, client, output, softwareListing):
	"""Parse Windows Registry software package results."""
	## I'm using the registry to pull products installed without an MSI
	## package and without responding to the previous WMI Product query
	if (output == None):
		runtime.logger.warn('Error: No output from Registry for installed products')
		return

	## Parse output (returned an org.python.core.PyJavaInstance)
	while output.next():
		try:
			productName     = output.getString(1)
			installLocation = output.getString(2)
			publisher       = output.getString(3)
			version         = output.getString(4)
			comments        = output.getString(5)
			installDate     = output.getString(6)

			## Debug print
			runtime.logger.report('  Registry Product Name: {productName!r}, installLocation: {installLocation!r}, publisher: {publisher!r}, version: {version!r}, comments: {comments!r}', productName=productName, installLocation=installLocation, publisher=publisher, version=version, comments=comments)

			## Uninstall locations aren't always useful; examples follow:
			## ======================================================================
			## "C:\Program Files (x86)\Microsoft Visual Studio .NET 2003\Setup\Visual C++ .NET Standard 2003 - English\setup.exe" /MaintMode
			## MsiExec.exe /I{DF6320E3-B716-4FAB-99CD-18AB6A2C3970}
			## RunDll32 C:\PROGRA~2\COMMON~1\INSTAL~1\PROFES~1\RunTime\11\00\Intel32\Ctor.dll,LaunchSetup "C:\Program Files (x86)\InstallShield Installation Information\{17B371B7-740F-4C83-BDFE-0C3A2C585103}\setup.exe" -l0x9  -removeonly
			## "C:\Program Files (x86)\Toolbar Editor\unins000.exe"
			## C:\Python\PYTHON~1\UNWISE.EXE C:\Python\PYTHON~1\INSTALL.LOG
			## C:\PROGRA~2\COMMON~1\INSTAL~1\Driver\7\INTEL3~1\IDriver.exe /M{76643356-611A-4A07-8BEC-79E85546916F}
			## C:\Windows\SysWOW64\Macromed\Flash\FlashUtil10u_ActiveX.exe -maintain activex
			## ======================================================================

			if (productName is None or productName == 'null' or len(productName.strip()) <= 0):
				runtime.logger.report('   cannot proceed with NULL entry in Windows Products via Registry.  Product Name: {productName!r}, installLocation: {installLocation!r}, publisher: {publisher!r}, version: {version!r}, comments: {comments!r}', productName=productName, installLocation=installLocation, publisher=publisher, version=version, comments=comments)
				continue

			## Remove args from the Software and resolve 8dot3 paths
			if (installLocation is not None and installLocation != "null" and re.search('\~', installLocation)):
				updatedInstallLocation = cleanInstallLocation(runtime, client, installLocation)
				if (updatedInstallLocation != installLocation):
					installLocation = updatedInstallLocation
					runtime.logger.report('    --> new install location: {installLocation!r}', installLocation=installLocation)

			## Was the product found previously?
			found = False
			for namedEntry in softwareListing:
				if (namedEntry.lower().strip() == productName.lower().strip()):
					try:
						## Yes, it was added previously; see if we have updates...
						(name, thisID, thisVersion, title, thisType, path, description, company, owner, vendor, thisDate) = softwareListing[namedEntry]

						## Update the install location if necessary
						if ((path is None or len(path) <= 0) and (installLocation and len(installLocation) > 0)):
							path = installLocation
						## Update the version if necessary
						if ((thisVersion is None or len(thisVersion) <= 0) and (version and len(version) > 0)):
							thisVersion = version
						## Update the publisher if necessary
						if (publisher and len(publisher) > 0):
							if (company is None or len(company) <= 0):
								company = publisher
							elif (owner is None or len(owner) <= 0):
								owner = publisher
						## Update the comments if necessary
						if ((description is None or len(description) <= 0) and (comments and len(comments) > 0)):
							description = comments
						## Update the installation date if necessary
						if ((thisDate is None or len(thisDate) <= 0) and (installDate and len(installDate) > 0)):
							thisDate = installDate

						## Override the previous entry
						softwareListing[namedEntry] = (name, thisID, thisVersion, title, thisType, path, description, company, owner, vendor, thisDate)
						found = True
						break
					except:
						stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
						runtime.logger.error('Exception in discovering Windows Products via Registry: {stacktrace!r}', stacktrace=stacktrace)

			if not found:
				## Add to the software list
				softwareListing[productName] = (productName, None, version, None, 'Windows Product from Registry', installLocation, comments, publisher, None, None, installDate)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in discovering Windows Products via Registry: {stacktrace!r}', stacktrace=stacktrace)

	## end windowsGetRegistryProduct
	return


def executeProductQueryViaWMI(runtime, client, timeout=None):
	"""Query Windows products via Win32_Products in WMI.

	We use global parameters to determine whether to run this standard, slower
	WMI method to get Win32_Products, or to use the fast VBScript method. This
	slower method does a WQL select from Win32_Product, and has a runtime of
	anywhere between 10 seconds and 10 minutes to complete.
	"""
	iterableObject = None
	stdError = None
	hitProblem = None
	try:
		delimiter = ':==:'
		wmiProductsQuery = 'Get-WmiObject -q "Select * from Win32_Product" | foreach {$_.Name,$_.InstallLocation,$_.Version,$_.InstallDate,$_.PackageName,$_.Vendor,$_.RegCompany,$_.RegOwner,$_.IdentifyingNumber,$_.Description -Join "'+ delimiter + '"}'
		(rawOutput, stdError, hitProblem) = client.run(wmiProductsQuery, timeout)
		iterableObject = delimitedStringToIterableObject(rawOutput, delimiter)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception with discovering Products via Win32_Products in WMI: {stacktrace!r}', stacktrace=stacktrace)

	## end executeProductQueryViaWMI
	return (iterableObject, stdError, hitProblem)


def executeProductQueryViaLibrary(runtime, client, timeout=None):
	"""Query Windows products via WindowsInstaller library in PowerShell.

	We use global parameters to determine whether to run the standard, slower
	WMI method to get Win32_Products, or to use the faster library method. This
	faster method inlines commands to leverage WindowsInstaller over PowerShell.
	Inlining a couple foreach loops isn't a clean "command", but has sub-second
	run times instead of anywhere between 10 seconds and 10 minutes to finish
	when doing it via Win32_Products in WMI.
	"""
	iterableObject = None
	stdError = None
	hitProblem = None
	try:
		delimiter = ':==:'
		productsQuery = '$I = New-Object -ComObject WindowsInstaller.Installer; $T = $I.GetType(); $Attributes = @(\'ProductName\', \'InstallLocation\', \'VersionString\', \'InstallDate\', \'PackageName\', \'Publisher\', \'RegCompany\', \'RegOwner\', \'ProductID\', \'URLInfoAbout\'); $PList = $T.InvokeMember(\'Products\', [System.Reflection.BindingFlags]::GetProperty, $null, $I, $null); $O = foreach ($P in $PList) {$hash = @{}; $hash.ProductCode = $P; foreach ($A In $Attributes) {try {$hash."$($A)" = $T.InvokeMember(\'ProductInfo\', [System.Reflection.BindingFlags]::GetProperty, $null, $I, @($P, $A))} catch [System.Exception] {$hash."$($A)" = $null}}; New-Object -TypeName PSObject -Property $hash}; $O | foreach {$_.ProductName,$_.InstallLocation,$_.VersionString,$_.InstallDate,$_.PackageName,$_.Publisher,$_.RegCompany,$_.RegOwner,$_.ProductID,$_.URLInfoAbout  -Join "'+ delimiter + '"}'
		(rawOutput, stdError, hitProblem) = client.run(productsQuery, timeout)
		iterableObject = delimitedStringToIterableObject(rawOutput, delimiter)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception with discovering Products via WindowsInstaller library in PowerShell: {stacktrace!r}', stacktrace=stacktrace)

	## end executeProductQueryViaLibrary
	return (iterableObject, stdError, hitProblem)


def executeProductQueryViaVBScript(runtime, client, timeout=None):
	"""Query Windows products via WindowsInstaller library in vbscript.

	We use global parameters to determine whether to run the standard, slower
	WMI method to get Win32_Products, or to use the fast library method. This
	faster method requires streaming a vbscript file over the client connection
	first, before being able to run that script on the endpoint. But it has
	sub-second run times instead of anywhere between 10 seconds and 10 minutes
	to finish when doing it via Win32_Products in WMI.
	"""
	resultStdError = None
	resultProblem = None
	iterableObject = None
	sectionDemarcation = '-=-==-=-==-=-==-=-'
	p = '\''
	try:
		## Ignoring the query sent in; left in for reference only
		runtime.logger.report('  Running executeProductQuery through vbscript')
		## Build VB script to execute WMI query
		#Name,InstallLocation,Version,InstallDate,PackageName,Vendor,RegCompany,RegOwner,IdentifyingNumber,Description
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, 'Const SCRIPTVERSION = 1.2', p, ' >y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, 'set oMSI = CreateObject("WindowsInstaller.Installer")', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, 'Set Products = oMSI.ProductsEx(vbNullString, "S-1-1-0", 7,"")', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, 'Wscript.Echo "' + sectionDemarcation + '"', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, 'attributeList = Array("InstallLocation", "VersionString", "InstallDate", "PackageName", "Vendor", "RegCompany", "RegOwner", "IdentifyingNumber", "Description")', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, 'If Not Products.count = 0 Then', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, '  For Each product In Products', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, '    On Error Resume Next', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, '    tmpName = product.InstallProperty("ProductName")', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, '    If Not tmpName = "" and Not IsEmpty(tmpName) and Len(tmpName) > 0 Then', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, '      Wscript.Echo tmpName', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, '      For Each attribute In attributeList', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, '        On Error Resume Next', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, '        tmpVar = ""', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, '        tmpVar = product.InstallProperty(attribute)', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, '        If Not tmpVar = "" and Not IsEmpty(tmpVar) and Len(tmpVar) > 0 Then', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, '          Wscript.Echo tmpVar', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, '        Else', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, '          Wscript.Echo "null"', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, '        End If', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, '      Next', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, '      Wscript.Echo "' + sectionDemarcation + '"', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, '    End If', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, '  Next', p, ' >>y.vbs'))
		(stdOut, stdError, hitProblem) = client.run(concatenate('echo ', p, 'End If', p, ' >>y.vbs'))
		## Execute the new script
		(vbScript, stdError, hitProblem) = client.run('cat y.vbs')
		runtime.logger.report('  File:\n {vbScript!r}', vbScript=vbScript)
		resultStdOut = None
		(resultStdOut, resultStdError, resultProblem) = client.run('cscript .\y.vbs', timeout)
		runtime.logger.report('  File:\n {resultStdOut!r}', resultStdOut=resultStdOut)
		#(stdOut, stdError, hitProblem) = client.run('del y.vbs')
		iterableObject = sectionedStringToIterableObject(resultStdOut, sectionDemarcation)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception with discovering Windows Products from WindowsInstaller in vbscript: {stacktrace!r}', stacktrace=stacktrace)

	## end executeProductQueryViaVBScript
	return (iterableObject, resultStdError, resultProblem)


def executeRegistryQuery(runtime, client, keyPath, timeout=None):
	"""Query Windows registry keypath."""
	iterableObject = None
	stdError = None
	hitProblem = None
	try:
		delimiter = ':==:'
		wmiRegistryQuery = 'Get-ItemProperty HKLM:\\' + keyPath + ' | foreach {$_.DisplayName,$_.InstallLocation,$_.Publisher,$_.DisplayVersion,$_.Comments,$_.InstallDate -Join "'+ delimiter + '"}'
		(rawOutput, stdError, hitProblem) = client.run(wmiRegistryQuery, timeout)
		iterableObject = delimitedStringToIterableObject(rawOutput, delimiter)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in executeRegistryQuery with {keyPath!r}: {stacktrace!r}', keyPath=keyPath, stacktrace=stacktrace)

	## end executeRegistryQuery
	return (iterableObject, stdError, hitProblem)

###############################################################################
############################  END WINDOWS SECTION  ############################
###############################################################################


###############################################################################
############################  BEGIN LINUX SECTION  ############################
###############################################################################

def linuxGetSoftware(runtime, client, softwareListing):
	"""Parse Linux Software.

	Display software package information from various utilities. I originally
	built this for the core RPM and Debian package managers. But I expect this
	to be built out in the future to cover the sprawl of Linux distributions.
	Yum is not required since it wraps the former two, though yum does seem to
	track initial installs vs updates across multiple repositories. However, I
	need coverage for child OS offshoots. For example, Debian is the parent
	product of different Linux distros (Knoppix, Kali, Ubuntu, Mint), but those
	child/forked distros leverage different package managers besides just dbkg
	(e.g. apt, aptitude, synaptic, tasksel, deselect, dpkg-deb, dpkg-split).

	FYI: the funny delimiters (:==: and :##:) are there because descriptions can
	wrap lines and so the easiest way to parse was forcing delimiters.
	"""
	try:
		## First try the RedHat package utilities
		command = updateCommand(runtime, 'rpm -q -a --qf \'%{Name}:==:%{Version}:==:%{Packager}:==:%{Vendor}:==:%{Summary}:==:%{INSTALLTIME:date}:==:%{Description}:##:\n\'')
		(stdout, stderr, hitProblem) = client.run(command, 300)
		if (stdout is None or len(stdout) <= 0):
			runtime.logger.report('  Nothing returned from rpm query')
		elif (re.search('rpm:\s*command\s*not\s*found', stdout, re.I)):
			runtime.logger.report('  RPM package manager not found')
		else:
			linuxGetProductFromRPM(runtime, client, softwareListing, stdout)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in linuxGetSoftware when querying packages via rpm: {stacktrace!r}', stacktrace=stacktrace)

	try:
		## Now try the Debian package utilities
		command = updateCommand(runtime, 'dpkg-query -W -f=\'${Package}:==:${Version}:==:${Maintainer}:==:${Origin}:==:${Description}:##:\n\'')
		(stdout, stderr, hitProblem) = client.run(command, 240)
		if (stdout is None or len(stdout) <= 0):
			runtime.logger.report('  Nothing returned from dpkg-query')
		elif (re.search('dpkg-query:\s*command\s*not\s*found', stdout, re.I)):
			runtime.logger.report('  Debian package manager not found')
		else:
			linuxGetProductFromDebian(runtime, client, softwareListing, stdout)

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		runtime.logger.error('Exception in linuxGetSoftware when querying packages via dpkg-query: {stacktrace!r}', stacktrace=stacktrace)

	## end linuxGetSoftware
	return


def linuxGetProductFromRPM(runtime, client, softwareListing, output):
	"""Get software from the RPM package manager.

	Sample output
	===================================================================
	gnome-python2:==:2.28.0:==:Red Hat, Inc. <http://bugzilla.redhat.com/bugzilla>:==:Red Hat, Inc.:==:PyGNOME Python extension module:==:Sat 27 Oct 2012 07:34:37 AM CDT:==:The gnome-python package contains the source packages for the Python bindings for GNOME called PyGNOME.
	eclipse-platform:==:3.6.1:==:Red Hat, Inc. <http://bugzilla.redhat.com/bugzilla>:==:Red Hat, Inc.:==:Eclipse platform common files:==:Sat 27 Oct 2012 07:38:46 AM CDT:==:The Eclipse Platform is the base of all IDE plugins.  This does not include the Java Development Tools or the Plugin Development Environment.
	===================================================================
	"""
	if (output == None or len(output.strip()) <= 0):
		runtime.logger.report('Error: No output from rpm for installed packages')
		return

	## Delimiting with custom delimiter ':##:'
	matchRegEx = re.compile(r':##:')
	packages = matchRegEx.split(output)
	## Parse each package separately
	for line in packages:
		try:
			## Ignore blank lines and bad entries
			if not line:
				continue
			line = line.strip()
			if (line is None or len(line.strip()) <= 0):
				continue
			## Take the custom delimiter off
			line = line.split(':##:')[0]
			## Parse line into respective variables
			runtime.logger.report('  line: {line!r}', line=line)
			(name, version, packager, vendor, summary, datestamp, description) = line.split(':==:')
			runtime.logger.report('  Software name: {name!r}, version: {version!r}, packager: {packager!r}, vendor: {vendor!r}, datestamp: {dateStamp!r}', name=name, version=version, packager=packager, vendor=vendor, dateStamp=datestamp)
			runtime.logger.report('        summary: {summary!r}', summary=summary)
			runtime.logger.report('    description: {description!r}', description=description)
			## Add to the software list
			softwareListing[name] = (name, None, version, summary, 'Linux Software from RPM', None, description, packager, None, vendor, datestamp)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in linuxGetProductFromRPM: {stacktrace!r}', stacktrace=stacktrace)

	## end linuxGetProductFromRPM
	return


def linuxGetProductFromDebian(runtime, client, softwareListing, output):
	"""Get software from the Debian package manager.

	Sample output
	===================================================================
	packageName:==:1.2.3:==:company:==:origin:==:description
	===================================================================
	"""
	if (output == None or len(output.strip()) <= 0):
		runtime.logger.report('Error: No output from dpkg-query for installed packages')
		return

	## Delimiting with custom delimiter ':##:'
	matchRegEx = re.compile(r':##:\d')
	packages = matchRegEx.split(output)
	## Parse each package separately
	for line in packages:
		try:
			## Ignore blank lines and bad entries
			if not line:
				continue
			line = line.strip()
			if (line is None or len(line.strip()) <= 0):
				continue
			## Take the custom delimiter off
			line = line.split(':##:')[0]
			datestamp = None
			## Parse line into respective variables
			runtime.logger.report('  line: {line!r}', line=line)
			(name, version, company, origin, description) = line.split(':==:')
			reportToDebug(['  Software Name: ', name, ', Version: ', version, ', Packager: ', company, ', Origin: ', origin, ', Description: ', description], printDebug)
			runtime.logger.report('  Software name: {name!r}, version: {version!r}, company: {company!r}, origin: {origin!r}', name=name, version=version, company=company, origin=origin)
			runtime.logger.report('    description: {description!r}', description=description)
			## Add to the software list
			softwareListing[name] = (name, None, version, None, 'Linux Software from Debian', None, description, company, None, origin, datestamp)

		except:
			stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			runtime.logger.error('Exception in linuxGetProductFromDebian: {stacktrace!r}', stacktrace=stacktrace)

	## end linuxGetProductFromDebian
	return

###############################################################################
#############################  END LINUX SECTION  #############################
###############################################################################
