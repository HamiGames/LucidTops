""" the jackpot system for the lucid projects
values:
- the first jackpot must be more than $2000 USD (minimum payout value for entire system)
- all jackpot goals will increase by 5% of the previous jackpot goal (1000% is the maximum increase)
- all none collected will not be added to the jackpot value (income) the uncollected jackpot value will stay in holding until the jackpot is collected.
- each token will have a unique LucidTokenID (LucidTokenID) that is used to identify the token and its owner.
- if token is not readable from the blockchain, it will be removed from the jackpot value (income) and the lucidTokenID will be listed in the uncollected archive on the master server database
- the payout value recieved is soley dependent on the LucidTokens balance of the requesting UserID, NodeUserID, MasterClassUserID, or AdminUserID
- the lucidTokens balance is calculated based on the LucidLedger system and LucidWallet system
- the balance excludes the account starting balance (of set amount of crypto currency)
- the payout value will never exceed the starting balance of the account (to prevent overpaying)

the jackpot function is not a winner takes all system, it is a shared payout system where the payout value is divided among the top 100 users based on the LucidTokens balance of the requesting UserID, NodeUserID, MasterClassUserID, or AdminUserID
the payout value is calculated based on the LucidTokens balance of the requesting UserID, NodeUserID, MasterClassUserID, or AdminUserID

all tier payments will add to the jackpot value (income)
all jackpot payouts will be deducted from the jackpot value (expense)
all jackpot goal va
"""