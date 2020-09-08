# This file is part of the citi_afip module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from trytond.pool import Pool
from . import citi
from . import pos


def register():
    Pool.register(
        pos.Pos,
        citi.CitiStart,
        citi.CitiExportar,
        module='citi_afip', type_='model')
    Pool.register(
        citi.CitiWizard,
        module='citi_afip', type_='wizard')
