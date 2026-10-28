import unittest
from sample_app.ledger import Payment, refund


class RefundTests(unittest.TestCase):
    def test_refund(self):
        payment = Payment("owner", 1000)
        self.assertEqual(refund(payment, "owner", 600), 600)
        with self.assertRaises(ValueError):
            refund(payment, "owner", 600)

    def test_other_user(self):
        with self.assertRaises(PermissionError):
            refund(Payment("owner", 1000), "attacker", 100)

    def test_negative_amount(self):
        with self.assertRaises(ValueError):
            refund(Payment("owner", 1000), "owner", -100)


if __name__ == "__main__":
    unittest.main()
