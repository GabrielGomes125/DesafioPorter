from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestRecurringContract(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Contract = cls.env["recurring.contract"]
        cls.partner = cls.env["res.partner"].create({"name": "Cliente Teste"})
        cls.product_a = cls.env["product.product"].create(
            {"name": "Serviço A", "list_price": 100.0}
        )
        cls.product_b = cls.env["product.product"].create(
            {"name": "Serviço B", "list_price": 30.0}
        )
        cls.today = fields.Date.context_today(cls.Contract)

    def _create_contract(self, **vals):
        base = {
            "partner_id": self.partner.id,
            "line_ids": [
                Command.create({"product_id": self.product_a.id, "quantity": 2})
            ],
        }
        base.update(vals)
        return self.Contract.create(base)

    def test_next_invoice_date_by_periodicity(self):
        contract = self._create_contract()
        base_date = date(2026, 1, 15)
        for periodicity, months in [
            ("monthly", 1),
            ("quarterly", 3),
            ("semiannual", 6),
            ("annual", 12),
        ]:
            contract.periodicity = periodicity
            self.assertEqual(
                contract._get_next_invoice_date(base_date),
                base_date + relativedelta(months=months),
                f"Próxima data incorreta para periodicidade {periodicity}",
            )

    def test_amount_total_compute(self):
        contract = self._create_contract()
        contract.line_ids = [
            Command.create({"product_id": self.product_b.id, "quantity": 3})
        ]
        self.assertEqual(contract.amount_total, 2 * 100.0 + 3 * 30.0)

    def test_activate_requires_lines(self):
        contract = self.Contract.create({"partner_id": self.partner.id})
        with self.assertRaises(ValidationError):
            contract.action_activate()

    def test_date_constraint(self):
        with self.assertRaises(ValidationError):
            self._create_contract(
                date_start=self.today,
                date_end=self.today - timedelta(days=1),
            )

    def test_sequence_and_next_invoice_default(self):
        contract = self._create_contract()
        self.assertTrue(contract.name.startswith("CTR/"))
        self.assertEqual(contract.date_next_invoice, contract.date_start)

    def test_generate_invoice_creates_move(self):
        contract = self._create_contract()
        contract.action_activate()
        move = contract._generate_invoice()
        self.assertEqual(move.move_type, "out_invoice")
        self.assertEqual(move.state, "posted")
        self.assertEqual(move.partner_id, self.partner)
        self.assertEqual(move.amount_untaxed, 200.0)
        self.assertEqual(move.invoice_origin, contract.name)
        self.assertEqual(len(contract.period_ids), 1)
        self.assertEqual(contract.period_ids.invoice_id, move)
        self.assertEqual(contract.period_ids.date_start, self.today)
        self.assertEqual(
            contract.date_next_invoice, self.today + relativedelta(months=1)
        )
        self.assertEqual(contract.invoice_count, 1)

    def test_idempotency_same_period(self):
        contract = self._create_contract()
        contract.action_activate()
        first = contract._generate_invoice()
        contract.date_next_invoice = self.today
        second = contract._generate_invoice()
        self.assertFalse(second, "Mesmo período não pode gerar segunda fatura")
        self.assertEqual(len(contract.period_ids), 1)
        self.assertEqual(contract.invoice_ids, first)

    def test_catch_up_stops_on_already_billed_period(self):
        """O laço de recuperação para no período já faturado, sem girar para sempre."""
        contract = self._create_contract()
        contract.action_activate()
        contract._generate_invoice()
        contract.date_next_invoice = self.today

        moves = contract._generate_invoices_until(self.today)

        self.assertFalse(moves)
        self.assertEqual(len(contract.period_ids), 1)

    def test_cron_catches_up_late_periods(self):
        """Contrato atrasado se acerta numa execução só, uma fatura por período."""
        contract = self._create_contract(
            date_start=self.today - relativedelta(months=2)
        )
        contract.action_activate()

        self.Contract._cron_generate_invoices()

        # os dois períodos vencidos mais o corrente
        self.assertEqual(len(contract.period_ids), 3)
        self.assertEqual(contract.invoice_count, 3)
        self.assertGreater(contract.date_next_invoice, self.today)

    def test_cron_invoices_due_active_only(self):
        active_due = self._create_contract()
        active_due.action_activate()
        draft = self._create_contract()
        suspended = self._create_contract()
        suspended.action_activate()
        suspended.action_suspend()
        future = self._create_contract(date_start=self.today + timedelta(days=10))
        future.action_activate()

        self.Contract._cron_generate_invoices()

        self.assertEqual(len(active_due.period_ids), 1)
        self.assertEqual(active_due.invoice_ids.state, "posted")
        self.assertFalse(draft.period_ids)
        self.assertFalse(suspended.period_ids)
        self.assertFalse(future.period_ids)

    def test_cron_expired_contract_no_invoice_and_closed(self):
        expired = self._create_contract(
            date_start=self.today - timedelta(days=60),
            date_end=self.today - timedelta(days=1),
        )
        expired.action_activate()

        self.Contract._cron_generate_invoices()

        self.assertEqual(expired.state, "closed")
        self.assertFalse(expired.period_ids)

    def test_cron_closes_expired_even_when_not_due(self):
        """Vencido com a próxima cobrança ainda no futuro também precisa encerrar.

        Esse contrato não entra na busca de faturamento, mas o vencimento não
        pode depender de ele ter algo a faturar.
        """
        expired = self._create_contract(
            date_start=self.today - timedelta(days=60),
            date_end=self.today - timedelta(days=1),
            date_next_invoice=self.today + timedelta(days=30),
        )
        expired.action_activate()

        self.Contract._cron_generate_invoices()

        self.assertEqual(expired.state, "closed")
        self.assertFalse(expired.period_ids)

    def test_addendum_flow(self):
        contract = self._create_contract()
        contract.action_activate()

        action = contract.action_create_addendum()
        order = self.env["sale.order"].browse(action["res_id"])
        self.assertEqual(order.x_recurring_contract_id, contract)
        self.assertEqual(order.partner_id, self.partner)
        self.assertEqual(order.state, "draft")

        order.order_line = [
            Command.create({"product_id": self.product_b.id, "product_uom_qty": 3})
        ]
        order.action_confirm()

        self.assertEqual(len(contract.line_ids), 2)
        new_line = contract.line_ids.filtered("order_id")
        self.assertEqual(new_line.order_id, order)
        self.assertEqual(new_line.sale_line_id, order.order_line)
        self.assertEqual(new_line.quantity, 3)
        self.assertEqual(new_line.price_unit, 30.0)
        self.assertEqual(contract.sale_order_count, 1)

        # reincorporação não pode duplicar itens
        contract._add_lines_from_sale_order(order)
        self.assertEqual(len(contract.line_ids), 2)

        move = contract._generate_invoice()
        self.assertEqual(len(move.invoice_line_ids), 2)
        self.assertEqual(move.amount_untaxed, 200.0 + 90.0)
