#! /usr/bin/python
from __future__ import absolute_import, division, print_function
import re, datetime
import os, sys, shutil
import getopt, fileinput
import base64, hashlib

def usage():

    print ('''
Usage: EmbedMarkdownImage -f document.md --action=<value> [-options] [args...]

where options include:
    -h | --help             show this helper
    -f | --file=<value>     set markdown document file
    -u | --use-old-data     use existing encoded data instead of re-encode the images
    -k | --keep-useless-data
                            keep existing encoded data even though no longer in use
    -l | --lines-of-space=<value>
                            set lines of space ahead of base64-encoded image data
    -b | --backup-dir=<value>
                            set backup file save directory
    --action=EncodeFile | EncodeNameOnly
                            set encode action type
    ''')

    sys.exit(-1)
 
 

class MarkDownFile :
    def __init__(self, mdFileName, inputConfigDict={}):
        if not os.path.exists(mdFileName):
            sys.stderr.write("[ERROR] No such file %s" % mdFileName)
            raise IOError

        # Split file name
        self.__mdFileName = mdFileName   
        self.__basedir = os.path.realpath(os.path.dirname(mdFileName))
        self.__mdFileBaseName = os.path.basename(mdFileName)

        # Line seperator of document
        self.__linesep = self.GetLinesep(mdFileName)

        # Set default config
        self.__config = {
            # Line of space between base64-encoded data
            "spacelines" : 20,

            # Ways to deal with existing base64-encoded data
            "useOldDataFlag" : False,
            "keepUselessDataFlag" : False,

            # Directory and exension of document backup file
            "backupDir" : self.__basedir,
            "backupExt" : ".%s.bak" % datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        }
        
        # Set config from input
        self.SetConfigDict(inputConfigDict)

        # Set Backup Filename
        self.__backupFileName = os.path.join(self.__config["backupDir"], self.__mdFileBaseName + self.__config["backupExt"])
        
        # Dictionary of MD5 of images to identify them
        self.__imageMd5CacheDict = {}

        # Dictionary to link label and image data. 
        # Key : image label (first 8 chars of MD5)
        # Value : (image path, image file extension)
        self.__imageFileDict = {}
        
        # Internal image : ![.*][label]
        # Externam image : ![.*](image path or url)
        # Encoded image  : [label]:data:image/extension;base64,encoded data
        self.__imagePattern = re.compile(r"!\[([^]]*)\]")
        self.__imageInternalPattern = re.compile(r"!\[([^]]*)\]\[([^]]*)\]")
        self.__imageExternalPattern = re.compile(r"!\[([^]]*)\]\(([^)]*)\)")            
        self.__dataPattern = re.compile(r"\[([^]]*)\]:data:image.*")

    def GetLinesep(self, fileName):
        linesep = ""
        with open(fileName,"r") as f:
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
            sys.stderr.write("[ERROR] Type of input config is not dictionary!")
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
            if filePath in self.__imageMd5CacheDict:
                hashValue = self.__imageMd5CacheDict[filePath]
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
                self.__imageMd5CacheDict[filePath] = hashValue

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
            result = self.__imagePattern.search(line)
            if result is None :
                break
                
            # Determine the line is ![.*][label] or ![.*](path)
            resultInternal = self.__imageInternalPattern.search(line)
            resultExternal = self.__imageExternalPattern.search(line)

            if resultInternal is not None :
                # Internal image, no need to continue process
                resultDict["type"] = "internal"
                resultDict["label"] = resultInternal.group(2)
                break

            if resultExternal is None :
                # Neither two types of pattern, unrecognized
                break

            # Validate the image path
            imageFilePath = resultExternal.group(2)
            if len(imageFilePath) == 0:
                break
            if os.path.isabs(imageFilePath) :
                imageFileAbsPath = imageFilePath
            else :
                imageFileAbsPath = os.path.realpath(os.path.join(self.__basedir, imageFilePath))
            if not os.path.exists(imageFileAbsPath) :
                break
            
            # Extract image extension
            imageFileNameWithoutExt, ext = os.path.splitext(os.path.basename(imageFilePath))
            if not ext in ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.bmp', '.tif']:
                break
                
            resultDict["type"] = "external"
            resultDict["path"] = imageFilePath
            resultDict["abspath"] = imageFileAbsPath
            resultDict["label"] = self.__GetMd5Label(imageFileAbsPath)
            resultDict["ext"] = ext

        return resultDict
        
    def __ReplaceImageLink(self, action="EncodeFile"):
        # First pass : Go through the document and replace image path with label
        mdFile = fileinput.FileInput(self.__mdFileName, inplace=True, backup='')

        for line in mdFile:
            # By default the line is intact
            outputLine = line
            resultDict = self.__GetImageInfo(line)
            if resultDict["type"] is None :
                # No valid image information found, do nothing
                pass
            elif resultDict["type"] == "internal" :
                if action == "EncodeFile":
                    # Log the label is in use, but no image path
                    self.__imageFileDict[resultDict["label"]] = None
            elif resultDict["type"] == "external" :
                if action == "EncodeFile" :
                    # Log the label and image path, then replace the image path with label
                    self.__imageFileDict[resultDict["label"]] = (resultDict["abspath"], resultDict["ext"])
                    outputLine = self.__imageExternalPattern.sub("![%s][%s]" % (resultDict["label"], resultDict["label"]), line)
                elif action == "EncodeNameOnly" :
                    # Just rename images by their MD5 if filename is too long
                    fileNameThreshold = 12
                    if len(resultDict["path"]) < fileNameThreshold :
                        continue

                    imageBasedir = os.path.dirname(resultDict["path"])
                    imageFileNameNew = resultDict["label"] + resultDict["ext"]
                    imageFilePathNew = os.path.join(imageBasedir, imageFileNameNew)
                    if os.path.isabs(imageFilePathNew) :
                        imageFileAbsPathNew = imageFilePathNew
                    else :
                        imageFileAbsPathNew = os.path.realpath(os.path.join(self.__basedir, imageFilePathNew))

                    sys.stderr.write(imageBasedir + "\n")
                    sys.stderr.write(imageFileNameNew + "\n")
                    sys.stderr.write(imageFilePathNew + "\n")

                    if not os.path.exists(imageFileAbsPathNew) :
                        os.rename(resultDict["abspath"], imageFileAbsPathNew)
                    else :
                        # If MD5 named file exists, use existed one
                        pass

                    resultDict["path"] = imageFilePathNew
                    resultDict["abspath"] = imageFileAbsPathNew
                    outputLine = self.__imageExternalPattern.sub("![%s](%s)" % (resultDict["label"], imageFilePathNew), line)

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
                
                imageFileLabel = result.group(1)
                if len(imageFileLabel) == 0:
                    break
                
                if imageFileLabel in self.__imageFileDict :
                    # This data is used by the image in the document

                    if self.__config["useOldDataFlag"] == True:
                        # Skip encode data of this image, use existing data
                        del self.__imageFileDict[imageFileLabel]

                    elif self.__imageFileDict[imageFileLabel] is not None :
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
            for imageFileLabel, value in self.__imageFileDict.items() :
                if value is None :
                    # Image has no path information, no data to insert
                    continue
                
                imageFilePath = value[0]
                ext = value[1]
                if not os.path.exists(imageFilePath):
                    print("No Such File %s" % imageFilePath)
                    continue

                with open(imageFilePath, "rb") as imageFile:
                    imageBase64 = base64.b64encode(imageFile.read())
                
                    mdData = "{margin}[{imageLabel}]:data:image/{ext};base64,{imageData}{linesep}".format(margin=margin, imageLabel=imageFileLabel, ext=ext, imageData=imageBase64, linesep=self.__linesep )
                    
                    mdFile.write(mdData)

            mdFile.close()
    
    def MakeBackup(self):        
        if not os.path.exists(self.__config["backupDir"]) :
            sys.stderr.write("[ERROR] No such backup directory %s" % self.__config["backupDir"])
            raise IOError

        shutil.copyfile(self.__mdFileName, self.__backupFileName)
        print("[INFO] Backup file is %s" % self.__backupFileName)

    def CleanRedundantBackup(self):
        # (Optional) Clean the backup at the end of process if document is intact
        if os.path.exists(self.__backupFileName):
            backupMd5 = self.__GetMd5Label(self.__backupFileName,labelLength=32)
            outputMd5 = self.__GetMd5Label(self.__mdFileName,labelLength=32)
            if backupMd5 == outputMd5 :
                os.remove(self.__backupFileName)
                print("[INFO] Backup file %s has been removed." % self.__backupFileName)


    def EncodeImageInDocument(self):
        self.__ReplaceImageLink()
        self.__ProcessOldData()
        self.__InsertNewData()

    def EncodeImageFileName(self):
        self.__ReplaceImageLink(action="EncodeNameOnly")




if __name__ == '__main__':
    
    mdFileName=None
    action=None
    configDict={}

    try:
        options, args = getopt.getopt(sys.argv[1:], "hf:l:ukb:", ['help', "file=", "lines-of-space=", "use-old-data", "keep-useless-data", "backup-dir=", "action="])
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
            elif name in ('-b', '--backup-dir'):
                configDict["backupDir"] = value
            elif name in ('--action'):
                action=value

    except getopt.GetoptError:
        usage()

    if mdFileName is None :
        sys.stderr.write("\n[ERROR] Please give the markdown document filename as argument!\n")
        usage()
        
    markDownFile = MarkDownFile(mdFileName, configDict)

    if action == "EncodeFile" :
        markDownFile.MakeBackup()
        markDownFile.EncodeImageInDocument()
        markDownFile.CleanRedundantBackup()
    elif action == "EncodeNameOnly" :
        markDownFile.MakeBackup()
        markDownFile.EncodeImageFileName()
        markDownFile.CleanRedundantBackup()
    else :
        usage()

    
    


