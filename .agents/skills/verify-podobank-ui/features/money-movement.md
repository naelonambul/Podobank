# Money movement

Customers can deposit, withdraw, search for a recipient, and confirm a transfer from their account.

## Sub-features

- deposit-and-withdrawal: accepted amounts update the account balance and ledger.
- recipient-search: phone-number search returns the isolated recipient.
- transfer-confirmation: the selected recipient and amount are shown before the transfer is submitted.

## How to get to it (user POV)

- Sign in, then use a balance action or select `거래` in the bottom navigation.
- Select `입금`, `출금`, or `송금`; for a transfer, search by the recipient phone number, select the recipient, and confirm the amount.

## Driving it

- `frontend/e2e/01-transactions.spec.js` drives all three transaction types through their labeled fields and buttons.
- It asserts the transfer confirmation message, success messages, final balance, and ledger entries.
- It checks the transaction and ledger screens for horizontal overflow at 384 × 832.

## Gotchas

- Transfer submission intentionally has a separate confirmation action. The test asserts both the review message and the completed transfer.
- A demo deposit is used to fund later withdrawal and transfer actions; no balance is edited directly by the test.
