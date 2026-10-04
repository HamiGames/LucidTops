""" this file is used to display the income of the incoming payments to the Ledger system.
content:
1. reads the value from the selected cryptocurrency wallet.
2. updates when a payment to the selected cryptocurrency wallet is detected.
3. is displayed in the frontend ledger income display.
4. this can not be manipulated by the user, node user, master server, admins or developers.
5. the value is always displayed in USD.
6. this is a READ ONLY for information collection.
7. the writing of the value is done by the master server.
8. the value is stored in the database. (LucidTops/Databases/ledger_income_display.json)
9. all values are stored in the database (LucidTops_LedgerDB @ <collection name>.json)
 """