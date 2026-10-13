API_URL = 'https://api.monobank.ua/api/merchant/'

# Currencies an invoice can be issued in when charging in the order currency.
SUPPORTED_CURRENCIES = ['UAH', 'USD', 'EUR']

DEFAULT_PAYMENT_METHOD_CODES = {'card', 'visa', 'mastercard'}

# https://api.monobank.ua/docs/acquiring.html — invoice `status`
STATUS_MAPPING = {
    'pending': ('created', 'processing'),
    'authorized': ('hold',),
    'done': ('success',),
    'cancel': ('expired', 'reversed'),
    'error': ('failure',),
}

# How long the customer has to pay an invoice, in seconds.
INVOICE_VALIDITY = 3600
