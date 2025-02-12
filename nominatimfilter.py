# -*- coding: utf-8 -*-

from qgis.core import Qgis, QgsMessageLog, QgsLocatorFilter, QgsLocatorResult, QgsRectangle, \
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsBlockingNetworkRequest

from qgis.PyQt.QtCore import pyqtSignal, QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

import json


class NominatimFilterPlugin:

    def __init__(self, iface):

        self.iface = iface

        self.filter = NominatimLocatorFilter(self.iface)

        # THIS is not working?? As in show_problem never called
        self.filter.resultProblem.connect(self.show_problem)
        self.iface.registerLocatorFilter(self.filter)

    def show_problem(self, err):
        self.filter.info("showing problem???")  # never come here?
        self.iface.messageBar().pushWarning("NominatimLocatorFilter Error", '{}'.format(err))

    def initGui(self):
        pass

    def unload(self):
        self.iface.deregisterLocatorFilter(self.filter)
        #self.filter.resultProblem.disconnect(self.show_problem)


# SEE: https://github.com/qgis/QGIS/blob/master/src/core/locator/qgslocatorfilter.h
#      for all attributes/members/functions to be implemented
class NominatimLocatorFilter(QgsLocatorFilter):

    USER_AGENT = b'Mozilla/5.0 QGIS NominatimLocatorFilter'

    SEARCH_URL = 'https://nominatim.openstreetmap.org/search?format=json&q='
    # test url to be able to force errors
    #SEARCH_URL = 'http://duif.net/cgi-bin/qlocatorcheck.cgi?q='

    # some magic numbers to be able to zoom to more or less defined levels
    ADDRESS = 1000
    STREET = 1500
    ZIP = 3000
    PLACE = 30000
    CITY = 120000
    ISLAND = 250000
    COUNTRY = 4000000

    resultProblem = pyqtSignal(str)

    def __init__(self, iface):
        # you REALLY REALLY have to save the handle to iface, else segfaults!!
        self.iface = iface
        super(QgsLocatorFilter, self).__init__()

    def name(self):
        return self.__class__.__name__

    def clone(self):
        return NominatimLocatorFilter(self.iface)

    def displayName(self):
        return 'Nominatim Geocoder (end with space to search)'

    def prefix(self):
        return 'osm'

    def fetchResults(self, search, context, feedback):

        if len(search) < 2:
            return

        # see https://operations.osmfoundation.org/policies/nominatim/
        # "Auto-complete search This is not yet supported by Nominatim and you must not implement such a service on the client side using the API."
        # so end with a space to trigger a search:
        if search[-1] != ' ':
            return

        url = '{}{}'.format(self.SEARCH_URL, search)
        self.info('Search url {}'.format(url))
        try:
            # see https://operations.osmfoundation.org/policies/nominatim/
            # "Pro4 vide a valid HTTP Referer or User-Agent identifying the application (QGIS geocoder)"
            # TODO
            #headers = {b'User-Agent': self.USER_AGENT}

            # nam = Network Access Manager
            nam = QgsBlockingNetworkRequest()
            request = QNetworkRequest(QUrl(url))
            request.setHeader(QNetworkRequest.UserAgentHeader, self.USER_AGENT)
            nam.get(request, forceRefresh=True)
            reply = nam.reply()
            if reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) == 200:  # other codes are handled by NetworkAccessManager
                content_string = reply.content().data().decode('utf8')
                locations = json.loads(content_string)
                for loc in locations:
                    result = QgsLocatorResult()
                    result.filter = self
                    result.displayString = '{} ({})'.format(loc['display_name'], loc['type'])
                    # use the json full item as userData, so all info is in it:
                    result.userData = loc
                    self.resultFetched.emit(result)

        except Exception as err:
            # Handle exception..
            # only this one seems to work
            self.info(err)

    def triggerResult(self, result):
        self.info("UserClick: {}".format(result.displayString))
        # Newer Version of PyQT does not expose the .userData (Leading to core dump)
        # Try via get Function, otherwise access attribute
        try:
            doc = result.getUserData()
        except:
            doc = result.userData
        extent = doc['boundingbox']
        # "boundingbox": ["52.641015", "52.641115", "5.6737302", "5.6738302"]
        rect = QgsRectangle(float(extent[2]), float(extent[0]), float(extent[3]), float(extent[1]))
        dest_crs = QgsProject.instance().crs()
        results_crs = QgsCoordinateReferenceSystem.fromEpsgId(4326)
        transform = QgsCoordinateTransform(results_crs, dest_crs, QgsProject.instance())
        r = transform.transformBoundingBox(rect)
        self.iface.mapCanvas().setExtent(r, False)
        # sometimes Nominatim has result with very tiny boundingboxes, let's set a minimum
        if self.iface.mapCanvas().scale() < 500:
            self.iface.mapCanvas().zoomScale(500)
        self.iface.mapCanvas().refresh()

    def info(self, msg=""):
        QgsMessageLog.logMessage('{} {}'.format(self.__class__.__name__, msg), 'NominatimLocatorFilter', Qgis.Info)
