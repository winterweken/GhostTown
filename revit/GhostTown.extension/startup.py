# -*- coding: utf-8 -*-
"""Ghost Town for Revit: registers the `ghosttown` Routes API when pyRevit loads.

    GET  /ghosttown/status   the Revit version and the open document, if any
    POST /ghosttown/site     a site from Ghost Town's Send to Revit (JSON), drawn as native elements

Routes must be turned on in pyRevit's settings (it is off by default) and listens on port 48884. It has no
authentication, so it must listen on 127.0.0.1 only, where Blender on this computer reaches it: README.md says
how to pin it there.
"""
import os
import sys

try:
    _LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
    if _LIB not in sys.path:
        sys.path.insert(0, _LIB)
except NameError:      # no __file__: pyRevit's own search path has the extension's lib folder
    pass

from pyrevit import routes  # noqa: E402

from ghosttown_revit import site as gs  # noqa: E402

api = routes.API("ghosttown")


@api.route("/status", methods=["GET"])
def status(uiapp):
    """Taking uiapp makes pyRevit run this on Revit's main thread, where the API may be read."""
    app = uiapp.Application
    uidoc = uiapp.ActiveUIDocument
    document = uidoc.Document if uidoc is not None else None
    return {"ok": True, "format": gs.FORMAT, "revit": app.VersionNumber, "build": app.VersionBuild,
            "document": document.Title if document is not None else None,
            "project": bool(document is not None and not document.IsFamilyDocument)}


@api.route("/site", methods=["POST"])
def site(doc, request):
    """Taking doc makes pyRevit run this through an ExternalEvent, inside Revit's API context. pyRevit
    parses a JSON body into request.data when the Content-Type is application/json."""
    try:
        from ghosttown_revit import draw   # imported here: a fault in it must not stop the status route loading
    except Exception as e:  # noqa: BLE001 - the answer says why, rather than pyRevit's bare 500
        return gs.Answer().fatal(u"Ghost Town's Revit extension couldn't load its drawing code: %s" % (e,))
    return draw.handle(doc, request.data)
