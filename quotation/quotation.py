__author__ = 'jcnorman'

from trytond.pool import PoolMeta, Pool
from trytond.model import ModelView, ModelSQL, Workflow, fields
from decimal import *
from trytond.pyson import If, Eval
from trytond.transaction import Transaction

import datetime

__all__ = ['QuotationMaster', 'Quotation']
__metaclass__ = PoolMeta

STATES = {
    'readonly': ~Eval('active', True),
}
DEPENDS = ['active']


class QuotationMaster(Workflow, ModelSQL, ModelView):
    """Quote Master record"""
    __name__ = 'quotation.master'
    _rec_name = 'reference'

    reference = fields.Char('Reference', select=True)
    company = fields.Many2One('company.company', 'Company', required=True,
                              states={
                                  'readonly': (Eval('state') != 'draft'),
                              },
                              domain=[
                                  ('id', If(Eval('context', {}).contains('company'), '=', '!='),
                                   Eval('context', {}).get('company', -1)),
                              ],
                              depends=['state'], select=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('quotation', 'Quotation'),
        ('confirmed', 'Confirmed'),
        ('cancel', 'Canceled'),
    ], 'State', readonly=True, required=True)
    # lines = fields.One2Many('quotation.quotation', 'quotation', 'Lines',
    #        depends=['party'])
    payment_term = fields.Many2One('account.invoice.payment_term',
                                   'Payment Term', required=True,
                                   depends=['state'])
    payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('credit', 'Credit Card'),
        ('check', 'Check'),
    ], 'Payment Method', sort=False
    )
    party = fields.Many2One('party.party', 'Customer', ondelete='RESTRICT', required=True)
    quote_date = fields.Date('Quotation Date', select=True)
    delivery_date = fields.Date('Delivery Date', select=True)
    quote_by = fields.Many2One('res.user', 'Quoted')
    quote_lines = fields.One2Many('quotation.quotation', 'quote_line', 'Quote Lines', states=STATES, depends=DEPENDS)
#    sales = fields.Function(fields.One2Many('sale.sale', None, 'Sales'), 'get_sales')
    invoices = fields.One2Many('account.invoice', 'party', 'Invoices')
    comment = fields.Text('Comment')
    internal_comment = fields.Text('Internal Comment')
    driver_comment = fields.Text('Driver Comment')

    @classmethod
    def __setup__(cls):
        super(QuotationMaster, cls).__setup__()
        cls._order.insert(0, ('quote_date', 'DESC'))
        cls._order.insert(1, ('id', 'DESC'))

        cls._transitions |= set((
            ('draft', 'quotation'),
            ('quotation', 'quotation'),
            ('quotation', 'draft'),
            ('quotation', 'cancel'),
            ('draft', 'cancel'),
            ('cancel', 'draft')
        ))

        cls._buttons.update({
            'draft': {
                'invisible': ~Eval('state').in_(['cancel', 'quotation']),
                'icon': If(Eval('state') == 'cancel', 'tryton-clear',
                           'tryton-go-previous'),
            },
            'quotation': {
                'invisible': Eval('state') != 'draft',
                #                    'readonly': ~Eval('lines', []),
            },
            'cancel': {
                'invisible': ~Eval('state').in_(['draft', 'quotation']),
            },
        })
        # The states where amounts are cached
        cls._states_cached = ['confirmed', 'cancel']

    @classmethod
    def default_quote_date(cls):
        return datetime.date.today()

    @classmethod
    def default_state(cls):
        return "draft"

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @classmethod
    def default_payment_term(cls):
        PaymentTerm = Pool().get('account.invoice.payment_term')
        payment_terms = PaymentTerm.search(cls.payment_term.domain)
        if len(payment_terms) == 1:
            return payment_terms[0].id

    @staticmethod
    def default_payment_method():
        return 'check'

    @staticmethod
    def default_quote_by():
        transaction = Transaction()
        usr = transaction.user
        cursor = Transaction().cursor
        pool = Pool()
        User = pool.get('res.user')
        user = User.__table__()
        ids = cursor.execute(*user.select(user.id, where=user.id == usr))
        childs = cursor.fetchall()
        return childs[0][0]

    @classmethod
    def delete(cls, quotations):
        # Cancel before delete
        cls.cancel(quotations)
        for quotation in quotations:
            if quotation.state != 'cancel':
                cls.raise_user_error('delete_cancel', (quotation.rec_name,))
        super(Quotation, cls).delete(quotations)

    @classmethod
    @ModelView.button
    @Workflow.transition('cancel')
    def cancel(cls, quotations):
        pass

    @classmethod
    @ModelView.button
    @Workflow.transition('draft')
    def draft(cls, quotations):
        pass

    def get_sales(self, name):
        pool = Pool()
        Sale = pool.get('sale.sale')
        cursor = Transaction().cursor
        sale = Sale.__table__()
        cursor.execute(*sale.select(sale.id, where=sale.quotation == self.id))
        childs = cursor.fetchall()
        print childs, self.id, sale, Sale
        if childs:
            childrecs = []
            for i in range(0, len(childs)): childrecs.append(childs[i][0])
            print 'childrecs', childrecs
            return Sale.browse(childrecs)
        else:
            return None

    def get_invoices(self, name):
        print "in get invoices"
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Quotation = pool.get('quotation.master')
        cursor = Transaction().cursor
        invoice = Invoice.__table__()
        quotation = Quotation.__table__()
        print 'before execute'
        ids = cursor.execute(*quotation.join(invoice, condition=(invoice.party == quotation.party)).select(invoice.id, quotation.party))
        print 'before fetch', ids
        childs = cursor.fetchall()
        print childs
        if childs:
            childrecs = []
            for i in range(0, len(childs)):
                print "in loop"
                if childs[i][1] == self.party['id']:
                    childrecs.append(childs[i][0])
            return Invoice.read(childrecs)
        else:
            print "returning []"
            return []

#    @fields.depends('party')
#    def on_change_party(self):
#        self.get_invoices(self)

    def _get_sale_quotation(self):
        """
        Return sale
        """
        pool = Pool()
        Sale = pool.get('sale.sale')
        Journal = pool.get('account.journal')

        journals = Journal.search([
            ('type', '=', 'revenue'),
        ], limit=1)
        if journals:
            journal, = journals
        else:
            journal = None

        return Sale(
            company=self.company,
            journal=journal,
            party=self.party,
            payment_term=self.payment_term,
            state='quotation',
            sale_date=datetime.date.today(),
            quote_date = self.quote_date,
            delivery_date = self.delivery_date,
            comment = self.comment,
            internal_comment = self.internal_comment,
            driver_comment = self.driver_comment,
            quotation=self.id,
            invoice_address=self.party.address_get(type='invoice'),
            shipment_address=self.party.address_get(type='delivery')
        )

    def create_sale(self):
        '''
        Create and return a sale
        '''
        sale = self._get_sale_quotation()
        sale.save()
        print sale
        return sale

    @classmethod
    @ModelView.button
    @Workflow.transition('quotation')
    def quotation(cls, master):
        pool = Pool()
        Master = pool.get('quotation.master')
        Detail = pool.get('quotation.quotation')
        cursor = Transaction().cursor
        detail = Detail.__table__()
        cursor.execute(*detail.select(detail.id, where=detail.quote_line == master[0].id))
        childs = cursor.fetchall()
        if childs:
            amount = Decimal('0')
            sale = master[0].create_sale()
            childrecs = []
            for i in range(0, len(childs)): childrecs.append(childs[i][0])
            quotations = Detail.browse(childrecs)
            for quotation in quotations:
                if quotation.deck_quote:
                    amount = quotation.get_deck_amount(sale)
                    if quotation.deck_steps:
                        amount = amount + quotation.get_steps_amount(sale)
                if quotation.algae_removal:
                    amount = amount + quotation.get_algae_amount(sale)
                if quotation.strip_color:
                    amount = amount + quotation.get_strip_amount(sale)
                if quotation.reapply_solid or quotation.reapply_2_tone:
                    amount = amount + quotation.get_stain_amount(sale)
                if quotation.reapply_2_tone:
                    amount = amount + quotation.get_stain_amount(sale)
                if quotation.sfhome_quote:
                    amount = amount + quotation.get_home_amount(sale)
                if quotation.th_quote:
                    amount = amount + quotation.get_townhouse_amount(sale)
                if quotation.gutter_quote:
                    amount = amount + quotation.get_gutter_amount(sale)
                if quotation.fence_quote:
                    amount = amount + quotation.get_fencing_amount(sale)

class Quotation(Workflow, ModelSQL, ModelView):
    'Quotation'
    __name__ = 'quotation.quotation'
    _rec_name = 'reference'
    reference = fields.Char('Reference')
    quote_line = fields.Many2One('quotation.master', "Quote",
                                 ondelete="CASCADE", select=True,
                                 depends=['state'])
    price_sqft = fields.Function(fields.Numeric('Rate per SqFt', digits=(16, 2)), 'on_change_with_price_sqft')
    rate_concrete = fields.Numeric('Rate per SqFt Concrete', digits=(16, 2))
    rate_step = fields.Numeric('Rate per step', digits=(16, 2))
    deck_length = fields.Numeric('Deck Length (Feet)', digits=(16, 0))
    deck_width = fields.Numeric('Deck Width (Feet)', digits=(16, 0))
    deck_surface = fields.Selection([
        ('wood', 'Wood'),
        ('composite', 'Composite'),
        ('concrete', 'Concrete or Brick'),
    ],
        'Deck Surface',
        sort=False
    )
    deck_steps = fields.Numeric('Steps', digits=(16, 0))
    lattice_height = fields.Numeric('Lattice Height (Feet)', digits=(16, 0),
                                    states={
                                        'invisible': Eval('deck_surface') == 'concrete'
                                    })

    deck_treatment = fields.Selection([
        ('C&S', 'Clean & Seal'),
        ('C', 'Clean Only'),
        ('CCS', 'Clean & Clear Sealant'),
    ],
        'Deck Treatment',
        sort=False)
    algae_removal = fields.Boolean('Algae Removal')
    strip_color = fields.Boolean('Strip Color',
                                 states={
                                     'invisible': Eval('deck_surface') == 'concrete'
                                 })
    reapply_solid = fields.Boolean('Reapply Solid Stain',
                                   states={
                                       'invisible': ((Eval('deck_surface') == 'concrete') | Eval('reapply_2_tone'))
                                   })
    reapply_2_tone = fields.Boolean('Reapply 2 Tone Stain',
                                    states={
                                        'invisible': ((Eval('deck_surface') == 'concrete') | Eval('reapply_solid'))
                                    })
    wax = fields.Boolean('Wax',
                         states={
                             'invisible': Eval('deck_surface') != 'composite'
                         })
    home_sqft = fields.Numeric('Home Sq Ft', digits=(16, 0))
    wood_siding = fields.Boolean('Wood Siding')
    townhouse_unit = fields.Selection([
        ('middle', 'Middle Unit'),
        ('end', 'End Unit'),
    ], 'Townhouse Unit',
        sort=False)
    townhouse_levels = fields.Selection([
        ('two', '2 Levels Front & Back'),
        ('three', '3 Levels Front & Back'),
        ('two/three', '2 Levels Front & 3 Levels Back'),
    ], 'Townhouse Levels',
        sort=False)
    fencing_posts = fields.Integer('Fence Posts')
    fencing_height = fields.Integer('Fence Height (Feet)')
    fencing_sides = fields.Selection([
        ('one', 'One'),
        ('two', 'Two'),
    ], 'Fence Sides')
    fence_sides = fields.Function(fields.Numeric('Sides', digits=(16, 0)), 'on_change_with_fence_sides')
    fencing_treatment = fields.Selection([
        ('C&S', 'Clean & Seal'),
        ('C', 'Clean Only'),
        ('S', 'Seal Only'),
    ], 'Fence Treatment',
        sort=False)
    deck_quote = fields.Boolean("Deck")
    sfhome_quote = fields.Boolean("Detached Home")
    th_quote = fields.Boolean("Townhouse")
    gutter_quote = fields.Boolean("Gutters")
    fence_quote = fields.Boolean("Fencing")
    deck_sqft = fields.Function(fields.Numeric('Deck SqFt', digits=(16, 0)), 'on_change_with_deck_sqft')
    lattice_sqft = fields.Function(fields.Numeric('Lattice SqFt', digits=(16, 0)), 'on_change_with_lattice_sqft')
    algae_amount = fields.Function(fields.Numeric('Algae Amount', digits=(16, 2)), 'on_change_with_algae_removal')
    strip_amount = fields.Function(fields.Numeric('Strip Amount', digits=(16, 2)), 'on_change_with_strip_amount')
    solid_amount = fields.Function(fields.Numeric('Solid Amount', digits=(16, 2)), 'on_change_with_solid_amount')
    tone2_amount = fields.Function(fields.Numeric('2 Tone Amount', digits=(16, 2)), 'on_change_with_tone2_amount')
    wax_amount = fields.Function(fields.Numeric('Wax Amount', digits=(16, 2)), 'on_change_with_wax_amount')
    deck_amount = fields.Function(fields.Numeric('Deck Amount', digits=(16, 2)), 'on_change_with_deck_amount')
    trmt_amount = fields.Function(fields.Numeric('Treatment Amount', digits=(16, 2)), 'on_change_with_trmt_amount')
    home_amount = fields.Function(fields.Numeric('Home Amount', digits=(16, 2)), 'on_change_with_home_amount')
    fencing_sqft = fields.Function(fields.Numeric('Fence SqFt', digits=(16, 2)), 'on_change_with_fencing_sqft')
    fence_amount = fields.Function(fields.Numeric('Fence Amount', digits=(16, 2)), 'on_change_with_fence_amount')


    @classmethod
    def __setup__(cls):
        super(Quotation, cls).__setup__()
        cls._error_messages.update({
            'productNotFound': ('Product not found. %s'),
            'largeHome': (
                'Contact Steve or Michelle for assistance. '),
            'invalidTHLevels': ('Invalid Townhouse Levels. '),
            'missing_account_receivable': ('only2or3 '
                                           'Only 2 or 3 levels accommodated.'),
            'invalidTHUnit': ('Townhouse unit must be Middle or End. '),
            'invalidTreatment': ('Invalid Treatment Choice. '),
            'invalidHome': ('Only Single Family Home or Townhouse allowed '),
        })

    small = 252
    medium = 360
    large = 580

    def on_change_with_deck_sqft(self, sqft):
        pass

    def on_change_with_lattice_sqft(self, sqft):
        pass

    def on_change_with_strip_amount(self, amount):
        pass

    def on_change_with_solid_amount(self, amount):
        pass

    def on_change_with_deck_amount(self, amount):
        pass

    def on_change_with_fencing_sqft(self, sqft):
        pass

    def on_change_with_price_sqft(self, sqft):
        pass

    def on_change_with_tone2_amount(self, amount):
        pass

    def on_change_with_algae_removal(self, amount):
        pass

    def on_change_with_wax_amount(self, amount):
        pass

    def on_change_with_trmt_amount(self, amount):
        pass

    def on_change_with_home_amount(self, amount):
        pass

    def on_change_home_amount(self):
        print self.sfhome_quote, self.deck_quote, amount > Decimal('0')
        if self.deck_quote and amount > Decimal('0'):
            return amount *  Decimal('0.75')

    def on_change_with_fence_amount(self, amount):
        pass

    @classmethod
    def set_reference(cls, quotations):
        '''
        Fill the reference field with the sale sequence
        '''
        pool = Pool()
        Sequence = pool.get('ir.sequence')
        Config = pool.get('sale.configuration')

        config = Config(1)
        for quotation in quotations:
            if quotation.reference:
                continue
            reference = Sequence.get_id(config.quotation_sequence.id)
            cls.write([quotation], {
                'reference': reference,
            })

    @classmethod
    def default_deck_surface(cls):
        return "wood"

    @classmethod
    def default_deck_treatment(cls):
        return "C&S"

    @classmethod
    def default_fencing_treatment(cls):
        return "C&S"

    @classmethod
    def default_fencing_sides(cls):
        return "one"

    @classmethod
    def default_townhouse_unit(cls):
        return "middle"

    @classmethod
    def default_townhouse_levels(cls):
        return "two"

    @fields.depends('party', 'payment_term')
    def on_change_party(self):
        invoice_address = None
        shipment_address = None
        payment_term = None
        if self.party:
            invoice_address = self.party.address_get(type='invoice')
            shipment_address = self.party.address_get(type='delivery')
            if self.party.customer_payment_term:
                payment_term = self.party.customer_payment_term

        changes = {}
        if invoice_address:
            changes['invoice_address'] = invoice_address.id
            changes['invoice_address.rec_name'] = invoice_address.rec_name
        else:
            changes['invoice_address'] = None
        if shipment_address:
            changes['shipment_address'] = shipment_address.id
            changes['shipment_address.rec_name'] = shipment_address.rec_name
        else:
            changes['shipment_address'] = None
        if payment_term:
            changes['payment_term'] = payment_term.id
            changes['payment_term.rec_name'] = payment_term.rec_name
        else:
            changes['payment_term'] = self.default_payment_term()
        return changes

    def on_change_with_fence_sides(self, name=None):
        if self.fencing_sides == "one":
            return Decimal("1")
        else:
            return Decimal("2")

    def error(self, msg, addl):
        self.raise_user_error(msg, addl)

    def on_change_with_lattice_sqft(self, name=None):
        pass

    def deck_sqft(self):
        deck_sqft = (self.deck_length or Decimal('0.0')) * (self.deck_width or Decimal('0.0')) + \
                    (Decimal(6.0) * self.deck_width) + (Decimal(3.0) * self.deck_length)
        return Decimal(round(deck_sqft))

    def lattice_sqft(self):
        lattice_sqft = (self.lattice_height or Decimal('0.0') + \
                        (2.0 * self.deck_width) + self.deck_length)
        return round(lattice_sqft)

    @fields.depends('fencing_posts', 'fencing_height', 'fencing_sides')
    def get_fencing_sqft(self):
        fencing_sqft = Decimal(self.fencing_posts) * Decimal('8.0') * Decimal(self.fencing_height) * Decimal(
            self.fence_sides)
        if self.deck_sqft > 0:
            return fencing_sqft
        else:
            return fencing_sqft - 120

    def build_sale_line(self, sale, product, quantity, amount):
        this_unit_price = round(amount / quantity, 4)
        this_unit_price_dec = Decimal(str(this_unit_price))
        # print product.name, quantity, this_unit_price_dec, amount
        pool = Pool()
        SaleLine = pool.get('sale.line')
        sale_line = SaleLine(
            sale=sale,
            company=self.quote_line.company,
            party=self.quote_line.party,
            payment_term=self.quote_line.payment_term,
            type='line',
            unit=product.default_uom,
            description=product.name,
            quantity=quantity,
            unit_price=this_unit_price_dec,
            product=product,
            quote_amount=amount,
            amount=amount,
        )
        print sale_line
        sale_line.save()

    def build_quote_line(self, master_quotation, quotation, product, quantity, amount):
        this_unit_price = round(amount / quantity, 4)
        this_unit_price_dec = Decimal(str(this_unit_price))
        pool = Pool()
        QuoteLine = pool.get('quotation.line')
        quote_line = QuoteLine(
            quotation=quotation,
            master_quotation=master_quotation,
            type='line',
            unit=product.default_uom,
            description=product.name,
            quantity=quantity,
            unit_price=this_unit_price_dec,
            product=product,
            quote_amount=amount,
            amount=amount,
        )
        quote_line.save()

    def get_amount(self, sale, productcode, quantity=0):
        pool = Pool()
        Product = pool.get('product.product')
        thisproduct = Product.search([
            ('code', '=', productcode),
            ('active', '=', True),
        ], limit=1)
        if thisproduct and thisproduct[0]:
            if thisproduct[0].cost_price < 0:
                amount = (thisproduct[0].list_price * quantity) - thisproduct[0].cost_price
            else:
                amount = thisproduct[0].list_price * quantity
        else:
            self.error('productNotFound', productcode)
        if (productcode[:2] == 'SF' or productcode[:2] == "TH") and self.deck_quote:
            amount = amount * Decimal('0.75')
        self.build_sale_line(sale, thisproduct[0], quantity, amount)
        # self.build_quote_line(master_quotation, quotation, thisproduct[0], quantity, amount)
        return amount

    def get_deck_amount(self, sale):
        sqft = self.deck_sqft()
        if self.deck_surface == 'wood':
            if self.deck_treatment == "C&S":
                return self.get_amount(sale, 'WDCS', sqft)
            elif self.deck_treatment == "C":
                return self.get_amount(sale, 'WDC', sqft)
            else:
                return self.get_amount(sale, 'WDS', sqft)
        elif self.deck_surface == 'composite':
            if self.deck_treatment == "C":
                return self.get_amount(sale, 'CDC', sqft)
            elif self.deck_treatment == "CCS":
                return self.get_amount(sale, 'CDCCS', sqft)
        elif self.deck_surface == 'concrete':
            return self.get_amount(sale, 'concrete', sqft)

    def get_steps_amount(self, sale):
        return self.get_amount(sale, 'STEPS', self.deck_steps)

    def get_strip_amount(self, sale):
        if self.deck_surface == "wood":
            if self.strip_color:
                if self.deck_sqft <= self.small:
                    return self.get_amount(sale, 'STRIPS', 1)
                elif self.deck_sqft <= self.medium:
                    return self.get_amount(sale, 'STRIPM', 1)
                else:
                    return self.get_amount(sale, 'STRIPL', 1)
            else:
                return Decimal('0')
        else:
            return Decimal('0')

    def get_stain_amount(self, sale):
        sqft = self.deck_sqft()
        if self.reapply_2_tone:
            return self.get_amount(sale, 'SOLID2', sqft)
        elif self.reapply_solid:
            return self.get_amount(sale, 'SOLID', sqft)
        else:
            return Decimal('0')

    def get_algae_amount(self, sale):
        sqft = self.deck_sqft()
        if self.algae_removal:
            if self.deck_sqft <= self.small:
                return self.get_amount(sale, 'ALGAES', 1)
            elif self.deck_sqft <= self.medium:
                return self.get_amount(sale, 'ALGAEM', 1)
            else:
                return self.get_amount(sale, 'ALGAEL', 1)
        else:
            return Decimal(0)

    def get_home_amount(self, sale):
        if self.home_sqft > 0:
            amount = Decimal('0')
            if self.home_sqft <= 2500:
                amount =  self.get_amount(sale, 'SF2500', 1)
            elif self.home_sqft <= 3000:
                amount =  self.get_amount(sale, 'SF3000', 1)
            elif self.home_sqft <= 3500:
                amount =  self.get_amount(sale, 'SF3500', 1)
            elif self.home_sqft <= 4000:
                amount =  self.get_amount(sale, 'SF4000', 1)
            elif self.home_sqft <= 4500:
                amount =  self.get_amount(sale, 'SF4500', 1)
            elif self.home_sqft <= 5000:
                amount =  self.get_amount(sale, 'SF5000', 1)
            elif self.home_sqft <= 6000:
                amount =  self.get_amount(sale, 'SF6000', 1)
            else:
                self.error("largeHome", self.home_sqft)
            return amount
        else:
            return Decimal('0')

    def get_townhouse_amount(self, sale):
        amount = Decimal('0')
        if self.townhouse_unit == "Middle":
            if self.townhouse_levels == "2":
                amount =  self.get_amount(sale, "THMID2", 1)
            elif self.townhouse_levels == "3":
                amount =  self.get_amount(sale, "THMID3", 1)
            elif self.townhouse.townhouse_levels == "2/3":
                amount =  self.get_amount(sale, "THMID2/3", 1)
            else:
                self.error("invalidTHLevels", self.townhouse_levels)
        elif self.townhouse_unit == "End":
            if self.townhouse_levels == "2":
                amount =  self.get_amount(sale, "THEND2", 1)
            elif self.townhouse_levels == "3":
                amount =  self.get_amount(sale, "THEND3", 1)
            else:
                self.error("only2or3", self.townhouse_levels)
        else:
            self.error("invalidTHUnit", self.townhouse_unit)
        if amount > 0.00 and self.deck_quote:
            amount = amount * Decimal('0.75')
        return amount

    def get_fencing_amount(self, sale):
        sqft = self.get_fencing_sqft()
        if sqft > 0:
            if self.fencing_treatment == "C&S":
                return self.get_amount(sale, "FENCINGC&S", sqft)
            elif self.fencing_treatment == "C":
                return self.get_amount(sale, "FENCINGC", sqft)
            elif self.fencing_treatment == "S":
                return self.get_amount(sale, "FENCINGS", sqft)
        elif self.home_type == "TH":
            if self.townhouse_unit == "middle":
                if self.fencing_treatment == "C&S":
                    return self.get_amount(sale, "PETHMIDFENCECS", 1)
                elif self.fencing_treatment == "C":
                    return self.get_amount(sale, "PETHMIDfFENCEC", 1)
                elif self.fencing_treatment == "S":
                    return self.get_amount(sale, "PETHMIDfFENCES", 1)
                else:
                    self.error("invalidTreatment", self.fencing_treatment)
            elif self.townhouse_unit == "End":
                if self.fencing_treatment == "C&S":
                    return self.get_amount(sale, "PETHMIDFENCECS", 1)
                elif self.fencing_treatment == "C":
                    return self.get_amount(sale, "PETHMIDFENCEC", 1)
                elif self.fencing_treatment == "S":
                    return self.get_amount(sale, "PETHMIDFENCES", 1)
                else:
                    self.error("invalidTreatment", self.fencing_treatment)
            else:
                self.error("invalidTHUnit", self.townhouse_unit)
        else:
            self.error("invalidHome", self.home_type)

    def get_lattice_amount(self, sale):
        return self.get_amount(sale, "LATTICE", self.lattice_sqft())

    def get_gutter_amount(self, sale):
        return self.get_amount(sale, "GUTTER", 1)

    def get_sale_line(self):
        '''
        Return a list of sale lines for quotation line
        '''
        pool = Pool()
        Uom = pool.get('product.uom')
        Property = pool.get('ir.property')
        SaleLine = pool.get('sale.line')

        sale_line = SaleLine()
        sale_line.type = self.type
        sale_line.description = self.description
        sale_line.note = self.note
        sale_line.origin = self

        rounding = self.unit.rounding if self.unit else 0.01
        sale_line.quantity = Uom.round(self.quantity, rounding)
        if sale_line.quantity <= 0:
            return []

        sale_line.unit = self.unit
        sale_line.product = self.product
        sale_line.unit_price = self.unit_price
        sale_line.taxes = self.taxes
        if self.product:
            sale_line.account = self.product.account_revenue_used
            if not sale_line.account:
                self.raise_user_error('missing_account_revenue', {
                    'sale': self.sale.rec_name,
                    'product': self.product.rec_name,
                })
        else:
            for model in ('product.template', 'product.category'):
                sale_line.account = Property.get('account_revenue', model)
                if sale_line.account:
                    break
            if not sale_line.account:
                self.raise_user_error('missing_account_revenue_property', {
                    'sale': self.sale.rec_name,
                })
        return [sale_line]
