# -*- coding: utf-8 -*-
# This file is part of the account_invoice_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from trytond.model import fields
from trytond.pool import PoolMeta

__all__ = ['Pos']


class Pos(metaclass=PoolMeta):
    __name__ = 'account.pos'
    pos_do_not_report = fields.Boolean('Do not report')

    @staticmethod
    def default_pos_do_not_report():
        return False
