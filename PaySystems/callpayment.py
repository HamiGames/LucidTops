""" this is the script that links to the frontend payment system (Frontend/Payment.js) and calls to the Masterserver via an API route.
the server will then call to a clearnet API route to continue the payment process.
this payment process will be performed via a intermediate payment system (NowPayments.io) using the API routes provided by the NowPayments.io API.
this payment process will be operational in a clearnet version of the payments.js script (Frontend/Payment.js) that is EMV 3DS compliant.
the payment information will be stored in a seperate database (payment_system.db) on the console Hosting the MasterServer container.

"""
