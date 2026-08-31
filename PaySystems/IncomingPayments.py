""" the incoming payments system for the lucid projects
objectives:
- to handle all incoming payments via the master server
- all payments will be deposited into a crypto wallet address (tron node wallet address or xrp wallet address)
- all payments will recieve a reciept of the payment details ( lucidTops reciept system)
- all payments will extend the access and usage of the session system
- all payments will be recorded in the master server database and LucidLedger system
- all payments will be validated by the master server API routes

failure to process the incoming payment will result in the UserID being returned to the free tier (super low access)
LucidTokens can be used by a NodeUser to pay for the tier system for use of the session system (session.py)(value of a token is based on the jackpot system (jackpot.py))
the payment system is a monthly subscription system (monthly subscription is based on the selected tier system (tier.py))
the monthly subcription transfers the funds in local currency based on the set values in the tier system (tier.py) to the selected wallet address (tron node wallet address or xrp wallet address)
the monthly subscription will be a direct deposit to the selected wallet address (tron node wallet address or xrp wallet address)
30 day period starts from the date of the first payment (first payment will be the start date)
the monthly subscription will be renewed automatically unless the UserID cancels the subscription
the monthly subscription can be cancelled at any time by the UserID by selecting cancel subscription in tier system (tier.py)
A UserID may ask to change the tier in the middle of the month by selecting change tier in tier system (tier.py) the purchase about will only be the difference in value between the new tier and the old tier
a user may request a refund at any time by selecting refund in tier system (tier.py) once subscription is cancelled, this is subject to balance of use left in the month and the value of the new tier.

all payments will be recorded in the master server database and LucidLedger system
all payments will be validated by the master server API routes
all payments will be recorded in the master server database and LucidLedger system
"""