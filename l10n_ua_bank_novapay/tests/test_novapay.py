"""Тести провайдера NovaPay (мок SOAP API бізнес-кабінету)."""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from xml.sax.saxutils import escape

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

MODULE = 'odoo.addons.l10n_ua_bank_novapay.models.l10n_ua_bank_novapay_config'
OWN_IBAN = 'UA753587100000067320000000019'
OTHER_IBAN = 'UA113052990000026007891234567'
THIRD_IBAN = 'UA533587100000067320000000027'
CERT = '-----BEGIN RSA PUBLIC KEY-----\nTEST\n-----END RSA PUBLIC KEY-----'


def _soap(method, body, status=200):
    """Відповідь сервера: `body` — готовий XML вмісту `<Method>Result`."""
    resp = MagicMock()
    resp.status_code = status
    resp.text = (
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
        '<s:Body><%(m)sResponse xmlns="http://tempuri.org/"><%(m)sResult>'
        '%(body)s</%(m)sResult></%(m)sResponse></s:Body></s:Envelope>'
    ) % {'m': method, 'body': body}
    resp.content = resp.text.encode('utf-8')
    return resp


def _auth(jwt='jwt-1', refresh='refresh-2', expiration=None):
    if expiration is None:
        expiration = (fields.Datetime.now() + timedelta(days=1)).strftime(
            '%Y-%m-%d %H:%M:%S')
    return _soap('UserAuthenticationJWT', (
        '<response_ref>r</response_ref><jwt>%s</jwt>'
        '<expiration>%s</expiration><refresh_token>%s</refresh_token>'
        '<public_certificate>CERT-2</public_certificate>'
    ) % (jwt, expiration, refresh))


def _error(method, title='User not access to account.'):
    return _soap(method, (
        '<response_ref>r</response_ref><result>error</result>'
        '<error><status>logic_error</status><title>%s</title></error>') % title)


def _clients():
    return _soap('GetClientsList', (
        '<result>ok</result><clients><Clients><id>8</id>'
        '<name>ФОП Тестовий</name><statecode>1234567899</statecode>'
        '</Clients></clients>'))


def _accounts():
    return _soap('GetAccountsList', (
        '<result>ok</result><accounts>'
        '<Accounts><id>49</id><IBAN>%s</IBAN><name>ФОП Тестовий</name>'
        '<currency>UAH</currency><status>1</status>'
        '<statuscode>Active</statuscode></Accounts>'
        '<Accounts><id>51</id><IBAN>UA443587100000067325000000019</IBAN>'
        '<name>ФОП Тестовий</name><currency>UAH</currency><status>4</status>'
        '<statuscode>OnApproval</statuscode></Accounts>'
        '</accounts>') % OWN_IBAN)


def _doc(code, amount, debit, credit, pay_date='02.09.2026', **extra):
    vals = {
        'Code': code, 'PayDate': pay_date, 'OrgDate': '01.09.2026',
        'Purpose': 'Оплата за товар', 'PaymentType': '1',
        'DebitName': 'ТОВ Платник', 'DebitCodeIBAN': debit,
        'DebitStateCode': '30000005',
        'CreditName': 'ТОВ Отримувач', 'CreditCodeIBAN': credit,
        'CreditStateCode': '30000015',
    }
    vals.update(extra)
    return '<Docs Amount="%s" CurrencyTag="UAH">%s</Docs>' % (
        amount, ''.join('<%s>%s</%s>' % (k, escape(v), k)
                        for k, v in vals.items()))


def _extract_xml(*docs):
    return (
        '<Extract xmlns:xsd="http://www.w3.org/2001/XMLSchema">'
        '<ExtractHead><GetExtractForXML><IBAN>%s</IBAN>%s'
        '</GetExtractForXML></ExtractHead></Extract>'
    ) % (OWN_IBAN, ''.join(docs))


def _extract(*docs):
    return _soap('GetAccountExtract', (
        '<result>ok</result><extract><![CDATA[%s]]></extract>'
    ) % _extract_xml(*docs))


def _turns(*rows):
    return _soap('GetAccountTurns', '<result>ok</result><turns>%s</turns>' % ''.join(
        '<Turns><date>%s</date><IBAN>%s</IBAN><Currency>UAH</Currency>'
        '<InRest>%s</InRest><CrncyDebit>0.0000</CrncyDebit>'
        '<CrncyCredit>0.0000</CrncyCredit><CrncyRest>%s</CrncyRest></Turns>'
        % (day, OWN_IBAN, opening, closing) for day, opening, closing in rows))


@tagged('post_install', '-at_install')
class TestNovapay(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        partner = cls.env.company.partner_id
        bank_account = cls.env['res.partner.bank'].create({
            'acc_number': OWN_IBAN, 'partner_id': partner.id})
        uah = cls.env.ref('base.UAH')
        uah.active = True
        cls.journal = cls.env['account.journal'].create({
            'name': 'NovaPay', 'type': 'bank', 'code': 'NVP',
            'bank_account_id': bank_account.id, 'currency_id': uah.id,
            'company_id': cls.env.company.id})
        cls.config = cls.env['l10n_ua.bank.sync.config'].create({
            'name': 'NovaPay', 'provider': 'novapay',
            'journal_id': cls.journal.id,
            'novapay_login': 'test_login',
            'novapay_refresh_token': 'refresh-1',
            'novapay_public_certificate': CERT,
        })

    def _patch(self, *responses):
        return patch('%s.requests.post' % MODULE, side_effect=list(responses))

    def _session(self):
        return self.env['l10n_ua.bank.novapay.session'].search(
            [('config_id', '=', self.config.id)])

    # --- транспорт ---------------------------------------------------------
    def test_call_envelope(self):
        with self._patch(_clients()) as post:
            data = self.config._novapay_call(
                'GetClientsList', {'jwt': 'a<b', 'principal': None})
        self.assertEqual(data['clients']['Clients']['id'], '8')
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs['headers']['SOAPAction'],
                         'http://tempuri.org/IClientAPIService/GetClientsList')
        body = kwargs['data'].decode('utf-8')
        self.assertIn('<tem:GetClientsList><tem:request>', body)
        self.assertIn('<tem:jwt>a&lt;b</tem:jwt>', body)
        self.assertIn('<tem:request_ref>', body)
        self.assertNotIn('principal', body)

    def test_call_errors(self):
        with self._patch(_error('GetClientsList')), \
                self.assertRaisesRegex(UserError, 'User not access'):
            self.config._novapay_call('GetClientsList', {})
        fault = MagicMock(status_code=500)
        fault.text = ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/'
                      'envelope/"><s:Body><s:Fault><faultstring>Boom'
                      '</faultstring></s:Fault></s:Body></s:Envelope>')
        fault.content = fault.text.encode('utf-8')
        with self._patch(fault), self.assertRaisesRegex(UserError, 'Boom'):
            self.config._novapay_call('GetClientsList', {})
        html = MagicMock(status_code=502, text='<html><body>Bad', content=b'<html><body>Bad')
        with self._patch(html), self.assertRaises(UserError):
            self.config._novapay_call('GetClientsList', {})

    # --- авторизація ---------------------------------------------------------
    def test_jwt_rotates_and_caches(self):
        with self._patch(_auth()) as post:
            jwt, cached = self.config._novapay_jwt()
            self.assertEqual((jwt, cached), ('jwt-1', False))
            # Другий виклик бере JWT із кешу — токен не витрачається.
            self.assertEqual(self.config._novapay_jwt(), ('jwt-1', True))
            self.assertEqual(post.call_count, 1)
        body = post.call_args.kwargs['data'].decode('utf-8')
        self.assertIn('<tem:refresh_token>refresh-1</tem:refresh_token>', body)
        self.assertIn('<tem:login>test_login</tem:login>', body)
        session = self._session()
        self.assertEqual(session.refresh_token, 'refresh-2')
        self.assertEqual(session.public_certificate, 'CERT-2')

        # Примусове оновлення використовує вже оновлений токен і сертифікат.
        with self._patch(_auth('jwt-2', 'refresh-3')) as post:
            self.assertEqual(self.config._novapay_jwt(force=True), ('jwt-2', False))
        body = post.call_args.kwargs['data'].decode('utf-8')
        self.assertIn('<tem:refresh_token>refresh-2</tem:refresh_token>', body)
        self.assertIn('CERT-2', body)
        self.assertEqual(self._session().refresh_token, 'refresh-3')

    def test_jwt_new_seed_restarts_chain(self):
        with self._patch(_auth()):
            self.config._novapay_jwt()
        self.config.novapay_refresh_token = 'regenerated'
        with self._patch(_auth('jwt-9', 'refresh-9')) as post:
            self.assertEqual(self.config._novapay_jwt(), ('jwt-9', False))
        body = post.call_args.kwargs['data'].decode('utf-8')
        self.assertIn('<tem:refresh_token>regenerated</tem:refresh_token>', body)
        self.assertIn('TEST', body)
        self.assertEqual(len(self._session()), 1)

    def test_jwt_without_expiration_time_is_not_cached(self):
        with self._patch(_auth(expiration='01.01.2027'), _auth('jwt-2')) as post:
            self.config._novapay_jwt()
            self.assertEqual(self.config._novapay_jwt(), ('jwt-2', False))
            self.assertEqual(post.call_count, 2)

    def test_jwt_failure_keeps_session(self):
        with self._patch(_auth()):
            self.config._novapay_jwt()
        with self._patch(_error('UserAuthenticationJWT', 'Invalid token')), \
                self.assertRaisesRegex(UserError, 'generate'):
            self.config._novapay_jwt(force=True)
        self.assertEqual(self._session().refresh_token, 'refresh-2')

    def test_jwt_requires_credentials(self):
        self.config.novapay_refresh_token = False
        with self.assertRaises(UserError):
            self.config._novapay_jwt()

    def test_api_retries_with_fresh_jwt(self):
        with self._patch(_auth()):
            self.config._novapay_jwt()
        with self._patch(_error('GetClientsList', 'Token expired'),
                         _auth('jwt-2', 'refresh-3'), _clients()) as post:
            data = self.config._novapay_api('GetClientsList')
        self.assertEqual(data['result'], 'ok')
        self.assertIn('<tem:jwt>jwt-2</tem:jwt>',
                      post.call_args.kwargs['data'].decode('utf-8'))

    def test_expiration_parsing(self):
        parse = self.config._novapay_parse_expiration
        # Київський час → UTC (взимку +2).
        self.assertEqual(str(parse('2026-01-15 12:00:00')), '2026-01-15 10:00:00')
        self.assertEqual(str(parse('15.01.2026 12:00:00')), '2026-01-15 10:00:00')
        self.assertFalse(parse('01.01.2027'))
        self.assertFalse(parse(''))

    # --- рахунки -------------------------------------------------------------
    def test_resolve_account_by_iban(self):
        with self._patch(_auth(), _clients(), _accounts()):
            self.assertEqual(self.config._novapay_resolve_account(), '49')
        self.assertEqual(self.config.novapay_client_id, '8')
        self.assertEqual(self.config.novapay_account_id, '49')
        # Збережений ID не потребує запитів.
        with self._patch():
            self.assertEqual(self.config._novapay_resolve_account(), '49')

    def test_resolve_account_not_found(self):
        self.journal.bank_account_id.acc_number = THIRD_IBAN
        with self._patch(_auth(), _clients(), _accounts()), \
                self.assertRaisesRegex(UserError, THIRD_IBAN):
            self.config._novapay_resolve_account()

    def test_actions(self):
        with self._patch(_auth(), _clients()):
            action = self.config.action_test_connection()
        self.assertEqual(action['params']['type'], 'success')
        self.assertIn('ФОП Тестовий', action['params']['message'])
        with self._patch(_clients(), _accounts()):
            action = self.config.action_novapay_fetch_accounts()
        self.assertIn(OWN_IBAN, action['params']['message'])
        self.assertEqual(self.config.novapay_account_id, '49')

    # --- виписка -------------------------------------------------------------
    def test_fetch(self):
        self.config.novapay_account_id = '49'
        with self._patch(_auth(), _extract(_doc('1', '10.00', OTHER_IBAN, OWN_IBAN)),
                         _turns(('01.09.2026', '100.0000', '110.0000'))) as post:
            raw = self.config._fetch_from_bank(date(2026, 9, 1), date(2026, 9, 10))
        body = post.call_args_list[1].kwargs['data'].decode('utf-8')
        self.assertIn('<tem:account_id>49</tem:account_id>', body)
        self.assertIn('<tem:date_from>01.09.2026</tem:date_from>', body)
        self.assertIn('<tem:date_to>10.09.2026</tem:date_to>', body)
        self.assertIn('<Docs', raw['extract'])
        self.assertEqual(raw['turns'][0]['InRest'], '100.0000')
        self.assertEqual(self.config._extract_balances(raw), (100.0, 110.0))

    def test_fetch_without_turns(self):
        self.config.novapay_account_id = '49'
        with self._patch(_auth(), _extract(), _error('GetAccountTurns'),
                         _auth('jwt-2'), _error('GetAccountTurns')):
            raw = self.config._fetch_from_bank(date(2026, 9, 1), date(2026, 9, 10))
        self.assertEqual(raw['turns'], [])
        self.assertEqual(self.config._extract_balances(raw), (None, None))
        self.assertEqual(self.config._parse_transactions(raw), [])

    def test_balances_span_period(self):
        raw = {'turns': [
            {'date': '03.09.2026', 'InRest': '150.00', 'CrncyRest': '90.00'},
            {'date': '01.09.2026', 'InRest': '100.00', 'CrncyRest': '150.00'},
        ]}
        self.assertEqual(self.config._extract_balances(raw), (100.0, 90.0))

    def test_parse_directions(self):
        raw = {'extract': _extract_xml(
            _doc('IN-1', '1000.00', OTHER_IBAN, OWN_IBAN),
            _doc('OUT-1', '250,50', OWN_IBAN, OTHER_IBAN, PayDate='',
                 Purpose='Оплата послуг & доставки'),
            _doc('ZERO', '0.00', OTHER_IBAN, OWN_IBAN),
        )}
        incoming, outgoing = self.config._parse_transactions(raw)
        self.assertEqual(incoming['amount'], 1000.0)
        self.assertEqual(incoming['date'], '2026-09-02')
        self.assertEqual(incoming['partner_name'], 'ТОВ Платник')
        self.assertEqual(incoming['partner_iban'], OTHER_IBAN)
        self.assertEqual(incoming['partner_edrpou'], '30000005')
        self.assertEqual(outgoing['amount'], -250.5)
        # Без дати проведення беремо дату документа.
        self.assertEqual(outgoing['date'], '2026-09-01')
        self.assertEqual(outgoing['partner_name'], 'ТОВ Отримувач')
        self.assertEqual(outgoing['partner_edrpou'], '30000015')
        self.assertEqual(outgoing['description'], 'Оплата послуг & доставки')

    def test_parse_direction_by_edrpou(self):
        self.env.company.partner_id.edrpou = '30000015'
        raw = {'extract': _extract_xml(
            _doc('X', '5.00', OTHER_IBAN, THIRD_IBAN)
        ).replace('<IBAN>%s</IBAN>' % OWN_IBAN, '<IBAN>UA00</IBAN>')}
        self.assertEqual(self.config._parse_transactions(raw)[0]['amount'], 5.0)

    def test_parse_unknown_direction(self):
        raw = {'extract': _extract_xml(
            _doc('X', '5.00', OTHER_IBAN, THIRD_IBAN))}
        with self.assertRaisesRegex(UserError, 'direction'):
            self.config._parse_transactions(raw)

    def test_parse_uids(self):
        twin = _doc('7', '10.00', OTHER_IBAN, OWN_IBAN)
        raw = {'extract': _extract_xml(
            twin, twin, _doc('8', '10.00', OTHER_IBAN, OWN_IBAN))}
        uids = [t['id'] for t in self.config._parse_transactions(raw)]
        self.assertEqual(len(set(uids)), 3)
        # Ті самі документи в іншій виписці дають ті самі ключі.
        again = [t['id'] for t in self.config._parse_transactions(
            {'extract': _extract_xml(twin, twin)})]
        self.assertEqual(again, uids[:2])

    def test_sync_job_creates_statement(self):
        self.config.novapay_account_id = '49'
        partner = self.env['res.partner'].create({
            'name': 'ТОВ Платник', 'edrpou': '30000005'})
        docs = (_doc('j1', '1000.00', OTHER_IBAN, OWN_IBAN),
                _doc('j2', '250.00', OWN_IBAN, OTHER_IBAN))
        turns = _turns(('01.09.2026', '500.0000', '500.0000'),
                       ('02.09.2026', '500.0000', '1250.0000'))

        def run():
            job = self.env['l10n_ua.bank.sync.job'].create({
                'config_id': self.config.id,
                'date_from': date(2026, 9, 1), 'date_to': date(2026, 9, 10)})
            job.action_fetch()
            return job

        with self._patch(_auth(), _extract(*docs), turns):
            job = run()
        self.assertEqual(job.state, 'done')
        self.assertEqual(job.imported_count, 2)
        statement = job.bank_statement_id
        self.assertEqual(sorted(statement.line_ids.mapped('amount')),
                         [-250.0, 1000.0])
        self.assertEqual(set(statement.line_ids.mapped('journal_id')),
                         {self.journal})
        self.assertEqual(statement.balance_start, 500.0)
        self.assertEqual(statement.balance_end_real, 1250.0)
        self.assertTrue(statement.l10n_ua_balance_ok)
        incoming = statement.line_ids.filtered(lambda line: line.amount > 0)
        self.assertEqual(incoming.partner_id, partner)

        # Повторна синхронізація того самого періоду не дублює рядки.
        with self._patch(_extract(*docs), turns):
            job = run()
        self.assertEqual(job.imported_count, 0)

    # --- знахідки рев'ю -------------------------------------------------------
    def test_jwt_response_without_new_pair_keeps_the_token(self):
        """Відповідь без refresh-токена не стирає той, що вже є."""
        expired = (fields.Datetime.now() - timedelta(hours=1)).strftime(
            '%Y-%m-%d %H:%M:%S')
        bare = _soap('UserAuthenticationJWT', (
            '<jwt>jwt-1</jwt><expiration>%s</expiration>') % expired)
        with self._patch(bare, _auth('jwt-2', 'refresh-2')) as post:
            self.config._novapay_jwt()
            session = self._session()
            self.assertEqual(session.refresh_token, 'refresh-1')
            self.assertEqual(session.public_certificate, CERT)
            self.config._novapay_jwt()
        body = post.call_args.kwargs['data'].decode('utf-8')
        self.assertIn('<tem:refresh_token>refresh-1</tem:refresh_token>', body)
        self.assertIn('TEST', body)

    def test_resolve_account_by_iban_and_currency(self):
        """Мультивалютний рахунок: один IBAN, береться рахунок валюти журналу."""
        both = _soap('GetAccountsList', (
            '<result>ok</result><accounts>'
            '<Accounts><id>70</id><IBAN>%(iban)s</IBAN><currency>USD</currency>'
            '<statuscode>Active</statuscode></Accounts>'
            '<Accounts><id>49</id><IBAN>%(iban)s</IBAN><currency>UAH</currency>'
            '<statuscode>Active</statuscode></Accounts>'
            '</accounts>') % {'iban': OWN_IBAN})
        with self._patch(_auth(), _clients(), both):
            self.assertEqual(self.config._novapay_resolve_account(), '49')

    def test_resolve_account_same_iban_unknown_currency(self):
        twins = _soap('GetAccountsList', (
            '<result>ok</result><accounts>'
            '<Accounts><id>70</id><IBAN>%(iban)s</IBAN><currency>USD</currency>'
            '</Accounts>'
            '<Accounts><id>71</id><IBAN>%(iban)s</IBAN><currency>EUR</currency>'
            '</Accounts></accounts>') % {'iban': OWN_IBAN})
        with self._patch(_auth(), _clients(), twins), \
                self.assertRaisesRegex(UserError, 'Account ID'):
            self.config._novapay_resolve_account()
        self.assertFalse(self.config.novapay_account_id)

    def test_amount_formats(self):
        amount = self.config._novapay_amount
        self.assertEqual(amount('1,250.00'), 1250.0)
        self.assertEqual(amount('1.250,50'), 1250.5)
        self.assertEqual(amount('1 250,5'), 1250.5)
        self.assertEqual(amount('250,50'), 250.5)
        self.assertIsNone(amount('abc'))

    def test_parse_error_after_a_good_document(self):
        """Помилка не на першому документі лишається помилкою користувача."""
        raw = {'extract': _extract_xml(
            _doc('OK', '10.00', OTHER_IBAN, OWN_IBAN),
            _doc('X', '5.00', OTHER_IBAN, THIRD_IBAN))}
        with self.assertRaisesRegex(UserError, 'direction'):
            self.config._parse_transactions(raw)

    def test_parse_unreadable_amount_is_not_dropped(self):
        raw = {'extract': _extract_xml(
            _doc('OK', '10.00', OTHER_IBAN, OWN_IBAN),
            _doc('BAD', 'abc', OTHER_IBAN, OWN_IBAN))}
        with self.assertRaisesRegex(UserError, 'BAD'):
            self.config._parse_transactions(raw)

    def test_parse_document_without_a_date(self):
        raw = {'extract': _extract_xml(
            _doc('NODATE', '10.00', OTHER_IBAN, OWN_IBAN,
                 pay_date='', OrgDate=''))}
        with self.assertRaisesRegex(UserError, 'NODATE'):
            self.config._parse_transactions(raw)

    def test_parse_iso_dates(self):
        raw = {'extract': _extract_xml(
            _doc('ISO', '10.00', OTHER_IBAN, OWN_IBAN,
                 pay_date='2026-09-02T10:00:00', OrgDate='2026-09-01'))}
        self.assertEqual(
            self.config._parse_transactions(raw)[0]['date'], '2026-09-02')

    def test_uid_survives_a_later_fetch(self):
        """Той самий документ до і після проведення — один ключ."""
        def uid(**kwargs):
            raw = {'extract': _extract_xml(
                _doc('9', '10.00', OTHER_IBAN, OWN_IBAN, **kwargs))}
            return self.config._parse_transactions(raw)[0]['id']

        booked = uid()
        self.assertEqual(uid(pay_date=''), booked)
        self.assertEqual(uid(Purpose='Оплата  за товар '), booked)
        self.assertNotEqual(uid(OrgDate='31.08.2026'), booked)

    def test_overlapping_period_statement_is_consistent(self):
        """Вікно, що перекриває вже імпортоване: у виписці лише нові рухи, і
        її залишки сходяться — початковий залишок вікна сюди не пасує."""
        self.config.novapay_account_id = '49'
        first = (_doc('o1', '1000.00', OTHER_IBAN, OWN_IBAN,
                      pay_date='01.09.2026'),)
        later = first + (_doc('o2', '30.00', OWN_IBAN, OTHER_IBAN,
                              pay_date='03.09.2026', OrgDate='03.09.2026'),)

        def run(date_to, docs, turns):
            job = self.env['l10n_ua.bank.sync.job'].create({
                'config_id': self.config.id,
                'date_from': date(2026, 9, 1), 'date_to': date_to})
            with self._patch(_extract(*docs), turns):
                job.action_fetch()
            return job.bank_statement_id

        with self._patch(_auth()):
            self.config._novapay_jwt()
        statement = run(date(2026, 9, 2), first, _turns(
            ('01.09.2026', '0.00', '1000.00')))
        self.assertTrue(statement.l10n_ua_balance_verified)
        self.assertTrue(statement.l10n_ua_balance_ok)

        statement = run(date(2026, 9, 3), later, _turns(
            ('01.09.2026', '0.00', '1000.00'),
            ('03.09.2026', '1000.00', '970.00')))
        self.assertEqual(statement.line_ids.mapped('amount'), [-30.0])
        self.assertEqual(statement.balance_start, 1000.0)
        self.assertEqual(statement.balance_end_real, 970.0)
        self.assertFalse(statement.l10n_ua_balance_verified)

    def test_non_novapay_delegates(self):
        other = self.env['l10n_ua.bank.sync.config'].create({
            'name': 'Manual', 'provider': 'manual', 'journal_id': self.journal.id})
        with self.assertRaises(NotImplementedError):
            other._parse_transactions({'extract': ''})
        self.assertEqual(other._extract_balances({}), (None, None))
        self.assertEqual(other.action_test_connection()['params']['type'], 'warning')
