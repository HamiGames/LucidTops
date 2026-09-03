""" this the API routes for the payment system container for the LucidTops system.
only the master server and the AdminUser will have access to the payment system container for outgoing payments.
the incoming payments will be handled by the payment system container via the API routes (From User or NodeUser)

this container will be useable via the API routes.(FastAPI)
the master server is a Uvicorn server and the AdminUser is an external user Portal for payments.
payment operations:
- update billing information for the user or node
- process a payment for the user or node
- payout to NodeUser, MasterServer, AdminUser, MasterClassUser, and User via the API routes.
- transfer of funds between wallet address and third party intermediaries via the API routes, using Clearnet protocols(NowPayments, Stripe, PayPal, etc.)
- No transactions will be performed directly from the Tor system, all transactions will be performed via the Clearnet protocols.
"""
