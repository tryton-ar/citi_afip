#! -*- coding: utf8 -*-
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

from trytond.wizard import Wizard, StateView, StateTransition, Button
from trytond.model import fields, ModelView
from trytond.pool import Pool
from decimal import Decimal
from pysimplesoap.client import SimpleXMLElement
from unidecode import unidecode
import logging
logger = logging.getLogger(__name__)

__all__ = ['CitiExportar', 'CitiStart', 'CitiWizard']

TABLA_MONEDAS = {
    'ARS': 'PES',
    'USD': 'DOL',
    'UYU': '011',
    'BRL': '012',
    'DKK': '014',
    'NOK': '015',
    'CAD': '018',
    'CHF': '009',
    'BOB': '031',
    'COP': '032',
    'CLP': '033',
    'HKD': '051',
    'SGD': '052',
    'JMD': '053',
    'TWD': '054',
    'EUR': '060',
    'CNY': '064',
}

ALICUOTAS_IVA = {
    "No Gravado": 1,
    "Exento": 2,
    Decimal('0'): 3,
    Decimal('0.105'): 4,
    Decimal('0.21'): 5,
    Decimal('0.27'): 6,
    Decimal('0.05'): 8,
    Decimal('0.025'): 9,
    Decimal('0.03'): 8,  # IVA RG3337
    Decimal('0.015'): 8,  # IVA RG3337
}

NO_CORRESPONDE = [
    6,
    11,
    7,
    8,
    9,
    10,
    12,
    13,
    15,
    16,
    18,
    25,
    26,
    28,
    35,
    36,
    40,
    41,
    43,
    46,
    61,
    64,
    82,
    83,
    111,
    113,
    114,
    116,
    117,
]

COMPROBANTES_EXCLUIDOS = [
    33,
    99,  # Exceptuados de la RG 1415 - Notas de credito
    90,  # Exceptuados de la RG 1415.
    331,
    332,
]


class CitiStart(ModelView):
    'CITI Start'
    __name__ = 'citi.afip.start'
    csv_format = fields.Boolean('CSV format', help='Check this box if you '
        'want export to csv format.')
    period = fields.Many2One('account.period', 'Period', required=True)
    proration = fields.Boolean('Prorreatear Crédito Fiscal Computable Global')


class CitiExportar(ModelView):
    'Exportar'
    __name__ = 'citi.afip.exportar'
    comprobante_compras = fields.Binary('Comprobante compras', readonly=True,
        filename='REGINFO_CV_COMPRAS_CBTE.TXT')
    alicuota_compras = fields.Binary('Alicuota compras', readonly=True,
        filename='REGINFO_CV_COMPRAS_ALICUOTAS.TXT')
    comprobante_ventas = fields.Binary('Comprobante ventas', readonly=True,
        filename='REGINFO_CV_VENTAS_CBTE.TXT')
    alicuota_ventas = fields.Binary('Alicuota ventas', readonly=True,
        filename='REGINFO_CV_VENTAS_ALICUOTAS.TXT')


class CitiWizard(Wizard):
    'CitiWizard'
    __name__ = 'citi.afip.wizard'

    _EOL = '\r\n'
    _SEPARATOR = ';'

    start = StateView(
        'citi.afip.start',
        'citi_afip.citi_afip_start_view', [
            Button('Cancelar', 'end', 'tryton-cancel'),
            Button('Generar archivos', 'exportar_citi', 'tryton-ok', True),
        ])
    exportar = StateView(
        'citi.afip.exportar',
        'citi_afip.citi_afip_exportar_view', [
            Button('Volver a generar archivos', 'start', 'tryton-ok'),
            Button('Done', 'end', 'tryton-close'),
        ])
    exportar_citi = StateTransition()

    def default_start(self, fields):
        res = {}
        return res

    def default_exportar(self, fields):
        comprobante_compras = self.exportar.comprobante_compras
        alicuota_compras = self.exportar.alicuota_compras
        comprobante_ventas = self.exportar.comprobante_ventas
        alicuota_ventas = self.exportar.alicuota_ventas

        self.exportar.comprobante_compras = False
        self.exportar.alicuota_compras = False
        self.exportar.comprobante_ventas = False
        self.exportar.alicuota_ventas = False

        res = {
            'comprobante_compras': comprobante_compras,
            'alicuota_compras': alicuota_compras,
            'comprobante_ventas': comprobante_ventas,
            'alicuota_ventas': alicuota_ventas,
        }
        return res

    def transition_exportar_citi(self):
        logger.info('exportar CITI REG3685')
        self.exportar.message = ''
        self.export_citi_alicuota_compras()
        self.export_citi_comprobante_compras()
        self.export_citi_alicuota_ventas()
        self.export_citi_comprobante_ventas()

        return 'exportar'

    def export_citi_alicuota_ventas(self):
        logger.info('exportar CITI REG3685 Alicuota Ventas')

        pool = Pool()
        Invoice = pool.get('account.invoice')
        Currency = pool.get('currency.currency')
        invoices = Invoice.search([
            ('state', 'in', ['posted', 'paid']),
            ('type', '=', 'out'),  # Invoice, Credit Note
            ('move.period', '=', self.start.period),
            ('pos.pos_do_not_report', '=', False),
        ], order=[('invoice_date', 'ASC')])
        lines = ""
        for invoice in invoices:
            tipo_comprobante = invoice.invoice_type.invoice_type.rjust(3, '0')
            punto_de_venta = invoice.number.split(
                '-')[0].encode().rjust(5, '0')
            if int(tipo_comprobante) in COMPROBANTES_EXCLUIDOS:
                punto_de_venta = ''.rjust(5, '0')  # se informan ceros.
            if ':' in invoice.number:
                parte_desde = invoice.number.split(':')[0]
                numero_comprobante = parte_desde.split(
                    '-')[1].encode().rjust(20, '0')
            else:
                numero_comprobante = invoice.number.split(
                    '-')[1].encode().rjust(20, '0')

            importe_neto_gravado = Decimal('0')
            impuesto_liquidado = Decimal('0')
            for tax_line in invoice.taxes:
                if (tax_line.tax.group and 'iva' in
                        tax_line.tax.group.code.lower()):
                    alicuota_id = tax_line.base_code.code.rjust(4, '0')
                    importe_neto_gravado = abs(tax_line.base)
                    impuesto_liquidado = abs(tax_line.amount)
                    importe_neto_gravado = Currency.round(invoice.currency,
                        importe_neto_gravado).to_eng_string().replace(
                            '.', '').rjust(15, '0')
                    impuesto_liquidado = Currency.round(invoice.currency,
                        impuesto_liquidado).to_eng_string().replace(
                            '.', '').rjust(15, '0')

                    campos = [tipo_comprobante, punto_de_venta,
                        numero_comprobante, importe_neto_gravado, alicuota_id,
                        impuesto_liquidado]
                    separador = self.start.csv_format and self._SEPARATOR or ''
                    lines += separador.join(campos) + self._EOL

            # factura de exportacion
            # no tiene alicuota, pero se informa con alicuota 0%
            if tipo_comprobante in ['019']:
                alicuota_id = '3'.rjust(4, '0')
                importe_neto_gravado = abs(invoice.total_amount)
                impuesto_liquidado = Decimal('0')
                importe_neto_gravado = Currency.round(invoice.currency,
                    importe_neto_gravado).to_eng_string().replace(
                        '.', '').rjust(15, '0')
                impuesto_liquidado = Currency.round(invoice.currency,
                    impuesto_liquidado).to_eng_string().replace(
                        '.', '').rjust(15, '0')
                campos = [tipo_comprobante, punto_de_venta,
                    numero_comprobante, importe_neto_gravado, alicuota_id,
                    impuesto_liquidado]
                separador = self.start.csv_format and self._SEPARATOR or ''
                lines += separador.join(campos) + self._EOL

        logger.info('Comienza attach alicuota de venta')

        self.exportar.alicuota_ventas = str(
            lines).encode('utf-8')

    def export_citi_comprobante_ventas(self):
        logger.info('exportar CITI REG3685 Comprobante Ventas')
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Currency = pool.get('currency.currency')
        invoices = Invoice.search([
            ('state', 'in', ['posted', 'paid']),
            ('type', '=', 'out'),  # Invoice, Credit Note
            ('move.period', '=', self.start.period),
            ('pos.pos_do_not_report', '=', False),
        ], order=[('invoice_date', 'ASC')])
        lines = ""
        for invoice in invoices:
            alicuotas = {
                3: 0,
                4: 0,
                5: 0,
                6: 0,
                8: 0,
                9: 0,
            }
            cant_alicuota = 0
            fecha_comprobante = invoice.invoice_date.strftime("%Y%m%d")
            tipo_comprobante = invoice.invoice_type.invoice_type.rjust(3, '0')
            punto_de_venta = invoice.number.split(
                '-')[0].encode().rjust(5, '0')
            if int(tipo_comprobante) in COMPROBANTES_EXCLUIDOS:
                punto_de_venta = ''.rjust(5, '0')  # se informan ceros.
            if ':' in invoice.number:
                parte_desde = invoice.number.split(':')[0]
                parte_hasta = invoice.number.split(':')[1]
                numero_comprobante = parte_desde.split(
                    '-')[1].encode().rjust(20, '0')
                numero_comprobante_hasta = parte_hasta.encode().rjust(20, '0')
            else:
                numero_comprobante = invoice.number.split(
                    '-')[1].encode().rjust(20, '0')
                #if int(punto_de_venta) in [33, 331, 332]:
                #    numero_comprobante = 'COE'
                numero_comprobante_hasta = invoice.number.split(
                    '-')[1].encode().rjust(20, '0')

            identificacion_comprador = None
            codigo_documento_comprador = invoice.party.tipo_documento
            if invoice.party.vat_number:
                # Si tenemos vat_number, entonces tenemos CUIT Argentino
                # use the Argentina AFIP's global CUIT for the country:
                identificacion_comprador = invoice.party.vat_number
                codigo_documento_comprador = '80'
            elif invoice.party.vat_number_afip_foreign:
                # use the VAT number directly
                identificacion_comprador = \
                    invoice.party.vat_number_afip_foreign
            else:
                for identifier in invoice.party.identifiers:
                    if identifier.type == 'ar_dni':
                        identificacion_comprador = identifier.code
                        codigo_documento_comprador = '96'
                        break
                if identificacion_comprador is None:
                    identificacion_comprador = '0'  # only "consumidor final"
                    codigo_documento_comprador = '99'  # consumidor final

            identificacion_comprador = identificacion_comprador.strip().rjust(
                20, '0')
            if codigo_documento_comprador == '99':
                apellido_nombre_comprador = 'VENTA GLOBAL DIARIA'.ljust(30)
            else:
                s = invoice.party.name[:30].encode('utf8')
                apellido_nombre_comprador = ''.join(
                    x for x in s if x.isalnum()).ljust(30)

            importe_total = Currency.round(invoice.currency,
                abs(invoice.total_amount)).to_eng_string().replace(
                    '.', '').rjust(15, '0')

            # iterar sobre lineas de facturas
            importe_total_lineas_sin_impuesto = Decimal('0')  # se calcula
            percepcion_no_categorizados = Decimal('0')  # se calcula
            importe_operaciones_exentas = Decimal('0')  # 0
            importe_total_percepciones = Decimal('0')  # 0
            importe_total_impuesto_iibb = Decimal('0')  # se calcula
            importe_total_percepciones_municipales = Decimal('0')  # 0
            importe_total_impuestos_internos = Decimal('0')  # 0

            for line in invoice.lines:
                if line.invoice_taxes is ():
                    if int(tipo_comprobante) not in [19, 20, 21, 22]:  # COMPROBANTES QUE NO CORESPONDE
                        importe_total_lineas_sin_impuesto += abs(line.amount)
                else:
                    for invoice_tax in line.invoice_taxes:
                        if (invoice_tax.tax.group and 'iva' in
                                invoice_tax.tax.group.code.lower()):
                            iva_id = ALICUOTAS_IVA[invoice_tax.tax.rate]
                            alicuotas[iva_id] += 1

            # calculo total de percepciones
            for invoice_tax in invoice.taxes:
                if (invoice_tax.tax.group and 'nacional' in
                        invoice_tax.tax.group.code.lower()):
                    importe_total_percepciones += invoice.currency.round(
                        abs(invoice_tax.amount))
                elif (invoice_tax.tax.group and 'iibb' in
                        invoice_tax.tax.group.code.lower()):
                    importe_total_impuesto_iibb += abs(invoice_tax.amount)
                elif (invoice_tax.tax.group and 'interno' in
                        invoice_tax.tax.group.code.lower()):
                    importe_total_impuestos_internos += abs(invoice_tax.amount)

            importe_total_lineas_sin_impuesto = Currency.round(invoice.currency,
                importe_total_lineas_sin_impuesto).to_eng_string().replace('.',
                    '').rjust(15, '0')
            percepcion_no_categorizados = Currency.round(invoice.currency,
                percepcion_no_categorizados).to_eng_string().replace('.',
                    '').rjust(15, '0')

            # En caso de que en una misma operación se vendan productos
            # exentos con gravados, la alícuota será la correspondiente a
            # los productos gravados. En este caso el monto correspondiente a
            # la parte exenta se consignará en este campo, y la porción
            # gravada en el campo correspondiente del detalle de alícuotas de IVA.
            # TODO: agregar tilde para marcar que linea de factura es exenta.
            importe_operaciones_exentas = Currency.round(invoice.currency,
                importe_operaciones_exentas).to_eng_string().replace('.',
                    '').rjust(15, '0')

            importe_total_percepciones = Currency.round(invoice.currency,
                importe_total_percepciones).to_eng_string().replace('.',
                    '').rjust(15, '0')
            importe_total_impuesto_iibb = Currency.round(invoice.currency,
                importe_total_impuesto_iibb).to_eng_string().replace('.',
                    '').rjust(15, '0')
            importe_total_percepciones_municipales = Currency.round(invoice.currency,
                importe_total_percepciones_municipales).to_eng_string().replace('.',
                    '').rjust(15, '0')
            importe_total_impuestos_internos = Currency.round(invoice.currency,
                importe_total_impuestos_internos).to_eng_string().replace('.',
                    '').rjust(15, '0')
            codigo_moneda = TABLA_MONEDAS[invoice.currency.code]
            if codigo_moneda != 'PES':
                for afip_tr in invoice.transactions:
                    if afip_tr.pyafipws_result == 'A':
                        request = SimpleXMLElement(unidecode(afip_tr.pyafipws_xml_request))
                        ctz = str(request('Moneda_ctz'))
                        break
                ctz = Currency.round(invoice.currency, Decimal(ctz))
                tipo_de_cambio =  str("%.6f" % ctz)
                tipo_de_cambio = tipo_de_cambio.replace('.',
                    '').rjust(10, '0')
            else:
                tipo_de_cambio = '0001000000'

            # recorrer alicuotas y saber cuantos tipos de alicuotas hay.
            for key, value in alicuotas.items():
                if value != 0:
                    cant_alicuota += 1

            cantidad_alicuotas = str(cant_alicuota)
            if cant_alicuota == 0:
                cantidad_alicuotas = '1'
                if int(invoice.invoice_type.invoice_type) in [19, 20, 21, 22]:  # Factura E
                    codigo_operacion = 'X'
                elif int(invoice.invoice_type.invoice_type) in NO_CORRESPONDE:
                    cantidad_alicuotas = '0'
                    codigo_operacion = 'N' # No corresponde
            else:
                codigo_operacion = ' '  # Segun tabla codigo de operaciones.
                if invoice.company.party.iva_condition == 'exento':  # Operacion exenta
                    codigo_operacion = 'E'

            otros_atributos = '0'.rjust(15, '0')
            fecha_venc_pago = '0'.rjust(8, '0')  # Opcional para resto de comprobantes. Obligatorio para liquidacion servicios clase A y B

            campos = [fecha_comprobante, tipo_comprobante, punto_de_venta,
                numero_comprobante, numero_comprobante_hasta,
                codigo_documento_comprador, identificacion_comprador,
                apellido_nombre_comprador, importe_total,
                importe_total_lineas_sin_impuesto, percepcion_no_categorizados,
                importe_operaciones_exentas, importe_total_percepciones,
                importe_total_impuesto_iibb,
                importe_total_percepciones_municipales,
                importe_total_impuestos_internos,
                codigo_moneda, tipo_de_cambio, cantidad_alicuotas,
                codigo_operacion, otros_atributos, fecha_venc_pago]

            separador = self.start.csv_format and self._SEPARATOR or ''
            lines += separador.join(campos) + self._EOL

        logger.info('Comienza attach comprobante de venta')
        self.exportar.comprobante_ventas = str(
            lines).encode('utf-8')

    def export_citi_alicuota_compras(self):
        logger.info('exportar CITI REG3685 Comprobante Compras')
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Currency = pool.get('currency.currency')
        invoices = Invoice.search([
            ('state', 'in', ['posted', 'paid']),
            ('type', '=', 'in'), # Supplier Invoice, Supplier Credit Note
            ('move.period', '=', self.start.period),
        ], order=[('invoice_date', 'ASC')])
        lines = ""
        for invoice in invoices:
            tipo_comprobante = invoice.tipo_comprobante
            if int(invoice.tipo_comprobante) not in COMPROBANTES_EXCLUIDOS:
                punto_de_venta = invoice.reference.split('-')[0] \
                    if '-' in invoice.reference else ''
                punto_de_venta = punto_de_venta.encode().rjust(5, '0')
                #punto_de_venta = invoice.reference.split('-')[0].encode().rjust(5, '0')
                numero_comprobante = invoice.reference.split('-')[1] \
                    if '-' in invoice.reference else ''
                numero_comprobante = numero_comprobante.encode().rjust(20, '0')
                #numero_comprobante = invoice.reference.split('-')[1].encode().rjust(20, '0')
                assert int(punto_de_venta) > 0 and int(punto_de_venta) < 9998, ('Punto de venta'
                    ' debe ser mayor o igual a "00001" y menor a "09998"!\n'
                    '- Number: %s\n- Reference: %s\n' % (
                        invoice.number, invoice.reference))
            else:
                punto_de_venta = '0'.rjust(5, '0')
                numero_comprobante = invoice.reference.split('-')[1] \
                    if '-' in invoice.reference else ''
                numero_comprobante = numero_comprobante.encode().rjust(20, '0')
            codigo_documento_vendedor = invoice.party.tipo_documento
            cuit_vendedor = invoice.party.vat_number.strip().rjust(20,'0')
            importe_neto_gravado = Decimal('0')
            impuesto_liquidado = Decimal('0')
            for tax_line in invoice.taxes:
                if (tax_line.tax.group and 'iva' in
                        tax_line.tax.group.code.lower()):
                    alicuota_id = str(ALICUOTAS_IVA[tax_line.tax.rate]).rjust(4, '0')
                    #alicuota_id = tax_line.base_code.code.rjust(4,'0')
                    importe_neto_gravado = abs(tax_line.base)
                    impuesto_liquidado = abs(tax_line.amount)
                    importe_neto_gravado = Currency.round(invoice.currency,
                        importe_neto_gravado).to_eng_string().replace('.',
                            '').rjust(15, '0')
                    impuesto_liquidado = Currency.round(invoice.currency,
                        impuesto_liquidado).to_eng_string().replace('.',
                            '').rjust(15, '0')
                    campos = [tipo_comprobante, punto_de_venta,
                        numero_comprobante, codigo_documento_vendedor,
                        cuit_vendedor, importe_neto_gravado, alicuota_id,
                        impuesto_liquidado]

                    separador = self.start.csv_format and self._SEPARATOR or ''
                    lines += separador.join(campos) + self._EOL

        logger.info('Comienza attach alicuota de compras')
        self.exportar.alicuota_compras = str(
            lines).encode('utf-8')

    def export_citi_comprobante_compras(self):
        logger.info('exportar CITI REG3685 Comprobante Compras')
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Currency = pool.get('currency.currency')
        invoices = Invoice.search([
            ('state', 'in', ['posted', 'paid']),
            ('type', '=', 'in'),  # Supplier Invoice, Supplier Credit Note
            ('move.period', '=', self.start.period),
        ], order=[('invoice_date', 'ASC')])

        lines = ""
        for invoice in invoices:
            alicuotas = {
                3: 0,
                4: 0,
                5: 0,
                6: 0,
                8: 0,
                9: 0,
            }
            cant_alicuota = 0
            # iterar sobre lineas de facturas
            importe_total_lineas_sin_impuesto = Decimal('0')  # se calcula
            importe_operaciones_exentas = Decimal('0')  # 0
            total_impuesto_iva = Decimal('0')  # se calcula
            importe_total_impuesto_iva = Decimal('0')  # se calcula
            importe_total_percepciones = Decimal('0')  # 0
            importe_total_impuesto_iibb = Decimal('0')  # se calcula
            importe_total_percepciones_municipales = Decimal('0')  # 0
            importe_total_impuestos_internos = Decimal('0')  # 0

            fecha_comprobante = invoice.invoice_date.strftime("%Y%m%d")
            tipo_comprobante = invoice.tipo_comprobante
            if int(invoice.tipo_comprobante) not in COMPROBANTES_EXCLUIDOS: # se completan con ceros.
                punto_de_venta = invoice.reference.split(
                    '-')[0].encode().rjust(5, '0')
                numero_comprobante = invoice.reference.split(
                    '-')[1].encode().rjust(20, '0')
            else:
                punto_de_venta = '0'.rjust(5, '0')
                numero_comprobante = invoice.reference.split(
                    '-')[1].encode().rjust(20, '0')

            despacho_importacion = ''.ljust(16)

            codigo_documento_vendedor = invoice.party.tipo_documento
            identificacion_vendedor = invoice.party.vat_number.strip().rjust(
                20, '0')
            s = invoice.party.name[:30].encode('utf8')
            apellido_nombre_vendedor = ''.join(
                x for x in s if x.isalnum()).ljust(30)
            importe_total = Currency.round(invoice.currency,
                abs(invoice.total_amount)).to_eng_string().replace('.',
                    '').rjust(15, '0')


            for line in invoice.lines:
                if line.invoice_taxes is ():
                    if int(invoice.tipo_comprobante) not in NO_CORRESPONDE:  # COMPROBANTES QUE NO CORESPONDE
                        importe_total_lineas_sin_impuesto += abs(line.amount)
                else:
                    for invoice_tax in line.invoice_taxes:
                        if (invoice_tax.tax.group and 'iva' in
                                invoice_tax.tax.group.code.lower()):
                            iva_id = ALICUOTAS_IVA[invoice_tax.tax.rate]
                            alicuotas[iva_id] += 1

            # calculo total de percepciones
            for invoice_tax in invoice.taxes:
                if (invoice_tax.tax.group and 'iva' in
                        invoice_tax.tax.group.code.lower()):
                    #importe_total_impuesto_iva += invoice.currency.round(invoice_tax.amount)
                    total_impuesto_iva += invoice.currency.round(
                        abs(invoice_tax.amount))
                if (invoice_tax.tax.group and 'nacional' in
                        invoice_tax.tax.group.code.lower()):
                    importe_total_percepciones += invoice.currency.round(
                        abs(invoice_tax.amount))
                if (invoice_tax.tax.group and 'iibb' in
                        invoice_tax.tax.group.code.lower()):
                    importe_total_impuesto_iibb += abs(invoice_tax.amount)
                if (invoice_tax.tax.group and 'interno' in
                        invoice_tax.tax.group.code.lower()):
                    importe_total_impuestos_internos += abs(invoice_tax.amount)

            importe_total_lineas_sin_impuesto = Currency.round(
                invoice.currency,
                importe_total_lineas_sin_impuesto).to_eng_string().replace(
                    '.', '').rjust(15, '0')
            # TODO: agregar tilde para marcar linea de factura exenta.
            importe_operaciones_exentas = Currency.round(invoice.currency,
                importe_operaciones_exentas).to_eng_string().replace('.',
                    '').rjust(15, '0')

            # Que caso se completa con != 0?
            importe_total_impuesto_iva = Currency.round(invoice.currency,
                importe_total_impuesto_iva).to_eng_string().replace('.',
                    '').rjust(15, '0')
            importe_total_impuesto_iibb = Currency.round(invoice.currency,
                importe_total_impuesto_iibb).to_eng_string().replace('.',
                    '').rjust(15, '0')

            importe_total_percepciones = Currency.round(invoice.currency,
                importe_total_percepciones).to_eng_string().replace('.',
                    '').rjust(15, '0')
            importe_total_percepciones_municipales = Currency.round(
                invoice.currency, importe_total_percepciones_municipales).to_eng_string().replace(
                    '.', '').rjust(15, '0')
            importe_total_impuestos_internos = Currency.round(
                invoice.currency, importe_total_impuestos_internos).to_eng_string().replace(
                    '.', '').rjust(15, '0')
            codigo_moneda = TABLA_MONEDAS[invoice.currency.code]
            #tipo_de_cambio = '0001000000'
            #tipo_de_cambio = invoice.currency.rate.to_eng_string().replace('.','').rjust(10,'0')
            codigo_moneda = TABLA_MONEDAS[invoice.currency.code]
            if codigo_moneda != 'PES':
                ctz = Currency.round(invoice.currency, 1 / invoice.currency.rate)
                tipo_de_cambio =  str("%.6f" % ctz)
                tipo_de_cambio = tipo_de_cambio.replace('.', '').rjust(10, '0')
            else:
                tipo_de_cambio = '0001000000'

            # recorrer alicuotas y saber cuantos tipos de alicuotas hay.
            for key, value in alicuotas.items():
                if value != 0:
                    cant_alicuota += 1

            cantidad_alicuotas = str(cant_alicuota)
            if cant_alicuota == 0:
                cantidad_alicuotas = '1'
                if int(invoice.tipo_comprobante) in [19, 20, 21, 22]: # Factura E
                    codigo_operacion = 'X'
                elif int(invoice.tipo_comprobante) in NO_CORRESPONDE: # COMPROBANTES QUE NO CORESPONDE
                    codigo_operacion = '0' # No corresponde
                    cantidad_alicuotas = '0'
                else:
                    codigo_operacion = 'N' # No alcanzado
            else:
                codigo_operacion = ' ' # Segun tabla codigo de operaciones.
                if invoice.company.party.iva_condition == 'exento': # Operacion exenta
                    codigo_operacion = 'E'

            if self.start.proration:
                credito_fiscal_computable = '0'.rjust(15, '0')
            else:
                credito_fiscal_computable = Currency.round(
                    invoice.currency, total_impuesto_iva).to_eng_string().replace(
                        '.', '').rjust(15, '0')
            otros_atributos = '0'.rjust(15, '0')

            if int(tipo_comprobante) in [33, 58, 59, 60, 63]:
                cuit_emisor = invoice.party.vat_number.strip().rjust(11, '0')
                denominacion_emisor = apellido_nombre_vendedor
                iva_comision = Currency.round(invoice.currency,
                    total_impuesto_iva).to_eng_string().replace('.',
                        '').rjust(15, '0')
            else:
                cuit_emisor = '0'.rjust(11, '0')
                denominacion_emisor = ' '.rjust(30)
                iva_comision = '0'.rjust(15, '0')

            campos = [fecha_comprobante, tipo_comprobante, punto_de_venta,
                numero_comprobante, despacho_importacion,
                codigo_documento_vendedor, identificacion_vendedor,
                apellido_nombre_vendedor, importe_total,
                importe_total_lineas_sin_impuesto, importe_operaciones_exentas,
                importe_total_impuesto_iva, importe_total_percepciones,
                importe_total_impuesto_iibb, importe_total_percepciones_municipales,
                importe_total_impuestos_internos,
                codigo_moneda, tipo_de_cambio, cantidad_alicuotas,
                codigo_operacion, credito_fiscal_computable,
                otros_atributos, cuit_emisor, denominacion_emisor, iva_comision]

            separador = self.start.csv_format and self._SEPARATOR or ''
            lines += separador.join(campos) + self._EOL

        logger.info('Comienza attach comprobante compra')
        self.exportar.comprobante_compras = str(
            lines).encode('utf-8')
