#This file is part of the bank_ar module for Tryton.
#The COPYRIGHT file at the top level of this repository contains
#the full copyright notices and license terms.
from trytond.pool import Pool
from .citi import *

def register():
    Pool.register(
        CitiStart,
        CitiExportar,
        module='citi_afip', type_='model')
    Pool.register(
        CitiWizard,
        module='citi_afip', type_='wizard')
