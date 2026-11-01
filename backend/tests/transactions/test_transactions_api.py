from tests.support import ApiTestCase


class TransactionsApiTests(ApiTestCase):
    def test_deposit_transfer_and_history_update_both_accounts_atomically(self) -> None:
        sender, sender_token = self.register_customer(
            access_token="sender",
            phone_number="01055550008",
        )
        recipient, recipient_token = self.register_customer(
            access_token="recipient",
            phone_number="01055550009",
        )
        self.set_session(sender_token)

        deposit = self.client.post(
            "/accounts/me/deposits",
            json={"amount_krw": 10_000, "memo": "sample deposit"},
        )
        self.assertEqual(deposit.status_code, 200)
        transfer = self.client.post(
            "/accounts/me/transfers",
            json={
                "recipient_account_number": recipient["account"]["account_number"],
                "amount_krw": 4_000,
                "memo": "sample transfer",
            },
        )
        self.assertEqual(transfer.status_code, 200)
        self.assertEqual(transfer.json()["balance_krw"], 6_000)

        sender_history = self.client.get("/accounts/me/transactions").json()
        self.assertEqual([row["entry_type"] for row in sender_history], ["transfer_out", "deposit"])
        self.assertEqual(sender_history[0]["transaction_id"], transfer.json()["transaction_id"])

        self.set_session(recipient_token)
        recipient_balance = self.client.get("/accounts/me").json()["balance_krw"]
        self.assertEqual(recipient_balance, 4_000)
        recipient_history = self.client.get("/accounts/me/transactions").json()
        self.assertEqual(recipient_history[0]["entry_type"], "transfer_in")
        self.assertEqual(recipient_history[0]["transaction_id"], transfer.json()["transaction_id"])
        self.assertNotEqual(
            sender["account"]["account_number"], recipient["account"]["account_number"]
        )

    def test_insufficient_withdrawal_and_transfer_leave_balances_and_ledger_unchanged(self) -> None:
        _sender, sender_token = self.register_customer(
            access_token="poor-sender",
            phone_number="01055550010",
        )
        recipient, recipient_token = self.register_customer(
            access_token="poor-recipient",
            phone_number="01055550011",
        )
        self.set_session(sender_token)
        self.client.post("/accounts/me/deposits", json={"amount_krw": 100})
        withdrawal = self.client.post("/accounts/me/withdrawals", json={"amount_krw": 101})
        transfer = self.client.post(
            "/accounts/me/transfers",
            json={
                "recipient_account_number": recipient["account"]["account_number"],
                "amount_krw": 101,
            },
        )
        self.assertEqual(withdrawal.status_code, 409)
        self.assertEqual(transfer.status_code, 409)
        self.assertEqual(self.client.get("/accounts/me").json()["balance_krw"], 100)
        history = self.client.get("/accounts/me/transactions").json()
        self.assertEqual(len(history), 1)

        self.set_session(recipient_token)
        self.assertEqual(self.client.get("/accounts/me").json()["balance_krw"], 0)
        self.assertEqual(self.client.get("/accounts/me/transactions").json(), [])

    def test_recipient_search_supports_account_phone_and_duplicate_names(self) -> None:
        _caller, caller_token = self.register_customer(
            access_token="search-caller",
            phone_number="01055550012",
        )
        self.set_session(caller_token)

        name_results = self.client.get("/recipients", params={"query": "김포도"})
        self.assertEqual(name_results.status_code, 200)
        self.assertGreaterEqual(len(name_results.json()), 2)
        self.assertEqual(len({row["name"] for row in name_results.json()}), 1)
        self.assertTrue(
            all(
                row["phone_number_masked"].endswith(tuple("0123456789"))
                for row in name_results.json()
            )
        )

        phone_result = self.client.get("/recipients", params={"query": "0002"})
        self.assertTrue(any(row["account_number"] == "100000000002" for row in phone_result.json()))
        formatted_phone_result = self.client.get("/recipients", params={"query": "010-0000-0002"})
        self.assertTrue(
            any(row["account_number"] == "100000000002" for row in formatted_phone_result.json())
        )
        account_result = self.client.get("/recipients", params={"query": "100000000003"})
        self.assertTrue(
            any(row["account_number"] == "100000000003" for row in account_result.json())
        )

    def test_zero_amount_and_self_transfer_are_rejected(self) -> None:
        account, token = self.register_customer(
            access_token="self-transfer",
            phone_number="01055550013",
        )
        self.set_session(token)
        zero = self.client.post("/accounts/me/deposits", json={"amount_krw": 0})
        self.assertEqual(zero.status_code, 422)
        self_transfer = self.client.post(
            "/accounts/me/transfers",
            json={
                "recipient_account_number": account["account"]["account_number"],
                "amount_krw": 1,
            },
        )
        self.assertEqual(self_transfer.status_code, 422)
