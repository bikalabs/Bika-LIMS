from AccessControl import ClassSecurityInfo
from Products.Archetypes.public import BaseContent
from Products.Archetypes.public import registerType
from zope.interface import implements

from bika.lims.content.bikaschema import BikaSchema
from bika.lims.config import PROJECTNAME
from bika.lims.interfaces import IBikaSetupType

schema = BikaSchema.copy()
schema['description'].widget.visible = False
schema['description'].schemata = 'default'

class BatchLabel(BaseContent):
    implements(IBikaSetupType)
    security = ClassSecurityInfo()
    displayContentsTab = False
    schema = schema

    _at_rename_after_creation = True
    def _renameAfterCreation(self, check_auto_id=False):
        from bika.lims.idserver import renameAfterCreation
        renameAfterCreation(self)

registerType(BatchLabel, PROJECTNAME)

