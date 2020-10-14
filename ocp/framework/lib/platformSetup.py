"""Base installer script for the Open Content Platform.

This sets up the key files and the database schemas/tables and inserts the
keys into the database, which is required before running OCP the first time.

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Jul 25, 2017

"""
import os
import sys

## Add openContentPlatform directories onto the sys path
thisPath = os.path.dirname(os.path.abspath(__file__))
basePath = os.path.abspath(os.path.join(thisPath, '..'))
if basePath not in sys.path:
	sys.path.append(basePath)
import env
env.addDatabasePath()
import configureDatabase
import initializeDatabase
import utils
externalEncryptionLibrary = utils.loadExternalLibrary('externalEncryptionLibrary', env)


def generateSalt(saltFile):
	"""Create a new salt and save into a file; overwrite if exists."""
	prettyEncodedSalt = externalEncryptionLibrary.getToken()
	with open(saltFile, 'w') as f:
		f.write(prettyEncodedSalt)

	return


def main():
	generateSalt(os.path.abspath(os.path.join(env.privateInternalKeyPath, 'key.conf')))
	generateSalt(os.path.abspath(os.path.join(env.privateInternalKeyPath, 'client.conf')))
	configureDatabase.main()
	initializeDatabase.main()


if __name__ == "__main__":
	sys.exit(main())
