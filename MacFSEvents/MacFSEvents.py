# This python autopsy module will export the .fsevents directory and run the 
# FSEParser_v2.1.exe prorgam against the exported data.  It will then import 
# the SQLite database that was created from the program.
#
# Contact: Mark McKinnon [Mark [dot] McKinnon <at> gmail [dot] com]
#
# This is free and unencumbered software released into the public domain.
#
# Anyone is free to copy, modify, publish, use, compile, sell, or
# distribute this software, either in source code form or as a compiled
# binary, for any purpose, commercial or non-commercial, and by any
# means.
#
# In jurisdictions that recognize copyright laws, the author or authors
# of this software dedicate any and all copyright interest in the
# software to the public domain. We make this dedication for the benefit
# of the public at large and to the detriment of our heirs and
# successors. We intend this dedication to be an overt act of
# relinquishment in perpetuity of all present and future rights to this
# software under copyright law.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.

# MacFSEvents.
# May 2017
# 
# Comments 
#   Version 1.0 - Initial version - May 2017
#   Version 1.1 - Updated executable called to FSEParser_v2.1.exe and
#                 add different types of fsevents to display.  The different
#                 types of events are stored in a SQLite database so more can
#                 be added at a later date without having to change the code.
# 

import jarray
import inspect
import os
from subprocess import Popen, PIPE
import shutil

from javax.swing import JCheckBox
from javax.swing import JButton
from javax.swing import ButtonGroup
from javax.swing import JTextField
from javax.swing import JLabel
from java.awt import GridLayout
from java.awt import GridBagLayout
from java.awt import GridBagConstraints
from javax.swing import JPanel
from javax.swing import JList
from javax.swing import JScrollPane
from javax.swing import JFileChooser
from javax.swing import JComboBox
from javax.swing.filechooser import FileNameExtensionFilter

from java.lang import Class
from java.lang import System
from java.sql  import DriverManager, SQLException
from java.util.logging import Level
from java.io import File
from org.sleuthkit.datamodel import SleuthkitCase
from org.sleuthkit.datamodel import AbstractFile
from org.sleuthkit.datamodel import ReadContentInputStream
from org.sleuthkit.datamodel import BlackboardArtifact
from org.sleuthkit.datamodel import BlackboardAttribute
from org.sleuthkit.datamodel import TskData
from org.sleuthkit.autopsy.ingest import IngestModule
from org.sleuthkit.autopsy.ingest.IngestModule import IngestModuleException
from org.sleuthkit.autopsy.ingest import DataSourceIngestModule
from org.sleuthkit.autopsy.ingest import IngestModuleFactoryAdapter
from org.sleuthkit.autopsy.ingest import IngestMessage
from org.sleuthkit.autopsy.ingest import IngestServices
from org.sleuthkit.autopsy.ingest import ModuleDataEvent
from org.sleuthkit.autopsy.coreutils import Logger
from org.sleuthkit.autopsy.coreutils import PlatformUtil
from org.sleuthkit.autopsy.casemodule import Case
from org.sleuthkit.autopsy.casemodule.services import Services
from org.sleuthkit.autopsy.casemodule.services import FileManager
from org.sleuthkit.autopsy.datamodel import ContentUtils


# Factory that defines the name and details of the module and allows Autopsy
# to create instances of the modules that will do the analysis.
class MacFSEventsIngestModuleFactory(IngestModuleFactoryAdapter):

    def __init__(self):
        self.settings = None

    moduleName = "Mac OSX FSEvents Module"
    
    def getModuleDisplayName(self):
        return self.moduleName
    
    def getModuleDescription(self):
        return "Get the FSEvents data"
    
    def getModuleVersionNumber(self):
        return "1.0"
    
    def isDataSourceIngestModuleFactory(self):
        return True

    def createDataSourceIngestModule(self, ingestOptions):
        return MacFSEventsIngestModule(self.settings)

# Data Source-level ingest module.  One gets created per data source.
class MacFSEventsIngestModule(DataSourceIngestModule):

    _logger = Logger.getLogger(MacFSEventsIngestModuleFactory.moduleName)

    def log(self, level, msg):
        self._logger.logp(level, self.__class__.__name__, inspect.stack()[1][3], msg)
    def __init__(self, settings):
        self.context = None
        self.local_settings = settings
        self.database_file = ""
        self.Plugins_for_SQL = ('FolderEvent','Mount','Unmount','EndOfTransaction','LastHardLinkRemoved','HardLink', \
                                'SymbolicLink','FileEvent','PermissionChange','ExtendedAttrModified','ExtendedAttrRemoved', \
                                'DocumentRevisioning','Created','Removed','InodeMetaMod','Renamed','Modified', \
                                'Exchange','FinderInfoMod','FolderCreated')
        self.Plugin_Like_Stmt = ""
        
    # Where any setup and configuration is done
    # 'context' is an instance of org.sleuthkit.autopsy.ingest.IngestJobContext.
    # See: http://sleuthkit.org/autopsy/docs/api-docs/3.1/classorg_1_1sleuthkit_1_1autopsy_1_1ingest_1_1_ingest_job_context.html
    def startUp(self, context):
        self.context = context

        #Show parameters that are passed in
        if PlatformUtil.isWindowsOS():
            self.path_to_exe = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fseparser_v2.1.exe")
            if not os.path.exists(self.path_to_exe):
                raise IngestModuleException("Windows Executable was not found in module folder")
        elif PlatformUtil.getOSName() == 'Linux':
            self.path_to_exe = os.path.join(os.path.dirname(os.path.abspath(__file__)), "FSEParser_V2.1")
            if not os.path.exists(self.path_to_exe):
                raise IngestModuleException("Linux Executable was not found in module folder")

        self.MacFSEvents_Executable = self.path_to_exe
        self.log(Level.INFO, "MacFSEvents Executable ==> " + self.MacFSEvents_Executable)
   
        
        # Throw an IngestModule.IngestModuleException exception if there was a problem setting up
        # raise IngestModuleException(IngestModule(), "Oh No!")
        pass

    # Where the analysis is done.
    # The 'dataSource' object being passed in is of type org.sleuthkit.datamodel.Content.
    # See:x http://www.sleuthkit.org/sleuthkit/docs/jni-docs/interfaceorg_1_1sleuthkit_1_1datamodel_1_1_content.html
    # 'progressBar' is of type org.sleuthkit.autopsy.ingest.DataSourceIngestModuleProgress
    # See: http://sleuthkit.org/autopsy/docs/api-docs/3.1/classorg_1_1sleuthkit_1_1autopsy_1_1ingest_1_1_data_source_ingest_module_progress.html
    def process(self, dataSource, progressBar):

        self.log(Level.INFO, "Starting to process, Just before call to parse_safari_history")

        # we don't know how much work there is yet
        progressBar.switchToIndeterminate()
        
        # Get the temp directory and create the sub directory
        Temp_Dir = Case.getCurrentCase().getTempDirectory()
        temp_dir = os.path.join(Temp_Dir, "MacFSEvents")
        try:
		    os.mkdir(temp_dir)
        except:
		    self.log(Level.INFO, "FSEvents Directory already exists " + temp_dir)

        # Set the database to be read to the once created by the prefetch parser program
        skCase = Case.getCurrentCase().getSleuthkitCase();
        fileManager = Case.getCurrentCase().getServices().getFileManager()
        files = fileManager.findFiles(dataSource, "%", ".fseventsd")
        numFiles = len(files)

        for file in files:
            #self.log(Level.INFO, "Files ==> " + file.getName())               
            if (file.getName() == "..") or (file.getName() == '.') or (file.getName() == 'fseventsd-uuid'):
                pass
                #self.log(Level.INFO, "Files ==> " + str(file))               
            else:
                # Check if the user pressed cancel while we were busy
                if self.context.isJobCancelled():
                    return IngestModule.ProcessResult.OK

                # Save the DB locally in the temp folder. use file id as name to reduce collisions
                filePath = os.path.join(temp_dir, file.getName())
                ContentUtils.writeToFile(file, File(filePath))

        
        self.log(Level.INFO, "Number of files to process ==> " + str(numFiles))
        self.log(Level.INFO, "Running program ==> " + self.MacFSEvents_Executable + " -c Autopsy " + "-o " + temp_dir + \
                             " -s " + Temp_Dir + "\MacFSEvents")
        pipe = Popen([self.MacFSEvents_Executable, "-c", "Autopsy", "-o", temp_dir, "-s", temp_dir], stdout=PIPE, stderr=PIPE)
        out_text = pipe.communicate()[0]
        self.log(Level.INFO, "Output from run is ==> " + out_text)               

        database_file = os.path.join(temp_dir, "Autopsy_FSEvents-Parsed_Records_DB.sqlite") 
        
        #open the database to get the SQL and artifact info out of
        try: 
            head, tail = os.path.split(os.path.abspath(__file__)) 
            settings_db = os.path.join(head, "fsevents_sql.db3")
            Class.forName("org.sqlite.JDBC").newInstance()
            dbConn1 = DriverManager.getConnection("jdbc:sqlite:%s"  % settings_db)
        except SQLException as e:
            self.log(Level.INFO, "Could not open database file (not SQLite) " + database_file + " (" + e.getMessage() + ")")
            return IngestModule.ProcessResult.OK

        try:
            stmt1 = dbConn1.createStatement()
            sql_statement1 = "select distinct artifact_name, artifact_title from extracted_content_sql;"
            #self.log(Level.INFO, "SQL Statement ==> " + sql_statement)
            resultSet1 = stmt1.executeQuery(sql_statement1)
            while resultSet1.next():
                try:
                     self.log(Level.INFO, "Begin Create New Artifacts")
                     artID_fse = skCase.addArtifactType( resultSet1.getString("artifact_name"), resultSet1.getString("artifact_title"))
                except:		
                     self.log(Level.INFO, "Artifacts Creation Error, " + resultSet1.getString("artifact_name") + " some artifacts may not exist now. ==> ")
                                      
        except SQLException as e:
           self.log(Level.INFO, "Could not open database file (not SQLite) " + database_file + " (" + e.getMessage() + ")")
           #return IngestModule.ProcessResult.OK
        
        # Create the attribute type, if it exists then catch the error
        try:
            attID_fse_fn = skCase.addArtifactAttributeType("TSK_FSEVENTS_FILE_NAME", BlackboardAttribute.TSK_BLACKBOARD_ATTRIBUTE_VALUE_TYPE.STRING, "File Name")
        except:		
             self.log(Level.INFO, "Attributes Creation Error, File Name. ==> ")
        
        try:
            attID_fse_msk = skCase.addArtifactAttributeType("TSK_FSEVENTS_FILE_MASK", BlackboardAttribute.TSK_BLACKBOARD_ATTRIBUTE_VALUE_TYPE.STRING, "Mask")
        except:		
             self.log(Level.INFO, "Attributes Creation Error, Mask. ==> ")
        
        try:
            attID_fse_src = skCase.addArtifactAttributeType("TSK_FSEVENTS_SOURCE", BlackboardAttribute.TSK_BLACKBOARD_ATTRIBUTE_VALUE_TYPE.STRING, "Source File")
        except:		
             self.log(Level.INFO, "Attributes Creation Error, Mask. ==> ")

        try:
            attID_fse_dte = skCase.addArtifactAttributeType("TSK_FSEVENTS_DATES", BlackboardAttribute.TSK_BLACKBOARD_ATTRIBUTE_VALUE_TYPE.STRING, "Date(s)")
        except:		
             self.log(Level.INFO, "Attributes Creation Error, Mask. ==> ")
             
        try: 
            Class.forName("org.sqlite.JDBC").newInstance()
            dbConn = DriverManager.getConnection("jdbc:sqlite:%s"  % os.path.join(temp_dir, "Autopsy_FSEvents-Parsed_Records_DB.sqlite"))
        except SQLException as e:
            self.log(Level.INFO, "Could not open database file (not SQLite) " + database_file + " (" + e.getMessage() + ")")
            return IngestModule.ProcessResult.OK
        
        #artID_fse = skCase.getArtifactTypeID("TSK_MACOS_FSEVENTS")
        #artID_fse_evt = skCase.getArtifactType("TSK_MACOS_FSEVENTS")
        artID_fse = skCase.getArtifactTypeID("TSK_MACOS_ALL_FSEVENTS")
        artID_fse_evt = skCase.getArtifactType("TSK_MACOS_ALL_FSEVENTS")
        attID_fse_fn = skCase.getAttributeType("TSK_FSEVENTS_FILE_NAME")
        attID_fse_msk = skCase.getAttributeType("TSK_FSEVENTS_FILE_MASK")
        attID_fse_src = skCase.getAttributeType("TSK_FSEVENTS_SOURCE")
        attID_fse_dte = skCase.getAttributeType("TSK_FSEVENTS_DATES")
 
        # Query the database 
        for file in files:
            if ('slack' in file.getName()):
                pass
            elif (file.getName() == '..') or (file.getName() == '.'):
                pass
            else:
               stmt1 = dbConn1.createStatement()
               sql_statement1 = "select sql_statement, artifact_name, artifact_title from extracted_content_sql;"
               #self.log(Level.INFO, "SQL Statement ==> " + sql_statement)
               resultSet1 = stmt1.executeQuery(sql_statement1)
               while resultSet1.next():
                    try:
                        artID_fse = skCase.getArtifactTypeID(resultSet1.getString("artifact_name"))
                        artID_fse_evt = skCase.getArtifactType(resultSet1.getString("artifact_name"))
                                 
                        try:
                            stmt = dbConn.createStatement()
                            sql_statement = resultSet1.getString("sql_statement") + " and source like '%" + file.getName() + "';"
                            #self.log(Level.INFO, "SQL Statement ==> " + sql_statement)
                            resultSet = stmt.executeQuery(sql_statement)
                            #self.log(Level.INFO, "query SQLite Master table ==> " )
                            #self.log(Level.INFO, "query " + str(resultSet))
                            # Cycle through each row and create artifact
                            while resultSet.next():
                            # Add the attributes to the artifact.
                                art = file.newArtifact(artID_fse)
                                #self.log(Level.INFO, "Result ==> " + resultSet.getString("mask") + ' <==> ' + resultSet.getString("source"))
                                art.addAttributes(((BlackboardAttribute(attID_fse_fn, MacFSEventsIngestModuleFactory.moduleName, resultSet.getString("filename"))), \
                                              (BlackboardAttribute(attID_fse_msk, MacFSEventsIngestModuleFactory.moduleName, resultSet.getString("mask"))), \
                                              (BlackboardAttribute(attID_fse_src, MacFSEventsIngestModuleFactory.moduleName, resultSet.getString("source"))), \
                                              (BlackboardAttribute(attID_fse_dte, MacFSEventsIngestModuleFactory.moduleName, resultSet.getString("OTHER_DATES")))))
                                              
                                #try:
                                # index the artifact for keyword search
                                   #blackboard.indexArtifact(art)
                                #except:
                                   #self.log(Level.INFO, "Error indexing artifact " + art.getDisplayName())

                        except SQLException as e:
                           self.log(Level.INFO, "Could not open database file (not SQLite) " + database_file + " (" + e.getMessage() + ")")
                           return IngestModule.ProcessResult.OK
                    except SQLException as e:
                        self.log(Level.INFO, "Could not open database file (not SQLite) " + database_file + " (" + e.getMessage() + ")")

            try:
               stmt.close()
            except:
                 self.log(Level.INFO, "Error closing statement for " + file.getName())
                 
            # Fire an event to notify the UI and others that there are new artifacts  
            IngestServices.getInstance().fireModuleDataEvent(ModuleDataEvent(MacFSEventsIngestModuleFactory.moduleName, artID_fse_evt, None))

        try:
             stmt.close()
             dbConn.close()
             stmt1.close()
             dbConn1.close()
             #os.remove(Temp_Dir + "Autopsy_FSEvents-EXCEPTIONS_LOG.txt")		
             #os.remove(Temp_Dir + "Autopsy_FSEvents-Parsed_Records.tsv")
             #os.remove(Temp_Dir + "Autopsy_FSEvents-Parsed_Records_DB.sqlite")
             shutil.rmtree(temp_dir)
        except:
		     self.log(Level.INFO, "removal of MacFSEvents imageinfo database failed " + temp_dir)
   
        # After all databases, post a message to the ingest messages in box.
        message = IngestMessage.createMessage(IngestMessage.MessageType.DATA,
            "MacFSEventsSettings", " MacFSEventsSettings Has Been Analyzed " )
        IngestServices.getInstance().postMessage(message)

        return IngestModule.ProcessResult.OK                
		
   
           
