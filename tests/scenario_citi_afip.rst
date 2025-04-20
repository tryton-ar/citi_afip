====================
RG3685 AFIP Scenario
====================

Imports::
    >>> import datetime
    >>> import io
    >>> from trytond.tools import file_open
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from operator import attrgetter
    >>> from proteus import Model, Wizard
    >>> from trytond.tests.tools import activate_modules
    >>> from trytond.modules.company.tests.tools import create_company, \
    ...     get_company
    >>> from trytond.modules.currency.tests.tools import get_currency
    >>> from trytond.modules.account.tests.tools import create_fiscalyear, \
    ...     create_chart, get_accounts, create_tax, create_tax_code
    >>> from trytond.modules.account_invoice.tests.tools import \
    ...     set_fiscalyear_invoice_sequences
    >>> from trytond.modules.account_invoice_ar.tests.tools import \
    ...     create_pos, get_invoice_types, get_pos, get_tax_group
    >>> today = datetime.date.today()
    >>> year = datetime.date(2020, 1, 1)

Install account_invoice::

    >>> config = activate_modules('citi_afip')

Create company::

    >>> currency = get_currency('ARS')
    >>> currency.afip_code = 'PES'
    >>> currency.save()
    >>> _ = create_company(currency=currency)
    >>> company = get_company()
    >>> tax_identifier = company.party.identifiers.new()
    >>> tax_identifier.type = 'ar_cuit'
    >>> tax_identifier.code = '30710158254' # gcoop CUIT
    >>> company.party.iva_condition = 'responsable_inscripto'
    >>> company.party.save()

Create fiscal year::

    >>> fiscalyear = set_fiscalyear_invoice_sequences(
    ...     create_fiscalyear(company, year))
    >>> fiscalyear.click('create_period')
    >>> period = fiscalyear.periods[0]
    >>> period_ids = [p.id for p in fiscalyear.periods]

Create chart of accounts::

    >>> _ = create_chart(company)
    >>> accounts = get_accounts(company)
    >>> receivable = accounts['receivable']
    >>> revenue = accounts['revenue']
    >>> expense = accounts['expense']
    >>> account_tax = accounts['tax']
    >>> account_cash = accounts['cash']

Create point of sale::

    >>> _ = create_pos(company)
    >>> pos = get_pos()
    >>> invoice_types = get_invoice_types()

Get tax group IVA Ventas Gravado::

    >>> tax_group_sale_gravado = get_tax_group('IVA', 'sale', 'gravado')

    >>> tax_group_purchase_gravado = get_tax_group('IVA', 'purchase', 'gravado')

Get tax group IVA Ventas No Gravado::

    >>> tax_group_no_gravado = get_tax_group('IVA', 'purchase', 'no_gravado')

Create customer tax IVA 21%::

    >>> TaxCode = Model.get('account.tax.code')
    >>> customer_tax = create_tax(Decimal('.21'))
    >>> customer_tax.iva_code = '5'
    >>> customer_tax.group = tax_group_sale_gravado
    >>> customer_tax.save()
    >>> invoice_base_code = create_tax_code(customer_tax, 'base', 'invoice')
    >>> invoice_base_code.save()
    >>> invoice_tax_code = create_tax_code(customer_tax, 'tax', 'invoice')
    >>> invoice_tax_code.save()
    >>> credit_note_base_code = create_tax_code(customer_tax, 'base', 'credit')
    >>> credit_note_base_code.save()
    >>> credit_note_tax_code = create_tax_code(customer_tax, 'tax', 'credit')
    >>> credit_note_tax_code.save()

Create supplier tax IVA 21%::

    >>> TaxCode = Model.get('account.tax.code')
    >>> supplier_tax = create_tax(Decimal('.21'))
    >>> supplier_tax.iva_code = '5'
    >>> supplier_tax.group = tax_group_purchase_gravado
    >>> supplier_tax.save()
    >>> invoice_base_code = create_tax_code(supplier_tax, 'base', 'invoice')
    >>> invoice_base_code.save()
    >>> invoice_tax_code = create_tax_code(supplier_tax, 'tax', 'invoice')
    >>> invoice_tax_code.save()
    >>> credit_note_base_code = create_tax_code(supplier_tax, 'base', 'credit')
    >>> credit_note_base_code.save()
    >>> credit_note_tax_code = create_tax_code(supplier_tax, 'tax', 'credit')
    >>> credit_note_tax_code.save()

Create tax IVA No gravado::

    >>> TaxCode = Model.get('account.tax.code')
    >>> tax_ = create_tax(Decimal('0.0'))
    >>> tax_.iva_code = '1'
    >>> tax_.group = tax_group_no_gravado
    >>> tax_.save()
    >>> invoice_base_code_ = create_tax_code(tax_, 'base', 'invoice')
    >>> invoice_base_code_.save()
    >>> invoice_tax_code_ = create_tax_code(tax_, 'tax', 'invoice')
    >>> invoice_tax_code_.save()
    >>> credit_note_base_code_ = create_tax_code(tax_, 'base', 'credit')
    >>> credit_note_base_code_.save()
    >>> credit_note_tax_code_ = create_tax_code(tax_, 'tax', 'credit')
    >>> credit_note_tax_code_.save()

Create parties::

    >>> Party = Model.get('party.party')
    >>> supplier = Party(name='Supplier',
    ...     iva_condition='responsable_inscripto',
    ...     vat_number='33333333339')
    >>> supplier.save()
    >>> customer = Party(name='Customer',
    ...     iva_condition='responsable_inscripto',
    ...     vat_number='30688555872')
    >>> customer.save()

Create account category::

    >>> ProductCategory = Model.get('product.category')
    >>> account_category = ProductCategory(name="Account Category")
    >>> account_category.accounting = True
    >>> account_category.account_expense = expense
    >>> account_category.account_revenue = revenue
    >>> account_category.customer_taxes.append(customer_tax)
    >>> account_category.supplier_taxes.append(supplier_tax)
    >>> account_category.save()

Create product::

    >>> ProductUom = Model.get('product.uom')
    >>> unit, = ProductUom.find([('name', '=', 'Unit')])
    >>> ProductTemplate = Model.get('product.template')
    >>> template = ProductTemplate()
    >>> template.name = 'product'
    >>> template.default_uom = unit
    >>> template.type = 'service'
    >>> template.list_price = Decimal('40')
    >>> template.account_category = account_category
    >>> template.save()
    >>> product, = template.products

Create customer invoices::

    >>> Invoice = Model.get('account.invoice')
    >>> invoice = Invoice()
    >>> invoice.party = customer
    >>> invoice.pos = pos
    >>> invoice.invoice_date = period.start_date
    >>> line = invoice.lines.new()
    >>> line.product = product
    >>> line.quantity = 5
    >>> line.unit_price = Decimal('40')
    >>> invoice.click('post')
    >>> invoice.state
    'posted'
    >>> invoice.total_amount
    Decimal('242.00')
    >>> invoice = Invoice()
    >>> invoice.party = customer
    >>> invoice.pos = pos
    >>> invoice.invoice_date = period.start_date
    >>> line = invoice.lines.new()
    >>> line.product = product
    >>> line.quantity = 5
    >>> line.unit_price = Decimal('20')
    >>> invoice.click('post')
    >>> invoice.state
    'posted'
    >>> invoice.total_amount
    Decimal('121.00')

Create supplier invoices::

    >>> Invoice = Model.get('account.invoice')
    >>> invoice = Invoice()
    >>> invoice.type = 'in'
    >>> invoice.party = supplier
    >>> invoice.tipo_comprobante = '001'
    >>> invoice.reference = '00001-00000312'
    >>> invoice.invoice_date = period.start_date
    >>> line = invoice.lines.new()
    >>> line.product = product
    >>> line.quantity = 5
    >>> line.unit_price = Decimal('40')
    >>> invoice.click('validate_invoice')
    >>> invoice.state
    'validated'
    >>> bool(invoice.move)
    True
    >>> invoice.click('post')
    >>> invoice.state
    'posted'
    >>> bool(invoice.move)
    True
    >>> invoice.move.state
    'posted'
    >>> invoice.untaxed_amount
    Decimal('200.00')
    >>> invoice.tax_amount
    Decimal('42.00')
    >>> invoice.total_amount
    Decimal('242.00')
    >>> invoice = Invoice()
    >>> invoice.type = 'in'
    >>> invoice.party = supplier
    >>> invoice.tipo_comprobante = '011'
    >>> invoice.reference = '00002-00000061'
    >>> invoice.invoice_date = period.start_date
    >>> line = invoice.lines.new()
    >>> line.account = expense
    >>> line.description = 'Test'
    >>> line.quantity = 5
    >>> line.unit_price = Decimal('20')
    >>> line.taxes.append(tax_)
    >>> invoice.click('validate_invoice')
    >>> invoice.state
    'validated'
    >>> bool(invoice.move)
    True
    >>> invoice.move.state
    'draft'
    >>> invoice.click('post')
    >>> invoice.state
    'posted'
    >>> bool(invoice.move)
    True
    >>> invoice.move.state
    'posted'
    >>> invoice.untaxed_amount
    Decimal('100.00')
    >>> invoice.tax_amount
    Decimal('0.00')
    >>> invoice.total_amount
    Decimal('100.00')

Generate rg3685 report::

    >>> Attachment = Model.get('ir.attachment')
    >>> rg3685 = Wizard('citi.afip.wizard')
    >>> rg3685.form.csv_format = False
    >>> rg3685.form.period = period
    >>> rg3685.execute('exportar')
    >>> rg3685.state
    'exportar'
    >>> # rg3685.form.sale_docs
    >>> with file_open('citi_afip/tests/VENTAS_RG3685.txt', 'rb') as f:
    ...     rg3685.form.sale_docs == f.read()
    True
    >>> with file_open('citi_afip/tests/VENTAS_ALICUOTAS_RG3685.txt', 'rb') as f:
    ...     rg3685.form.sale_aliqs == f.read()
    True
    >>> with file_open('citi_afip/tests/COMPRAS_ALICUOTAS_RG3685.txt', 'rb') as f:
    ...     rg3685.form.purchase_aliqs == f.read()
    True
    >>> with file_open('citi_afip/tests/COMPRAS_RG3685.txt', 'rb') as f:
    ...     rg3685.form.purchase_docs == f.read()
    True
