"""Compare two JSON objects in Nested-Simple format.

This was setup specifically to find detailed differences between logical models,
but can be used to compare any JSONs returned from an API query.

.. hidden::

    Author: Chris Satterthwaite (CS)
    Contributors:
    Version info:
      1.0 : (CS) Created Aug 21, 2018

"""
import json
import traceback
import sys


class ChangeTracker:
    def __init__(self):
        self.changes = {}

    def add(self, change):
        if change.identifier in self.changes:
            if change.reason != 'Content modified':
                self.changes[change.identifier] = change
        else:
            self.changes[change.identifier] = change
        return self

    def appendToList(self, changeList):
        """Dump the tracked changes into a json (list of dictionary values).

        Requiring a list as an input list, so that we can drop the custom
        ChangeTracker instance (using internal keys) out of memory upon exit.
        """
        for changeId,change in self.changes.items():
            thisChange = {}
            thisChange['reason'] = change.reason
            thisChange['old'] = change.old
            thisChange['new'] = change.new
            thisChange['oldId'] = change.oldId
            thisChange['newId'] = change.newId
            thisChange['contextType'] = change.contextType
            thisChange['oldContext'] = change.oldContext
            thisChange['newContext'] = change.newContext
            thisChange['objectType'] = change.objectType
            changeList.append(thisChange)

    def __repr__(self):
        changeString = ''
        for changeId,change in self.changes.items():
            changeString += str(change) + '\n\n'
        return changeString

    __str__ = __repr__
    ## end class ChangeTracker


class Change:
    def __init__(self, reason, old, new, oldId, newId, contextType=None, objectType=None, oldContext=None, newContext=None):
        self.reason = reason
        self.old = old
        self.new = new
        self.oldId = oldId
        self.newId = newId
        self.contextType = contextType
        self.oldContext = oldContext
        self.newContext = newContext
        self.objectType = objectType
        self.identifier = '{}:{}'.format(oldId, newId)

    def indent(self, data):
        return '\n'.join('  ' + line for line in data.splitlines())

    def format(self, value):
        return indent(json.dumps(value, sort_keys=True, indent=4))

    def __repr__(self):
        return 'Reason: {0}\nIdentifier: {1}\nName: {2}\nOld:\n{3}\nNew:\n{4}' \
               .format(self.reason, self.identifier, self.context, self.format(self.old), self.format(self.new))

    __str__ = __repr__
    ## end class Change


def processDictType(changes, old, new, oldId, newId, ignore_value_of_keys, flipped, context, objectType):
    for key in old:
        if not key in new:
            if flipped:
                changes.add(Change('Attribute created', new, old, newId, oldId, key, objectType, None, old[key]))
                return False
            else:
                changes.add(Change('Attribute removed', old, new, oldId, newId, key, objectType, old[key], None))
                return False

        if not key in ignore_value_of_keys:
            if not compare(changes, old[key], new[key], oldId, newId, ignore_value_of_keys, flipped, key, objectType):
                if flipped:
                    changes.add(Change('Content modified', new, old, newId, oldId, key, objectType, new[key], old[key]))
                else:
                    changes.add(Change('Content modified', old, new, oldId, newId, key, objectType, old[key], new[key]))
                return False

    ## end processDictType
    return True


def processListType(changes, old, new, oldId, newId, ignore_value_of_keys, flipped, context, objectType):
    for i in range(len(old)):
        oldObject = old[i]
        ## List of dictionaries (e.g. Processes) may not be in the same order
        if isinstance(oldObject, dict) and oldObject.get('identifier') is not None:
            oldId = oldObject.get('identifier')
            objectType = oldObject.get('class_name')
            context = oldObject.get('data').get('caption')

            matchFound = False
            for x in range(len(new)):
                newObject = new[x]
                newId = newObject.get('identifier')
                if oldId == newId:
                    matchFound = True
                    resultValue = processDictType(changes, oldObject, newObject, oldId, newId, ignore_value_of_keys, flipped, context, objectType)
                    ## Compare new to old
                    otherCompare = not flipped
                    result2Bool = processDictType(changes, newObject, oldObject, oldId, newId, ignore_value_of_keys, otherCompare, context, objectType)
                    resultValue = resultValue and result2Bool
                    if not resultValue:
                        ## This is a generic message that usually is hit after a
                        ## more specific one with keys or content added/removed
                        changes.add(Change('Content modified', oldObject, newObject, oldId, newId, context, objectType))
                    break

            ## If we get here, a dictionary entry wasn't found in both lists
            if not matchFound:
                if flipped:
                    changes.add(Change('Object created', None, oldObject.get('data'), None, oldId, None, objectType))
                else:
                    changes.add(Change('Object removed', oldObject.get('data'), None, oldId, None, None, objectType))

        ## Probably want to check instance types for lists containing non-dict
        ## entries, to perhaps sort a list of strings before the comparison.
        else:
            if not compare(changes, old[i], new[i], oldId, newId, ignore_value_of_keys, flipped, context, objectType):
                changes.add(Change('Content modified', old[i], new[i], oldId, newId, context, objectType))
                return False

    ## end processListType
    return True


def compare(changes, old, new, oldId, newId, ignore_value_of_keys, flipped=False, context=None, objectType=None, isTop=False):
    # Check for None
    if old is None or new is None:
        return old == new

    # Ensure they are of same type
    elif type(old) != type(new):
        changes.add(Change('Type Mismatch: Old Type: {0}, New Type: {1}'.format(type(old), type(new)), old, new, oldId, newId, context, objectType))
        return False

    # Compare primitive types immediately
    elif type(old) in (int, str, bool, float):
        return old == new

    elif isinstance(old, dict):
        className = old.get('class_name')
        if className is not None:
            oldId = old.get('identifier')
            newId = new.get('identifier')
            objectType = old.get('class_name')
            context = old.get('data').get('caption')

        ## Compare old to new
        resultValue = processDictType(changes, old, new, oldId, newId, ignore_value_of_keys, flipped, context, objectType)

        ## Avoid reverse compare on the first/top object (the app)
        if not isTop:
            otherCompare = not flipped
            ## Compare new to old
            result2Bool = processDictType(changes, new, old, oldId, newId, ignore_value_of_keys, otherCompare, context, objectType)
            resultValue = resultValue and result2Bool
        return resultValue

    elif isinstance(old, list):
        ## Compare old to new
        resultValue = processListType(changes, old, new, oldId, newId, ignore_value_of_keys, flipped, context, objectType)
        return resultValue

    else:
        print(' -- UNKNOWN type {} with id {}: {}'.format(type(old), oldId, old))
        changes.add(Change('Unhandled Type: {0}'.format(type(old)), old, new, oldId, newId, context, objectType))

    ## end compare
    return False


def jsonCompare(a, b, changeList, ignore_value_of_keys=[]):
    changes = ChangeTracker()
    compare(changes, a, b, None, None, ignore_value_of_keys, isTop=True)
    changes.appendToList(changeList)
    del changes
    return


def jsonStringsCompare(a, b, changeList, ignore_value_of_keys=[]):
    return jsonCompare(json.loads(a), json.loads(b), changeList, ignore_value_of_keys)
