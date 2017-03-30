# -*- coding: utf-8 -*-

from bika.lims.jsonapi import url_for
from bika.lims.jsonapi import add_route

from bika.lims.jsonapi.v2 import __version__
from bika.lims.jsonapi.v2 import __build__
from bika.lims.jsonapi.v2 import __date__


@add_route("/v2/version", "bika.lims.jsonapi.v2.version", methods=["GET"])
def version(context, request):
    """get the version, build number and date of this API
    """
    return {
        "url":     url_for("bika.lims.jsonapi.v2.version"),
        "version": __version__,
        "build":   __build__,
        "date":    __date__,
    }
