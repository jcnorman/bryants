__author__ = 'jcnorman'

from trytond.model import fields
from trytond.pool import PoolMeta

__all__ = ['Sale']
__metaclass__ = PoolMeta

class Sale:

    __name__ = 'sale.sale'

    quotation = fields.Many2One('quotation.master', "Quote",
                            ondelete="CASCADE", select=True,
                            depends=['state', 'reference'])
    quote_date = fields.Date('Quote Date')

