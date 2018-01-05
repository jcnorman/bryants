__author__ = 'jcnorman'

from trytond.pool import Pool
from .quotation import *

def register():
    Pool.register(
        QuotationMaster,
        Quotation,
        module='quotation', type_='model')
