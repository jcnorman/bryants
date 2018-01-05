#zip.py - get city/state from zip code
# JCNorman 4/29/2015

from xml.dom import Node, minidom
from xml.dom.minidom import *
import requests

__all__ = ['Zip']

class Zip():

    def gettext(self, nodeList):
        retlist = []

        for node in nodeList:
            if node.nodeType == Node.TEXT_NODE:
                retlist.append(node.wholeText)
            elif node.hasChildNodes:
                retlist.append(self.gettext(node.childNodes))
        print 'retlist', retlist
        return retlist

    def handleresponse(self, node):
#        return self.gettext(node)
        retlist = []
        for child in node.childNodes:
            if node.nodeType == Node.TEXT_NODE:
                retlist.append(node.wholeText)
            elif node.hasChildNodes:
                retlist.append(self.gettext(node.childNodes))
            return retlist

def getzip(self, zipcode):
    reqxml = '<CityStateLookupRequest USERID="161THEFA4286"><ZipCode ID="0"><Zip5>' + zipcode + '</Zip5></ZipCode></CityStateLookupRequest>'
    resp = requests.get('http://production.shippingapis.com/ShippingAPI.dll?API=CityStateLookup&XML=' + reqxml)
    resdom = []
    doc = minidom.parseString(resp.text)
    scanr = Zip()
    for child in doc.childNodes:
        if child.nodeType == Node.ELEMENT_NODE and child.tagName == 'CityStateLookupResponse':
            resdom = scanr.handleresponse(child)
    while len(resdom) == 1:
        resdom = resdom[0]
    zip = resdom[0][0]
    city = resdom[1][0].title()
    state = resdom[2][0]
    return {
        'city': city,
        'state': state,
        'zipcode': zip
    }
