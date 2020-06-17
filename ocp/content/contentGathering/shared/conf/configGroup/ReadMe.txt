Flow of how settings are loaded from contentGathering/shared/conf/configGroup:
  1: osParameters (using the section matching the OS type)
  2: configDefault
  3: configGroup (using the matching section)

Settings set in later loaded files will override previous settings. So those in
configDefault will override osParameters, and those in configGroups override
values set from the previous two.

Entries in configGroup are read top-down, and the first matching group wins. If
a node matches multiple groups, only the first one is applied/saved. Place more
restrictive groups towards the top and catch-all groups at the bottom. Note,
most companies will not need to have catch-all type config groups; generally
applied settings can just be set/updated in the top two files (osParameters and
configDefault).

Sample format of configGroup:
===================================================================
[
	{
		"name": "citrixLinux",
		"createdBy": "John Doe",
		"description": "Standard Linux image built through Citrix",
		"matchCriteria": {
			"condition": {
				"class_name": "Linux",
				"attribute": "platform",
				"operator": "iregex",
				"value": "citrix"
			}
		},
		"parameters": {
			"softwareFilterExcludeList": "Red\\s*Hat",
			"processFilterList": "xfs,xscreensaver"
		}
	},
	{
		"name": "citrixLinux",
		"createdBy": "John Doe",
		"description": "Standard Linux image built through VMware",
		"matchCriteria": {
			"condition": {
				"class_name": "Linux",
				"attribute": "platform",
				"operator": "==",
				"value": "VMware"
			}
		},
		"parameters": {
			"softwareFilterExcludeList": "VMware",
			"processFilterList": "vmware,xfs,xscreensaver"
		}
	}
]
===================================================================

Field descriptions:
  * name: a unique name for the config group
  * createdBy: for tracking purposes
  * description: so you can remember why you created the group
  * matchCriteria: one or more expression, with one or more conditions;
    describing how to match a node result to this group
  * parameters: parameters to direct job execution
