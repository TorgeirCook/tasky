#!/usr/bin/env python2

"""
A Google Tasks command line interface.
"""

__author__ = 'Ajay Roopakalu (https://github.com/jrupac/tasky)'

import codecs
import datetime as dt
import os
import shlex
from collections import OrderedDict

import gflags
import httplib2
import sys
import time
from apiclient.discovery import build
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.file import Storage
from oauth2client.tools import run_flow as run

FLAGS = gflags.FLAGS

# Flags related to operations on task lists.
gflags.DEFINE_boolean(
    'add', False, 'Add operation', short_name='a')
gflags.DEFINE_boolean(
    'clear', False, 'Clear operation', short_name='c')
gflags.DEFINE_boolean(
    'delete', False, 'Delete operation', short_name='d')
gflags.DEFINE_boolean(
    'edit', False, 'Edit operation', short_name='e')
gflags.DEFINE_boolean(
    'list', False, 'List operation', short_name='l')
gflags.DEFINE_boolean(
    'move', False, 'Move operation', short_name='m')
gflags.DEFINE_boolean(
    'new', False, 'New operation', short_name='n')
gflags.DEFINE_boolean(
    'remove', False, 'Remove operation', short_name='r')
gflags.DEFINE_boolean(
    'rename', False, 'Rename operation.', short_name='rn')
gflags.DEFINE_boolean(
    'summary', False, 'Print a summary of the task lists.', short_name='s')
gflags.DEFINE_boolean(
    'toggle', False, 'Toggle operation', short_name='t')
gflags.DEFINE_boolean(
    'quit', False, 'Quit operation', short_name='q')

# Flags related to options on above operations.
gflags.DEFINE_integer(
    'after', -1, 'The index of the task that this should be after')
gflags.DEFINE_string(
    'date', '', 'A date in MM/DD/YYYY format.')
gflags.DEFINE_spaceseplist(
    'index', '', 'Index of task.', short_name='i')
gflags.DEFINE_boolean(
    'force', False, 'Forcibly perform the operation.', short_name='f')
gflags.DEFINE_boolean(
    'only-completed', False, 'Show only completed.', short_name='oc')
gflags.DEFINE_boolean(
    'completed-on', False, 'Show completed on date', short_name='co')
gflags.DEFINE_boolean(
    'color', True, 'Display output with terminal colors.', short_name='o')
gflags.DEFINE_string(
    'note', '', 'A note to attach to a task.')
gflags.DEFINE_integer(
    'parent', 0, 'Index of parent task.', short_name='p')

gflags.DEFINE_integer(
    'tasklist', 0, 'Id of task list to operate on.', short_name="tl")
gflags.DEFINE_string(
    'title', '', 'The name of the task.')

USAGE = ('[-a]dd, [-c]lear, [-d]elete, [-e]dit, [-r]emove task, [-m]ove, ' +
         '[-n]ew list, -rename/-rn, [-s]ummary, [-t]oggle, [-q]uit: ')

# Environment constants
TASKY_DIR = os.path.join(os.environ['HOME'], '.tasky')
KEYS_FILE = os.path.join(TASKY_DIR, 'keys.txt')


class TextColor(object):
    """A class to provide terminal keycodes for colored output."""

    HEADER = '\033[1;38;5;218m'
    DATE = '\033[1;38;5;249m'
    NOTES = '\033[1;38;5;252m'
    TITLE = '\033[1;38;5;195m'
    CLEAR = '\033[0m'


class Auth(object):
    """A class to handle persistence and access of various OAuth keys."""

    def __init__(self, keyFile):
        try:
            with open(keyFile, 'r') as self.f:
                self.clientId = self.f.readline().rstrip()
                self.clientSecret = self.f.readline().rstrip()
                self.apiKey = self.f.readline().rstrip()
        except IOError:
            self.clientId = raw_input("Enter your clientID: ")
            self.clientSecret = raw_input("Enter your client secret: ")
            self.apiKey = raw_input("Enter your API key: ")
            self._WriteAuth()

    def _WriteAuth(self):
        if not os.path.exists(TASKY_DIR):
            os.makedirs(TASKY_DIR)
        with open(KEYS_FILE, 'w') as self.auth:
            self.auth.write(str(self.clientId) + '\n')
            self.auth.write(str(self.clientSecret) + '\n')
            self.auth.write(str(self.apiKey) + '\n')

    def GetClientId(self):
        return self.clientId

    def GetClientSecret(self):
        return self.clientSecret

    def GetApiKey(self):
        return self.apiKey


class Tasky(object):
    """Main class that handles task manipulation."""

    UNCHANGED = 0
    MODIFIED = 1
    DELETED = 2

    def __init__(self):
        self.taskLists = OrderedDict()
        self.idToTitle = OrderedDict()
        self.service = None

    def Authenticate(self):
        """Runs authentication flow and returns service object."""
        f = Auth(KEYS_FILE)

        # OAuth 2.0 Authentication
        flow = OAuth2WebServerFlow(
            client_id=f.GetClientId(),
            client_secret=f.GetClientSecret(),
            scope='https://www.googleapis.com/auth/tasks',
            user_agent='Tasky/v1')

        # If credentials don't exist or are invalid, run through the native client
        # flow. The Storage object will ensure that if successful, the good
        # Credentials will get written back to a file.
        storage = Storage(os.path.join(TASKY_DIR, 'tasks.dat'))
        credentials = storage.get()

        if credentials is None or credentials.invalid:
            credentials = run(flow, storage)

        http = httplib2.Http()
        http = credentials.authorize(http)

        # The main Tasks API object.
        self.service = build(
            serviceName='tasks', version='v1', http=http,
            developerKey=f.GetApiKey())

    def AddTask(self, task):
        tasklistId = self.taskLists.keys()[FLAGS.tasklist]
        tasklist = self.taskLists[tasklistId]
        if 'parent' in task:
            parent = tasklist.keys()[task['parent']]
            task['parent'] = parent
            newTask = self.service.tasks().insert(
                tasklist=tasklistId, parent=parent, body=task).execute()
            # Re-insert the new task in order.
            newDict = OrderedDict()
            for tt in tasklist:
                newDict[tt] = tasklist[tt]
                if tt is parent:
                    newDict[newTask['id']] = newTask
        else:
            afterTaskId = ""
            if FLAGS["after"].present:
                afterTaskId = tasklist.keys()[FLAGS.after]
            newTask = self.service.tasks().insert(
                tasklist=tasklistId, previous=afterTaskId, body=task).execute()
            newDict = OrderedDict()
            newDict[newTask['id']] = newTask
            for tt in tasklist:
                newDict[tt] = tasklist[tt]

        # Update records.
        self.taskLists[tasklistId] = newDict
        self.idToTitle[newTask['id']] = newTask['title']
        newTask['modified'] = Tasky.UNCHANGED

    def MoveTask(self, task):
        tasklistIndex = self.taskLists.keys()[FLAGS.tasklist]
        tasklist = self.taskLists[tasklistIndex]
        after = None
        parent = None

        if FLAGS['after'].present:
            after = tasklist.keys()[FLAGS.after]

        if FLAGS['parent'].present:
            parent = tasklist.keys()[FLAGS.parent]
        elif 'parent' in task:
            parent = task['parent']

        self.service.tasks().move(
            tasklist=tasklistIndex, task=task['id'], parent=parent,
            previous=after).execute()

    def RemoveTask(self, task):
        tasklist = self.taskLists[self.taskLists.keys()[FLAGS.tasklist]]

        # If already deleted, do nothing.
        if task['modified'] is Tasky.DELETED:
            return
        task['modified'] = Tasky.DELETED
        del self.idToTitle[task['id']]

        # Also delete all children of deleted tasks.
        for taskId in tasklist:
            t = tasklist[taskId]
            if ('parent' in t and
                    t['parent'] in tasklist and
                    tasklist[t['parent']]['modified'] is Tasky.DELETED):
                t['modified'] = Tasky.DELETED
                if t['id'] in self.idToTitle:
                    del self.idToTitle[t['id']]

    def ToggleTask(self, task):
        tasklist = self.taskLists[self.taskLists.keys()[FLAGS.tasklist]]

        # If already deleted, do nothing.
        if task['modified'] is Tasky.DELETED:
            return
        task['modified'] = Tasky.MODIFIED

        if task['status'] == 'needsAction':
            task['status'] = 'completed'
        else:
            task['status'] = 'needsAction'
            if 'completed' in task:
                del task['completed']

        # Also toggle all children whose parents were toggled.
        toggle_tree = [task['id']]
        for taskId in tasklist:
            t = tasklist[taskId]
            if t['status'] is Tasky.DELETED:
                continue
            if 'parent' in t and t['parent'] in toggle_tree:
                t['status'] = tasklist[t['parent']]['status']
                if t['status'] == 'needsAction' and 'completed' in t:
                    del t['completed']
                toggle_tree.append(t['id'])
                t['modified'] = Tasky.MODIFIED
                tasklist[t['id']] = t

    def GetData(self):
        # Only retrieve data once per run
        if self.taskLists != {}:
            return

        # Fetch task lists
        tasklists = self.service.tasklists().list().execute()

        # No task lists
        if 'items' not in tasklists:
            return

        # Over all task lists
        for tasklist in tasklists['items']:
            # Handle repeats
            if tasklist['title'] in self.idToTitle:
                continue
            self.idToTitle[tasklist['id']] = tasklist['title']
            self.taskLists[tasklist['id']] = OrderedDict()
            tasks = self.service.tasks().list(tasklist=tasklist['id'], showCompleted=True, showHidden=True,
                                              maxResults=100).execute()
            # No task in current list
            if 'items' not in tasks:
                continue
            # Over all tasks in a given list
            for task in tasks['items']:
                self.idToTitle[task['id']] = task['title']
                # Set everything to be initially unmodified
                task['modified'] = Tasky.UNCHANGED
                self.taskLists[tasklist['id']][task['id']] = task

            tasks = sorted(self.taskLists[tasklist['id']].items(), key=lambda t: t[1]['position'])
            sorted_tasks = []
            for index, task_list_item in enumerate(tasks):
                if 'parent' not in task_list_item[1]:
                    parent_task_id = task_list_item[1]["id"]
                    sorted_tasks.append(task_list_item)
                    child_tasks = []
                    for _index, _task_list_item in enumerate(tasks):
                        if 'parent' in _task_list_item[1] and _task_list_item[1]["parent"] == parent_task_id:
                            child_tasks.append(_task_list_item)
                    child_tasks = sorted(child_tasks, key=lambda t: t[1]['position'])
                    for child_task in child_tasks:
                        sorted_tasks.append(child_task)
            self.taskLists[tasklist['id']] = OrderedDict(sorted_tasks)

    def PutData(self):
        # Nothing to write home about
        if self.taskLists == {}:
            return

        for taskListId in self.taskLists:
            for taskId in self.taskLists[taskListId]:
                task = self.taskLists[taskListId][taskId]
                if task['modified'] is Tasky.UNCHANGED:
                    continue
                elif task['modified'] is Tasky.MODIFIED:
                    self.service.tasks().update(
                        tasklist=taskListId, task=taskId, body=task).execute()
                elif task['modified'] is Tasky.DELETED:
                    self.service.tasks().delete(
                        tasklist=taskListId, task=taskId).execute()

    def PrintAllTaskLists(self):
        for idx, taskListId in enumerate(self.taskLists):
            self.PrintAllTasks(idx, taskListId)

    def PrintAllTasks(self, idx, taskListId, onlySummary=False):
        tab = '  '

        # No task lists
        if self.taskLists == {}:
            print('Found no task lists.')
            return

        # Use a dictionary to store the indent depth of each task
        depthMap = {taskListId: 0}

        # Print task name
        if len(self.taskLists[taskListId]) == 0:
            print('%d %s%s%s (empty)' % (
                idx, TextColor.HEADER, self.idToTitle[taskListId],
                TextColor.CLEAR))
        else:
            print('%d %s%s%s' % (
                idx, TextColor.HEADER, self.idToTitle[taskListId],
                TextColor.CLEAR))

        for taskId in self.taskLists[taskListId]:
            task = self.taskLists[taskListId][taskId]
            if task['modified'] is Tasky.DELETED:
                continue
            depth = 1
            isCompleted = (task['status'] == 'completed')

            # Set the depth of the current task.
            if 'parent' in task and task['parent'] in depthMap:
                depth = depthMap[task['parent']] + 1
            depthMap[task['id']] = depth

            if FLAGS['only-completed'].present:
                if isCompleted:
                    print('%s%s [x] %s' % (
                        tab * depth, self.taskLists[taskListId].keys().index(taskId),
                        task['title']))
                    if not onlySummary:
                        if 'completed' in task:
                            date = dt.datetime.strptime(task['completed'],
                                                        '%Y-%m-%dT%H:%M:%S.%fZ')
                            output = date.strftime('%a, %b %d, %Y')
                            if FLAGS['completed-on'].present:
                                print('%s%sCompleted on: %s%s' % (
                                    tab * (depth + 1), TextColor.DATE,
                                    output, TextColor.CLEAR))
                        if 'due' in task:
                            date = dt.datetime.strptime(task['due'],
                                                        '%Y-%m-%dT%H:%M:%S.%fZ')
                            output = date.strftime('%a, %b %d, %Y')
                            print('%s%sDue Date: %s%s' % (
                                tab * (depth + 1), TextColor.DATE,
                                output, TextColor.CLEAR))

                        # Print notes if specified.
                        if 'notes' in task:
                            print('%s%sNotes: %s%s' % (
                                tab * (depth + 1), TextColor.NOTES, task['notes'],
                                TextColor.CLEAR))
            else:
                if not isCompleted:
                    print('%s%s%s [ ] %s%s' % (
                        TextColor.TITLE, tab * depth,
                        self.taskLists[taskListId].keys().index(taskId), task['title'],
                        TextColor.CLEAR))
                    if not onlySummary:
                        # Print due date if specified.
                        if 'due' in task:
                            date = dt.datetime.strptime(task['due'],
                                                        '%Y-%m-%dT%H:%M:%S.%fZ')
                            output = date.strftime('%a, %b %d, %Y')
                            print('%s%sDue Date: %s%s' % (
                                tab * (depth + 1), TextColor.DATE,
                                output, TextColor.CLEAR))

                        # Print notes if specified.
                        if 'notes' in task:
                            self.PrintNotes(task['notes'], tab * (depth + 1))

    def PrintSummary(self):
        for taskListId in self.taskLists:
            print('%s %s (%s)' % (
                self.taskLists.keys().index(taskListId),
                self.idToTitle[taskListId], len(self.taskLists[taskListId])))

    def PrintNotes(self, notes, preamble):
        indent_length = len(preamble) + 7
        indent = (" " * indent_length)
        columns, rows = self.GetTerminalSize()
        line_length = columns - indent_length - 50
        note_with_indent = ""
        acc_line_length = 0
        for i, char in enumerate(notes):
            acc_line_length = acc_line_length + 1
            if acc_line_length >= line_length or char == "\n":
                if char == "\n":
                    char = char + indent
                else:
                    char = char + "\n" + indent
                acc_line_length = 0
            note_with_indent = note_with_indent + char
        print('%s%sNotes: %s%s' % (
            preamble, TextColor.NOTES, note_with_indent + "\n",
            TextColor.CLEAR))

    def GetTerminalSize(self):
        env = os.environ

        def ioctl_GWINSZ(fd):
            try:
                import fcntl, termios, struct, os
                cr = struct.unpack('hh', fcntl.ioctl(fd, termios.TIOCGWINSZ,
                                                     '1234'))
            except:
                return
            return cr

        cr = ioctl_GWINSZ(0) or ioctl_GWINSZ(1) or ioctl_GWINSZ(2)
        if not cr:
            try:
                fd = os.open(os.ctermid(), os.O_RDONLY)
                cr = ioctl_GWINSZ(fd)
                os.close(fd)
            except:
                pass
        if not cr:
            cr = (env.get('LINES', 25), env.get('COLUMNS', 80))
        return int(cr[1]), int(cr[0])

    def HandleInputArgs(self):
        taskListId = self.taskLists.keys()[FLAGS.tasklist]
        tasklist = self.taskLists[taskListId]

        # First off, check if we should be displaying in color or not.
        if not FLAGS.color:
            TextColor.HEADER = ''
            TextColor.DATE = ''
            TextColor.NOTES = ''
            TextColor.TITLE = ''
            TextColor.CLEAR = ''

        if FLAGS.add:
            task = {'title': FLAGS.title}
            if FLAGS['date'].present:
                d = time.strptime(FLAGS.date, "%m/%d/%Y")
                task['due'] = (str(d.tm_year) + '-' +
                               str(d.tm_mon) + '-' +
                               str(d.tm_mday) +
                               'T12:00:00.000Z')
            if FLAGS['note'].present:
                task['notes'] = FLAGS.note
            if FLAGS['parent'].present:
                task['parent'] = FLAGS.parent
            print('Adding task...')
            self.AddTask(task)
        elif FLAGS.delete:
            readIn = raw_input(
                'This will delete the list "' + self.idToTitle[taskListId] +
                '" and all its contents permanently. Are you sure? (y/n): ')
            if readIn in ['y', 'Y']:
                self.service.tasklists().delete(tasklist=taskListId).execute()
                del self.taskLists[taskListId]
            self.PutData()
        elif FLAGS.new:
            print('Creating new task list...')
            if not FLAGS.title:
                print('WARNING: Creating task list with no title')
            newTaskList = self.service.tasklists().insert(
                body={'title': FLAGS.title}).execute()
            self.idToTitle[newTaskList['id']] = newTaskList['title']
            self.taskLists[newTaskList['id']] = OrderedDict()
            self.PutData()
        elif FLAGS.rename:
            print('Renaming task list...')
            tasklist = self.service.tasklists().get(tasklist=taskListId).execute()
            tasklist['title'] = FLAGS.title
            self.idToTitle[taskListId] = FLAGS.title
            self.service.tasklists().update(
                tasklist=taskListId, body=tasklist).execute()
            self.PutData()
        elif FLAGS.edit:
            print('Editing task...')
            task = tasklist[tasklist.keys()[int(FLAGS.index[0])]]
            if FLAGS.title:
                task['title'] = FLAGS.title
            if FLAGS.date:
                d = time.strptime(FLAGS.date, "%m/%d/%Y")
                task['due'] = (str(d.tm_year) + '-' +
                               str(d.tm_mon) + '-' +
                               str(d.tm_mday) +
                               'T12:00:00.000Z')
            if FLAGS.note:
                task['notes'] = FLAGS.note
            if task['modified'] == Tasky.DELETED:
                return
            task['modified'] = Tasky.MODIFIED
        elif FLAGS.move:
            print('Moving task...')
            task = tasklist[tasklist.keys()[int(FLAGS.index[0])]]
            self.MoveTask(task)
            self.PutData()
        elif FLAGS.clear:
            if FLAGS.force:
                print('Removing all task(s)...')
                for taskId in tasklist:
                    self.RemoveTask(tasklist[taskId])
            else:
                print('Clearing completed task(s)...')
                self.service.tasks().clear(tasklist=taskListId).execute()
                for taskId in tasklist:
                    task = tasklist[taskId]
                    if task['status'] == 'completed':
                        task['modified'] = Tasky.DELETED
        elif FLAGS.remove:
            print('Removing task(s)...')
            for index in FLAGS.index:
                self.RemoveTask(tasklist[tasklist.keys()[int(index)]])
        elif FLAGS.toggle:
            print('Toggling task(s)...')
            for index in FLAGS.index:
                self.ToggleTask(tasklist[tasklist.keys()[int(index)]])
        elif FLAGS.list:
            if FLAGS['tasklist'].present:
                print('Printing Task List %d...' % FLAGS.tasklist)
                tasklistId = self.taskLists.keys()[FLAGS.tasklist]
                if FLAGS.summary:
                    self.PrintAllTasks(FLAGS.tasklist, tasklistId, onlySummary=True)
                else:
                    self.PrintAllTasks(FLAGS.tasklist, tasklistId)
            else:
                print('Printing all Task Lists...')
                if FLAGS.summary:
                    self.PrintSummary()
                else:
                    self.PrintAllTaskLists()


def ReadLoop(tasky):
    while True:
        # In the interactive case, display the list before any operations unless
        # the previous operation was a --list.
        if not FLAGS['list'].present:
            if FLAGS.summary:
                tasky.PrintSummary()
            else:
                tasky.PrintAllTaskLists()

        # Convert all input to unicode type with utf-8 encoding.
        readIn = unicode(raw_input(USAGE), 'utf-8')
        # shlex does not accept unicode types, so convert to str before lexing.
        # Also prepend a string to hold the place of the application name.
        args = [''] + shlex.split(readIn.encode('utf-8'))
        # Decode back to unicode type again before further processing.
        args = [x.decode('utf-8') for x in args]

        # Re-populate flags based on this input.
        FLAGS.Reset()
        FLAGS(args)

        if FLAGS.quit:
            break
        tasky.HandleInputArgs()


def main(args):
    # Ensure that stdout is written as utf-8.
    writer = codecs.getwriter('utf-8')
    sys.stdout = writer(sys.stdout)

    FLAGS(args)

    tasky = Tasky()
    tasky.Authenticate()
    tasky.GetData()

    if len(args) > 1:
        tasky.HandleInputArgs()

        # In the non-interactive case, print task list after the operation unless
        # --list was the operation just performed.
        if not FLAGS['list'].present:
            if FLAGS.summary:
                tasky.PrintSummary()
            else:
                if FLAGS['tasklist'].present:
                    tasklistId = tasky.taskLists.keys()[FLAGS.tasklist]
                    if FLAGS.summary:
                        tasky.PrintAllTasks(FLAGS.tasklist, tasklistId, onlySummary=True)
                    else:
                        if not FLAGS.move:
                            tasky.PrintAllTasks(FLAGS.tasklist, tasklistId)
                else:
                    tasky.PrintAllTaskLists()
    else:
        ReadLoop(tasky)

    # Push any final changes before exiting.
    tasky.PutData()


if __name__ == '__main__':
    main(sys.argv)
