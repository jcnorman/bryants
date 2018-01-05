#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
'Address'
from trytond.model import ModelView, ModelSQL, fields
from trytond.pyson import Eval, If
from trytond.transaction import Transaction
from trytond import backend
from trytond.pool import Pool
from xml.dom import Node, minidom
from xml.dom.minidom import *
import requests


__all__ = ['Address', 'Zip']

STATES = {
    'readonly': ~Eval('active'),
    }
DEPENDS = ['active']


class Address(ModelSQL, ModelView):
    "Address"
    __name__ = 'party.address'
    party = fields.Many2One('party.party', 'Party', required=True,
        ondelete='CASCADE', select=True, states={
            'readonly': If(~Eval('active'), True, Eval('id', 0) > 0),
            },
        depends=['active', 'id'])
    name = fields.Char('Name', states=STATES, depends=DEPENDS)
    street = fields.Char('Street', states=STATES, depends=DEPENDS)
    streetbis = fields.Char('Street (bis)', states=STATES, depends=DEPENDS)
    zip = fields.Char('Zip', states=STATES, depends=DEPENDS)
    city = fields.Char('City', states=STATES, depends=DEPENDS)
    country = fields.Many2One('country.country', 'Country',
        states=STATES, depends=DEPENDS, select=True)
#    subdivision = fields.Many2One("country.subdivision",
#            'State', domain=[('country', '=', eval('country'))],
#            states=STATES, depends=['active', 'country'], select=True)
    subdivision = fields.Char("State",states=STATES, depends=['active'])
    active = fields.Boolean('Active')
    sequence = fields.Integer("Sequence")
    full_address = fields.Function(fields.Text('Full Address'),
            'get_full_address')

    @classmethod
    def __setup__(cls):
        super(Address, cls).__setup__()
        cls._order.insert(0, ('party', 'ASC'))
        cls._order.insert(1, ('sequence', 'ASC'))
        cls._error_messages.update({
                'write_party': 'You can not modify the party of address "%s".',
                })

    @classmethod
    def __register__(cls, module_name):
        TableHandler = backend.get('TableHandler')
        cursor = Transaction().cursor
        table = TableHandler(cursor, cls, module_name)

        super(Address, cls).__register__(module_name)

        # Migration from 2.4: drop required on sequence
        table.not_null_action('sequence', action='remove')

    @staticmethod
    def order_sequence(tables):
        table, _ = tables[None]
        return [table.sequence == None, table.sequence]

    @staticmethod
    def default_active():
        return True

    @staticmethod
    def default_country():
        return 61

#    @staticmethod
#    def default_subdivision():
#        return 3551

    _autocomplete_limit = 100

    def _autocomplete_domain(self):
        domain = []
        if self.country:
            domain.append(('country', '=', self.country.id))
#        if self.subdivision:
#            domain.append(['OR',
#                    ('subdivision', '=', self.subdivision.id),
#                    ('subdivision', '=', None),
#                    ])
        return domain

    def _autocomplete_search(self, domain, name):
        pool = Pool()
        Zip = pool.get('country.zip')
        if domain:
            records = Zip.search(domain, limit=self._autocomplete_limit)
            if len(records) < self._autocomplete_limit:
                return sorted({getattr(z, name) for z in records})
        return []

    @fields.depends('city', 'country', 'subdivision')
    def autocomplete_zip(self):
        domain = self._autocomplete_domain()
        if self.city:
            domain.append(('city', 'ilike', '%%%s%%' % self.city))
        return self._autocomplete_search(domain, 'zip')

    @fields.depends('zip', 'country', 'subdivision')
    def autocomplete_city(self):
        domain = self._autocomplete_domain()
        if self.zip:
            domain.append(('zip', 'ilike', '%s%%' % self.zip))
        return self._autocomplete_search(domain, 'city')

    def get_full_address(self, name):
        full_address = ''
        if self.name:
            full_address = self.name
        if self.street:
            if full_address:
                full_address += '\n'
            full_address += self.street
        if self.streetbis:
            if full_address:
                full_address += '\n'
            full_address += self.streetbis
        if self.zip or self.city:
            if full_address:
                full_address += '\n'
            if self.city:
                if full_address[-1:] != '\n':
                    full_address += ' '
                full_address += self.city
                if full_address[-1:] != '\n':
                    full_address += ' '
                if self.subdivision:
                    full_address += self.subdivision #.name
                if full_address[-1:] != '\n':
                    full_address += ' '
                if self.zip:
                    full_address += self.zip
        return full_address

    def get_rec_name(self, name):
        return ", ".join(x for x in [self.name,
                self.party.rec_name, self.zip, self.city] if x)

    @classmethod
    def search_rec_name(cls, name, clause):
        return ['OR',
            ('zip',) + tuple(clause[1:]),
            ('city',) + tuple(clause[1:]),
            ('name',) + tuple(clause[1:]),
            ('party',) + tuple(clause[1:]),
            ]

    @classmethod
    def write(cls, *args):
        actions = iter(args)
        for addresses, values in zip(actions, actions):
            if 'party' in values:
                for address in addresses:
                    if address.party.id != values['party']:
                        cls.raise_user_error('write_party', (address.rec_name,))
        super(Address, cls).write(*args)

    @fields.depends('zip')
    def on_change_zip(self):
        print 'in zip change'
        zipcode = Zip()
        addr = zipcode.getzip(zipcode, self.zip)
        searchstr = 'US-' + addr['subdivision']
        print 'addr', addr, searchstr, addr['city']
        self.city = addr['city']
        self.subdivision = addr['subdivision']
        print self, self.city, self.subdivision
        return addr

class Zip():
    'Zipcode lookup'
    __name__ = 'address.zip'

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

    def getzip(self, zipinst, zipcode):
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
            'subdivision': state,
            'zipcode': zip
        }
