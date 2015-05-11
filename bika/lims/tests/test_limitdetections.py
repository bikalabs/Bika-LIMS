from bika.lims import logger
from bika.lims.content.analysis import Analysis
from bika.lims.testing import BIKA_FUNCTIONAL_TESTING
from bika.lims.tests.base import BikaFunctionalTestCase
from bika.lims.utils.analysisrequest import create_analysisrequest
from bika.lims.workflow import doActionFor
from plone.app.testing import login, logout
from plone.app.testing import TEST_USER_NAME
import unittest

try:
    import unittest2 as unittest
except ImportError: # Python 2.7
    import unittest


class TestLimitDetections(BikaFunctionalTestCase):
    layer = BIKA_FUNCTIONAL_TESTING

    def setUp(self):
        super(TestLimitDetections, self).setUp()
        login(self.portal, TEST_USER_NAME)
        servs = self.portal.bika_setup.bika_analysisservices
        # analysis-service-3: Calcium (Ca)
        # analysis-service-6: Cooper (Cu)
        # analysis-service-7: Iron (Fe)
        self.services = [servs['analysisservice-3'],
                         servs['analysisservice-6'],
                         servs['analysisservice-7']]
        self.lds = [{'min': '0.0',  'max': '1000.0', 'manual': False},
                    {'min': '10.0', 'max': '20.0',   'manual': True},
                    {'min': '0.0',  'max': '20.0',   'manual': True}]
        idx = 0
        for s in self.services:
            s.setAllowManualDetectionLimit(self.lds[idx]['manual'])
            s.setLowerDetectionLimit(self.lds[idx]['min'])
            s.setUpperDetectionLimit(self.lds[idx]['max'])
            idx+=1

    def tearDown(self):
        for s in self.services:
            s.setAllowManualDetectionLimit(False)
            s.setLowerDetectionLimit(str(0))
            s.setUpperDetectionLimit(str(1000))
        logout()
        super(TestLimitDetections, self).tearDown()

    def test_ar_manageresults_limitdetections(self):
        # Input results
        # Client:       Happy Hills
        # SampleType:   Apple Pulp
        # Contact:      Rita Mohale
        # Analyses:     [Calcium, Copper]
        client = self.portal.clients['client-1']
        sampletype = self.portal.bika_setup.bika_sampletypes['sampletype-1']
        values = {'Client': client.UID(),
                  'Contact': client.getContacts()[0].UID(),
                  'SamplingDate': '2015-01-01',
                  'SampleType': sampletype.UID()}
        request = {}
        services = [s.UID() for s in self.services]
        ar = create_analysisrequest(client, request, values, services)

        # Basic detection limits
        asidxs = {'analysisservice-3': 0,
                  'analysisservice-6': 1,
                  'analysisservice-7': 2}
        for a in ar.getAnalyses():
            an = a.getObject()
            idx = asidxs[an.getService().id]
            self.assertEqual(an.getLowerDetectionLimit(), float(self.lds[idx]['min']))
            self.assertEqual(an.getUpperDetectionLimit(), float(self.lds[idx]['max']))
            self.assertEqual(an.getService().getAllowManualDetectionLimit(), self.lds[idx]['manual'])

            # Empty result
            self.assertFalse(an.getDetectionLimitOperand())
            self.assertFalse(an.isBelowLowerDetectionLimit())
            self.assertFalse(an.isAboveUpperDetectionLimit())

            # Set a result
            an.setResult('15')
            self.assertEqual(float(an.getResult()), 15)
            self.assertFalse(an.isBelowLowerDetectionLimit())
            self.assertFalse(an.isAboveUpperDetectionLimit())
            self.assertFalse(an.getDetectionLimitOperand())
            self.assertEqual(an.getFormattedResult(), '15')
            an.setResult('-1')
            self.assertEqual(float(an.getResult()), -1)
            self.assertTrue(an.isBelowLowerDetectionLimit())
            self.assertFalse(an.isAboveUpperDetectionLimit())
            self.assertFalse(an.getDetectionLimitOperand())
            self.assertEqual(an.getFormattedResult(), '< %s' % (self.lds[idx]['min']))
            an.setResult('2000')
            self.assertEqual(float(an.getResult()), 2000)
            self.assertFalse(an.isBelowLowerDetectionLimit())
            self.assertTrue(an.isAboveUpperDetectionLimit())
            self.assertFalse(an.getDetectionLimitOperand())
            self.assertEqual(an.getFormattedResult(), '> %s' % (self.lds[idx]['max']))

            # Set a DL result
            an.setResult('<15')
            self.assertEqual(float(an.getResult()), 15)
            if self.lds[idx]['manual']:
                self.assertTrue(an.isBelowLowerDetectionLimit())
                self.assertFalse(an.isAboveUpperDetectionLimit())
                self.assertEqual(an.getDetectionLimitOperand(), '<')
                self.assertEqual(an.getFormattedResult(), '< 15.0')
            else:
                self.assertFalse(an.isBelowLowerDetectionLimit())
                self.assertFalse(an.isAboveUpperDetectionLimit())
                self.assertFalse(an.getDetectionLimitOperand())
                self.assertEqual(an.getFormattedResult(), '15')

            an.setResult('>15')
            self.assertEqual(float(an.getResult()), 15)
            if self.lds[idx]['manual']:
                self.assertFalse(an.isBelowLowerDetectionLimit())
                self.assertTrue(an.isAboveUpperDetectionLimit())
                self.assertEqual(an.getDetectionLimitOperand(), '>')
                self.assertEqual(an.getFormattedResult(), '> 15.0')
            else:
                self.assertFalse(an.isBelowLowerDetectionLimit())
                self.assertFalse(an.isAboveUpperDetectionLimit())
                self.assertFalse(an.getDetectionLimitOperand())
                self.assertEqual(an.getFormattedResult(), '15')

            # Set a DL result explicitely
            an.setDetectionLimitOperand('<')
            an.setResult('15')
            self.assertEqual(float(an.getResult()), 15)
            if self.lds[idx]['manual']:
                self.assertTrue(an.isBelowLowerDetectionLimit())
                self.assertFalse(an.isAboveUpperDetectionLimit())
                self.assertEqual(an.getDetectionLimitOperand(), '<')
                self.assertEqual(an.getFormattedResult(), '< 15.0')
            else:
                self.assertFalse(an.isBelowLowerDetectionLimit())
                self.assertFalse(an.isAboveUpperDetectionLimit())
                self.assertFalse(an.getDetectionLimitOperand())
                self.assertEqual(an.getFormattedResult(), '15')

            an.setDetectionLimitOperand('>')
            an.setResult('15')
            self.assertEqual(float(an.getResult()), 15)
            if self.lds[idx]['manual']:
                self.assertFalse(an.isBelowLowerDetectionLimit())
                self.assertTrue(an.isAboveUpperDetectionLimit())
                self.assertEqual(an.getDetectionLimitOperand(), '>')
                self.assertEqual(an.getFormattedResult(), '> 15.0')
            else:
                self.assertFalse(an.isBelowLowerDetectionLimit())
                self.assertFalse(an.isAboveUpperDetectionLimit())
                self.assertFalse(an.getDetectionLimitOperand())
                self.assertEqual(an.getFormattedResult(), '15')


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestLimitDetections))
    suite.layer = BIKA_FUNCTIONAL_TESTING
    return suite
