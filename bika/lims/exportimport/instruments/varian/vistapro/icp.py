# -*- coding: utf-8 -*-
""" Varian Vista-PRO ICP
"""
import csv
import logging
from cStringIO import StringIO

from DateTime import DateTime
from Products.CMFCore.utils import getToolByName
from plone.i18n.normalizer.interfaces import IIDNormalizer
from zope.component import getUtility

from bika.lims.browser import BrowserView
from bika.lims.exportimport.instruments.resultsimport import \
    AnalysisResultsImporter, InstrumentResultsFileParser
from bika.lims import bikaMessageFactory as _
from bika.lims.utils import t
import json
import traceback

logger = logging.getLogger(__name__)

title = "Varian Vista-PRO ICP"


class VistaPROICPParser(InstrumentResultsFileParser):
    """ Vista-PRO Parser
    """
    def __init__(self, rsf):
        InstrumentResultsFileParser.__init__(self, rsf, 'CSV')

    def parse(self):
        """ CSV Parser
        """

        reader = csv.DictReader(self.getInputFile(), delimiter=',')

        for n, row in enumerate(reader):

            resid = row['Solution Label'].split('*')[0].strip()

            # Service Keyword
            element = row.get("Element", "").replace(" ", "").replace(".", "")

            # Date and Time parsing
            date_string = "{Date} {Time}".format(**row)
            date_time = DateTime(date_string)

            rawdict = row
            rawdict['DateTime'] = date_time
            rawdict['DefaultResult'] = 'Soln Conc'

            self._addRawResult(resid, values={element: rawdict}, override=False)

        self.log(
            "End of file reached successfully: ${total_objects} objects, "
            "${total_analyses} analyses, ${total_results} results",
            mapping={"total_objects": self.getObjectsTotalCount(),
                     "total_analyses": self.getAnalysesTotalCount(),
                     "total_results": self.getResultsTotalCount()}
        )

        return True


class VistaPROICPImporter(AnalysisResultsImporter):
    """ Importer
    """

    def __init__(self, parser, context, idsearchcriteria, override,
                 allowed_ar_states=None, allowed_analysis_states=None,
                 instrument_uid=None):

        AnalysisResultsImporter.__init__(self,
                                         parser,
                                         context,
                                         idsearchcriteria,
                                         override,
                                         allowed_ar_states,
                                         allowed_analysis_states,
                                         instrument_uid)


def Import(context, request):
    """ Import Form
    """
    infile = request.form['varian_vistapro_icp_file']
    fileformat = request.form['varian_vistapro_icp_format']
    artoapply = request.form['varian_vistapro_icp_artoapply']
    override = request.form['varian_vistapro_icp_override']
    sample = request.form.get('varian_vistapro_icp_sample', 'requestid')
    instrument = request.form.get('varian_vistapro_icp_instrument', None)
    errors = []
    logs = []
    warns = []

    # Load the most suitable parser according to file extension/options/etc...
    parser = None
    if not hasattr(infile, 'filename'):
        errors.append(_("No file selected"))
    if fileformat == 'csv':
        parser = VistaPROICPParser(infile)
    else:
        errors.append(t(_("Unrecognized file format ${fileformat}",
                          mapping={"fileformat": fileformat})))

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
        if sample == 'requestid':
            sam = ['getRequestID']
        if sample == 'sampleid':
            sam = ['getSampleID']
        elif sample == 'clientsid':
            sam = ['getClientSampleID']
        elif sample == 'sample_clientsid':
            sam = ['getSampleID', 'getClientSampleID']

        importer = VistaPROICPImporter(parser=parser,
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


class Export(BrowserView):
    """ Writes worksheet analyses to a CSV file for Varian Vista Pro ICP.
        Sends the CSV file to the response for download by the browser.
    """

    def __init__(self, context, request):
        self.context = context
        self.request = request

    def __call__(self, analyses):
        uc = getToolByName(self.context, 'uid_catalog')
        instrument = self.context.getInstrument()
        norm = getUtility(IIDNormalizer).normalize
        # We use ".sin" extension, but really it's just a little CSV inside.
        filename = '{}-{}.sin'.format(self.context.getId(),
                                      norm(instrument.getDataInterface()))

        # write rows, one per Sample, including including refs and duplicates.
        # COL A:  "sample-id*sampletype-title"  (yes that's a '*').
        # COL B:  "                    ",
        # COL C:  "                    ",
        # COL D:  "                    ",
        # COL E:  1.000000000,
        # COL F:  1.000000,
        # COL G:  1.0000000
        # If routine analysis, COL B is the AR ID + sample type.
        # If Reference analysis, COL B is the Ref Sample.
        # If Duplicate analysis, COL B is the Worksheet.
        lyt = self.context.getLayout()
        lyt.sort(cmp=lambda x, y: cmp(int(x['position']), int(y['position'])))
        rows = []

        # These are always the same on each row
        b = '"                    "'
        c = '"                    "'
        d = '"                    "'
        e = '1.000000000'
        f = '1.000000'
        g = '1.0000000'

        result = ''
        # We don't want to include every single slot!  Just one entry
        # per AR, Duplicate, or Control.
        used_ids = []
        for x, row in enumerate(lyt):
            a_uid = row['analysis_uid']
            c_uid = row['container_uid']
            analysis = uc(UID=a_uid)[0].getObject() if a_uid else None
            container = uc(UID=c_uid)[0].getObject() if c_uid else None
            if row['type'] == 'a':
                if 'a{}'.format(container.id) in used_ids:
                    continue
                used_ids.append('a{}'.format(container.id))
                sample = container.getSample()
                samplepoint = sample.getSamplePoint()
                sp_title = samplepoint.Title() if samplepoint else ''
                a = '"{}*{}"'.format(container.id, sp_title)
            elif row['type'] in 'bcd':
                refgid = analysis.getReferenceAnalysesGroupID()
                if 'bcd{}'.format(refgid) in used_ids:
                    continue
                used_ids.append('bcd{}'.format(refgid))
                a = refgid
            rows.append(','.join([a, b, c, d, e, f, g]))
        result += '\r\n'.join(rows)

        # stream to browser
        setheader = self.request.RESPONSE.setHeader
        setheader('Content-Length', len(result))
        setheader('Content-Type', 'text/comma-separated-values')
        setheader('Content-Disposition', 'inline; filename=%s' % filename)
        self.request.RESPONSE.write(result)
