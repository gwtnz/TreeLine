#!/usr/bin/env python3

#******************************************************************************
# nodeformat.py, provides a class to handle node format objects
#
# TreeLine, an information storage program
# Copyright (C) 2017, Douglas W. Bell
#
# This is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License, either Version 2 or any later
# version.  This program is distributed in the hope that it will be useful,
# but WITTHOUT ANY WARRANTY.  See the included LICENSE file for details.
#******************************************************************************

import re
import sys
import collections
import xml.sax.saxutils
import fieldformat


_defaultFieldName = _('Name')
_defaultOutputSeparator = ', '
_fieldSplitRe = re.compile(r'({\*(?:\**|\?|!|&|#)[\w_\-.]+\*})')
_fieldPartRe = re.compile(r'{\*(\**|\?|!|&|#)([\w_\-.]+)\*}')
_endTagRe = re.compile(r'.*(<br[ /]*?>|<BR[ /]*?>|<hr[ /]*?>|<HR[ /]*?>)$')

class NodeFormat:
    """Class to handle node format info

    Stores node field lists and line formatting.
    Provides methods to return formatted data.
    """
    def __init__(self, name, formatData=None, addDefaultField=False):
        """Initialize a tree format.

        Arguments:
            name -- the type name string
            formatData -- the JSON dict for this format
            addDefaultField -- if true, adds a default initial field
        """
        self.name = name
        self.readFormat(formatData)
        self.siblingPrefix = ''
        self.siblingSuffix = ''
        self.origOutputLines = [] # lines without bullet or table modifications
        if addDefaultField:
            self.addFieldIfNew(_defaultFieldName)
            self.titleLine = ['{{*{0}*}}'.format(_defaultFieldName)]
            self.outputLines = [['{{*{0}*}}'.format(_defaultFieldName)]]
        self.updateLineParsing()
        if self.useBullets:
            self.addBullets()
        if self.useTables:
            self.addTables()

    def readFormat(self, formatData=None):
        """Read JSON format data into this format.

        Arguments:
            formatData -- JSON dict for this format (None for default settings)
        """
        self.fieldDict = collections.OrderedDict()
        if formatData:
            for fieldData in formatData['fields']:
                fieldName = fieldData['fieldname']
                self.addField(fieldName, fieldData)
        else:
            formatData = {}
        self.titleLine = formatData.get('titleline', '')
        self.outputLines = formatData.get('outputlines', [])
        self.spaceBetween = formatData.get('spacebetween', True)
        self.formatHtml = formatData.get('formathtml', False)
        self.useBullets = formatData.get('bullets', False)
        self.useTables = formatData.get('tables', False)
        self.childType = formatData.get('childtype', '')
        self.iconName = formatData.get('icon', '')
        self.outputSeparator = formatData.get('outputsep',
                                              _defaultOutputSeparator)

    def storeFormat(self):
        """Return JSON format data for this format.
        """
        formatData = {}
        formatData['formatname'] = self.name
        formatData['fields'] = [field.formatData() for field in self.fields()]
        formatData['titleline'] = self.getTitleLine()
        formatData['outputlines'] = self.getOutputLines()
        if not self.spaceBetween:
            formatData['spacebetween'] = False
        if self.formatHtml:
            formatData['formathtml'] = True
        if self.useBullets:
            formatData['bullets'] = True
        if self.useTables:
            formatData['tables'] = True
        if self.childType:
            formatData['childtype'] = self.childType
        if self.iconName:
            formatData['icon'] = self.iconName
        return formatData

    def copySettings(self, sourceFormat):
        """Copy all settings from another format to this one.

        Arguments:
            sourceFormat -- the format to copy
        """
        self.name = sourceFormat.name
        self.readFormat(sourceFormat.storeFormat())
        self.siblingPrefix = sourceFormat.siblingPrefix
        self.siblingSuffix = sourceFormat.siblingSuffix
        self.outputLines = sourceFormat.getOutputLines(False)
        self.origOutputLines = sourceFormat.getOutputLines()
        self.updateLineParsing()

    def fields(self):
        """Return list of all fields.
        """
        return self.fieldDict.values()

    def fieldNames(self):
        """Return list of names of all fields.
        """
        return list(self.fieldDict.keys())

    def formatTitle(self, node):
        """Return a string with formatted title data.

        Arguments:
            node -- the node used to get data for fields
        """
        line = ''.join([part.outputText(node, True, self.formatHtml)
                        if hasattr(part, 'outputText') else part
                        for part in self.titleLine])
        return line.strip().split('\n', 1)[0]   # truncate to 1st line

    def formatOutput(self, node, plainText=False, keepBlanks=False):
        """Return a list of formatted text output lines.

        Arguments:
            node -- the node used to get data for fields
            plainText -- if True, remove HTML markup from fields and formats
            keepBlanks -- if True, keep lines with empty fields
        """
        result = []
        for lineData in self.outputLines:
            line = ''
            numEmptyFields = 0
            numFullFields = 0
            for part in lineData:
                if hasattr(part, 'outputText'):
                    text = part.outputText(node, plainText, self.formatHtml)
                    if text:
                        numFullFields += 1
                    else:
                        numEmptyFields += 1
                    line += text
                else:
                    if not self.formatHtml and not plainText:
                        part = xml.sax.saxutils.escape(part)
                    elif self.formatHtml and plainText:
                        part = fieldformat.removeMarkup(part)
                    line += part
            if keepBlanks or numFullFields or not numEmptyFields:
                result.append(line)
            elif self.formatHtml and not plainText and result:
                # add ending HTML tag from skipped line back to previous line
                endTagMatch = _endTagRe.match(line)
                if endTagMatch:
                    result[-1] += endTagMatch.group(1)
        return result

    def addField(self, name, fieldData=None):
        """Add a field type with its format to the field list.

        Arguments:
            name -- the field name string
            fieldData -- the dict that defines this field's format
        """
        if not fieldData:
            fieldData = {}
        typeName = '{}Field'.format(fieldData.get('fieldtype', 'Text'))
        fieldClass = getattr(fieldformat, typeName, fieldformat.TextField)
        field = fieldClass(name, fieldData)
        self.fieldDict[name] = field

    def addFieldIfNew(self, name, fieldData=None):
        """Add a field type to the field list if not already there.

        Arguments:
            name -- the field name string
            fieldData -- the dict that defines this field's format
        """
        if name not in self.fieldDict:
            self.addField(name, fieldData)

    def addFieldList(self, nameList, addFirstTitle=False, addToOutput=False):
        """Add text fields with names given in list.

        Also add to title and output lines if addOutput is True.
        Arguments:
            nameList -- the list of names to add
            addFirstTitle -- if True, use first field for title output format
            addToOutput -- repelace output lines with all fields if True
        """
        for name in nameList:
            self.addFieldIfNew(name)
        if addFirstTitle:
            self.changeTitleLine('{{*{0}*}}'.format(nameList[0]))
        if addToOutput:
            self.changeOutputLines(['{{*{0}*}}'.format(name) for name in
                                    nameList])

    def reorderFields(self, fieldNameList):
        """Change the order of fieldDict to match the given list.

        Arguments:
            fieldNameList -- a list of existing field names in a desired order
        """
        newFieldDict = collections.OrderedDict()
        for fieldName in fieldNameList:
            newFieldDict[fieldName] = self.fieldDict[fieldName]
        self.fieldDict = newFieldDict

    def removeField(self, field):
        """Remove all occurances of field from title and output lines.

        Arguments:
            field -- the field to be removed
        """
        while field in self.titleLine:
            self.titleLine.remove(field)
        for lineData in self.outputLines:
            while field in lineData:
                lineData.remove(field)
        self.outputLines = [line for line in self.outputLines if line]
        # if len(self.lineList) == 0:
            # self.lineList.append([''])

    def setInitDefaultData(self, data, overwrite=False):
        """Add initial default data from fields into supplied data dict.

        Arguments:
            data -- the data dict to modify
            overwrite -- if true, replace previous data entries
        """
        for field in self.fields():
            text = field.getInitDefault()
            if text and (overwrite or not data.get(field.name, '')):
                data[field.name] = text

    def updateLineParsing(self):
        """Update the fields parsed in the output lines.

        Converts lines back to whole lines with embedded field names,
        then parse back to individual fields and text.
        """
        self.titleLine = self.parseLine(self.getTitleLine())
        self.outputLines = [self.parseLine(line) for line in
                            self.getOutputLines(False)]
        if self.origOutputLines:
            self.origOutputLines = [self.parseLine(line) for line in
                                    self.getOutputLines(True)]

    def parseLine(self, text):
        """Parse text format line, return list of field types and text.

        Splits the line into field and text segments.
        Arguments:
            text -- the raw format text line to be parsed
        """
        text = ' '.join(text.split())
        segments = (part for part in _fieldSplitRe.split(text) if part)
        return [self.parseField(part) for part in segments]

    def parseField(self, text):
        """Parse text field, return field type or plain text if not a field.

        Arguments:
            text -- the raw format text (could be a field)
        """
        fieldMatch = _fieldPartRe.match(text)
        if fieldMatch:
            modifier = fieldMatch.group(1)
            fieldName = fieldMatch.group(2)
            try:
                if not modifier:
                    return self.fieldDict[fieldName]
            except KeyError:
                pass
        return text

    def getTitleLine(self):
        """Return text of title format with field names embedded.
        """
        return ''.join([part.sepName() if hasattr(part, 'sepName') else part
                        for part in self.titleLine])

    def getOutputLines(self, useOriginal=True):
        """Return text list of output format lines with field names embedded.

        Arguments:
            useOriginal -- use original line list, wothout bullet or table mods
        """
        lines = self.outputLines
        if useOriginal and self.origOutputLines:
            lines = self.origOutputLines
        lines = [''.join([part.sepName() if hasattr(part, 'sepName') else part
                          for part in line])
                 for line in lines]
        return lines if lines else ['']

    def changeTitleLine(self, text):
        """Replace the title format line.

        Arguments:
            text -- the new title format line
        """
        self.titleLine = self.parseLine(text)
        if not self.titleLine:
            self.titleLine = ['']

    def changeOutputLines(self, lines, keepBlanks=False):
        """Replace the output format lines with given list.

        Arguments:
            lines -- a list of replacement format lines
            keepBlanks -- if False, ignore blank lines
        """
        self.outputLines = []
        for line in lines:
            newLine = self.parseLine(line)
            if keepBlanks or newLine:
                self.outputLines.append(newLine)
        if self.useBullets:
            self.origOutputLines = self.outputLines[:]
            self.addBullets()
        if self.useTables:
            self.origOutputLines = self.outputLines[:]
            self.addTables()

    def addOutputLine(self, line):
        """Add an output format line after existing lines.

        Arguments:
            line -- the text line to add
        """
        newLine = self.parseLine(line)
        if newLine:
            self.outputLines.append(newLine)

    def extractTitleData(self, titleString, data):
        """Modifies the data dictionary based on a title string.

        Match the title format to the string, return True if successful.
        Arguments:
            title -- the string with the new title
            data -- the data dictionary to be modified
        """
        fields = []
        pattern = ''
        extraText = ''
        for seg in self.titleLine:
            if hasattr(seg, 'name'):  # a field segment
                fields.append(seg)
                pattern += '(.*)'
            else:                     # a text separator
                pattern += re.escape(seg)
                extraText += seg
        match = re.match(pattern, titleString)
        try:
            if match:
                for num, field in enumerate(fields):
                    text = match.group(num + 1)
                    data[field.name] = field.storedTextFromTitle(text)
            elif not extraText.strip():
                # assign to 1st field if sep is only spaces
                text = fields[0].storedTextFromTitle(titleString)
                data[fields[0].name] = text
                for field in fields[1:]:
                    data[field.name] = ''
            else:
                return False
        except ValueError:
            return False
        return True

    def addBullets(self):
        """Add bullet HTML tags to sibling prefix, suffix and output lines.
        """
        self.siblingPrefix = '<ul>'
        self.siblingSuffix = '</ul>'
        lines = self.getOutputLines()
        if lines != ['']:
            lines[0] = '<li>' + lines[0]
            lines[-1] += '</li>'
        self.origOutputLines = self.outputLines[:]
        self.outputLines = lines
        self.updateLineParsing()

    def addTables(self):
        """Add table HTML tags to sibling prefix, suffix and output lines.
        """
        lines = [line for line in self.getOutputLines() if line]
        newLines = []
        headings = []
        for line in lines:
            head = ''
            firstPart = self.parseLine(line)[0]
            if hasattr(firstPart, 'split') and ':' in firstPart:
                head, line = line.split(':', 1)
            newLines.append(line.strip())
            headings.append(head.strip())
        self.siblingPrefix = '<table border="1" cellpadding="3">'
        if [head for head in headings if head]:
            self.siblingPrefix += '<tr>'
            for head in headings:
                self.siblingPrefix = ('{0}<th>{1}</th>'.
                                      format(self.siblingPrefix, head))
            self.siblingPrefix += '</tr>'
        self.siblingSuffix = '</table>'
        newLines = ['<td>{0}</td>'.format(line) for line in newLines]
        newLines[0] = '<tr>' + newLines[0]
        newLines[-1] += '</tr>'
        self.origOutputLines = self.outputLines[:]
        self.outputLines = newLines
        self.updateLineParsing()

    def clearBulletsAndTables(self):
        """Remove any HTML tags for bullets and tables.
        """
        self.siblingPrefix = ''
        self.siblingSuffix = ''
        if self.origOutputLines:
            self.outputLines = self.origOutputLines
            self.updateLineParsing()
        self.origOutputLines = []


class FileInfoFormat(NodeFormat):
    """Node format class to store and update special file info fields.

    Fields used in print header/footer and in outputs of other node types.
    """
    typeName = 'INT_TL_FILE_DATA_FORM'
    fileFieldName = 'File_Name'
    pathFieldName = 'File_Path'
    sizeFieldName = 'File_Size'
    dateFieldName = 'File_Mod_Date'
    timeFieldName = 'File_Mod_Time'
    ownerFieldName = 'File_Owner'
    pageNumFieldName = 'Page_Number'
    numPagesFieldName = 'Number_of_Pages'
    def __init__(self):
        """Create a file info format.
        """
        super().__init__(FileInfoFormat.typeName)
        self.fieldFormatModified = False
        self.addField(FileInfoFormat.fileFieldName)
        self.addField(FileInfoFormat.pathFieldName)
        self.addField(FileInfoFormat.sizeFieldName, {'type': 'Number'})
        self.addField(FileInfoFormat.dateFieldName, {'type': 'Date'})
        self.addField(FileInfoFormat.timeFieldName, {'type': 'Time'})
        if not sys.platform.startswith('win'):
            self.addField(FileInfoFormat.ownerFieldName)
        # page info only for print header:
        self.addField(FileInfoFormat.pageNumFieldName)
        self.fieldDict[FileInfoFormat.pageNumFieldName].showInDialog = False
        self.addField(FileInfoFormat.numPagesFieldName)
        self.fieldDict[FileInfoFormat.numPagesFieldName].showInDialog = False
        for field in self.fields():
            field.useFileInfo = True

    def updateFileInfo(self, fileName, fileInfoNode):
        """Update data of file info node.

        Arguments:
            fileName -- the TreeLine file path
            fileInfoNode -- the node to update
        """
        try:
            status = os.stat(fileName)
        except OSError:
            fileInfoNode.data = {}
            return
        fileInfoNode.data[FileInfoFormat.fileFieldName] = (os.path.
                                                           basename(fileName))
        fileInfoNode.data[FileInfoFormat.pathFieldName] = (os.path.
                                                           dirname(fileName))
        fileInfoNode.data[FileInfoFormat.sizeFieldName] = str(status[stat.
                                                                     ST_SIZE])
        modDateTime = QDateTime()
        modDateTime.setTime_t(status[stat.ST_MTIME])
        modDateTime = modDateTime.toLocalTime()
        modDate = modDateTime.date().toString(Qt.ISODate)
        modTime = modDateTime.time().toString()
        fileInfoNode.data[FileInfoFormat.dateFieldName] = modDate
        fileInfoNode.data[FileInfoFormat.timeFieldName] = modTime
        if not sys.platform.startswith('win'):
            try:
                owner = pwd.getpwuid(status[stat.ST_UID])[0]
            except KeyError:
                owner = repr(status[stat.ST_UID])
            fileInfoNode.data[FileInfoFormat.ownerFieldName] = owner

    def duplicateFieldFormats(self, altFileFormat):
        """Copy field format settings from alternate file format.

        Arguments:
            altFileFormat -- the file info format to copy from
        """
        for field in self.fields():
            altField = altFileFormat.fieldDict.get(field.name)
            if altField:
                if field.format != altField.format:
                    field.setFormat(altField.format)
                    self.fieldFormatModified = True
                if altField.prefix:
                    field.prefix = altField.prefix
                    self.fieldFormatModified = True
                if altField.suffix:
                    field.suffix = altField.suffix
                    self.fieldFormatModified = True
