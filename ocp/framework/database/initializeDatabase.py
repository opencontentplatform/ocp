"""Utility to initialize database tables.

Functions:
  |  main                : entry point
  |  getSettings         : pull connection parameters from file
  |  createObjects       : create schemas/tables/objects
  |  createRealms        : Inserting the instances of Relm to relm table
  |  createTriggerTypes  : Inserting the instances of TriggerType to trigger_type table
  |  createContentModule : Inserting the instances of ContentModule to content_module table
  |  createApiAccess     : Inserting instances of ContentModule into content_module table

Author: Chris Satterthwaite (CS)
Contributors:
Version info:
  1.0 : (CS) Created July 27, 2017

"""

import os
import sys
import re
import traceback
import uuid
import json
import logging

## Add openContentPlatform directories onto the sys path
thisPath = os.path.dirname(os.path.abspath(__file__))
basePath = os.path.abspath(os.path.join(thisPath, '..'))
if basePath not in sys.path:
	sys.path.append(basePath)
import env
env.addLibPath()

## from Open Content Platform
import utils
from database.connectionPool import DatabaseClient
from database.schema.linkSchema import *
from database.schema.baseSchema import *
from database.schema.platformSchema import *


def createRealms(dbClient, logger):
	"""Inserting instances of Realm into realm table.

	Arguments:
	  dbClient (DatabaseClient) : Instance of database client
	  logger                    : Handler for the database log

	"""
	try:
		r = Realm.as_unique(dbClient.session, name='default')
		r2 = Realm.as_unique(dbClient.session, name='custom')
		dbClient.session.commit()
		r3 = Realm.as_unique(dbClient.session, name='custom')
		dbClient.session.commit()

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Failure in createRealms: {}'.format(str(stacktrace)))

	## end createRealms
	return


def createScopes(dbClient, logger):
	"""Inserting instances of Scope into scope table.

	Arguments:
	  dbClient (DatabaseClient) : Instance of database client
	  logger                    : Handler for the database log

	"""
	try:
		scope1 = { "entry" : "192.168.121.1/24",
				   "exclusion" : [{"entry" : "192.168.121.14/32"}, {"entry" : "192.168.121.24"}, {"entry" : "192.168.121.34", "entryStop" : "192.168.121.37"}]
				   }
		scope2 = { "entry" : "192.168.120.1/255.255.255.0",
				   "exclusion" : []
				   }
		scope3 = { "entry" : "192.168.1.100",
				   "entryStop" : "192.168.1.200",
				   "exclusion" : []
				   }

		s1 = Scope(object_id=uuid.uuid4().hex, data=json.dumps(scope1), realm='default')
		dbClient.session.add(s1)
		dbClient.session.commit()
		s2 = Scope(object_id=uuid.uuid4().hex, data=json.dumps(scope2), realm='default')
		dbClient.session.add(s2)
		dbClient.session.commit()
		s3 = Scope(object_id=uuid.uuid4().hex, data=json.dumps(scope3), realm='default')
		dbClient.session.add(s3)
		dbClient.session.commit()

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Failure in createScopes: {}'.format(str(stacktrace)))

	## end createScopes
	return


def createTriggerTypes(dbClient, logger):
	"""Inserting instances of TriggerType into trigger_types table.

	Arguments:
	  dbClient (DatabaseClient) : Instance of database client
	  logger                    : Handler for the database log

	"""
	try:
		tcron = TriggerType.as_unique(dbClient.session, name='cron')
		tinterval = TriggerType.as_unique(dbClient.session, name='interval')
		dbClient.session.commit()

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Failure in createTriggerTypes: {}'.format(str(stacktrace)))

	## end createTriggerTypes
	return


def baselineContentGatheringParameters(dbClient, logger):

	"""Inserting os_parameters and config_default.

	Arguments:
	  dbClient (DatabaseClient) : Instance of database client
	  logger                    : Handler for the database log

	"""
	try:
		content = {"Windows": {"connectViaFQDN": False, "useLibraryToGetWin32Products": True, "createVbscriptToGetWin32Products": False, "networkSocketUtilities": ["netstat"], "commandsToTransform": {"netstat": {"replacementList": ["netstat"], "testCmd": "Get-Command <cmd> | %{$_.source}", "testOutput": None}, "python": {"replacementList": ["python"], "testCmd": "<cmd> -V", "testOutput": "[Pp]ython"}, "ping": {"replacementList": ["ping"], "testCmd": "<cmd> -n 1 localhost", "testOutput": None}}, "softwareFilterFlag": True, "softwareFilterByPackageName": True, "softwareFilterByVendor": True, "softwareFilterByCompany": True, "softwareFilterByOwner": True, "softwareFilterIncludeList": [], "softwareFilterExcludeList": ["Security Update", "Hotfix", "Redistributable", "Silverlight"], "softwareFilterExcludeCompare": "==", "startTaskFilterFlag": True, "startTaskFilterByName": False, "startTaskFilterByDisplayName": False, "startTaskFilterByStartName": False, "startTaskFilterByActiveState": True, "startTaskFilterIncludeList": [], "startTaskFilterExcludeList": [], "startTaskFilterPathExcludeList": ["system32\\\\svchost\\.exe"], "startTaskFilterPathExcludeCompare": "regex", "startTaskFilterExcludeCompare": "==", "processIgnoreList": ["conhost.exe", "svchost.exe"], "processFilterExcludeOsList": ["notepad.exe", "mmc.exe", "TrustedInstaller.exe"], "processFilterExcludeOsCompare": "regex", "interpreters": ["^cmd(?:\\.exe)?$", "^powershell(?:\\.exe)?$", "^perl(?:\\.exe)?$", "^win-bash(?:\\.exe)?$", "^cygwin(?:\\.exe)?$", "^python(?:\\d(?:\\.\\d)?)?", "^pwsh(?:\\.exe)?$"], "topLevelProcess": ["explorer.exe", "services.exe", "wininit.exe", "system", "system idle process"]}, "Linux": {"commandsToRunOnLowPriority": ["rpm", "dpkg-query"], "lowPriorityOnAllCommands": False, "lowPriorityCommandUtility": "nice", "commandsToRunWithElevatedAccess": ["dmidecode", "cat", "ls", "netstat", "lsof", "ss", "rpm", "dpkg-query"], "elevatedCommandUtility": "sudo", "networkSocketUtilities": ["netstat", "lsof", "ss"], "commandsToTransform": {"sudo": {"replacementList": ["sudo", "pbrun", "rbac", "dzdo"], "testCmd": "which <cmd>", "testOutput": None}, "dmidecode": {"replacementList": ["/usr/sbin/dmidecode", "dmidecode"], "testCmd": "<cmd> --version", "testOutput": None}, "netstat": {"replacementList": ["netstat", "/bin/netstat"], "testCmd": "<cmd> --version", "testOutput": None}, "lsof": {"replacementList": ["lsof", "/usr/sbin/lsof"], "testCmd": "<cmd> -v", "testOutput": None}, "ss": {"replacementList": ["ss", "/usr/sbin/ss"], "testCmd": "<cmd> -v", "testOutput": None}, "rpm": {"replacementList": ["/bin/rpm", "rpm"], "testCmd": "<cmd> --version", "testOutput": None}, "ls": {"replacementList": ["ls --color=never"], "testCmd": "<cmd>", "testOutput": None}, "perl": {"replacementList": ["perl"], "testCmd": "<cmd> -v", "testOutput": None}}, "softwareFilterFlag": True, "softwareFilterByPackageName": True, "softwareFilterByVendor": True, "softwareFilterIncludeList": [], "softwareFilterExcludeList": ["Red\\s*Hat", "gvfs", "note-taking", "gnome-*", "imsettings"], "softwareFilterExcludeCompare": "==", "processIgnoreList": ["su"], "processFilterExcludeOsList": ["^awk$", "gnome-", "-gnome", "kthread", "khelper", "^less$", "^mail$", "^man$", "^more$", "^sleep$", "^X$", "xscreensaver", "^ps$", "^netstat$", "^lsof$"], "processFilterExcludeOsCompare": "regex", "interpreters": ["^sh$", "^-sh$", "^bash$", "^-bash$", "^csh$", "^tcsh$", "^ksh$", "^zsh$", "^fish$", "^perl$", "^python(?:\\d(?:\\.\\d)?)?$", "^pwsh$"], "topLevelProcess": ["init", "systemd", "sshd", "gnome-shell", "bash", "-bash"]}}
		osParams = OsParameters(realm='default', content=content)
		dbClient.session.add(osParams)
		dbClient.session.commit()
		logger.debug('Created OsParameters')

		content = {"networkCreateLocalEndpoints": False, "networkResolveUnspecifiedEndpoints": True, "networkCreateUdpListeners": True, "networkCreateTcpListeners": True, "networkCreateTcpEstablished": True, "processFilterExcludeOverrideCompare": "regex", "processFilterExcludeOverrideList": ["gnome-shell", "^sh$", "^bash$", "^sshd$", "^[Pp]ython$", "^[Jj]ava", "^[Pp]erl$", "^[Pp]ower[Ss]hell", "^[Pp]wsh", "[Cc]ygwin", "^[Cc]md.exe$"], "softwareFilterExcludeOverrideCompare": "regex", "softwareFilterExcludeOverrideList": ["^[Pp]ython$", "^[Jj]ava", "^[Pp]erl$", "^[Pp]ower[Ss]hell", "[Cc]ygwin"]}
		defaultParams = ConfigDefault(realm='default', content=content)
		dbClient.session.add(defaultParams)
		dbClient.session.commit()
		logger.debug('Created ConfigDefault')

		configGroups = ConfigGroups(realm='default', content=[])
		dbClient.session.add(configGroups)
		dbClient.session.commit()
		logger.debug('Created ConfigGroups')

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Failure in baselineContentGatheringParameters: {}'.format(str(stacktrace)))

	## end baselineContentGatheringParameters
	return


def createQueryDefinitions(dbClient, logger):
	"""Inserting query_definition's.

	Arguments:
	  dbClient (DatabaseClient) : Instance of database client
	  logger                    : Handler for the database log

	"""
	try:
		query1 = {"objects": [{"label": "NODE","class_name": "Node","attributes": [ "caption", "domain" ],"minimum": "1","maximum": "","filter": [],"linchpin": True},{"label": "IP","class_name": "IpAddress","attributes": [ "caption" ],"minimum": "0","maximum": "","filter": [{"condition": {"attribute": "address","operator": "!=","value": "127.0.0.1"}}]},{"label": "HW","class_name": "HardwareNode","attributes": ["caption", "vendor", "model", "serial_number", "bios_info"],"minimum": "0","maximum": ""},{"label": "SHELL","class_name": "Shell","attributes": ["caption", "ipaddress", "protocol_reference", "realm", "config_group"],"minimum": "0","maximum": "","filter": []},{"label": "WMI","class_name": "WMI","attributes": ["caption", "ipaddress", "protocol_reference", "realm"],"minimum": "0","maximum": "","filter": []},{"label": "SNMP","class_name": "SNMP","attributes": ["caption", "ipaddress", "protocol_reference", "realm"],"minimum": "0","maximum": "","filter": []}],"links": [{"label": "NODE_TO_IP","class_name": "Usage","attributes": [],"first_id": "NODE","second_id": "IP"},{"label": "NODE_TO_HW","class_name": "Usage","attributes": [],"first_id": "NODE","second_id": "HW"},{"label": "NODE_TO_SHELL","class_name": "Enclosed","attributes": [],"first_id": "NODE","second_id": "SHELL"},{"label": "NODE_TO_WMI","class_name": "Enclosed","attributes": [],"first_id": "NODE","second_id": "WMI"},{"label": "NODE_TO_SNMP","class_name": "Enclosed","attributes": [],"first_id": "NODE","second_id": "SNMP"}]}
		definition1 = QueryDefinition(name='Find endpoints', json_query=query1)
		dbClient.session.add(definition1)
		dbClient.session.commit()
		logger.debug('Created input driven query 1')


		query2 = {"objects": [{"label": "NODE1","class_name": "Node","attributes": ["caption","vendor","platform","version","hardware_provider"],"minimum": "1","maximum": "","linchpin": true},{"label": "PROCESS1","class_name": "ProcessFingerprint","attributes": ["caption","process_owner","process_args","path_from_process","path_from_analysis","path_working_dir","process_hierarchy"],"minimum": "1","maximum": ""},{"label": "PORT2","class_name": "TcpIpPortClient","attributes": ["caption","ip","port_type"],"minimum": "1","maximum": ""},{"label": "PROCESS2","class_name": "ProcessFingerprint","attributes": ["caption","process_owner","process_args","path_from_process","path_from_analysis","path_working_dir","process_hierarchy"],"minimum": "0","maximum": ""},{"label": "NODE2","class_name": "Node","attributes": ["caption","vendor","platform","version","hardware_provider"],"minimum": "1","maximum": ""},{"label": "PORT3","class_name": "TcpIpPortClient","attributes": ["caption","ip","port_type"],"minimum": "1","maximum": ""},{"label": "PROCESS3","class_name": "ProcessFingerprint","attributes": ["caption","process_owner","process_args","path_from_process","path_from_analysis","path_working_dir","process_hierarchy"],"minimum": "0","maximum": ""},{"label": "NODE3","class_name": "Node","attributes": ["caption","vendor","platform","version","hardware_provider"],"minimum": "1","maximum": ""}],"links": [{"label": "NODE_TO_SOFTWARE","class_name": "Enclosed","first_id": "NODE1","second_id": "PROCESS1"},{"label": "PROCESS1_TO_PORT1","class_name": "ServerClient","first_id": "PROCESS1","second_id": "PORT2"},{"label": "PORT2_TO_PROCESS","class_name": "Usage","first_id": "PROCESS2","second_id": "PORT2"},{"label": "NODE2_TO_PROCESS","class_name": "Enclosed","first_id": "NODE2","second_id": "PROCESS2"},{"label": "PORT3_TO_PROCESS","class_name": "ServerClient","first_id": "PROCESS3","second_id": "PORT3"},{"label": "NODE3_TO_PROCESS","class_name": "Enclosed","first_id": "NODE3","second_id": "PROCESS3"}]}
		definition2 = QueryDefinition(name='Process dependencies between nodes', json_query=query2)
		dbClient.session.add(definition2)
		dbClient.session.commit()
		logger.debug('Created input driven query 2')

		query3 = {"objects": [{"label": "APPLICATION","class_name": "BusinessApplication","attributes": [],"minimum": "1","maximum": "","linchpin": True}, {"label": "ENVIRONMENT","class_name": "EnvironmentGroup","attributes": [],"minimum": "1","maximum": ""}, {"label": "SOFTWARE","class_name": "SoftwareGroup","attributes": [],"minimum": "1","maximum": ""}, {"label": "LOCATION","class_name": "LocationGroup","attributes": [],"minimum": "0","maximum": ""}, {"label": "MODELOBJECT","class_name": "ModelObject","attributes": [],"minimum": "0","maximum": "","filter": []}, {"label": "PROCESS","class_name": "SoftwareElement","attributes": [],"minimum": "0","maximum": "","filter": []}],    "links": [{"label": "APP_TO_ENV","class_name": "Contain","first_id": "APPLICATION","second_id": "ENVIRONMENT"}, {"label": "ENV_TO_SW","class_name": "Contain","first_id": "ENVIRONMENT","second_id": "SOFTWARE"}, {"label": "SW_TO_LOC","class_name": "Contain","first_id": "SOFTWARE","second_id": "LOCATION"}, {"label": "LOC_TO_OBJECT","class_name": "Contain","first_id": "LOCATION","second_id": "MODELOBJECT"}, {"label": "OBJECT_TO_PROCESS","class_name": "Usage","first_id": "MODELOBJECT","second_id": "PROCESS"}]}
		definition3 = QueryDefinition(name='Models in graph form', json_query=query3)
		dbClient.session.add(definition3)
		dbClient.session.commit()
		logger.debug('Created input driven query 3')

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Failure in createQueryDefinitions: {}'.format(str(stacktrace)))

	## end createQueryDefinitions
	return


def createInputDrivenQueryDefinitions(dbClient, logger):
	"""Inserting input_driven_query_definition's.

	Arguments:
	  dbClient (DatabaseClient) : Instance of database client
	  logger                    : Handler for the database log

	"""
	try:
		queryDefinitions = {
			'Node software' :
				{"objects": [{"label": "NODE1","class_name": "Node","attributes": [],"minimum": "1","maximum": "","linchpin": True, "filter": [{"condition": {"attribute": "hostname","operator": "==","value": "INPUT"}}]}, {"label": "SOFTWARE1","class_name": "SoftwareFingerprint","attributes": [],"minimum": "1","maximum": ""}, {"label": "PROCESS1","class_name": "ProcessFingerprint","attributes": [],"minimum": "1","maximum": ""}],"links": [{"label": "NODE1_TO_SOFTWARE1","class_name": "Enclosed","first_id": "NODE1","second_id": "SOFTWARE1"}, {"label": "SOFTWARE1_TO_PROCESS1","class_name": "Usage","first_id": "SOFTWARE1","second_id": "PROCESS1"}]},

			'Node software to process' :
				{"objects": [{"label": "NODE1","class_name": "Node","attributes": [],"minimum": "1","maximum": "","linchpin": True, "filter": [{"condition": {"attribute": "hostname","operator": "==","value": "INPUT"}}]}, {"label": "SOFTWARE1","class_name": "SoftwareFingerprint","attributes": [],"minimum": "1","maximum": ""}, {"label": "PROCESS1","class_name": "ProcessFingerprint","attributes": [],"minimum": "1","maximum": ""}],"links": [{"label": "NODE1_TO_SOFTWARE1","class_name": "Enclosed","first_id": "NODE1","second_id": "SOFTWARE1"}, {"label": "SOFTWARE1_TO_PROCESS1","class_name": "Usage","first_id": "SOFTWARE1","second_id": "PROCESS1"}]},

			'Node server software established' :
				{"objects": [{"label": "SERVER","class_name": "Node","attributes": ["hostname"],"minimum": "1","maximum": "","linchpin": True, "filter": [{"condition": {"attribute": "hostname","operator": "==","value": "INPUT"}}]},{"label": "SERVERSOFTWARE","class_name": "SoftwareFingerprint","attributes": ["caption", "software_version", "software_info", "software_id", "software_source", "vendor"],"minimum": "1","maximum": ""},{"label": "SERVERPROCESS","class_name": "ProcessFingerprint","attributes": ["caption", "process_owner", "process_args", "process_hierarchy", "path_from_process", "path_from_filesystem", "path_from_analysis" ],"minimum": "1","maximum": ""},{"label": "CLIENTPORT","class_name": "TcpIpPortClient","attributes": ["caption", "ip"],"minimum": "1","maximum": ""},{"label": "CLIENTPROCESS","class_name": "ProcessFingerprint","attributes": ["caption", "process_owner", "process_args", "process_hierarchy", "path_from_process", "path_from_filesystem", "path_from_analysis" ],"minimum": "1","maximum": ""},{"label": "CLIENTSOFTWARE","class_name": "SoftwareFingerprint","attributes": ["caption", "software_version", "software_info", "software_id", "software_source", "vendor"],"minimum": "1","maximum": ""},{"label": "CLIENT","class_name": "Node","attributes": ["caption"],"minimum": "1","maximum": ""}],"links": [{"label": "Server_to_process","class_name": "Enclosed","first_id": "SERVER","second_id": "SERVERSOFTWARE"},{"label": "Software_to_process","class_name": "Usage","first_id": "SERVERSOFTWARE","second_id": "SERVERPROCESS"},{"label": "Server_proc_to_port","class_name": "ServerClient","first_id": "SERVERPROCESS","second_id": "CLIENTPORT"},{"label": "Client_to_port","class_name": "Usage","first_id": "CLIENTPROCESS","second_id": "CLIENTPORT"},{"label": "Client_to_process","class_name": "Usage","first_id": "CLIENTSOFTWARE","second_id": "CLIENTPROCESS"},{"label": "Client_to_software","class_name": "Enclosed","first_id": "CLIENT","second_id": "CLIENTSOFTWARE"}]},

			'Node server software TCP connections' :
				{"objects": [{"label": "SERVER","class_name": "Node","attributes": [ "caption" ],"minimum": "1","maximum": "","linchpin": True,"filter": [{"condition": {"attribute": "hostname","operator": "==","value": "INPUT"}}]},{"label": "SERVERSOFTWARE","class_name": "SoftwareFingerprint","attributes": [ "caption", "software_version", "software_info", "software_id", "software_source", "vendor" ],"minimum": "1","maximum": ""},{"label": "SERVERPROCESS","class_name": "ProcessFingerprint","attributes": ["caption", "process_owner", "process_args", "process_hierarchy", "path_from_process", "path_from_filesystem", "path_from_analysis" ],"minimum": "1","maximum": ""},{"label": "CLIENTPORT","class_name": "TcpIpPortClient","attributes": ["caption", "ip"],"minimum": "1","maximum": ""},{"label": "CLIENTIP","class_name": "IpAddress","attributes": ["caption"],"minimum": "1","maximum": ""},{"label": "CLIENT","class_name": "Node","attributes": ["caption"],"minimum": "0","maximum": ""}],"links": [{"label": "Server_to_process","class_name": "Enclosed","first_id": "SERVER","second_id": "SERVERSOFTWARE"},{"label": "Software_to_process","class_name": "Usage","first_id": "SERVERSOFTWARE","second_id": "SERVERPROCESS"},{"label": "Server_proc_to_port","class_name": "ServerClient","first_id": "SERVERPROCESS","second_id": "CLIENTPORT"},{"label": "Client_to_port","class_name": "Enclosed","first_id": "CLIENTIP","second_id": "CLIENTPORT"},{"label": "Client_to_ip","class_name": "Usage","first_id": "CLIENT","second_id": "CLIENTIP"}]},

			'Node process' :
				{"objects": [{"label": "Server","class_name": "Node","attributes": ["caption"],"minimum": "1","maximum": "","linchpin": True, "filter": [{"condition": {"attribute": "hostname","operator": "==","value": "INPUT"}}]},{"label": "Process","class_name": "ProcessFingerprint","attributes": ["caption", "process_owner", "process_args", "process_hierarchy", "path_from_process", "path_from_filesystem", "path_from_analysis" ],"minimum": "1","maximum": ""}],"links": [{"label": "Server_to_Process","class_name": "Enclosed","first_id": "Server","second_id": "Process"}]},

			'Node process to software' :
				{"objects": [{"label": "Server","class_name": "Node","attributes": ["caption"],"minimum": "1","maximum": "","linchpin": True, "filter": [{"condition": {"attribute": "hostname","operator": "==","value": "INPUT"}}]},{"label": "Process","class_name": "ProcessFingerprint","attributes": ["caption", "process_owner", "process_args", "process_hierarchy", "path_from_process", "path_from_filesystem", "path_from_analysis" ],"minimum": "1","maximum": ""},{"label": "Software","class_name": "SoftwareFingerprint","attributes": [ "caption", "software_info", "software_version", "vendor"],"minimum": "0","maximum": ""}],"links": [{"label": "Server_to_Process","class_name": "Enclosed","first_id": "Server","second_id": "Process"},{"label": "Software_to_Process","class_name": "Usage","first_id": "Software","second_id": "Process"}]},

			'Node network stack' :
				{"objects": [{"label": "SOURCENODE","class_name": "Node","attributes": ["caption"],"minimum": "1","maximum": "","linchpin": True, "filter": [{"condition": {"attribute":"hostname","operator": "==","value": "INPUT"}}]},{"label": "SOURCEIP","class_name": "IpAddress","attributes": ["caption"],"minimum": "1","maximum": ""},{"label": "CLIENTPORT","class_name": "TcpIpPortClient","attributes": ["caption", "ip"],"minimum": "0","maximum": ""},{"label": "CLIENTIP","class_name":"IpAddress","attributes": ["caption"],"minimum": "0","maximum": ""},{"label": "CLIENT","class_name": "Node","attributes": ["caption"],"minimum": "0","maximum": ""},{"label": "SERVERPORT","class_name": "TcpIpPortClient","attributes": ["caption", "ip"],"minimum": "0","maximum": ""},{"label": "SERVERIP","class_name":"IpAddress","attributes": ["caption"],"minimum": "0","maximum": ""},{"label": "SERVER","class_name": "Node","attributes": ["caption"],"minimum": "0","maximum": ""}],"links": [{"label": "Server_to_process","class_name": "Usage","first_id": "SOURCENODE","second_id": "SOURCEIP"},{"label": "Server_IP_port","class_name":"ServerClient","first_id": "SOURCEIP","second_id": "CLIENTPORT"},{"label": "Server_proc_to_port1","class_name": "Enclosed","first_id": "CLIENTIP","second_id":"CLIENTPORT"},{"label": "Client_to_IP1","class_name": "Usage","first_id": "CLIENT","second_id": "CLIENTIP"},{"label": "Server_IP_port","class_name": "Enclosed","first_id": "SOURCEIP","second_id": "SERVERPORT"},{"label": "Server_proc_to_port2","class_name": "ServerClient","first_id": "SERVERIP","second_id": "SERVERPORT"},{"label": "Client_to_IP2","class_name": "Usage","first_id": "SERVER","second_id": "SERVERIP"}]},

			'Node process dependencies':
				{"objects": [{"label": "NODE1","class_name": "Node","attributes": ["caption","vendor","platform","version","hardware_provider"],"minimum": "1","maximum": "","linchpin": True, "filter": [{"condition": {"attribute": "hostname","operator": "==","value": "INPUT"}}]},{"label": "PROCESS1","class_name": "ProcessFingerprint","attributes": ["caption","process_owner","process_args","path_from_process","path_from_analysis","path_working_dir","process_hierarchy"],"minimum": "1","maximum": ""},{"label": "PORT2","class_name": "TcpIpPortClient","attributes": ["caption","ip","port_type"],"minimum": "1","maximum": ""},{"label": "PROCESS2","class_name": "ProcessFingerprint","attributes": ["caption","process_owner","process_args","path_from_process","path_from_analysis","path_working_dir","process_hierarchy"],"minimum": "0","maximum": ""},{"label": "NODE2","class_name": "Node","attributes": ["caption","vendor","platform","version","hardware_provider"],"minimum": "1","maximum": ""},{"label": "PORT3","class_name": "TcpIpPortClient","attributes": ["caption","ip","port_type"],"minimum": "1","maximum": ""},{"label": "PROCESS3","class_name": "ProcessFingerprint","attributes": ["caption","process_owner","process_args","path_from_process","path_from_analysis","path_working_dir","process_hierarchy"],"minimum": "0","maximum": ""},{"label": "NODE3","class_name": "Node","attributes": ["caption","vendor","platform","version","hardware_provider"],"minimum": "1","maximum": ""}],"links": [{"label": "NODE_TO_SOFTWARE","class_name": "Enclosed","first_id": "NODE1","second_id": "PROCESS1"},{"label": "PROCESS1_TO_PORT1","class_name": "ServerClient","first_id": "PROCESS1","second_id": "PORT2"},{"label": "PORT2_TO_PROCESS","class_name": "Usage","first_id": "PROCESS2","second_id": "PORT2"},{"label": "NODE2_TO_PROCESS","class_name": "Enclosed","first_id": "NODE2","second_id": "PROCESS2"},{"label": "PORT3_TO_PROCESS","class_name": "ServerClient","first_id": "PROCESS3","second_id": "PORT3"},{"label": "NODE3_TO_PROCESS","class_name": "Enclosed","first_id": "NODE3","second_id": "PROCESS3"}]}

			'Node server process established' :
				{"objects": [{"label": "SERVER","class_name": "Node","attributes": ["caption", "platform"],"minimum": "1","maximum": "","linchpin": True, "filter": [{"condition": {"attribute": "hostname","operator": "==","value": "INPUT"}}]},{"label": "SERVERPROCESS","class_name": "ProcessFingerprint","attributes": ["caption", "process_owner", "process_args", "process_hierarchy", "path_from_process", "path_from_filesystem", "path_from_analysis" ],"minimum": "1","maximum": ""},{"label": "CLIENTPORT","class_name": "TcpIpPortClient","attributes": ["caption", "ip", "port"],"minimum": "1","maximum": ""},{"label": "CLIENTPROCESS","class_name": "ProcessFingerprint","attributes": ["caption", "process_owner", "process_args", "process_hierarchy", "path_from_process", "path_from_filesystem", "path_from_analysis" ],"minimum": "1","maximum": ""},{"label": "CLIENT","class_name": "Node","attributes": ["caption", "platform"],"minimum": "1","maximum": ""}],"links": [{"label": "Server_to_process","class_name": "Enclosed","first_id": "SERVER","second_id": "SERVERPROCESS"},{"label": "Server_proc_to_port","class_name": "ServerClient","first_id": "SERVERPROCESS","second_id": "CLIENTPORT"},{"label": "Client_to_port","class_name": "Usage","first_id": "CLIENTPROCESS","second_id": "CLIENTPORT"},{"label": "Client_to_process","class_name": "Enclosed","first_id": "CLIENT","second_id": "CLIENTPROCESS"}]},

			'Node server process TCP connections' :
				{"objects": [{"label": "SERVER","class_name": "Node","attributes": ["caption", "platform"],"minimum": "1","maximum": "","linchpin": True, "filter": [{"condition": {"attribute": "hostname","operator": "==","value": "INPUT"}}]},{"label": "SERVERPROCESS","class_name": "ProcessFingerprint","attributes": ["caption", "process_owner", "process_args", "process_hierarchy", "path_from_process", "path_from_filesystem", "path_from_analysis" ],"minimum": "1","maximum": ""},{"label": "CLIENTPORT","class_name": "TcpIpPortClient","attributes": ["caption", "ip", "port"],"minimum": "1","maximum": ""},{"label": "CLIENTIP","class_name": "IpAddress","attributes": ["caption"],"minimum": "1","maximum": ""},{"label": "CLIENT","class_name": "Node","attributes": ["caption", "platform"],"minimum": "0","maximum": ""}],"links": [{"label": "Server_to_process","class_name": "Enclosed","first_id": "SERVER","second_id": "SERVERPROCESS"},{"label": "Server_proc_to_port","class_name": "ServerClient","first_id": "SERVERPROCESS","second_id": "CLIENTPORT"},{"label": "Client_IP_port","class_name": "Enclosed","first_id": "CLIENTIP","second_id": "CLIENTPORT"},{"label": "Client_to_IP","class_name": "Usage","first_id": "CLIENT","second_id": "CLIENTIP"}]},

			'Node server process TCP listeners' :
				{"objects": [{"label": "SERVER","class_name": "Node","attributes": ["caption"],"minimum": "1","maximum": "","linchpin": True, "filter": [{"condition": {"attribute": "hostname","operator": "==","value": "INPUT"}}]},{"label": "SERVERPROCESS","class_name": "ProcessFingerprint","attributes": ["caption", "process_owner", "process_args", "process_hierarchy", "path_from_process", "path_from_filesystem", "path_from_analysis" ],"minimum": "1","maximum": ""},{"label": "PORT","class_name": "TcpIpPort","attributes": ["caption", "ip", "port"],"minimum": "1","maximum": ""}],"links": [{"label": "Server_to_process","class_name": "Enclosed","first_id": "SERVER","second_id": "SERVERPROCESS"},{"label": "Server_proc_to_port","class_name": "Usage","first_id": "SERVERPROCESS","second_id": "PORT"}]},

			'Node client process established' :
				{"objects": [{"label": "CLIENT","class_name": "Node","attributes": ["caption"],"minimum": "1","maximum": "","linchpin": True, "filter": [{"condition": {"attribute": "hostname","operator": "==","value": "INPUT"}}]},{"label": "CLIENTPROCESS","class_name": "ProcessFingerprint","attributes": ["caption", "process_owner", "process_args", "process_hierarchy", "path_from_process", "path_from_filesystem", "path_from_analysis" ],"minimum": "1","maximum": ""},{"label": "CLIENTPORT","class_name": "TcpIpPortClient","attributes": ["caption", "ip", "port"],"minimum": "1","maximum": ""},{"label": "SERVERPROCESS","class_name": "ProcessFingerprint","attributes": ["caption", "process_owner", "process_args", "process_hierarchy", "path_from_process", "path_from_filesystem", "path_from_analysis" ],"minimum": "1","maximum": ""},{"label": "SERVER","class_name": "Node","attributes": ["caption"],"minimum": "1","maximum": ""}],"links": [{"label": "Client_to_process","class_name": "Enclosed","first_id": "CLIENT","second_id": "CLIENTPROCESS"},{"label": "Client_to_port","class_name": "Usage","first_id": "CLIENTPROCESS","second_id": "CLIENTPORT"},{"label": "Server_proc_to_port","class_name": "ServerClient","first_id": "SERVERPROCESS","second_id": "CLIENTPORT"},{"label": "Server_to_process","class_name": "Enclosed","first_id": "SERVER","second_id": "SERVERPROCESS"}]},

			'Node client process TCP connections' :
				{"objects": [{"label": "CLIENT","class_name": "Node","attributes": ["caption"],"minimum": "1","maximum": "","linchpin": True, "filter": [{"condition": {"attribute": "hostname","operator": "==","value": "INPUT"}}]},{"label": "CLIENTPROCESS","class_name": "ProcessFingerprint","attributes": ["caption", "process_owner", "process_args", "process_hierarchy", "path_from_process", "path_from_filesystem", "path_from_analysis" ],"minimum": "1","maximum": ""},{"label": "CLIENTPORT","class_name": "TcpIpPortClient","attributes": ["caption", "ip", "port"],"minimum": "1","maximum": ""},{"label": "SERVERIP","class_name": "IpAddress","attributes": ["caption"],"minimum": "1","maximum": ""},{"label": "SERVER","class_name": "Node","attributes": ["caption"],"minimum": "0","maximum": ""}],"links": [{"label": "Client_to_process","class_name": "Enclosed","first_id": "CLIENT","second_id": "CLIENTPROCESS"},{"label": "Client_to_port","class_name": "Usage","first_id": "CLIENTPROCESS","second_id": "CLIENTPORT"},			{"label": "Server_proc_to_port","class_name": "ServerClient","first_id": "SERVERIP","second_id": "CLIENTPORT"},{"label": "Server_to_process","class_name": "Usage","first_id": "SERVER","second_id": "SERVERIP"}]},

			'Process args with dependencies' :
				{"objects": [{"label": "NODE1","class_name": "Node","attributes": [],"minimum": "1","maximum": "","linchpin": True}, {"label": "PROCESS1","class_name": "ProcessFingerprint","attributes": [],"minimum": "1","maximum": "","filter": [{"negation": "False","expression": [{"condition": {"attribute": "process_args","operator": "==","value" : "INPUT"}}]}]}, {"label": "PORT1","class_name": "TcpIpPort","attributes": ["caption", "ip", "port_type"],"minimum": "0","maximum": ""}, {"label": "PROCESS2","class_name": "ProcessFingerprint","attributes": [],"minimum": "1","maximum": ""}, {"label": "NODE2","class_name": "Node","attributes": [],"minimum": "1","maximum": ""}, {"label": "PORT3","class_name": "TcpIpPort","attributes": ["caption", "ip", "port_type"],"minimum": "0","maximum": ""}, {"label": "PROCESS3","class_name": "ProcessFingerprint","attributes": [],"minimum": "1","maximum": ""}, {"label": "NODE3","class_name": "Node","attributes": [],"minimum": "1","maximum": ""}],"links": [{"label": "NODE1_TO_PROCESS1","class_name": "Enclosed","first_id": "NODE1","second_id": "PROCESS1"}, {"label": "PROCESS1_TO_PORT1","class_name": "WeakLink","first_id": "PROCESS1","second_id": "PORT1"}, {"label": "PORT1_TO_PROCESS2","class_name": "WeakLink","first_id": "PORT1","second_id": "PROCESS2"}, {"label": "NODE2_TO_PROCESS2","class_name": "Enclosed","first_id": "NODE2","second_id": "PROCESS2"}, {"label": "PORT3_TO_PROCESS1","class_name": "WeakLink","first_id": "PORT3","second_id": "PROCESS1"}, {"label": "PROCESS3_TO_PORT3","class_name": "WeakLink","first_id": "PROCESS3","second_id": "PORT3"}, {"label": "NODE3_TO_PROCESS3","class_name": "Enclosed","first_id": "NODE3","second_id": "PROCESS3"}]},

			'Software groups' :
				{"objects": [{"label": "GROUP","class_name": "SoftwareSignature","attributes": ["caption", "os_type", "software_info", "notes"],"minimum": "1","maximum": "","linchpin": True,"filter": [{"condition": {"attribute": "name","operator": "==","value": "INPUT"}}]},{"label": "SOFTWARE","class_name": "SoftwareFingerprint","attributes": [],"minimum": "1","maximum": ""},{"label": "NODE","class_name": "Node","attributes": [],"minimum": "1","maximum": ""}],"links": [{"label": "GROUP_TO_SOFTWARE","class_name": "Contain","first_id": "GROUP","second_id": "SOFTWARE"},{"label": "NODE_TO_SOFTWARE","class_name": "Enclosed","first_id": "NODE","second_id": "SOFTWARE"}]},

			'Process groups' :
				{"objects": [{"label": "GROUP","class_name": "ProcessSignature","attributes": ["caption", "name"],"minimum": "1","maximum": "","linchpin": True,"filter": [{"condition": {"attribute": "name","operator": "==","value": "INPUT"}}]},{"label": "PROCESS","class_name": "ProcessFingerprint","attributes": [],"minimum": "1","maximum": ""},{"label": "NODE","class_name": "Node","attributes": [],"minimum": "1","maximum": ""}],"links": [{"label": "GROUP_TO_PROCESS","class_name": "Contain","first_id": "GROUP","second_id": "PROCESS"},{"label": "NODE_TO_PROCESS","class_name": "Enclosed","first_id": "NODE","second_id": "PROCESS"}]}
		}

		for name,query in queryDefinitions.items():
			definition = InputDrivenQueryDefinition(name=name, json_query=query)
			dbClient.session.add(definition)
			dbClient.session.commit()
			logger.debug('Created input driven query: {}'.format(name))

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Failure in createInputDrivenQueryDefinitions: {}'.format(str(stacktrace)))

	## end createInputDrivenQueryDefinitions
	return


def createApiContentGatheringEntry(dbClient, logger, globalSettings):
	"""Insert a token into the into api_access_consumer table.

	Arguments:
	  dbClient (DatabaseClient) : Instance of database client
	  logger                    : Handler for the database log

	"""
	try:
		newApiConsumer = ApiConsumerAccess(name=globalSettings['contentGatheringClientApiUser'], key=uuid.uuid4().hex, owner='ITDM', access_delete=True, access_write=True, access_admin=True)
		dbClient.session.add(newApiConsumer)
		dbClient.session.commit()

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Failure in createApiContentGatheringEntry: {}'.format(str(stacktrace)))

	## end createApiContentGatheringEntry
	return


def createApiAccess(dbClient, logger):

	"""Inserting instances of api_access into content_module table.

	Arguments:
	  dbClient (DatabaseClient) : Instance of database client
	  logger                    : Handler for the database log

	"""
	try:
		myKey = utils.getServiceKey(env.configPath)
		if myKey is not None:
			apiObject = ApiAccess(key=myKey, name='serviceClient')
			dbClient.session.add(apiObject)
			dbClient.session.commit()
			logger.debug('Added serviceClient API access')

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Failure in createApiAccess: {}'.format(str(stacktrace)))

	## end createApiAccess
	return


def createObjects(dbClient, logger, globalSettings):
	"""Create schemas, tables, and objects.

	Arguments:
	  dbClient (DatabaseClient) : Instance of database client
	  logger                    : The handler for database log

	"""
	try:
		## Remove all tables if they exist first
		dbClient.session.commit()
		for schemaName in ['data', 'platform', 'archive']:
			print('Dropping schema {} ...'.format(schemaName))
			logger.debug('Dropping schema {} ...'.format(schemaName))
			try:
				dbClient.engine.execute('drop schema if exists {} cascade'.format(schemaName))
			except:
				pass
			dbClient.engine.execute('create schema {}'.format(schemaName))
		## Initialize DB schemas if not done previously; sqlalchemy does not
		## clobber any existing tables/content, so it's safe to leave enabled
		## by default without checking explicitely first
		dbClient.createTables()
		print('Schema and Tables created')
		logger.debug('Schema and Tables created')
		## Now create initial objects in the database...
		## jobs, app server info, etc
		createRealms(dbClient, logger)
		#createScopes(dbClient, logger)
		#createTriggerTypes(dbClient, logger)
		createApiAccess(dbClient, logger)
		createApiContentGatheringEntry(dbClient, logger, globalSettings)
		baselineContentGatheringParameters(dbClient, logger)
		createQueryDefinitions(dbClient, logger)
		createInputDrivenQueryDefinitions(dbClient, logger)
		dbClient.session.remove()
		print('Objects created\n')
		logger.debug('Objects created')
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Failure in createObjects: {}'.format(str(stacktrace)))

	## end createObjects
	return


def getSettings(settings, configPath, fileName="databaseSettings.json"):
	"""Get settings from config file.

	Arguments:
	  settings (dict)   : Dictionary to hold the database connection parameters
	  configPath (str)  : String containing path to the conf directory

	"""
	## Settings will come from ../conf/databaseSettings.json
	dbConfFile = os.path.join(configPath, fileName)
	fileSettings = utils.loadSettings(dbConfFile)
	for key, value in fileSettings.items():
		settings[key] = value

	## end getSettings
	return


def main():
	"""Entry point for the database configuration utility.

	Usage::

	  $ python initializeDatabase.py

	"""
	try:
		## Setup requested log handlers
		logEntity = 'Database'
		logger = utils.setupLogger(logEntity, env, 'logSettingsCore.json')
		logger.info('Starting initializeDatabase utility.')

		## Get settings (new or updated)
		globalSettings = utils.loadSettings(os.path.join(env.configPath, 'globalSettings.json'))

		## Attempt connection
		dbClient = DatabaseClient(logger, env=env)
		if dbClient is None:
			raise SystemError('Failed to connect to database; unable to initialize tables.')

		print('\nDatabase connection successful.')
		logger.debug('Database connection successful')

		## Start the work
		createObjects(dbClient, logger, globalSettings)

		## Close the connection
		dbClient.session.remove()
		dbClient.close()
		logger.info('Exiting initializeDatabase utility.')

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		## The basic print is here for a console message in case we weren't
		## able to use the logging mechanism before encountering the failure.
		print('Failure in initializeDatabase.main: {}'.format(stacktrace))
		try:
			logger.debug('Failure in initializeDatabase.main: {}'.format(stacktrace))
		except:
			pass

	## end main
	return


if __name__ == '__main__':
	sys.exit(main())
