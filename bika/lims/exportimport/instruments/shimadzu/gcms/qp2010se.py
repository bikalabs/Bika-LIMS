# This file is part of Bika LIMS
#
# Copyright 2011-2016 by it's authors.
# Some rights reserved. See LICENSE.txt, AUTHORS.txt.

""" Shimadzu's 'GCMS QP2010 SE'
"""
from DateTime import DateTime
from Products.Archetypes.event import ObjectInitializedEvent
from Products.CMFCore.utils import getToolByName
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from bika.lims import bikaMessageFactory as _
from bika.lims.utils import t
from bika.lims import logger
from bika.lims.browser import BrowserView
from bika.lims.idserver import renameAfterCreation
from bika.lims.utils import changeWorkflowState
from bika.lims.utils import tmpID
from cStringIO import StringIO
from datetime import datetime
from operator import itemgetter
from plone.i18n.normalizer.interfaces import IIDNormalizer
from zope.component import getUtility
import csv
import json
import plone
import zope
import zope.event
from bika.lims.exportimport.instruments.resultsimport import InstrumentCSVResultsFileParser,\
    AnalysisResultsImporter
import traceback

title = "Shimadzu - GCMS-QP2010 SE"


def Import(context, request):
    """ Read Shimadzu's GCMS-QP2010 SE analysis results
    """
    form = request.form
    #TODO form['file'] sometimes returns a list
    infile = form['file'][0] if isinstance(form['file'],list) else form['file']
    artoapply = form['artoapply']
    override = form['override']
    sample = form.get('sample', 'requestid')
    instrument = form.get('instrument', None)
    errors = []
    logs = []

    # Load the most suitable parser according to file extension/options/etc...
    parser = None
    if not hasattr(infile, 'filename'):
        errors.append(_("No file selected"))
    parser = MasshunterQuantCSVParser(infile)

    if parser:
        # Load the importer
        status = ['sample_received', 'attachment_due', 'to_be_verified']
        if artoapply == 'received':
            status = ['sample_received']
        elif artoapply == 'received_tobeverified':
            status = ['sample_received', 'attachment_due', 'to_be_verified']

        over = [False, False]
        if override == 'nooverride':
            over = [False, False]
        elif override == 'override':
            over = [True, False]
        elif override == 'overrideempty':
            over = [True, True]

        sam = ['getRequestID', 'getSampleID', 'getClientSampleID']
        if sample =='requestid':
            sam = ['getRequestID']
        if sample == 'sampleid':
            sam = ['getSampleID']
        elif sample == 'clientsid':
            sam = ['getClientSampleID']
        elif sample == 'sample_clientsid':
            sam = ['getSampleID', 'getClientSampleID']

        importer = MasshunterQuantImporter(parser=parser,
                                           context=context,
                                           idsearchcriteria=sam,
                                           allowed_ar_states=status,
                                           allowed_analysis_states=None,
                                           override=over,
                                           instrument_uid=instrument)
        tbex = ''
        try:
            importer.process()
        except:
            tbex = traceback.format_exc()
        errors = importer.errors
        logs = importer.logs
        warns = importer.warns
        if tbex:
            errors.append(tbex)

    results = {'errors': errors, 'log': logs, 'warns': warns}

    return json.dumps(results)


class MasshunterQuantCSVParser(InstrumentCSVResultsFileParser):

    HEADERTABLE_KEY = '[Header]'
    HEADERKEY_FILENAME = 'Data File Name'
    HEADERKEY_OUTPUTDATE = 'Output Date'
    HEADERKEY_OUTPUTTIME = 'Output Time'

    FILEINFORMATION_KEY = '[File Information]'
    FILEINFORMATIONKEY_TYPE = 'Data File'
    FILEINFORMATIONKEY_GENERATED = 'Generated'
    FILEINFORMATIONKEY_GENERATEDBY = 'Generated By'
    FILEINFORMATIONKEY_MODIFIED = 'Modified'
    FILEINFORMATIONKEY_MODIFIEDBY = 'Modified by'

    # TODO: Ask what to do with whether to ignore or add to headers on the sample file
    SAMPLEINFORMATIONTABLE_KEY = '[Sample Information]'
    SAMPLEINFORMATIONKEY_OPERATORNAME = 'Operator Name'
    SAMPLEINFORMATIONKEY_ANALYZED = 'Analyzed'
    SAMPLEINFORMATIONKEY_TYPE = 'Type'
    SAMPLEINFORMATIONKEY_LEVEL = 'Level'
    SAMPLEINFORMATIONKEY_SAMPLENAME = 'Sample Name'
    SAMPLEINFORMATIONKEY_SAMPLEID = 'Sample ID'
    SAMPLEINFORMATIONRESULT_SAMPLEAMOUNT = 'Sample Amount'
    SAMPLEINFORMATIONRESULT_DILUTIONFACTOR = 'Dilution Factor'


    ORIGINALFILESTABLE_KEY = '[Original Files]'
    ORIGINALFILESKEY_DATAFILE = 'Data File'
    ORIGINALFILESKEY_METHODFILE = 'Method File'
    ORIGINALFILESKEY_BATCHFILE = 'Batch File'
    ORIGINALFILESKEY_REPORTFORMATFILE = 'Report Format File'
    ORIGINALFILESKEY_TUNINGFILE = 'Tuning File'

    HEADERKEY_OUTPUTDATE = 'Output Date'
    HEADERKEY_OUTPUTTIME = 'Output Time'


    SEQUENCETABLE_HEADER_SAMPLENAME = 'Sample Name'
    SEQUENCETABLE_PRERUN = 'prerunrespchk.d'
    SEQUENCETABLE_MIDRUN = 'mid_respchk.d'
    SEQUENCETABLE_POSTRUN = 'post_respchk.d'
    SEQUENCETABLE_NUMERICHEADERS = ('Inj Vol',)
    QUANTITATIONRESULTS_KEY = 'Quantification Results'
    QUANTITATIONRESULTS_TARGETCOMPOUND = 'Target Compound'
    QUANTITATIONRESULTS_HEADER_DATAFILE = 'Data File'
    QUANTITATIONRESULTS_PRERUN = 'prerunrespchk.d'
    QUANTITATIONRESULTS_MIDRUN = 'mid_respchk.d'
    QUANTITATIONRESULTS_POSTRUN = 'post_respchk.d'
    QUANTITATIONRESULTS_NUMERICHEADERS = ('Resp', 'ISTD Resp', 'Resp Ratio',
                                          'Final Conc', 'Exp Conc', 'Accuracy')
    QUANTITATIONRESULTS_COMPOUNDCOLUMN = 'Compound'
    COMMAS = ','
    SEPERATOR = '\t'

    def __init__(self, csv):
        InstrumentCSVResultsFileParser.__init__(self, csv)
        self._end_header = False
        self._end_sampleinformationtable = False 
        self._sampleinformationresults = [] 
        self._sampleinformation = []

        self._quantitationresultsheader = []
        self._sampleinformationheader = []
        self._numline = 0

    def getAttachmentFileType(self):
        return "Agilent's Masshunter Quant CSV"

    def _parseline(self, line):
        if self._end_header == False:
            return self.parse_headerline(line)
        elif self._end_sampleinformationtable == False:
            return self.parse_sampleinformationtableline(line)
        else:
            return self.parse_quantitationesultsline(line)

    def parse_headerline(self, line):
        """ Parses header lines

            Header example:
            Batch Info,2013-03-20T07:11:09.9053262-07:00,2013-03-20T07:12:55.5280967-07:00,2013-03-20T07:11:07.1047817-07:00,,,,,,,,,,,,,,
            Batch Data Path,D:\MassHunter\Data\130129\QuantResults\130129LS.batch.bin,,,,,,,,,,,,,,,,
            Analysis Time,3/20/2013 7:11 AM,Analyst Name,Administrator,,,,,,,,,,,,,,
            Report Time,3/20/2013 7:12 AM,Reporter Name,Administrator,,,,,,,,,,,,,,
            Last Calib Update,3/20/2013 7:11 AM,Batch State,Processed,,,,,,,,,,,,,,
            ,,,,,,,,,,,,,,,,,
        """
        if self._end_header == True:
            # Header already processed
            return 0

        if line.startswith(self.SAMPLEINFORMATIONTABLE_KEY):
            self._end_header = True
            if len(self._header) == 0:
                self.err("No header found", numline=self._numline)
                return -1
            return 0

        splitted = [token.strip() for token in line.split(',')]

        # [Header]
        if splitted[0] == self.HEADERTABLE_KEY:
            if self.HEADERTABLE_KEY in self._header:
                self.warn("Header [Header] Info already found. Discarding",
                          numline=self._numline, line=line)
                return 0

            self._header[self.HEADERTABLE_KEY] = []
            for i in range(len(splitted) - 1):
                if splitted[i + 1]:
                    self._header[self.HEADERTABLE_KEY].append(splitted[i + 1])

        # Data File Name, C:\GCMSsolution\Data\October\1-16-02249-001_CD_10172016_2.qgd
        elif splitted[0] == self.HEADERKEY_FILENAME:
            if self.HEADERKEY_FILENAME in self._header:
                self.warn("Header File Data Name already found. Discarding",
                          numline=self._numline, line=line)
                return 0;

            if splitted[1]:
                self._header[self.HEADERKEY_FILENAME] = splitted[1]
            else:
                self.warn("File Data Name not found or empty",
                          numline=self._numline, line=line)

        # Output Date	10/18/2016
        elif splitted[0] == self.HEADERKEY_OUTPUTDATE:
            if splitted[1]:
                try:
                    d = datetime.strptime(splitted[1], "%m/%d/%Y")
                    self._header[self.HEADERKEY_OUTPUTDATE] = d
                except ValueError:
                    self.err("Invalid Output Date format",
                             numline=self._numline, line=line)
            else:
                self.warn("Output Date not found or empty",
                          numline=self._numline, line=line)
                d = datetime.strptime(splitted[1], "%m/%d/%Y")

        # Output Time	12:04:11 PM
        elif splitted[0] == self.HEADERKEY_OUTPUTTIME:
            if splitted[1]:
                try:
                    d = datetime.strptime(splitted[1], "%I:%M:%S %p")
                    self._header[self.HEADERKEY_OUTPUTTIME] = d
                except ValueError:
                    self.err("Invalid Output Time format",
                             numline=self._numline, line=line)
            else:
                self.warn("Output Time not found or empty",
                          numline=self._numline, line=line)
                d = datetime.strptime(splitted[1], "%I:%M %p")

        # [File Information]
        if splitted[0] == self.FILEINFORMATION_KEY:
            if self.FILEINFORMATION_KEY in self._header:
                self.warn("Header [Header] Info already found. Discarding",
                          numline=self._numline, line=line)
                return 0

            self._header[self.FILEINFORMATION_KEY] = []
            for i in range(len(splitted) - 1):
                if splitted[i + 1]:
                    self._header[self.FILEINFORMATION_KEY].append(splitted[i + 1])

        # Type \t Data File
        elif splitted[0] == self.FILEINFORMATIONKEY_TYPE:
            if self.FILEINFORMATIONKEY_TYPE in self._header:
                self.warn("Header Type already found. Discarding",
                          numline=self._numline, line=line)
                return 0;

            if splitted[1]:
                self._header[self.FILEINFORMATIONKEY_TYPE] = splitted[1]
            else:
                self.warn("File Data Name not found or empty",
                          numline=self._numline, line=line)

        # Generated 10/17/2016 4:25:40 PM
        elif splitted[0] == self.FILEINFORMATIONKEY_GENERATED:
            if splitted[1]:
                try:
                    d = datetime.strptime(splitted[1], "%m/%d/%Y %I:%M %p")
                    self._header[self.FILEINFORMATIONKEY_GENERATED] = d
                except ValueError:
                    self.err("Invalid Generated Date format",
                             numline=self._numline, line=line)
            else:
                self.warn("Generated Date not found or empty",
                          numline=self._numline, line=line)
                d = datetime.strptime(splitted[1], "%m/%d/%Y")

        # Generated by admin
        elif splitted[0] == self.FILEINFORMATIONKEY_GENERATEDBY:
            if self.FILEINFORMATIONKEY_GENERATEDBY in self._header:
                self.warn("Header Generated by already found. Discarding",
                          numline=self._numline, line=line)
                return 0;

            if splitted[1]:
                self._header[self.FILEINFORMATIONKEY_GENERATEDBY] = splitted[1]
            else:
                self.warn("File Data Name not found or empty",
                          numline=self._numline, line=line)

        # Modified 10/17/2016 4:25:40 PM
        elif splitted[0] == self.FILEINFORMATIONKEY_MODIFIED:
            if splitted[1]:
                try:
                    d = datetime.strptime(splitted[1], "%m/%d/%Y %I:%M %p")
                    self._header[self.FILEINFORMATIONKEY_MODIFIED] = d
                except ValueError:
                    self.err("Invalid Modified Date format",
                             numline=self._numline, line=line)
            else:
                self.warn("Modified Date not found or empty",
                          numline=self._numline, line=line)
                d = datetime.strptime(splitted[1], "%m/%d/%Y")

        # Modified by admin
        elif splitted[0] == self.FILEINFORMATIONKEY_MODIFIEDBY:
            if self.FILEINFORMATIONKEY_MODIFIEDBY in self._header:
                self.warn("Header Modified by already found. Discarding",
                          numline=self._numline, line=line)
                return 0;

            if splitted[1]:
                self._header[self.FILEINFORMATIONKEY_MODIFIEDBY] = splitted[1]
            else:
                self.warn("File Data Name not found or empty",
                          numline=self._numline, line=line)


        if line.startswith(self.QUANTITATIONRESULTS_KEY):
            self._end_header = True
            if len(self._header) == 0:
                self.err("No header found", numline=self._numline)
                return -1
            return 0


        return 0

    def parse_sampleinformationtableline(self, line):
        """ Parses sequence table lines

            Sequence Table example:
        """

        sampleinformationresult = {}
        # Operator Name \t Admin
        if line.startswith(self.SAMPLEINFORMATIONKEY_OPERATORNAME) \
                or line.startswith(self.SAMPLEINFORMATIONKEY_ANALYZED) \
                or line.startswith(self.SAMPLEINFORMATIONKEY_TYPE) \
                or line.startswith(self.SAMPLEINFORMATIONKEY_LEVEL) \
                or line.startswith(self.SAMPLEINFORMATIONKEY_SAMPLENAME) \
                or line.startswith(self.SAMPLEINFORMATIONKEY_SAMPLEID):
            # Nothing to do, continue
            return 0

        # Sample Amount\t 3.2397
        # Dilution factor\t10
        import pdb; pdb.set_trace()
        if line.startswith(self.SAMPLEINFORMATIONRESULT_DILUTIONFACTOR) \
            or line.startswith(self.SAMPLEINFORMATIONRESULT_SAMPLEAMOUNT) \
            or self._end_sampleinformationtable == False:

            splitted = [token.strip() for token in line.split(SEPERATOR)]
            sampleinformationresult[splitted[0]] =  float(splitted[1])
            self._sampleinformationresults.append(sampleinformationresult)
            return 0


        # [Original Files]
        # \t
        if line.startswith(self.ORIGINALFILESTABLE_KEY) \
            or line.startswith(self.SEPERATOR):
            self._end_sampleinformationtable = True
            if len(self._sampleinformationresults) == 0:
                self.err("No Sample Information Table found", linenum=self._numline)
                return -1
            return 0


    def parse_quantitationesultsline(self, line):
        """ Parses quantitation result lines

            Quantitation results example:
            Quantitation Results,,,,,,,,,,,,,,,,,
            Target Compound,25-OH D3+PTAD+MA,,,,,,,,,,,,,,,,
            Data File,Compound,ISTD,Resp,ISTD Resp,Resp Ratio, Final Conc,Exp Conc,Accuracy,,,,,,,,,
            prerunrespchk.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,5816,274638,0.0212,0.9145,,,,,,,,,,,
            DSS_Nist_L1.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,6103,139562,0.0437,1.6912,,,,,,,,,,,
            DSS_Nist_L2.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,11339,135726,0.0835,3.0510,,,,,,,,,,,
            DSS_Nist_L3.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,15871,141710,0.1120,4.0144,,,,,,,,,,,
            mid_respchk.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,4699,242798,0.0194,0.8514,,,,,,,,,,,
            DSS_Nist_L3-r002.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,15659,129490,0.1209,4.3157,,,,,,,,,,,
            UTAK_DS_L1-r001.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,29846,132264,0.2257,7.7965,,,,,,,,,,,
            UTAK_DS_L1-r002.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,28696,141614,0.2026,7.0387,,,,,,,,,,,
            post_respchk.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,5022,231748,0.0217,0.9315,,,,,,,,,,,
            ,,,,,,,,,,,,,,,,,
            Target Compound,25-OH D2+PTAD+MA,,,,,,,,,,,,,,,,
            Data File,Compound,ISTD,Resp,ISTD Resp,Resp Ratio, Final Conc,Exp Conc,Accuracy,,,,,,,,,
            prerunrespchk.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,6222,274638,0.0227,0.8835,,,,,,,,,,,
            DSS_Nist_L1.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,1252,139562,0.0090,0.7909,,,,,,,,,,,
            DSS_Nist_L2.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,3937,135726,0.0290,0.9265,,,,,,,,,,,
            DSS_Nist_L3.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,826,141710,0.0058,0.7697,,,,,,,,,,,
            mid_respchk.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,7864,242798,0.0324,0.9493,,,,,,,,,,,
            DSS_Nist_L3-r002.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,853,129490,0.0066,0.7748,,,,,,,,,,,
            UTAK_DS_L1-r001.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,127496,132264,0.9639,7.1558,,,,,,,,,,,
            UTAK_DS_L1-r002.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,135738,141614,0.9585,7.1201,,,,,,,,,,,
            post_respchk.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,6567,231748,0.0283,0.9219,,,,,,,,,,,
            ,,,,,,,,,,,,,,,,,
        """

        # Quantitation Results,,,,,,,,,,,,,,,,,
        # prerunrespchk.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,5816,274638,0.0212,0.9145,,,,,,,,,,,
        # mid_respchk.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,4699,242798,0.0194,0.8514,,,,,,,,,,,
        # post_respchk.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,6567,231748,0.0283,0.9219,,,,,,,,,,,
        # ,,,,,,,,,,,,,,,,,
        if line.startswith(self.QUANTITATIONRESULTS_KEY) \
            or line.startswith(self.QUANTITATIONRESULTS_PRERUN) \
            or line.startswith(self.QUANTITATIONRESULTS_MIDRUN) \
            or line.startswith(self.QUANTITATIONRESULTS_POSTRUN) \
            or line.startswith(self.COMMAS):

            # Nothing to do, continue
            return 0

        # Data File,Compound,ISTD,Resp,ISTD Resp,Resp Ratio, Final Conc,Exp Conc,Accuracy,,,,,,,,,
        if line.startswith(self.QUANTITATIONRESULTS_HEADER_DATAFILE):
            self._quantitationresultsheader = [token.strip() for token in line.split(',') if token.strip()]
            return 0

        # Target Compound,25-OH D3+PTAD+MA,,,,,,,,,,,,,,,,
        if line.startswith(self.QUANTITATIONRESULTS_TARGETCOMPOUND):
            # New set of Quantitation Results
            splitted = [token.strip() for token in line.split(',')]
            if not splitted[1]:
                self.warn("No Target Compound found",
                          numline=self._numline, line=line)
            return 0

        # DSS_Nist_L1.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,1252,139562,0.0090,0.7909,,,,,,,,,,,
        splitted = [token.strip() for token in line.split(',')]
        quantitation = {}
        for colname in self._quantitationresultsheader:
            quantitation[colname] = ''

        for i in range(len(splitted)):
            token = splitted[i]
            if i < len(self._quantitationresultsheader):
                colname = self._quantitationresultsheader[i]
                if token and colname in self.QUANTITATIONRESULTS_NUMERICHEADERS:
                    try:
                        quantitation[colname] = float(token)
                    except ValueError:
                        self.warn(
                            "No valid number ${token} in column ${index} (${column_name})",
                            mapping={"token": token,
                                     "index": str(i + 1),
                                     "column_name": colname},
                            numline=self._numline, line=line)
                        quantitation[colname] = token
                else:
                    quantitation[colname] = token
            elif token:
                self.err("Orphan value in column ${index} (${token})",
                         mapping={"index": str(i+1),
                                  "token": token},
                         numline=self._numline, line=line)

        if self.QUANTITATIONRESULTS_COMPOUNDCOLUMN in quantitation:
            compound = quantitation[self.QUANTITATIONRESULTS_COMPOUNDCOLUMN]

            # Look for sequence matches and populate rawdata
            datafile = quantitation.get(self.QUANTITATIONRESULTS_HEADER_DATAFILE, '')
            if not datafile:
                self.err("No Data File found for quantitation result",
                         numline=self._numline, line=line)

            else:
                seqs = [sequence for sequence in self._sequences \
                        if sequence.get('Data File', '') == datafile]
                if len(seqs) == 0:
                    self.err("No sample found for quantitative result ${data_file}",
                             mapping={"data_file": datafile},
                             numline=self._numline, line=line)
                elif len(seqs) > 1:
                    self.err("More than one sequence found for quantitative result: ${data_file}",
                             mapping={"data_file": datafile},
                             numline=self._numline, line=line)
                else:
                    objid = seqs[0].get(self.SEQUENCETABLE_HEADER_SAMPLENAME, '')
                    if objid:
                        quantitation['DefaultResult'] = 'Final Conc'
                        quantitation['Remarks'] = _("Autoimport")
                        rows = self.getRawResults().get(objid, [])
                        raw = rows[0] if len(rows) > 0 else {}
                        raw[compound] = quantitation
                        self._addRawResult(objid, raw, True)
                    else:
                        self.err("No valid sequence for ${data_file}",
                                 mapping={"data_file": datafile},
                                 numline=self._numline, line=line)
        else:
            self.err("Value for column '${column}' not found",
                     mapping={"column": self.QUANTITATIONRESULTS_COMPOUNDCOLUMN},
                     numline=self._numline, line=line)


class MasshunterQuantImporter(AnalysisResultsImporter):

    def __init__(self, parser, context, idsearchcriteria, override,
                 allowed_ar_states=None, allowed_analysis_states=None,
                 instrument_uid=''):
        AnalysisResultsImporter.__init__(self, parser, context, idsearchcriteria,
                                         override, allowed_ar_states,
                                         allowed_analysis_states,
                                         instrument_uid)
