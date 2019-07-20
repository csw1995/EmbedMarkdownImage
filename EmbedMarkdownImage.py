#! /usr/bin/python
from __future__ import absolute_import, division, print_function
import fileinput
import re
import os

import getopt
import sys
import base64
import hashlib
import datetime

def usage():

    print ('''
Usage: EmbedMarkdownImage -f document.md [-options] [args...]

where options include:
    -h | --help             show this helper
    -f | --file=<value>     set markdown document file
    -u | --use-old-data     use existing encoded data instead of re-encode the images
    -k | --keep-useless-data
                            keep existing encoded data even though no longer in use
    -l | --lines-of-space=<value>
                            set lines of space ahead of base64-encoded image data
    ''')

    sys.exit(-1)
 
 

class MarkDownFile :
    def __init__(self, mdFileName, inputConfigDict={}):
        if not os.path.exists(mdFileName):
            print("No Such File %s" % mdFileName)
            raise IOError

        self.__mdFileName = mdFileName   
        self.__basedir = os.path.dirname(self.__mdFileName)

        # Line seperator of document
        self.__linesep = self.__GetLinesep()

        # Set default config
        self.__config = {
            # Line of space between base64-encoded data
            "spacelines" : 20,

            # Ways to deal with existing base64-encoded data
            "useOldDataFlag" : False,
            "keepUselessDataFlag" : False
        }
        
        # Set config from input
        self.SetConfigDict(inputConfigDict)

        # Extension of document backup file
        self.backupExt = ".%s.bak" % datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Dictionary of MD5 of images to identify them
        self.__imgMd5CacheDict = {}

        # Dictionary to link label and image data. 
        # Key : image label (first 8 chars of MD5)
        # Value : (image path, image file extension)
        self.__imgFileDict = {}
        
        # Internal image : ![.*][label]
        # Externam image : ![.*](image path or url)
        # Encoded image  : [label]:data:image/extension;base64,encoded data
        self.__imgPattern = re.compile(r"!\[([^]]*)\]")
        self.__imgInternalPattern = re.compile(r"!\[([^]]*)\]\[([^]]*)\]")
        self.__imgExternalPattern = re.compile(r"!\[([^]]*)\]\(([^)]*)\)")            
        self.__dataPattern = re.compile(r"\[([^]]*)\]:data:image.*")

    def __GetLinesep(self):
        linesep = ""
        with open(self.__mdFileName,"r") as f:
            while True:
                data = f.read(1024)
                if not data :
                    break
                
                if "\r\n" in data :
                    linesep = "\r\n"
                    break
                elif "\n" in data :
                    linesep += "\n"
                    break
                elif "\r" in data :
                    linesep = "\r"
                    continue
                elif linesep == "\r":
                    break
        return linesep

    def SetConfig(self, key, value):
        self.__config[key] = value

    def SetConfigDict(self, inputConfigDict):             
        if type(inputConfigDict) != type({}):
            raise TypeError
        for key, value in inputConfigDict.items():
            self.__config[key] = value
    
    def GetConfig(self, key):
        return self.__config.setdefault(key, None)
        
    def GetConfigDict(self):
        return self.__config
        
    def __GetMd5Label(self, filePath, labelLength=8):
        # Get first 8 chars of MD5 hash of image to distinguish them

        result = None
        for dummy in range(1) :
            if type(labelLength) != type(0) :
                break
            if not os.path.exists(filePath) :
                break

            # Reduce redundant computation using dictionary to cache result
            if filePath in self.__imgMd5CacheDict:
                hashValue = self.__imgMd5CacheDict[filePath]
            else :
                m = hashlib.md5()
                with open(filePath, "rb") as f :
                    while True:
                        data = f.read(1024)
                        if not data:
                            break
                        m.update(data)

                # Save the result in the dictionary
                hashValue = m.hexdigest()
                self.__imgMd5CacheDict[filePath] = hashValue

            result = hashValue[:labelLength]

        return result

        
    def __GetImageInfo(self, line):
        # Analyse if the line represents image then extract information
        resultDict = {
            "type":None,
            "label":"",
            "path":"",
            "ext":""
        }

        # Break and return when encouter errors
        for dummy in range(1):
            # Find lines like ![.*]
            result = self.__imgPattern.search(line)
            if result is None :
                break
                
            # Determine the line is ![.*][label] or ![.*](path)
            resultInternal = self.__imgInternalPattern.search(line)
            resultExternal = self.__imgExternalPattern.search(line)

            if resultInternal is not None :
                # Internal image, no need to continue process
                resultDict["type"] = "internal"
                resultDict["label"] = resultInternal.group(2)
                break

            if resultExternal is None :
                # Neither two types of pattern, unrecognized
                break

            # Validate the image path
            imgFilePath = resultExternal.group(2)
            if len(imgFilePath) == 0:
                break
            if not os.path.isabs(imgFilePath) :
                imgFilePath = os.path.join(self.__basedir, imgFilePath)
            if not os.path.exists(imgFilePath) :
                break
            if not '.' in imgFilePath:
                break
            
            # Extract image extension
            imgFileNameWithoutExt, ext = os.path.splitext(os.path.basename(imgFilePath))
            if not ext in ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.bmp', '.tif']:
                break
                
            resultDict["type"] = "external"
            resultDict["path"] = imgFilePath
            resultDict["label"] = self.__GetMd5Label(imgFilePath)
            resultDict["ext"] = ext

        return resultDict
        
    def __ReplaceImageLink(self):
        # First pass : Go through the document and replace image path with label
        mdFile = fileinput.FileInput(self.__mdFileName, inplace=True, backup=self.backupExt)

        for line in mdFile:
            # By default the line is intact
            outputLine = line
            resultDict = self.__GetImageInfo(line)
            if resultDict["type"] is None :
                # No valid image information found, do nothing
                pass
            elif resultDict["type"] == "internal" :
                # Log the label is in use, but no image path
                self.__imgFileDict[resultDict["label"]] = None
            elif resultDict["type"] == "external" :
                # Log the label and image path, then replace the image path with label
                self.__imgFileDict[resultDict["label"]] = (resultDict["path"], resultDict["ext"])
                outputLine = self.__imgExternalPattern.sub("![%s][%s]" % (resultDict["label"], resultDict["label"]), line)

            print(outputLine, end='')

        mdFile.close()

    def __ProcessOldData(self):
        # Second pass : Deal with Existing image data
        mdFile = fileinput.FileInput(self.__mdFileName, inplace=True, backup='')

        for line in mdFile:
            # By default the line is intact
            outputLine = line
            for dummy in range(1):
                # Data pattern : [label]:data:image
                result = self.__dataPattern.search(line)
                if result is None :
                    break
                
                imgFileLabel = result.group(1)
                if len(imgFileLabel) == 0:
                    break
                
                if imgFileLabel in self.__imgFileDict :
                    # This data is used by the image in the document

                    if self.__config["useOldDataFlag"] == True:
                        # Skip encode data of this image, use existing data
                        del self.__imgFileDict[imgFileLabel]

                    elif self.__imgFileDict[imgFileLabel] is not None :
                        # Clean old image data and use new data
                        outputLine = ""
                else :
                    # Existing data is useless in the document

                    if self.__config["keepUselessDataFlag"] == False :
                        # Clean this old useless image data
                        outputLine = ""

                break
                # dummy loop end


            print(outputLine, end='')
            continue

        mdFile.close()


    def __InsertNewData(self):
        # Encode images and insert them at the end of document

        # The space lines ahead of data
        margin = self.__linesep * self.__config["spacelines"]
        
        with open(self.__mdFileName, 'a+') as mdFile :
            for imgFileLabel, value in self.__imgFileDict.items() :
                if value is None :
                    # Image has no path information, no data to insert
                    continue
                
                imgFilePath = value[0]
                ext = value[1]
                if not os.path.exists(imgFilePath):
                    print("No Such File %s" % imgFilePath)
                    continue

                with open(imgFilePath, "rb") as imgFile:
                    imgBase64 = base64.b64encode(imgFile.read())
                
                    mdData = "{margin}[{imgLabel}]:data:image/{ext};base64,{imgData}{linesep}".format(margin=margin, imgLabel=imgFileLabel, ext=ext, imgData=imgBase64, linesep=self.__linesep )
                    
                    mdFile.write(mdData)

            mdFile.close()
    
    def CleanRedundantBackup(self):
        # (Optional) Clean the backup at the end of process if document is intact
        backupFileName = self.__mdFileName + self.backupExt
        if os.path.exists(backupFileName):
            if self.__GetMd5Label(backupFileName,labelLength=32) == self.__GetMd5Label(self.__mdFileName,labelLength=32):
                os.remove(backupFileName)

    def EncodeImageInDocument(self):
        self.__ReplaceImageLink()
        self.__ProcessOldData()
        self.__InsertNewData()



if __name__ == '__main__':
    
    mdFileName=None
    configDict={}

    try:
        options, args = getopt.getopt(sys.argv[1:], "hf:l:uk", ['help', "file=", "lines-of-space=", "use-old-data", "keep-useless-data"])
        for name, value in options:
            if name in ('-h', '--help'):
                usage()
            elif name in ('-f', '--file'):
                mdFileName = value
            elif name in ('-l', '--lines-of-space'):
                configDict["spacelines"] = value
            elif name in ('-u', '--use-old-data'):
                configDict["useOldDataFlag"] = True
            elif name in ('-k', '--keep-useless-data'):
                configDict["keepUselessDataFlag"] = True

    except getopt.GetoptError:
        usage()

    if mdFileName is None :
        sys.stderr.write("\n[ERROR] Please give the markdown document filename as argument!\n")
        usage()
        
    markDownFile = MarkDownFile(mdFileName, configDict)

    markDownFile.EncodeImageInDocument()
    markDownFile.CleanRedundantBackup()
    
    


