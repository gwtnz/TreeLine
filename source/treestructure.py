#!/usr/bin/env python3

#******************************************************************************
# treestructure.py, provides a class to store the tree's data
#
# TreeLine, an information storage program
# Copyright (C) 2017, Douglas W. Bell
#
# This is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License, either Version 2 or any later
# version.  This program is distributed in the hope that it will be useful,
# but WITTHOUT ANY WARRANTY.  See the included LICENSE file for details.
#******************************************************************************

import operator
import copy
import json
import uuid
import treenode
import treeformats
import undo
try:
    from __main__ import __version__
except ImportError:
    __version__ = ''

_defaultRootTitle = _('Main')


class TreeStructure(treenode.TreeNode):
    """Class to store all tree data.

    Inherits TreeNode to get childList (holds top nodes) and other methods.
    """
    def __init__(self, fileData=None, topNodes=None, addDefaults=False,
                 addSpots=True):
        """Create and store a tree structure from file data.

        If no file data is given, create an empty or a default new structure.
        Arguments:
            fileData -- a dict in JSON file format of a structure
            topNodes -- existing top-level nodes to add to a structure
            addDefaults -- if True, adds default new structure
            addSpots -- if True, adds parent spot references
        """
        super().__init__(None)  # init TreeNode, with no formatRef
        self.nodeDict = {}
        self.undoList = None
        self.redoList = None
        self.configDialogFormats = None
        if fileData:
            self.treeFormats = treeformats.TreeFormats(fileData['formats'])
            for nodeInfo in fileData['nodes']:
                formatRef = self.treeFormats[nodeInfo['format']]
                node = treenode.TreeNode(formatRef, nodeInfo)
                self.nodeDict[node.uId] = node
            for node in self.nodeDict.values():
                node.assignRefs(self.nodeDict)
            for uId in fileData['properties']['topnodes']:
                node = self.nodeDict[uId]
                self.childList.append(node)
                if addSpots:
                    node.generateSpots(None)
        elif topNodes:
            self.childList = topNodes
            self.treeFormats = treeformats.TreeFormats()
            for topNode in topNodes:
                for node in topNode.descendantGen():
                    self.nodeDict[node.uId] = node
                    self.treeFormats.addTypeIfMissing(node.formatRef)
                if addSpots:
                    node.generateSpots(None)
        elif addDefaults:
            self.treeFormats = treeformats.TreeFormats(setDefault=True)
            node = treenode.TreeNode(self.treeFormats[treeformats.
                                                      defaultTypeName])
            node.setTitle(_defaultRootTitle)
            self.nodeDict[node.uId] = node
            self.childList.append(node)
            if addSpots:
                node.generateSpots(None)
        else:
            self.treeFormats = treeformats.TreeFormats()

    def fileData(self):
        """Return a fileData dict in JSON file format.
        """
        formats = self.treeFormats.storeFormats()
        nodeList = sorted([node.fileData() for node in self.nodeDict.values()],
                          key=operator.itemgetter('uid'))
        topNodeIds = [node.uId for node in self.childList]
        properties = {'tlversion': __version__, 'topnodes': topNodeIds}
        fileData = {'formats': formats, 'nodes': nodeList,
                    'properties': properties}
        return fileData

    def addNodeDictRef(self, node):
        """Add the given node to the node dictionary.

        Arguments:
            node -- the node to add
        """
        self.nodeDict[node.uId] = node

    def removeNodeDictRef(self, node):
        """Remove the given node from the node dictionary.

        Arguments:
            node -- the node to remove
        """
        try:
            del self.nodeDict[node.uId]
        except KeyError:
            pass

    def deleteNodeSpot(self, spot):
        """Remove the given spot, removing the entire node if no spots remain.

        Arguments:
            spot -- the spot to remove
        """
        parentNode = spot.parentSpot.nodeRef if spot.parentSpot else self
        parentNode.childList.remove(spot.nodeRef)
        for node in spot.nodeRef.descendantGen():
            if len(node.spotRefs) <= 1:
                self.removeNodeDictRef(node)
                node.spotRefs = set()
            else:
                node.removeInvalidSpotRefs(False)

    def getConfigDialogFormats(self, forceReset=False):
        """Return duplicate formats for use in the config dialog.

        Arguments:
            forceReset -- if True, sets duplicate formats back to original
        """
        if not self.configDialogFormats or forceReset:
            self.configDialogFormats = copy.deepcopy(self.treeFormats)
        return self.configDialogFormats

    def applyConfigDialogFormats(self, addUndo=True):
        """Replace the formats with the duplicates and signal for view update.

        Also updates all nodes for changed type and field names.
        """
        if addUndo:
            undo.FormatUndo(self.undoList, self.treeFormats,
                            self.configDialogFormats)
        self.treeFormats.copySettings(self.configDialogFormats)
        if self.configDialogFormats.fieldRenameDict:
            for node in self.nodeDict.values():
                fieldRenameDict = (self.configDialogFormats.fieldRenameDict.
                                   get(node.formatRef.name, {}))
                tmpDataDict = {}
                for oldName, newName in fieldRenameDict.items():
                    if oldName in node.data:
                        tmpDataDict[newName] = node.data[oldName]
                        del node.data[oldName]
                node.data.update(tmpDataDict)
            self.configDialogFormats.fieldRenameDict = {}

    def usesType(self, typeName):
        """Return true if any nodes use the give node format type.

        Arguments:
            typeName -- the format name to search for
        """
        for node in self.nodeDict.values():
            if node.formatRef.name == typeName:
                return True
        return False

    def replaceDuplicateIds(self, duplicateDict):
        """Generate new unique IDs for any nodes found in newNodeDict.

        Arguments:
            newNodeDict -- a dict to search for duplicates
        """
        for node in list(self.nodeDict.values()):
            if node.uId in duplicateDict:
                del self.nodeDict[node.uId]
                node.uId = uuid.uuid1().hex
                self.nodeDict[node.uId] = node

    def addNodesFromStruct(self, treeStruct, parent, position=-1):
        """Add nodes from the given structure under the given parent.

        Arguments:
            treeStruct -- the structure to insert
            parent -- the parent of the new nodes
            position -- the location to insert (-1 is appended)
        """
        for nodeFormat in treeStruct.treeFormats.values():
            self.treeFormats.addTypeIfMissing(nodeFormat)
        for node in treeStruct.nodeDict.values():
            self.nodeDict[node.uId] = node
        for node in treeStruct.childList:
            if position >= 0:
                parent.childList.insert(position, node)
                position += 1
            else:
                parent.childList.append(node)
            if parent == self:
                parent = None
            node.addSpotRef(parent)


####  Utility Functions  ####

def structFromMimeData(mimeData):
    """Return a tree structure based on mime data.

    Arguments:
        mimeData -- data to be used
    """
    try:
        data = json.loads(str(mimeData.data('application/json'), 'utf-8'))
        return TreeStructure(data, addSpots=False)
    except (ValueError, KeyError, TypeError):
        return None
