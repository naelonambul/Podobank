from tests.support import ApiTestCase


class AccountsApiTests(ApiTestCase):
    def test_customer_account_is_private_and_starts_with_zero_balance(self) -> None:
        payload, token = self.register_customer(
            access_token="account-owner",
            phone_number="01055550007",
        )
        response = self.client.get("/accounts/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload["account"])

        self.set_session(None)
        self.assertEqual(self.client.get("/accounts/me").status_code, 401)
        self.set_session(token)
        self.assertEqual(self.client.get("/accounts/me").status_code, 200)
