""" this is the API routes for the PaySystems module (using FastAPI)
PayRoutes:
- /payment-create: create a new payment
- /payment-find: find a payment
- /payment-receipt: generate a receipt for a payment
- /payment-update: update a payment
- /payment-accept: accept a payment
- /payment-reject: reject a payment
- /payment-cancel: cancel a payment
- /payment-account: view the payment account details
- /jackpot-read: read the jackpot system
- /jackpot-create: create a new jackpot
- /jackpot-update: update a jackpot
- /jackpot-calculate: calculate the jackpot's payout value based on the LucidTokens balance of the requesting UserID, NodeUserID, MasterClassUserID, or AdminUserID
- /jackpot-payout: payout the the jackpot-calculate value to the UserID, NodeUserID, MasterClassUserID, or AdminUserID

limitations:
- the PayRoutes use the selected payment method from master server (eg. tron, xrp, or USD)
- all payments will only be made to a verified payment account (paypal, stripe, or crypto wallet address)
- all payments will be recorded in the master server database and LucidLedger system
- the PayRoutes are only used by the master server API routes
- the PayRoutes are hosted on the MasterServer container
- the PayRoutes are used to access billing and payment data in the master server database
- the PayRoutes require a valid IDToken for the UserID, NodeUserID, MasterClassUserID, or AdminUserID
- the PayRoutes require a valid API key for the UserID, NodeUserID, MasterClassUserID, or AdminUserID
- the PayRoutes require a valid source for the UserID, NodeUserID, MasterClassUserID, or AdminUserID
- the PayRoutes require a valid payment method for the UserID, NodeUserID, MasterClassUserID, or AdminUserID
- the PayRoutes require a valid payment currency for the UserID, NodeUserID, MasterClassUserID, or AdminUserID
- the PayRoutes require a valid payment amount for the UserID, NodeUserID, MasterClassUserID, or AdminUserID

-payments are limited to jackpot senario only (no other outgoing payments are allowed from the master server)
-all payments will be recorded in the master server database and LucidLedger system

"""