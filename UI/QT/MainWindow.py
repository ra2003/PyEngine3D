import sys
import traceback
import os
import time
from functools import partial

import PyQt4
from PyQt4 import Qt, QtCore, QtGui, uic
import numpy

from Utilities import Singleton, Attribute, Attributes
from UI import logger
from Core.Command import *
UI_FILENAME = os.path.join(os.path.split(__file__)[0], "MainWindow.ui")


def findTreeItem(parentItem, findItemName):
    if type(parentItem) == QtGui.QTreeWidget:
        for item in parentItem.findItems("", QtCore.Qt.MatchContains):
            if item.text(0) == findItemName:
                return item
    elif type(parentItem) == QtGui.QTreeWidgetItem:
        for i in range(parentItem.childCount()):
            item = parentItem.child(i)
            if item.text(0) == findItemName:
                return item
    return None


class MessageThread(QtCore.QThread):
    def __init__(self, cmdQueue):
        QtCore.QThread.__init__(self)
        self.running = True
        self.cmdQueue = cmdQueue

        self.limitDelta = 1.0 / 60.0  # 60fps
        self.delta = 0.0
        self.lastTime = 0.0

    def run(self):
        self.lastTime = time.time()
        while self.running:
            # Timer
            self.delta = time.time() - self.lastTime
            if self.delta < self.limitDelta:
                time.sleep(self.limitDelta - self.delta)
            # print(1.0/(time.time() - self.lastTime))
            self.lastTime = time.time()

            # Process recieved queues
            if not self.cmdQueue.empty():
                # receive value must be tuple type
                cmd, value = self.cmdQueue.get()
                cmdName = get_command_name(cmd)
                # recieved queues
                if cmd == COMMAND.CLOSE_UI:
                    self.running = False
                # call binded signal event
                self.emit(QtCore.SIGNAL(cmdName), value)


class MainWindow(QtGui.QMainWindow, Singleton):
    def __init__(self, project_filename, cmdQueue, appCmdQueue, cmdPipe):
        logger.info("Create MainWindow.")
        super(MainWindow, self).__init__()
        self.project_filename = project_filename
        self.cmdQueue = cmdQueue
        self.appCmdQueue = appCmdQueue
        self.cmdPipe = cmdPipe
        self.isFillAttributeTree = False

        # MessageThread
        self.message_thread = MessageThread(self.cmdQueue)
        self.message_thread.start()

        self.connect(self.message_thread, QtCore.SIGNAL(get_command_name(COMMAND.CLOSE_UI)), self.exit)

        # load ui file
        uic.loadUi(UI_FILENAME, self)

        # set windows title
        self.setWindowTitle(project_filename if project_filename else "Default Project")

        # exit
        actionExit = self.findChild(QtGui.QAction, "actionExit")
        QtCore.QObject.connect(actionExit, QtCore.SIGNAL("triggered()"), self.exit)
        # project
        actionNewProject = self.findChild(QtGui.QAction, "actionNewProject")
        QtCore.QObject.connect(actionNewProject, QtCore.SIGNAL("triggered()"), self.new_project)
        actionOpenProject = self.findChild(QtGui.QAction, "actionOpenProject")
        QtCore.QObject.connect(actionOpenProject, QtCore.SIGNAL("triggered()"), self.open_project)
        actionSaveProject = self.findChild(QtGui.QAction, "actionSaveProject")
        QtCore.QObject.connect(actionSaveProject, QtCore.SIGNAL("triggered()"), self.save_project)
        # scene
        actionNewScene = self.findChild(QtGui.QAction, "actionNewScene")
        QtCore.QObject.connect(actionNewScene, QtCore.SIGNAL("triggered()"), self.new_scene)
        actionSaveScene = self.findChild(QtGui.QAction, "actionSaveScene")
        QtCore.QObject.connect(actionSaveScene, QtCore.SIGNAL("triggered()"), self.save_scene)

        # action draw mode
        actionWireframe = self.findChild(QtGui.QAction, "actionWireframe")
        actionShading = self.findChild(QtGui.QAction, "actionShading")
        QtCore.QObject.connect(actionWireframe, QtCore.SIGNAL("triggered()"),
                               lambda: self.setViewMode(COMMAND.VIEWMODE_WIREFRAME))
        QtCore.QObject.connect(actionShading, QtCore.SIGNAL("triggered()"),
                               lambda: self.setViewMode(COMMAND.VIEWMODE_SHADING))

        # Resource list
        self.resourceListWidget = self.findChild(QtGui.QTreeWidget, "resourceListWidget")
        self.resourceListWidget.itemDoubleClicked.connect(self.addResourceToScene)
        self.resourceListWidget.itemClicked.connect(self.selectResource)
        self.connect(self.message_thread, QtCore.SIGNAL(get_command_name(COMMAND.TRANS_RESOURCE_LIST)),
                     self.addResourceList)
        self.connect(self.message_thread, QtCore.SIGNAL(get_command_name(COMMAND.TRANS_RESOURCE_INFO)),
                     self.addResourceInfo)
        self.connect(self.message_thread, QtCore.SIGNAL(get_command_name(COMMAND.TRANS_RESOURCE_ATTRIBUTE)),
                     self.fillAttribute)

        self.btnAddResource = self.findChild(QtGui.QPushButton, "btnAddResource")
        self.btnAddResource.clicked.connect(self.addResourceToScene)

        # Object list
        self.objectList = self.findChild(QtGui.QTreeWidget, "objectListWidget")
        self.objectList.setSortingEnabled(True)
        self.objectList.itemClicked.connect(self.selectObject)
        self.objectList.itemActivated.connect(self.selectObject)
        self.objectList.itemDoubleClicked.connect(self.focusObject)
        self.connect(self.message_thread, QtCore.SIGNAL(get_command_name(COMMAND.DELETE_OBJECT_INFO)),
                     self.deleteObjectInfo)
        self.connect(self.message_thread, QtCore.SIGNAL(get_command_name(COMMAND.TRANS_OBJECT_INFO)),
                     self.addObjectInfo)
        self.connect(self.message_thread, QtCore.SIGNAL(get_command_name(COMMAND.TRANS_OBJECT_ATTRIBUTE)),
                     self.fillAttribute)
        self.connect(self.message_thread, QtCore.SIGNAL(get_command_name(COMMAND.CLEAR_OBJECT_LIST)),
                     self.clearObjectList)

        self.btnRemoveObject = self.findChild(QtGui.QPushButton, "btnRemoveObject")
        self.btnRemoveObject.clicked.connect(self.deleteObject)

        # Object attribute tree
        self.attributeTree = self.findChild(QtGui.QTreeWidget, "attributeTree")
        self.attributeTree.setEditTriggers(self.attributeTree.NoEditTriggers) # hook editable event
        self.attributeTree.itemSelectionChanged.connect(self.checkEditable)
        self.attributeTree.itemClicked.connect(self.checkEditable)
        self.attributeTree.itemChanged.connect(self.attributeChanged)

        # wait a UI_RUN message, and send success message
        if self.cmdPipe:
            self.cmdPipe.RecvAndSend(COMMAND.UI_RUN, None, COMMAND.UI_RUN_OK, None)

    def keyPressEvent(self, e):
        if e.key() == QtCore.Qt.Key_Escape:
            self.exit()

    # on closed event
    def closeEvent(self, event):
        # let the window close
        logger.info("Bye")
        event.accept()
        self.exit()

    # ------------------------- #
    # Menu
    # ------------------------- #
    def exit(self, *args):
        if args != () and args[0] is not None:
            logger.info(*args)
        self.appCmdQueue.put(COMMAND.CLOSE_APP)
        self.close()
        sys.exit()

    def new_project(self):
        filename = QtGui.QFileDialog.getSaveFileName(self, 'New Project', os.path.join(".", "Projects"))
        self.appCmdQueue.put(COMMAND.NEW_PROJECT, filename)

    def open_project(self):
        filename = QtGui.QFileDialog.getOpenFileName(self, 'Open File', os.path.join(".", "Projects"),
                                                     "Project file (*.project)\nAll files (*.*)")
        self.appCmdQueue.put(COMMAND.OPEN_PROJECT, filename)

    def save_project(self):
        self.appCmdQueue.put(COMMAND.SAVE_PROJECT)

    def new_scene(self):
        self.appCmdQueue.put(COMMAND.NEW_SCENE)

    def save_scene(self):
        self.appCmdQueue.put(COMMAND.SAVE_SCENE)

    def setViewMode(self, mode):
        self.appCmdQueue.put(mode)

    # ------------------------- #
    # Widget - Propery Tree
    # ------------------------- #
    def checkEditable(self, item=None, column=0):
        """in your connected slot, you can implement any edit-or-not-logic. you want"""
        if item is None:
            item = self.attributeTree.currentItem()
            column = self.attributeTree.currentColumn()

        # e.g. to allow editing only of column and have not child item:
        if column == 1 and item.childCount() == 0 and not self.isFillAttributeTree:
            self.attributeTree.editItem(item, column)

    def attributeChanged(self, item):
        if not self.isFillAttributeTree:
            try:
                # check value chaned
                if item.oldValue == item.text(1):
                    return
                item.oldValue = item.text(1)
                # check array type, then combine components
                parent = item.parent()
                if type(parent) == QtGui.QTreeWidgetItem and parent.dataType in (tuple, list, numpy.ndarray):
                    attributeName = parent.text(0)
                    value = []
                    for i in range(parent.childCount()):
                        child = parent.child(i)
                        value.append(child.dataType(child.text(1)))
                    # numpy array
                    if parent.dataType == numpy.ndarray:
                        value = numpy.array(value)
                    # list or tuple
                    else:
                        value = parent.dataType(value)
                else:
                    attributeName = item.text(0)
                    value = item.dataType(item.text(1))
                # send data
                currentItem = self.objectList.currentItem()
                if currentItem:
                    currentObjectName = self.objectList.currentItem().text()
                    self.appCmdQueue.put(COMMAND.SET_OBJECT_ATTRIBUTE, (currentObjectName, attributeName, value))
            except:
                logger.error(traceback.format_exc())
                # failed to convert string to dataType, so restore to old value
                item.setText(1, item.oldValue)

    def addAttribute(self, parent, attributeName, value):
        item = QtGui.QTreeWidgetItem(parent)
        item.setFlags(QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsUserCheckable)
        item.setExpanded(True)
        # attribute name and type
        item.setText(0, attributeName)
        item.dataType = type(value)
        item.remove = False  # this is flag for remove item when Layout Refresh

        # set value
        if item.dataType == bool:  # bool type
            item.setCheckState(1, QtCore.Qt.Checked if value else QtCore.Qt.Unchecked)
        elif item.dataType in (tuple, list, numpy.ndarray):  # set list type
            item.setText(1, "")  # set value to None
            for i, itemValue in enumerate(value):  # add child component
                self.addAttribute(item, "[%d]" % i, itemValue)
        else:  # set general type value - int, float, string
            item.setText(1, str(value))
        item.oldValue = item.text(1)  # set old value

    def fillAttribute(self, attributes):
        # lock edit attribute ui
        self.isFillAttributeTree = True

        self.attributeTree.clear()  # clear

        # fill properties of selected object
        for attribute in attributes.getAttributes():
            self.addAttribute(self.attributeTree, attribute.name, attribute.value)

        # self.showProperties()

        # unlock edit attribute ui
        self.isFillAttributeTree = False

    def showProperties(self):
        for item in self.attributeTree.findItems("", QtCore.Qt.MatchContains | QtCore.Qt.MatchRecursive):
            print(item.text(0), item.text(1))

    # ------------------------- #
    # Widget - Resource List
    # ------------------------- #
    def addResourceList(self, resourceList):
        for resName, resType in resourceList:
            item = QtGui.QTreeWidgetItem(self.resourceListWidget)
            item.setText(0, resName)
            item.setText(1, resType)

    def addResourceInfo(self, resource_info):
        resource_name, resource_type = resource_info
        item = QtGui.QTreeWidgetItem(self.resourceListWidget)
        item.setText(0, resource_name)
        item.setText(1, resource_type)

    def addResourceToScene(self, item=None):
        if item is False:  # button clicked
            selectedItems = self.resourceListWidget.selectedItems()
            if selectedItems:
                item = selectedItems[0]
        self.appCmdQueue.put(COMMAND.ADD_RESOURCE_TO_SCENE, (item.text(0), item.text(1)))  # send message and receive

    def selectResource(self):
        getSelected = self.resourceListWidget.selectedItems()
        if getSelected:
            node = getSelected[0]
            self.appCmdQueue.put(COMMAND.REQUEST_RESOURCE_ATTRIBUTE, (node.text(0), node.text(1)))

    # ------------------------- #
    # Widget - Object List
    # ------------------------- #
    def addObjectInfo(self, object_info):
        object_name, object_type = object_info
        item = QtGui.QTreeWidgetItem(self.objectList)
        item.setText(0, object_name)
        item.setText(1, object_type)

    def deleteObject(self, *args):
        selectedItems = self.objectList.selectedItems()
        for selectedItem in selectedItems:
            self.appCmdQueue.put(COMMAND.DELETE_OBJECT, selectedItem.text(0))

    def deleteObjectInfo(self, objName):
        items = self.objectList.findItems(objName, QtCore.Qt.MatchContains, column=0)
        for item in items:
            index = self.objectList.indexOfTopLevelItem(item)
            self.objectList.takeTopLevelItem(index)

    def clearObjectList(self, *args):
        self.objectList.clear()

    def selectObject(self):
        selectedItems = self.objectList.selectedItems()
        if selectedItems:
            item = selectedItems[0]
            selectedObjectName = item.text(0)
            # request selected object infomation to fill attribute widget
            self.appCmdQueue.put(COMMAND.SET_OBJECT_SELECT, selectedObjectName)
            self.appCmdQueue.put(COMMAND.REQUEST_OBJECT_ATTRIBUTE, selectedObjectName)

    def focusObject(self, item=None):
        if item:
            selectedObjectName = item.text(0)
            self.appCmdQueue.put(COMMAND.SET_OBJECT_FOCUS, selectedObjectName)


def run_editor(project_filename, cmdQueue, appCmdQueue, cmdPipe):
    """process - QT Widget"""
    app = QtGui.QApplication(sys.argv)
    main_window = MainWindow.instance(project_filename, cmdQueue, appCmdQueue, cmdPipe)
    main_window.show()
    sys.exit(app.exec_())
