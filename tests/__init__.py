# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

try:
    from trytond.modules.citi_afip.tests.test_citi_afip import suite
except ImportError:
    from .test_citi_afip import suite

__all__ = ['suite']
