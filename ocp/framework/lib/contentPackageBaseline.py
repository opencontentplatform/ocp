"""Package baseline utility."""
import sys
import traceback
import contentManagement


def main():
	try:
		contentManagement.baselinePackagesInDatabase()
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		print('Exception in main: {}'.format(stacktrace))


if __name__ == '__main__':
	sys.exit(main())
